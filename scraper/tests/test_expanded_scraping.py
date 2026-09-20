import asyncio
import gzip
import json

import httpx
from bs4 import BeautifulSoup

from app.connectors.merchant import MerchantConnector
from app.services.discovery import candidates_from


def connector():
    return MerchantConnector({'name': 'Test', 'url': 'https://shop.test', 'currency': 'EUR'}, max_pages=30)


def product(url='/products/box'):
    return {'@type': 'Product', 'name': 'One Piece OP09 FR display', 'url': url,
            'offers': {'price': 99, 'priceCurrency': 'EUR', 'availability': 'https://schema.org/InStock'}}


def test_product_nested_in_item_list():
    data = {'@type': 'ItemList', 'itemListElement': [{'@type': 'ListItem', 'item': product()}]}
    soup = BeautifulSoup('<script type="application/ld+json">'+json.dumps(data)+'</script>', 'html.parser')
    assert connector().parse_product(soup, 'https://shop.test/category')[0]['price'] == 99


def test_expanded_results_keep_diversity_and_variants():
    data = [{'url': f'https://shop{shop}.example/box?variant={variant}'} for shop in range(30) for variant in range(8)]
    rows = candidates_from(data, limit=120, domain_limit=6)
    assert len(rows) == 120
    assert len({r['url'] for r in rows}) == 120
    assert max(sum(r['domain'] == domain for r in rows) for domain in {r['domain'] for r in rows}) == 6


def test_general_woocommerce_sale():
    soup = BeautifulSoup('<li class="product product-type-simple instock"><a class="woocommerce-LoopProduct-link" href="/produit/box"><h2>One Piece OP09 FR display</h2></a><span class="price"><del><span class="amount">120,00</span></del><ins><span class="amount">99,00</span></ins></span></li>', 'html.parser')
    row = connector().parse_product(soup, 'https://shop.test/category')[0]
    assert row['price'] == 99 and row['in_stock']


def test_repeated_shopify_page_stops_without_losing_variants():
    async def run():
        c = connector()
        c.robots.parse([])
        data = {'products': [{'title': 'One Piece OP09 FR display', 'handle': f'box{i}', 'variants': [{'id': i, 'title': 'Default Title', 'price': '99', 'available': True}]} for i in range(250)]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))) as client:
            rows = await c.shopify(client)
        assert len(rows) == 250 and c.requests == 2
    asyncio.run(run())


def test_budgeted_crawl_resumes_remaining_pages(monkeypatch, tmp_path):
    monkeypatch.setenv('CRAWL_STATE_DIR', str(tmp_path))
    calls = []
    def response(request):
        calls.append(request.url.path)
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *')
        if request.url.path == '/':
            return httpx.Response(200, text=''.join(f'<a href="/products/box{i}">One Piece OP09 display FR</a>' for i in range(6)))
        if request.url.path.startswith('/products/box'):
            return httpx.Response(200, text='<script type="application/ld+json">'+json.dumps(product(request.url.path))+'</script>')
        return httpx.Response(404)
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(response), **kwargs))
    async def run():
        first = connector()
        first.max_pages = 4
        rows = await first.crawl()
        assert first.remaining_urls > 0
        second = connector()
        rows += await second.crawl()
        assert len({row['url'] for row in rows}) == 6
        assert calls.count('/') == 1 and second.remaining_urls == 0
    asyncio.run(run())


def test_robots_sitemap_gzip_and_opaque_product_url(monkeypatch):
    async def run():
        c = connector()
        pages = {
            '/robots.txt': httpx.Response(200, text='User-agent: *\nSitemap: https://shop.test/custom-products.xml.gz'),
            '/custom-products.xml.gz': httpx.Response(200, content=gzip.compress(b'<urlset><url><loc>https://shop.test/sku123</loc></url></urlset>')),
            '/sku123': httpx.Response(200, text='<script type="application/ld+json">'+json.dumps(product('/sku123'))+'</script>'),
        }
        original = httpx.AsyncClient
        monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(lambda r: pages.get(r.url.path, httpx.Response(404))), **kwargs))
        rows = await c.crawl()
        assert len(rows) == 1 and rows[0]['url'].endswith('/sku123')
    asyncio.run(run())


def test_product_carousel_does_not_starve_category_pagination(monkeypatch):
    async def run():
        c = connector()
        calls = []
        def response(request):
            path = request.url.path
            calls.append(str(request.url))
            if path == '/robots.txt':
                return httpx.Response(200, text='User-agent: *')
            if path == '/':
                if request.url.query:
                    return httpx.Response(200, text='<script type="application/ld+json">'+json.dumps(product('/products/second'))+'</script>')
                return httpx.Response(200, text='<a href="/products/box">One Piece OP09 FR display</a><a rel="next" href="/?page=2">Next</a>')
            if path == '/products/box':
                return httpx.Response(200, text='<script type="application/ld+json">'+json.dumps(product())+'</script><a href="/products/trap">One Piece OP09 FR display</a>')
            return httpx.Response(404)
        original = httpx.AsyncClient
        monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(response), **kwargs))
        rows = await c.crawl()
        assert len(rows) == 2
        assert not any('/products/trap' in url for url in calls)
    asyncio.run(run())
