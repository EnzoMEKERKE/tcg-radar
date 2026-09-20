"""Conservative extraction from a product's purchase area, never related cards."""
import math
import re


def amount(value):
    text = re.sub(r'\s+', '', str(value)).replace('\u202f', '')
    text = re.sub(r'[^\d.,-]', '', text)
    if ',' in text and '.' in text:
        text = text.replace(',', '') if text.rfind('.') > text.rfind(',') else text.replace('.', '').replace(',', '.')
    else:
        text = text.replace(',', '.')
    try:
        number = float(text)
        return number if math.isfinite(number) and number > 0 else None
    except ValueError:
        return None


def purchase_area(soup):
    return soup.select_one('.product-information, .product-summary, .summary.entry-summary, #product-details, [data-product-information]')


def stock_status(value):
    value = str(value).lower().replace('_', ' ')
    if re.search(r'outofstock|out of stock|sold out|rupture|épuisé|unavailable|indisponible|réassort en cours', value):
        return 'out_of_stock'
    if re.search(r'preorder|précommande|pre-order|backorder', value):
        return 'preorder'
    if re.search(r'instock|in stock|en stock|disponible', value):
        return 'in_stock'
    return 'unknown'


def visible_offer(soup):
    area = purchase_area(soup)
    price = soup.select_one('meta[property="product:price:amount"]')
    if price is None:
        scope = area or soup
        for selector in ('[itemprop="price"]', '.current-price [content]', '.current-price-value', '.current-price', '.price ins .amount', '.price .amount', '[data-product-price]'):
            nodes = [n for n in scope.select(selector) if not n.find_parent(['del', 's']) and not n.find_parent(class_=re.compile(r'related|upsell|cross-sell'))]
            values = {amount(n.get('content') or n.get('data-product-price') or n.get_text(' ', strip=True)) for n in nodes}
            values.discard(None)
            if len(values) == 1:
                price = nodes[0]
                break
    value = amount(price.get('content') or price.get('data-product-price') or price.get_text(' ', strip=True)) if price else None
    scope = area or soup
    stock = scope.select_one('[itemprop="availability"], #product-availability, .stock, [data-stock-status]')
    stock = stock if stock is not None else soup.select_one('meta[property="product:availability"]')
    status = stock_status((stock.get('href') or stock.get('content') or stock.get_text(' ', strip=True)) if stock else '')
    return value, status
