import asyncio
import httpx
import pytest
from app.deals.ebay_provider import ScrapingBeePages
from app.deals.browser import MarketplaceAccessError
from app.deals.local_browser import LocalOrBrowserPages
from app.deals.parsers import parse_ebay

URL='https://www.ebay.fr/sch/i.html?_nkw=pikachu&LH_Sold=1&LH_Complete=1'
HTML='''<title>Ventes Pikachu</title><div class="s-item"><h3 class="s-item__title">Pikachu 25/102 FR NM non-holo</h3>
<a class="s-item__link" href="https://www.ebay.fr/itm/123456789012">Annonce</a>
<span class="s-item__price">20,00 €</span><span class="s-item__ended-date">Vendu le 18 septembre 2026</span>
<span>Best offer accepted</span></div>'''


def test_provider_request_and_hidden_final_price():
    async def scenario():
        def handle(request):
            assert request.headers['Authorization']=='Bearer secret-test'
            assert 'secret-test' not in str(request.url)
            assert request.url.params['url']==URL
            assert request.url.params['premium_proxy']=='true'
            return httpx.Response(200,text=HTML,headers={'spb-resolved-url':URL})
        provider=ScrapingBeePages('secret-test',httpx.MockTransport(handle),max_requests=1)
        html,url=await provider.product(URL)
        rows=parse_ebay(html,True)
        assert len(rows)==1 and not rows[0].price_exact and rows[0].sold_at
        with pytest.raises(MarketplaceAccessError,match='six appels'):
            await provider.product(URL)
    asyncio.run(scenario())


@pytest.mark.parametrize('code,final,title',[(401,URL,''),(403,URL,''),(200,'https://signin.ebay.fr/signin','Sign in'),
    (200,'https://www.ebay.fr/sch/i.html','Pikachu'),(200,URL,'Just a moment...')])
def test_provider_does_not_turn_failure_into_empty_search(code,final,title):
    async def scenario():
        provider=ScrapingBeePages('test',httpx.MockTransport(lambda request:httpx.Response(code,
            text='<title>'+title+'</title>',headers={'spb-resolved-url':final})))
        with pytest.raises(MarketplaceAccessError):await provider.product(URL)
    asyncio.run(scenario())


def test_missing_key_sends_no_request():
    async def scenario():
        provider=ScrapingBeePages('')
        with pytest.raises(MarketplaceAccessError,match='clé API'):await provider.product(URL)
        assert provider.requests==0
    asyncio.run(scenario())


def test_local_reader_ignores_api_provider_configuration(monkeypatch):
    async def scenario():
        monkeypatch.setenv('DEALS_EBAY_PROVIDER','scrapingbee')
        pages=LocalOrBrowserPages()
        calls=[]
        async def product(url):calls.append(url);return HTML,url
        pages.fallback.product=product
        pages.remote=False
        assert (await pages.product(URL))[0]==HTML
        assert calls==[URL] and not hasattr(pages,'ebay_provider')
    asyncio.run(scenario())
