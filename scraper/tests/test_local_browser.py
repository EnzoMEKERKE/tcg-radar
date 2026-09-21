import asyncio
import importlib.util
from pathlib import Path
import pytest
import httpx
from fastapi.testclient import TestClient
from app.deals.browser import MarketplaceAccessError
from app.deals.local_browser import LocalOrBrowserPages
from app.deals.parsers import parse_ebay

spec=importlib.util.spec_from_file_location('local_deals_helper',Path(__file__).resolve().parents[2]/'tools/local_deals_browser.py')
helper=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class TargetClosedError(Exception): pass


def test_cardmarket_pagination_survives_sanitization_without_account_data():
    fragment=helper.public_fragment('<form><input value="secret"></form><a rel="next" href="?site=2">Next</a>')
    assert '?site=2' in fragment and 'secret' not in fragment


class FakePage:
    def __init__(self): self.closed=False;self.url='about:blank';self.visited=[];self.foreground=False
    def is_closed(self):return self.closed
    async def title(self):return 'Pikachu'
    async def goto(self,url,**kwargs):self.url=url;self.visited.append(url)
    async def wait_for_timeout(self,ms):pass
    async def bring_to_front(self):self.foreground=True


class FakeContext:
    def __init__(self):self.closed=False;self.listeners={};self.created=[];self.window_commands=[]
    def on(self,event,callback):self.listeners[event]=callback
    async def new_page(self):
        if self.closed:raise TargetClosedError('Closed')
        page=FakePage();self.created.append(page);return page
    async def new_cdp_session(self,page):
        context=self
        class Session:
            async def send(self,method,params=None):
                context.window_commands.append((method,params))
                return {'windowId':42}
            async def detach(self):pass
        return Session()
    def shut(self,notify=True):
        self.closed=True
        for page in self.created:page.closed=True
        if notify and 'close' in self.listeners:self.listeners['close']()


class FakeSession:
    def __init__(self,**kwargs):self.options=kwargs;self.context=FakeContext()
    async def start(self):pass
    async def close(self):self.context.shut()


@pytest.mark.parametrize('notify',[True,False])
def test_closed_browser_restarts_with_same_profile(monkeypatch,tmp_path,notify):
    monkeypatch.setattr(helper,'ROOT',tmp_path)
    sessions=[]
    def factory(**kwargs):
        session=FakeSession(**kwargs);sessions.append(session);return session
    async def run():
        browser=helper.LocalBrowser(factory)
        url='https://www.ebay.fr/sch/i.html?_nkw=Pikachu'
        first=await browser.open(url)
        sessions[0].context.shut(notify)
        second=await browser.open(url)
        assert second is not first and second.visited==[url]
        assert len(sessions)==2
        assert sessions[0].options['user_data_dir']==sessions[1].options['user_data_dir']
        assert not browser.closed
        await browser.reset()
        assert (await browser.status())['browser_open'] is False
    asyncio.run(run())


def test_closed_single_tab_reloads_same_search(monkeypatch,tmp_path):
    monkeypatch.setattr(helper,'ROOT',tmp_path)
    async def run():
        browser=helper.LocalBrowser(FakeSession)
        url='https://www.ebay.fr/sch/i.html?_nkw=Pikachu'
        first=await browser.open(url)
        session=browser.session
        first.closed=True
        second=await browser.open(url)
        assert browser.session is session and second.visited==[url]
        await browser.reset()
    asyncio.run(run())


def test_prepare_recovers_blank_tab_and_restores_cardmarket_window(monkeypatch,tmp_path):
    monkeypatch.setattr(helper,'ROOT',tmp_path)
    async def run():
        browser=helper.LocalBrowser(FakeSession)
        url='https://www.cardmarket.com/fr/Pokemon/Products/Search?searchString=Pikachu'
        page=await browser.open(url)
        page.url='chrome-error://chromewebdata/'
        await browser.prepare('Pikachu')
        assert page.visited==[url,url] and page.foreground
        assert list(browser.pages)==['cardmarket']
        assert ('Browser.setWindowBounds',{'windowId':42,'bounds':{'windowState':'normal'}}) in browser.session.context.window_commands
        await browser.reset()
    asyncio.run(run())


def test_navigation_error_is_reported_and_can_be_retried(monkeypatch,tmp_path):
    monkeypatch.setattr(helper,'ROOT',tmp_path)
    async def run():
        browser=helper.LocalBrowser(FakeSession)
        url='https://www.cardmarket.com/fr/Pokemon/Products/Search?searchString=Pikachu'
        page=await browser.open(url)
        async def fail(*args,**kwargs):
            page.url='about:blank'
            raise RuntimeError('net::ERR_FAILED')
        monkeypatch.setattr(page,'goto',fail)
        browser.preparing=asyncio.create_task(browser.open(url,force=True))
        with pytest.raises(helper.BrowserNavigationError):await browser.preparing
        assert 'charger' in (await browser.status())['error']
        monkeypatch.setattr(page,'goto',FakePage.goto.__get__(page))
        await browser.prepare('Pikachu')
        assert page.url==url
        await browser.reset()
    asyncio.run(run())


def test_french_challenge_is_not_reloaded_by_scan(monkeypatch,tmp_path):
    monkeypatch.setattr(helper,'ROOT',tmp_path)
    async def run():
        browser=helper.LocalBrowser(FakeSession)
        url='https://www.cardmarket.com/fr/Pokemon/Products/Search?searchString=Pikachu'
        page=await browser.open(url)
        async def title():return 'Un instant…'
        monkeypatch.setattr(page,'title',title)
        await browser.open(url,force=True)
        assert page.visited==[url]
        assert helper.access_gate(url,await page.title()).status=='verification_required'
        await browser.reset()
    asyncio.run(run())


def test_manual_login_keeps_profile_and_blocks_automation_until_closed(monkeypatch,tmp_path):
    monkeypatch.setattr(helper,'ROOT',tmp_path)
    monkeypatch.setenv('ProgramFiles',str(tmp_path))
    chrome=tmp_path/'Google/Chrome/Application/chrome.exe'
    chrome.parent.mkdir(parents=True)
    chrome.touch()
    calls=[]
    class Process:
        exited=False
        def poll(self):return 0 if self.exited else None
    process=Process()
    def launch(args,**kwargs):calls.append(args);return process
    monkeypatch.setattr(helper.subprocess,'Popen',launch)
    async def run():
        browser=helper.LocalBrowser(FakeSession)
        url='https://www.cardmarket.com/fr/Pokemon/Products/Search'
        page=await browser.open(url)
        profile=browser.session.options['user_data_dir']
        await browser.prepare('Pikachu',manual=True)
        assert page.closed
        assert '--user-data-dir='+profile in calls[0]
        assert (await browser.status())['mode']=='manual'
        with pytest.raises(helper.BrowserNavigationError,match='manuelle'):
            await browser.open(url)
        await browser.prepare('Pikachu',manual=True)
        assert len(calls)==1
        process.exited=True
        await browser.open(url)
        assert browser.session.options['user_data_dir']==profile
        await browser.reset()
    asyncio.run(run())


@pytest.mark.parametrize('error',[TargetClosedError('Closed'),RuntimeError('Launch failed')])
def test_read_failure_returns_recovery_message_not_http_500(monkeypatch,error):
    browser=helper.LocalBrowser(FakeSession)
    async def fail(url,**kwargs):raise error
    monkeypatch.setattr(browser,'open',fail)
    monkeypatch.setattr(helper,'browser',browser)
    with TestClient(helper.app,base_url='http://localhost') as client:
        result=client.post('/read',json={'url':'https://www.ebay.fr/sch/i.html'},headers={'X-TCG-Local':'browser'})
        assert result.status_code==200 and result.json()['status']=='unavailable'
        assert 'Chrome' in result.json()['message']


def test_only_listing_fragments_leave_local_browser():
    html='''<header>Private account name <input value="SECRET"></header><script>token="PRIVATE_TOKEN"</script>
    <li class="s-card"><h3 class="s-card__title">Pikachu 25/102 holo FR NM</h3><a class="s-card__link" href="https://www.ebay.fr/itm/123456789012">Offer</a><span class="s-card__price">50 EUR</span><button data-token="SECRET">Buy</button><script>cookie="SECRET"</script></li>'''
    fragment=helper.public_fragment(html)
    assert all(value not in fragment for value in ['SECRET','PRIVATE_TOKEN','Private account name','<script','<input','<button'])
    rows=parse_ebay(fragment)
    assert len(rows)==1 and rows[0].price==50


def test_local_helper_rejects_cross_site_mutations_and_arbitrary_urls():
    with TestClient(helper.app,base_url='http://localhost') as client:
        assert client.post('/prepare',json={}).status_code==403
        assert client.post('/read',json={'url':'https://evil.example/'},headers={'X-TCG-Local':'browser'}).status_code==400
        assert client.get('/status').json()['available'] is True
        assert client.get('/status',headers={'Host':'evil.example'}).status_code==403


def test_local_reader_keeps_login_required_instead_of_using_anonymous_fallback(monkeypatch):
    async def status():return {'available':True}
    monkeypatch.setattr('app.deals.local_browser.local_status',status)
    monkeypatch.setenv('DEALS_LOCAL_BROWSER_URL','http://localhost:8766')
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'login_required','message':'Connecte-toi dans Chrome.'}))
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=transport,**kwargs))
    async def run():
        reader=LocalOrBrowserPages()
        with pytest.raises(MarketplaceAccessError) as error:
            await reader.product('https://www.ebay.fr/sch/i.html?_nkw=Pikachu')
        assert error.value.status=='login_required'
        assert reader.fallback.driver is None
        await reader.close()
    asyncio.run(run())


def test_local_reader_returns_only_verified_page_payload(monkeypatch):
    async def status():return {'available':True}
    monkeypatch.setattr('app.deals.local_browser.local_status',status)
    monkeypatch.setenv('DEALS_LOCAL_BROWSER_URL','http://localhost:8766')
    url='https://www.ebay.fr/sch/i.html?_nkw=Pikachu'
    original=httpx.AsyncClient
    transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'ok','html':'<h1>Pikachu</h1>','url':url}))
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=transport,**kwargs))
    async def run():
        assert await LocalOrBrowserPages().product(url)==('<h1>Pikachu</h1>',url)
    asyncio.run(run())


def test_unavailable_configured_browser_does_not_switch_session(monkeypatch):
    async def status(): return {'available':False}
    monkeypatch.setattr('app.deals.local_browser.local_status',status)
    monkeypatch.setenv('DEALS_LOCAL_BROWSER_URL','http://localhost:8766')
    async def run():
        reader=LocalOrBrowserPages()
        with pytest.raises(MarketplaceAccessError,match='session Chrome locale'):
            await reader.product('https://www.ebay.fr/sch/i.html?_nkw=Pikachu')
        assert reader.fallback.driver is None and reader.remote is None
    asyncio.run(run())


@pytest.mark.parametrize('url',[
    'https://signin.ebay.fr/ws/eBayISAPI.dll?SignIn',
    'https://www.ebay.fr/splashui/challenge',
    'https://www.cardmarket.com/fr/Login',
])
def test_prepare_preserves_manual_login_and_challenge(monkeypatch,tmp_path,url):
    monkeypatch.setattr(helper,'ROOT',tmp_path)
    async def run():
        browser=helper.LocalBrowser(FakeSession)
        search='https://www.cardmarket.com/fr/Pokemon/Products/Search' if 'cardmarket' in url else 'https://www.ebay.fr/sch/i.html'
        page=await browser.open(search)
        page.url=url
        await browser.open(search+'?query=changed',force=True)
        await browser.prepare('Pikachu')
        assert page.url==url and page.visited==[search]
        await browser.reset()
    asyncio.run(run())


def test_status_remains_available_when_browser_is_unresponsive():
    async def run():
        browser=helper.LocalBrowser(FakeSession)
        page=FakePage()
        async def stuck(): await asyncio.Event().wait()
        page.title=stuck
        browser.pages={'ebay_sold':page,'ebay_active':page,'cardmarket':page}
        result=await asyncio.wait_for(browser.status(),2.5)
        assert result['available'] and len(result['pages'])==3
        assert all(row['status']=='waiting' for row in result['pages'])
    asyncio.run(run())


def test_read_refreshes_page_and_rejects_removed_sold_filter(monkeypatch):
    async def run():
        page=FakePage()
        page.url='https://www.ebay.fr/sch/i.html?_nkw=Pikachu'
        calls=[]
        async def open_page(url,force=False):calls.append(force);return page
        monkeypatch.setattr(helper.browser,'open',open_page)
        result=await helper.read_page(helper.ReadRequest(url=page.url+'&LH_Sold=1&LH_Complete=1'))
        assert calls==[True] and result['status']=='unavailable'
    asyncio.run(run())
