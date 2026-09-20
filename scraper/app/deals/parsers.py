"""eBay and Cardmarket selectors ported from pokedeals-v2, with strict evidence checks."""
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, parse_qs
from bs4 import BeautifulSoup
from pydantic import ValidationError
from app.services.product_page import amount
from .identity import condition_of, language_of, flat
from .models import Listing


def text(node, selector):
    found = node.select_one(selector)
    if found:
        for hidden in found.select('.clipped, .visually-hidden, .sr-only'):
            hidden.decompose()
    return found.get_text(' ', strip=True) if found else ''


def date_of(value):
    value = flat(value)
    months = {'jan':1,'fev':2,'feb':2,'mar':3,'avr':4,'apr':4,'mai':5,'may':5,'juin':6,'jun':6,'juil':7,'jul':7,'aou':8,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
    iso = re.search(r'\b(20\d\d)-(\d\d)-(\d\d)\b',value)
    if iso:
        try: return datetime(*map(int,iso.groups()),tzinfo=timezone.utc)
        except ValueError: return None
    match = re.search(r'(\d{1,2})\s+([a-z]+)\.?\s+(20\d\d)', value)
    reverse = re.search(r'([a-z]+)\s+(\d{1,2}),?\s+(20\d\d)', value)
    if not match and not reverse: return None
    day, month, year = match.groups() if match else (reverse[2],reverse[1],reverse[3])
    key = month[:4] if month.startswith(('juin','juil')) else month[:3]
    try: return datetime(int(year),months[key],int(day),tzinfo=timezone.utc)
    except (ValueError,KeyError): return None


def shipping_of(value):
    if re.search(r'free|gratuit',flat(value)): return 0.0
    return amount(value) if value else None


def parse_ebay(html, sold=False):
    soup = BeautifulSoup(html,'html.parser')
    result = []
    for item in soup.select('.s-item, .s-card'):
        title = text(item,'.s-item__title, .s-card__title, h3')
        if not title or re.search(r'shop on ebay|acheter sur ebay',title,re.I): continue
        link = item.select_one('a.s-item__link, a.s-card__link, a[href*="/itm/"]')
        price_text = text(item,'.s-item__price, .s-card__price')
        if not link or re.search(r'\s(?:to|à|a)\s|\d\s*[-–]\s*\d',price_text): continue
        price = amount(price_text)
        if price is None: continue
        raw = item.get_text(' ',strip=True)
        # A sold search may contain promoted active cards. Require per-row proof.
        sold_text = text(item,'.s-item__title--tag, .s-item__ended-date, .s-card__caption, .s-item__caption')
        sold_at = date_of(sold_text) if re.search(r'vendu|sold',flat(sold_text)) else None
        if sold and not sold_at: continue
        if not sold and re.search(r'\b(encheres|bids?)\b',flat(raw)): continue
        currency = 'USD' if '$' in price_text or 'USD' in price_text else 'GBP' if '£' in price_text else 'EUR' if '€' in price_text or 'EUR' in price_text else None
        if not currency: continue
        # "Used" is not a trading-card condition; do not assume LP from it.
        condition = condition_of(text(item,'.SECONDARY_INFO, .s-item__subtitle, .s-card__subtitle'))
        if condition == 'UNKNOWN':
            precise = re.search(r'\b(near mint|nm|mint|mt|excellent|light played|lp|played|pl|poor|po)\b',flat(title))
            condition = condition_of(precise[0]) if precise else 'UNKNOWN'
        shipping_text = text(item,'.s-item__shipping, .s-card__shipping, .s-item__logisticsCost')
        if not shipping_text:
            for attribute in item.select('.s-card__attribute-row'):
                value = attribute.get_text(' ',strip=True)
                if re.search(r'shipping|livraison',value,re.I) and (re.match(r'\s*\+',value) or re.search(r'free|gratuit',value,re.I)):
                    shipping_text = value
                    break
        listing_id = re.search(r'/itm/(?:[^/?]+/)?(\d+)', link['href'])
        seller_link = item.select_one('a[href*="/usr/"]')
        seller = seller_link.get_text(' ',strip=True) if seller_link else ''
        try:
            result.append(Listing(source='ebay',title=title,url=link['href'].split('?')[0],price=price,currency=currency,
                shipping=shipping_of(shipping_text),
                language=language_of(title),condition=condition,sold=sold,sold_at=sold_at,
                listing_id=listing_id[1] if listing_id else '',seller=seller[:120],
                price_exact=not bool(re.search(r'best offer accepted|offre acceptee|prix accepte',flat(raw))),
                available=not bool(re.search(r'out of stock|rupture|sold out',flat(raw)))))
        except (ValidationError,KeyError): continue
    return result


def product_links(html, base):
    soup = BeautifulSoup(html,'html.parser')
    return list(dict.fromkeys(urljoin(base,a['href']).split('#')[0] for a in soup.select('a[href*="/Products/Singles/"]') if urlsplit(urljoin(base,a['href'])).hostname == 'www.cardmarket.com'))


def cardmarket_next_page(html, url):
    soup = BeautifulSoup(html,'html.parser')
    base = urlsplit(url)
    try:
        current = int(parse_qs(base.query).get('site',['1'])[0])
    except ValueError:
        return None
    for anchor in soup.select('a[rel="next"], .pagination a[href]'):
        if anchor.find_parent(class_='disabled'):
            continue
        target = urljoin(url,anchor.get('href',''))
        parsed = urlsplit(target)
        if parsed.scheme != 'https' or parsed.netloc != base.netloc or parsed.path != base.path:
            continue
        params = parse_qs(parsed.query)
        original = parse_qs(base.query)
        if {k:v for k,v in params.items() if k!='site'} != {k:v for k,v in original.items() if k!='site'}:
            continue
        try:
            following = int(params.get('site',['1'])[0])
        except ValueError:
            continue
        if following == current+1:
            return target
    return None


def parse_cardmarket(html,url):
    soup = BeautifulSoup(html,'html.parser')
    title = text(soup,'h1')
    number = ''
    for dt in soup.select('dt'):
        if re.search(r'number|numero|nombre',flat(dt.get_text())):
            dd = dt.find_next_sibling('dd')
            if dd: number = dd.get_text(' ',strip=True)
    result = []
    for row in soup.select('.article-row'):
        price = amount(text(row,'.price-container .font-weight-bold, .price-container .fw-bold, .col-price'))
        if not price or not title: continue
        # Seller location and comments are not evidence of the card's language.
        attributes = row.select_one('.product-attributes')
        tips = ' '.join((n.get('data-original-title') or n.get('data-bs-original-title') or n.get('title') or '') for n in attributes.select('[title], [data-original-title], [data-bs-original-title]')) if attributes else ''
        attrs = text(row,'.product-attributes')+' '+tips
        language = language_of(attrs)
        condition = condition_of(attrs)
        seller = text(row,'a[href*="/Users/"]')
        if not seller: continue
        try:
            result.append(Listing(source='cardmarket',title=title,url=url,price=price,language=language,
                condition=condition,card_number=number if re.fullmatch(r'[A-Za-z0-9 /-]{1,30}',number) else '',
                shipping=shipping_of(text(row,'.shipping-price, .shipping-cost')),seller=seller,
                listing_id=row.get('id',''),variant='reverse' if re.search(r'reverse',attrs,re.I) else '',
                available=not bool(re.search(r'sold out|rupture|indisponible',flat(row.get_text())))))
        except ValidationError: continue
    return result
