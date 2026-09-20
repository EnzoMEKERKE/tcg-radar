"""Bounded product-page reads on public addresses, with explicit comparable prices."""
import asyncio
import ipaddress
import re
import socket
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from app.connectors.merchant import MerchantConnector
from app.connectors.universal import UA
from app.services.fx import eur_rates
from app.services.origin import origin_for, policy_links, merge_origins
from app.services.product_page import visible_offer


async def public_address(host):
    rows = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM), 3)
    addresses = list(dict.fromkeys(row[4][0] for row in rows))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError('Non-public destination')
    return next((address for address in addresses if ':' not in address), addresses[0])


class PublicPages:
    def __init__(self, transport=None, resolver=public_address):
        self.transport = transport
        self.resolver = resolver

    async def get(self, client, url, origin, robots=None):
        # Resolve once per request and connect to that literal address to prevent DNS rebinding.
        from app.services.discovery import clean_url
        for _ in range(4):
            if not clean_url(url) or urlsplit(url).netloc != urlsplit(origin).netloc:
                raise ValueError('Redirect outside merchant')
            if re.search(r'add[-_]?to[-_]?cart|checkout|wishlist|/cart(?:[/?]|$)', url, re.I):
                raise ValueError('Not a product page')
            if robots and not robots.can_fetch(UA, url):
                raise ValueError('Path disallowed')
            target = httpx.URL(url)
            address = await self.resolver(target.host)
            pinned = target.copy_with(host=address)
            async with client.stream('GET', pinned, headers={'Host': target.netloc.decode()},
                                     extensions={'sni_hostname': target.host}) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location', ''))
                    continue
                if response.status_code == 404 and robots is None:
                    return '', url
                response.raise_for_status()
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ValueError('Page too large')
                    chunks.append(chunk)
                return b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace'), url
        raise ValueError('Too many redirects')

    async def product(self, url):
        parts = urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False,
                                    transport=self.transport, headers={'User-Agent': UA}) as client:
            text, _ = await self.get(client, origin + '/robots.txt', origin)
            robots = RobotFileParser()
            robots.parse(text.splitlines())
            return await self.get(client, url, origin, robots)


def price_from_html(html, url, query, rates):
    from app.services.discovery import relevance_for
    soup = BeautifulSoup(html, 'html.parser')
    # Unknown currencies are not implicitly treated as EUR.
    currency_meta = soup.select_one('meta[property="product:price:currency"], meta[itemprop="priceCurrency"]')
    currency = currency_meta.get('content', 'UNK') if currency_meta else 'UNK'
    parts = urlsplit(url)
    connector = MerchantConnector({'name': parts.hostname, 'url': f'{parts.scheme}://{parts.netloc}', 'currency': currency}, max_pages=1)
    rows = connector.parse_product(soup, url)
    valid = []
    for row in rows:
        # Ignore related products and prices on category pages.
        if urlsplit(row['url']).path.rstrip('/') != parts.path.rstrip('/'):
            continue
        hints = relevance_for(row['title'], query)
        meta = row['meta']
        if meta.get('game') != query.game or not hints['set_match'] or meta.get('kind') not in ('display', 'case'):
            continue
        code = meta.get('set_code')
        # A conflicting explicit code takes precedence over a shared set name.
        if code and query.code and not query.code.startswith(('YGO-', 'UNKNOWN', 'UNMATCHED-')):
            def normalized_code(value):
                value = re.sub(r'[^a-z0-9.]', '', value.lower())
                value = re.sub(r'^sv', 'ev', value)
                value = re.sub(r'^swsh', 'eb', value)
                return re.sub(r'(?<=[a-z])0+(?=\d)', '', value)
            if normalized_code(code) != normalized_code(query.code):
                continue
        count = meta.get('display_count')
        currency = str(row['currency']).upper()
        if not re.fullmatch(r'[A-Z]{3}', currency):
            currency = 'UNK'
        euro = round(row['price'] * rates[currency], 2) if currency in rates else None
        unit = round(euro / count, 2) if euro is not None and count else None
        comparable = bool(unit and row['in_stock'] and hints['language_match'] == 'match')
        valid.append(dict(price=row['price'], currency=currency, price_eur=euro, unit_price_eur=unit,
                          display_count=count, in_stock=row['in_stock'], comparable=comparable,
                          stock_status=row.get('stock_status', 'in_stock' if row['in_stock'] else 'unknown'),
                          price_title=row['title'], price_url=row['url'], checked_at=int(time.time()),
                          price_status='read', **hints))
    # Different variants on one URL are ambiguous: do not present a fictitious lowest SKU.
    unique = {(row['price'], row['currency'], row['price_title'], row['in_stock']): row for row in valid}
    return next(iter(unique.values())) if len(unique) == 1 else None


class WebPrices:
    def __init__(self, pages=None):
        self.pages = pages or PublicPages()

    async def enrich(self, candidates, query):
        rates = await eur_rates()
        semaphore = asyncio.Semaphore(12)
        domains = {}
        policy_tasks = {}
        policy_semaphore = asyncio.Semaphore(4)
        async def read_policies(url, html):
            result = origin_for(url)
            for link in policy_links(html, url):
                try:
                    async with policy_semaphore, asyncio.timeout(6):
                        text, final_url = await self.pages.product(link)
                    result = merge_origins(result, origin_for(final_url, text))
                except (TimeoutError, OSError, ValueError, httpx.HTTPError):
                    continue
            return result
        async def one(row):
            row.update(price_status='unavailable', comparable=False, shipping_origin=origin_for(row['url']))
            if row.get('language_match') == 'mismatch':
                return
            domain = urlsplit(row['url']).netloc
            domain_semaphore = domains.setdefault(domain, asyncio.Semaphore(2))
            async with domain_semaphore, semaphore:
                try:
                    async with asyncio.timeout(7):
                        html, url = await self.pages.product(row['url'])
                        _, status = visible_offer(BeautifulSoup(html, 'html.parser'))
                        row['stock_status'] = status
                        row['shipping_origin'] = origin_for(url, html)
                        if domain not in policy_tasks and policy_links(html, url):
                            policy_tasks[domain] = asyncio.create_task(read_policies(url, html))
                        price = price_from_html(html, url, query, rates)
                        if price:
                            row.update(price)
                        if status in ('out_of_stock', 'preorder'):
                            row.update(stock_status=status, in_stock=False, comparable=False)
                except (TimeoutError, OSError, ValueError, TypeError, KeyError, AttributeError, httpx.HTTPError):
                    pass
        tasks = [asyncio.create_task(one(row)) for row in candidates]
        try:
            async with asyncio.timeout(42):
                await asyncio.gather(*tasks)
        except TimeoutError:
            pass
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if policy_tasks:
            try:
                async with asyncio.timeout(5):
                    await asyncio.gather(*policy_tasks.values(), return_exceptions=True)
            except TimeoutError:
                pass
            finally:
                for task in policy_tasks.values():
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*policy_tasks.values(), return_exceptions=True)
            for row in candidates:
                task = policy_tasks.get(urlsplit(row['url']).netloc)
                if task and not task.cancelled() and task.exception() is None:
                    row['shipping_origin'] = merge_origins(row['shipping_origin'], task.result())
        candidates.sort(key=lambda row: (not row.get('comparable', False), row.get('unit_price_eur') or float('inf')))
        candidates[:] = [row for row in candidates if row.get('stock_status') not in ('out_of_stock', 'preorder')]
        return candidates
