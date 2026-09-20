import asyncio
import json
import socket
import httpx
import pytest
from app.services.discovery import DiscoveryQuery, Discovery
from app.services.web_prices import PublicPages, WebPrices, price_from_html, public_address


QUERY = DiscoveryQuery(game='One Piece', name='Two Legends', code='OP-08', language='FR', include_prices=True)
URL = 'https://shop.example/product'


def page(title='One Piece OP-08 Two Legends display FR', price=120, currency='EUR', stock='InStock', **extra):
    offer = dict(price=price, priceCurrency=currency, availability='https://schema.org/'+stock, **extra)
    return '<h1>'+title+'</h1><script type="application/ld+json">'+json.dumps({'@type':'Product','name':title,'offers':offer})+'</script>'


def test_price_stock_case_and_currency():
    row = price_from_html(page(), URL, QUERY, {'EUR':1})
    assert row['comparable'] and row['unit_price_eur'] == 120
    row = price_from_html(page(title='One Piece OP08 FR case 6 displays', price=600), URL, QUERY, {'EUR':1})
    assert row['unit_price_eur'] == 100 and row['price'] == 600 and row['display_count'] == 6
    row = price_from_html(page(price=10000,currency='JPY'), URL, QUERY, {'JPY':0.006})
    assert row['unit_price_eur'] == 60 and row['currency']=='JPY'


@pytest.mark.parametrize('changes', [
    {'stock':'OutOfStock'}, {'stock':''}, {'currency':'XYZ'},
    {'title':'One Piece OP08 display japonais'}, {'title':'One Piece OP08 display'},
    {'title':'One Piece OP08 FR case'}, {'title':'One Piece OP08 display FR / JP'},
])
def test_unconfirmed_offers_not_ranked(changes):
    row = price_from_html(page(**changes), URL, QUERY, {'EUR':1})
    assert row and not row['comparable']


@pytest.mark.parametrize('changes', [
    {'title':'One Piece OP09 Two Legends display FR'},
    {'title':'One Piece OP08 booster FR'}, {'price':0}, {'price':'NaN'},
    {'url':'https://shop.example/related-product'},
])
def test_wrong_products_and_invalid_prices_rejected(changes):
    assert price_from_html(page(**changes), URL, QUERY, {'EUR':1}) is None


def test_ambiguous_variants_and_aggregate_rejected():
    assert price_from_html(page()+page(price=90), URL, QUERY, {'EUR':1}) is None
    html=page().replace('"price": 120', '"lowPrice": 120')
    assert price_from_html(html, URL, QUERY, {'EUR':1}) is None


def test_dns_private_address_rejected(monkeypatch):
    async def run():
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',0))]
        monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',resolve)
        with pytest.raises(ValueError):
            await public_address('shop.example')
    asyncio.run(run())


def test_public_fetch_pins_ip_and_respects_robots():
    calls=[]
    async def resolve(host): return '93.184.216.34'
    def handler(request):
        assert request.url.host=='93.184.216.34'
        assert request.headers['host']=='shop.example'
        assert request.extensions['sni_hostname']=='shop.example'
        calls.append(request.url.path)
        return httpx.Response(200,text='User-agent: *\nDisallow: /product' if request.url.path=='/robots.txt' else page())
    async def run():
        with pytest.raises(ValueError):
            await PublicPages(httpx.MockTransport(handler),resolve).product(URL)
    asyncio.run(run())
    assert calls==['/robots.txt']


def test_external_redirect_is_never_followed():
    calls=[]
    async def resolve(host): return '93.184.216.34'
    def handler(request):
        calls.append(request.url.path)
        if request.url.path=='/robots.txt': return httpx.Response(404)
        return httpx.Response(302,headers={'location':'http://127.0.0.1/secret'})
    async def run():
        with pytest.raises(ValueError):
            await PublicPages(httpx.MockTransport(handler),resolve).product(URL)
    asyncio.run(run())
    assert calls==['/robots.txt','/product']


def test_enrichment_orders_comparable_prices_and_keeps_failures(monkeypatch):
    async def rates(): return {'EUR':1}
    monkeypatch.setattr('app.services.web_prices.eur_rates',rates)
    class Pages:
        async def product(self,url):
            if url.endswith('/blocked'): raise ValueError('blocked')
            return page(price=200 if url.endswith('/expensive') else 100),url
    candidates=[{'url':'https://shop.example/'+name} for name in ['expensive','blocked','cheap']]
    result=asyncio.run(WebPrices(Pages()).enrich(candidates,QUERY))
    assert [row.get('unit_price_eur') for row in result]==[100,200,None]
    assert result[-1]['price_status']=='unavailable'


def test_priced_search_cache_expires_after_five_minutes(tmp_path,monkeypatch):
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY',raising=False)
    monkeypatch.setenv('SEARXNG_URL','https://search.example')
    calls=[]
    async def enrich(self,rows,query):
        calls.append(True)
        rows[0].update(price_status='read',comparable=True,unit_price_eur=100)
    monkeypatch.setattr(WebPrices,'enrich',enrich)
    async def run():
        service=Discovery(tmp_path/'cache.sqlite',httpx.MockTransport(lambda r:httpx.Response(200,json={'results':[{'url':URL,'title':'One Piece OP08 FR display'}]})))
        first=await service.search(QUERY)
        second=await service.search(QUERY)
        assert first['cache_ttl_seconds']==300 and first['comparable_count']==1
        assert second['cached'] and len(calls)==1
    asyncio.run(run())
