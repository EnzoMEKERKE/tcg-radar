"""Bounded merchant category crawlers, Shopify variants and structured product data."""
import asyncio
import json
import re
import math
import gzip
import io
import os
import hashlib
from pathlib import Path
from app.services.product_page import amount, visible_offer, stock_status
from .browser import BrowserRenderer
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
from .universal import UniversalConnector, UA, PRODUCT_HINTS
from app.services.normalizer import normalize
from app.services.origin import origin_for, policy_links, merge_origins

PROFILES = {
    'UltraJeux': ['/type-469-4-boite-de-boosters-francais.html', '/type-469-2-boite-de-boosters-francais.html', '/type-469-1031-boite-de-boosters-francais.html'],
    'Ludotrotter': ['/categorie-produit/magasin/cartes/pokemon/boite-de-booster-pokemon/', '/categorie-produit/magasin/cartes/one-piece/boite-de-booster/', '/categorie-produit/magasin/cartes/yugi-ho/boite-de-booster-y/'],
    'DestockTCG': ['/jeux-de-cartes-a-collectionner/pokemon/boite-de-boosters-pokemon/', '/jeux-de-cartes-a-collectionner/one-piece-card-game/boosters-et-boite-de-boosters-en-francais/', '/jeux-de-cartes-a-collectionner/yu-gi-oh/booster-et-boite-de-boosters-551/'],
    'Play-in': ['/pokemon/', '/fr/categorie/193/booster-et-display-pokemon', '/yu-gi-oh/', '/one-piece/'],
    'Nippon TCG': ['/nos-displays', '/displays-japonais'],
    'Japan TCG Direct': ['/collections/pokemon', '/collections/one-piece'],
}


class MerchantConnector(UniversalConnector):
    def __init__(self, store, max_pages=250):
        super().__init__(store, max_pages)
        self.requests = 0
        self.failures = 0
        self.blocked = 0
        self.robots = RobotFileParser()
        self.browser = BrowserRenderer()
        self.policy_urls = []
        self.remaining_urls = 0

    async def get(self, client, url, **kwargs):
        if re.search(r'add[-_]?to[-_]?cart|checkout|monpanier|wishlist|/cart(?:[/?]|$)',url,re.I):
            return None
        if urlparse(url).netloc != urlparse(self.base).netloc or not self.robots.can_fetch(UA, url):
            self.blocked += 1
            return None
        if self.requests >= self.max_pages:
            return None
        self.requests += 1
        try:
            response = await client.get(url, **kwargs)
            # Retry transient throttling once, counting the retry in the same budget.
            if response.status_code in (429, 502, 503, 504) and self.requests < self.max_pages:
                delay = response.headers.get('retry-after', '1')
                if delay.isdigit() and int(delay) <= 5:
                    await asyncio.sleep(max(1, int(delay)))
                    self.requests += 1
                    response = await client.get(url, **kwargs)
            # Do not follow off-domain redirects or redirects to disallowed paths.
            for _ in range(4):
                if not response.is_redirect:
                    break
                target = urljoin(str(response.url), response.headers['location'])
                if urlparse(target).netloc != urlparse(self.base).netloc or not self.robots.can_fetch(UA, target):
                    self.blocked += 1
                    return None
                if self.requests >= self.max_pages:
                    return None
                self.requests += 1
                response = await client.get(target)
            if response.status_code != 200:
                self.failures += 1
                return None
            return response
        except httpx.HTTPError:
            self.failures += 1
            return None

    async def crawl(self):
        try:
            rows = await self._crawl()
            # At most two merchant policy reads, using the same robots and request budget.
            if rows and self.policy_urls:
                async with httpx.AsyncClient(timeout=8, headers=self.headers, follow_redirects=False) as client:
                    for url in self.policy_urls[:2]:
                        response = await self.get(client, url)
                        if response is not None:
                            evidence = origin_for(url, response.text)
                            for row in rows:
                                row['shipping_origin'] = merge_origins(row['shipping_origin'], evidence)
            return rows
        finally:
            await self.browser.close()

    async def _crawl(self):
        async with httpx.AsyncClient(timeout=25, headers=self.headers, follow_redirects=False) as client:
            response = await client.get(self.base + '/robots.txt')
            if response.status_code == 404:
                self.robots.parse([])
            elif response.status_code == 200:
                self.robots.parse(response.text.splitlines())
            else:
                raise ValueError(f'robots.txt unavailable ({response.status_code})')
            output = await self.shopify(client)
            if output:
                # JSON catalogues have no footer: inspect the home page for shipping evidence.
                response = await self.get(client, self.base + '/')
                if response is not None:
                    self.policy_urls = policy_links(response.text, self.base + '/')
                    evidence = origin_for(self.base + '/', response.text)
                    for row in output:
                        row['shipping_origin'] = merge_origins(row['shipping_origin'], evidence)
                return self._dedupe(output)
            queue = [urljoin(self.base, path) for path in PROFILES.get(self.store['name'], ['/'])]
            # Category traversal is complemented by product sitemaps.
            queue += [self.base + '/sitemap.xml', self.base + '/sitemap_index.xml', self.base + '/wp-sitemap.xml']
            queue += self.robots.site_maps() or []
            seen = set()
            state_dir = os.getenv('CRAWL_STATE_DIR')
            checkpoint = Path(state_dir) / (hashlib.sha256(self.base.encode()).hexdigest() + '.json') if state_dir else None
            if checkpoint and checkpoint.exists():
                try:
                    saved = json.loads(checkpoint.read_text())
                    if saved.get('queue'):
                        queue = saved['queue']
                        seen = set(saved.get('seen', []))
                except (OSError, ValueError, TypeError):
                    pass
            while queue and self.requests < self.max_pages:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                response = await self.get(client, url)
                if response is None:
                    continue
                if '.xml' in url or response.text.lstrip().startswith('<?xml'):
                    import xml.etree.ElementTree as ET
                    try:
                        content = response.content
                        if content.startswith(b'\x1f\x8b'):
                            with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
                                content = stream.read(10_000_001)
                            if len(content) > 10_000_000:
                                raise ValueError('Sitemap too large')
                        root = ET.fromstring(content)
                        links = [n.text for n in root.iter() if n.tag.split('}')[-1] == 'loc' and n.text]
                        is_index = root.tag.split('}')[-1] == 'sitemapindex'
                        links = sorted(links, key=lambda u: not bool(re.search(r'display|booster|case|carton|product', u, re.I)))
                        product_map = bool(re.search(r'product|produit', url, re.I))
                        queue.extend(u for u in links if u not in seen and (is_index or product_map or any(h in u.lower() for h in PRODUCT_HINTS) or re.search(r'/(?:products?|produit)/', u)))
                        queue = list(dict.fromkeys(queue))[:20000]
                    except (ET.ParseError, OSError, ValueError):
                        self.failures += 1
                    continue
                soup = BeautifulSoup(response.text, 'html.parser')
                parsed = self.parse_product(soup, url)
                # Render empty app shells and product pages lacking structured prices.
                if not parsed and soup.select_one('script') and (
                    len(soup.select('a[href]')) < 8 or
                    (not re.search(r'categor|collection|/type-|/nos-|/displays', url, re.I)
                     and soup.select_one('h1') and normalize(soup.select_one('h1').get_text(' ', strip=True)).get('kind'))
                ):
                    rendered = await self.browser.render(self, client, url, response.text)
                    soup = BeautifulSoup(rendered, 'html.parser')
                    parsed = self.parse_product(soup, url)
                output.extend(parsed)
                # Related-product carousels must not keep us away from catalogue pagination.
                if any(urlparse(row['url']).path.rstrip('/') == urlparse(url).path.rstrip('/') for row in parsed):
                    continue
                next_pages = []
                products = []
                categories = []
                for anchor in soup.select('a[href]'):
                    target = urljoin(url, anchor['href']).split('#')[0]
                    if target in seen or urlparse(target).netloc != urlparse(self.base).netloc:
                        continue
                    label = (anchor.get_text(' ', strip=True) + ' ' + target).lower()
                    if 'next' in anchor.get('rel', []) or re.search(r'/page/\d|[?&](page|p|pageNumber|start|offset)=\d', target):
                        next_pages.append(target)
                    elif (re.search(r'/(?:products?|produit)/|/(?:produit|product)-\d', target) and re.search(r'display|booster.?box|boite.*booster|case|carton',label)) or (normalize(anchor.get_text(' ',strip=True)).get('kind') and not re.search(r'categorie|category|type-|cat-', target)):
                        products.append(target)
                    elif any(h in label for h in PRODUCT_HINTS) and not re.search(r'/blogs?/|/news/|/tag/', target):
                        categories.append(target)
                queue = list(dict.fromkeys(products + next_pages + queue + categories))[:20000]
            self.remaining_urls = len(queue)
            if checkpoint:
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                temporary = checkpoint.with_suffix('.tmp')
                temporary.write_text(json.dumps({'queue': queue, 'seen': list(seen) if queue else []}))
                temporary.replace(checkpoint)
            return self._dedupe(output)

    async def shopify(self, client):
        output = []
        seen_pages = set()
        for page in range(1, self.max_pages + 1):
            response = await self.get(client, f'{self.base}/products.json?limit=250&page={page}')
            if response is None or 'json' not in response.headers.get('content-type', ''):
                break
            try:
                products = response.json()['products']
            except (ValueError, KeyError, TypeError):
                break
            if not products:
                break
            signature = json.dumps(products, sort_keys=True)
            if signature in seen_pages:
                break
            seen_pages.add(signature)
            for product in products:
                for variant in product.get('variants', []):
                    title = product.get('title', '')
                    if variant.get('title') != 'Default Title':
                        title += ' ' + variant.get('title', '')
                    meta = normalize(title)
                    if not meta.get('game') or not meta.get('kind'):
                        continue
                    try:
                        price = float(variant['price'])
                    except (TypeError, ValueError, KeyError):
                        continue
                    if not math.isfinite(price) or price <= 0:
                        continue
                    url = f"{self.base}/products/{product['handle']}?variant={variant['id']}"
                    output.append(self._offer(title, url, price, self.store.get('currency', 'EUR'), variant.get('available') is True, meta, 'shopify-variant'))
            if len(products) < 250:
                break
        return output

    def _offer(self, *args, **kwargs):
        row = super()._offer(*args, **kwargs)
        row['shipping_origin'] = origin_for(row['url'])
        return row

    def parse_product(self, soup, url):
        html = str(soup)
        self.policy_urls = list(dict.fromkeys(self.policy_urls + policy_links(html, url)))[:2]
        rows = self._parse_product(soup, url)
        evidence = origin_for(url, html)
        for row in rows:
            row['shipping_origin'] = merge_origins(row['shipping_origin'], evidence)
        return rows

    def _parse_product(self, soup, url):
        output = []
        if soup.select_one('li.product.product-type-simple'):
            # WooCommerce cards have explicit stock classes and sale-price markup.
            for card in soup.select('li.product.product-type-simple'):
                heading=card.select_one('h2,h3,h4,.woocommerce-loop-product__title')
                link=card.select_one('a.woocommerce-LoopProduct-link, a[href*="/produit/"]')
                price=card.select_one('.price ins .amount') or card.select_one('.price .amount')
                if not heading or not link or not price: continue
                title=heading.get_text(' ',strip=True)
                meta=normalize(title)
                if not meta.get('game') or not meta.get('kind'): continue
                value=re.search(r'\d[\d\s\u00a0]*[,.]\d{2}',price.get_text(' ',strip=True))
                if not value: continue
                number=float(re.sub(r'\s','',value[0]).replace(',','.'))
                target=urljoin(url,link['href'])
                if urlparse(target).netloc == urlparse(self.base).netloc and math.isfinite(number) and number > 0:
                    output.append(self._offer(title,target,number,self.store.get('currency','EUR'),'instock' in card.get('class',[]),meta,'woocommerce-card'))
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or script.get_text())
            except (ValueError, TypeError):
                continue
            stack = data if isinstance(data, list) else [data]
            while stack:
                node = stack.pop()
                if not isinstance(node, dict):
                    continue
                for key in ('@graph', 'itemListElement', 'item', 'hasVariant'):
                    child = node.get(key, [])
                    stack.extend(child if isinstance(child, list) else [child])
                if 'Product' not in (node.get('@type') if isinstance(node.get('@type'), list) else [node.get('@type')]):
                    continue
                title = node.get('name', '')
                meta = normalize(title)
                if meta.get('game') and not meta.get('kind'):
                    described = normalize(str(node.get('description', '')))
                    if described.get('game') == meta['game'] and described.get('kind') == 'display' and described.get('set_code') == meta.get('set_code'):
                        meta['kind'] = 'display'
                        meta['display_count'] = 1
                if not meta.get('game') or not meta.get('kind'):
                    continue
                offers = node.get('offers', [])
                offers = offers if isinstance(offers, list) else [offers]
                offers = [child for offer in offers for child in (
                    (offer['offers'] if isinstance(offer['offers'], list) else [offer['offers']])
                    if isinstance(offer, dict) and 'offers' in offer else [offer])]
                for offer in offers:
                    # Aggregate lowPrice is not a purchasable SKU.
                    if not isinstance(offer, dict):
                        continue
                    specification = offer.get('priceSpecification', {})
                    specification = specification if isinstance(specification, dict) else {}
                    price = amount(offer.get('price', specification.get('price', '')))
                    if price is None:
                        continue
                    if not math.isfinite(price) or price <= 0:
                        continue
                    target = urljoin(url, offer.get('url') or node.get('url') or url)
                    if urlparse(target).netloc != urlparse(self.base).netloc:
                        continue
                    stock = str(offer.get('availability', '')).rsplit('/', 1)[-1].lower() == 'instock'
                    row=self._offer(title, target, price, offer.get('priceCurrency', self.store.get('currency', 'EUR')), stock, meta, 'jsonld')
                    row['currency'] = offer.get('priceCurrency') or specification.get('priceCurrency') or row['currency']
                    row['stock_status'] = stock_status(offer.get('availability', ''))
                    details=offer.get('shippingDetails',[])
                    for detail in (details if isinstance(details,list) else [details]):
                        if not isinstance(detail,dict): continue
                        destination=detail.get('shippingDestination',{})
                        rate=detail.get('shippingRate',{})
                        if isinstance(destination,dict) and isinstance(rate,dict) and destination.get('addressCountry')=='FR' and rate.get('currency')=='EUR':
                            try:
                                fee=float(rate['value'])
                                if math.isfinite(fee) and fee>=0: row['shipping_eur']=fee
                            except (ValueError,TypeError,KeyError): pass
                    output.append(row)
        if any(urlparse(row['url']).path.rstrip('/') == urlparse(url).path.rstrip('/') for row in output):
            return output
        # Merchant pages without JSON-LD: only explicit price/availability metadata.
        heading = soup.select_one('h1')
        value, status = visible_offer(soup)
        currency = soup.select_one('meta[property="product:price:currency"], [itemprop="priceCurrency"]')
        stock = soup.select_one('[itemprop="availability"], meta[property="product:availability"]')
        if heading and value is not None:
            title = heading.get_text(' ', strip=True)
            meta = normalize(title)
            if meta.get('game') and meta.get('kind') and math.isfinite(value) and value > 0:
                available = status == 'in_stock'
                money = currency.get('content', currency.get_text(strip=True)) if currency else self.store.get('currency', 'EUR')
                if money == 'UNK' and '€' in str(soup.select_one('.current-price, .summary .price')):
                    money = 'EUR'
                output.append(self._offer(title, url, value, money, bool(available), meta, 'merchant-meta'))
                output[-1]['stock_status'] = status
        return output

    def _dedupe(self, rows):
        return list({row['url']: row for row in rows}.values())
