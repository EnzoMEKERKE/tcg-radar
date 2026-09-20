import asyncio
import json
import pytest
from app.services.web_prices import price_from_html, WebPrices
from app.services.discovery import DiscoveryQuery

QUERY = DiscoveryQuery(game='One Piece', code='OP-08', name='Two Legends', language='FR', include_prices=True)
URL = 'https://shop.example/product'
TITLE = '<h1>One Piece OP08 display FR</h1>'


@pytest.mark.parametrize('markup,expected', [
    ('<div class="current-price"><span content="109.90">109,90 €</span></div>',109.90),
    ('<div class="summary entry-summary"><p class="price"><del><b class="amount">150,00 €</b></del><ins><b class="amount">119,90 €</b></ins></p></div>',119.90),
    ('<span itemprop="price" content="1.299,90"></span>',1299.90),
])
def test_visible_purchase_price(markup, expected):
    markup = markup.replace('</div>', '<p class="stock in-stock">En stock</p></div>')
    row = price_from_html(TITLE+markup+'<meta itemprop="priceCurrency" content="EUR"><p class="stock in-stock">En stock</p>', URL, QUERY, {'EUR':1})
    assert row['price'] == expected and row['in_stock']


def test_price_specification_and_sold_out_filter(monkeypatch):
    html = TITLE + '<script type="application/ld+json">' + json.dumps({'@type':'Product','name':'One Piece OP08 display FR','offers':{'priceSpecification':{'price':'99,90','priceCurrency':'EUR'},'availability':'https://schema.org/OutOfStock'}}) + '</script>'
    row = price_from_html(html, URL, QUERY, {'EUR':1})
    assert row['price'] == 99.90 and row['stock_status'] == 'out_of_stock'
    class Pages:
        async def product(self, url):
            return html, url
    async def rates():
        return {'EUR':1}
    monkeypatch.setattr('app.services.web_prices.eur_rates', rates)
    candidates = [{'url':URL,'language_match':'match'}]
    asyncio.run(WebPrices(Pages()).enrich(candidates, QUERY))
    assert candidates == []


def test_related_price_and_ambiguous_range_rejected():
    for markup in ('<div class="related"><span class="amount">19,90 €</span></div>', '<div class="current-price">100,00 € - 200,00 €</div>'):
        assert price_from_html(TITLE+markup, URL, QUERY, {'EUR':1}) is None


def test_display_identified_in_own_product_description():
    product = {'@type':'Product', 'name':'Bandai Gundam GD02 (24 boosters)', 'description':'Display 24 boosters Gundam GD02 Dual Impact', 'offers':{'price':'119.99','priceCurrency':'EUR','availability':'https://schema.org/OutOfStock'}}
    html = '<script type="application/ld+json">'+json.dumps(product)+'</script>'
    row = price_from_html(html, URL, DiscoveryQuery(game='Gundam', code='GD-02', name='Dual Impact', language='JP'), {'EUR':1})
    assert row['price'] == 119.99 and row['stock_status'] == 'out_of_stock'
