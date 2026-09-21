"""Visible, persistent marketplace browser. Passwords/cookies never leave this process.

Run from the project root: python tools/local_deals_browser.py
Only sanitized product/search fragments are sent to the local collector.
"""
import asyncio
from contextlib import asynccontextmanager
from copy import copy
from pathlib import Path
import os
import subprocess
import sys
from urllib.parse import urlsplit, parse_qs, urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scraper'))
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
import uvicorn
from app.deals.browser import BrowserPages, access_gate


def public_fragment(html):
    soup = BeautifulSoup(html,'html.parser')
    output = BeautifulSoup('<html><body></body></html>','html.parser')
    selectors = '.s-item, .s-card, .article-row, h1, .info-list-container, dl, a[href*="/Products/Singles/"], a[rel="next"], .pagination'
    containers = {id(node) for node in soup.select('.s-item, .s-card, .article-row, .pagination')}
    for original in soup.select(selectors):
        if any(id(parent) in containers for parent in original.parents):
            continue
        node = copy(original)
        for private in node.select('script,style,form,input,button,iframe,svg'):
            private.decompose()
        for element in [node]+list(node.find_all(True)):
            element.attrs = {k:v for k,v in element.attrs.items() if k in ('class','id','href','rel','title','aria-label','aria-current','data-original-title','data-bs-original-title')}
            href = element.get('href')
            if href and not ((element.get('rel') == ['next'] or 'pagination' in node.get('class',[])) and href.startswith('?')) and not any(part in href for part in ('/itm/','/Products/','/Users/','/usr/')):
                element.attrs.pop('href',None)
        output.body.append(node)
    return str(output)


class ReadRequest(BaseModel):
    url: str = Field(max_length=3000)


class PrepareRequest(BaseModel):
    query: str = Field(default='Pikachu',max_length=120)
    manual: bool = False


class BrowserNavigationError(RuntimeError):
    pass


class LocalBrowser:
    def __init__(self, session_factory=None):
        self.session = None
        self.session_factory = session_factory
        self.closed = True
        self.pages = {}
        self.targets = {}
        self.lock = asyncio.Lock()
        self.preparing = None
        self.manual_process = None

    def manual_running(self):
        return self.manual_process is not None and self.manual_process.poll() is None

    async def start(self):
        if self.manual_running():
            raise BrowserNavigationError('Connexion manuelle en cours. Fermez cette fenêtre Chrome après la connexion, puis relancez l’analyse.')
        if self.session and not self.closed: return
        await self.reset()
        factory = self.session_factory
        if factory is None:
            from scrapling.fetchers import AsyncStealthySession
            factory = AsyncStealthySession
        profile = ROOT/'.local-browser/profile'
        profile.mkdir(parents=True,exist_ok=True)
        self.session = factory(headless=False,real_chrome=True,user_data_dir=str(profile),
            google_search=False,solve_cloudflare=False,locale='fr-FR',timeout=25000)
        try:
            await self.session.start()
            current = self.session
            self.closed = False
            def on_close(*args):
                if self.session is current:
                    self.closed = True
            self.session.context.on('close',on_close)
        except Exception:
            await self.reset()
            raise

    async def reset(self):
        previous,self.session = self.session,None
        self.closed = True
        self.pages.clear()
        self.targets.clear()
        if previous:
            try:
                async with asyncio.timeout(5):
                    await previous.close()
            except Exception:
                pass

    def source(self,url):
        parsed = urlsplit(url)
        return 'cardmarket' if parsed.hostname=='www.cardmarket.com' else 'ebay_sold' if parse_qs(parsed.query).get('LH_Sold')==['1'] else 'ebay_active'

    async def open(self,url,force=False):
        if not BrowserPages.allowed_document(url) or urlsplit(url).path in ('/','/splashui/challenge'):
            raise HTTPException(400,'Page de recherche ou de produit non autorisée.')
        # Handle both a recorded context-close event and a closure racing new_page().
        for attempt in range(2):
            try:
                return await self._open(url,force)
            except Exception as error:
                if not is_closed_error(error) or attempt:
                    raise
                await self.reset()

    async def _open(self,url,force=False):
        await self.start()
        source = self.source(url)
        page = self.pages.get(source)
        if page is None or page.is_closed():
            page = await self.session.context.new_page()
            self.pages[source] = page
            force = True
        elif page.url.startswith(('about:', 'chrome-error:')):
            force = True
        elif access_gate(page.url,await page.title()) or not BrowserPages.allowed_document(page.url):
            # Leave the tab untouched while the user signs in / handles a verification.
            return page
        if force or self.targets.get(source)!=url:
            self.targets[source]=url
            try:
                await page.goto(url,wait_until='domcontentloaded',timeout=25000)
                await page.wait_for_timeout(2000)
            except Exception as error:
                if is_closed_error(error):
                    raise
                if not access_gate(page.url,await page.title()):
                    self.targets.pop(source,None)
                    raise BrowserNavigationError('Chrome n’a pas pu charger la page. Vérifiez la connexion Internet puis réessayez.') from error
        return page

    async def prepare(self,query,manual=False):
        async with self.lock:
            if self.manual_running():
                return
            if manual:
                candidates = [Path(os.environ.get(name,''))/'Google/Chrome/Application/chrome.exe'
                              for name in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA') if os.environ.get(name)]
                chrome = next((path for path in candidates if path.is_file()),None)
                if chrome is None:
                    raise BrowserNavigationError('Google Chrome est introuvable sur cet ordinateur.')
                await self.reset()
                profile = ROOT/'.local-browser/profile'
                profile.mkdir(parents=True,exist_ok=True)
                self.manual_process = subprocess.Popen([str(chrome),'--user-data-dir='+str(profile),
                    '--no-first-run','--new-window','https://www.cardmarket.com/fr/Pokemon'],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                return
            word = query or 'Pikachu'
            url = 'https://www.cardmarket.com/fr/Pokemon/Products/Search?'+urlencode({'searchString':word})
            page = await self.open(url)
            await page.bring_to_front()
            # Selecting a tab alone does not restore a minimized Chrome window.
            cdp = await self.session.context.new_cdp_session(page)
            try:
                window = await cdp.send('Browser.getWindowForTarget')
                await cdp.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'normal'}})
            finally:
                await cdp.detach()

    async def status(self):
        rows=[]
        for source,page in list(self.pages.items()):
            if page.is_closed(): continue
            try:
                async with asyncio.timeout(0.5):
                    gate=access_gate(page.url,await page.title())
                    count=await page.locator('.s-item,.s-card,.article-row,a[href*="/Products/Singles/"]').count()
                rows.append({'source':source,'status':gate.status if gate else 'ready' if count else 'waiting','items':count})
            except Exception:
                rows.append({'source':source,'status':'waiting','items':0})
        error = None
        if self.preparing and self.preparing.done() and not self.preparing.cancelled() and self.preparing.exception():
            failure = self.preparing.exception()
            error = str(failure) if isinstance(failure,BrowserNavigationError) else 'Impossible d’ouvrir Chrome. Relancez le service local puis réessayez.'
        manual = self.manual_running()
        return {'available':True,'browser_open':manual or bool(self.session and not self.closed),'preparing':bool(self.preparing and not self.preparing.done()),'pages':rows,'error':error,
                'mode':'manual' if manual else 'collector',
                'message':'Chrome manuel ouvert. Terminez la connexion à Cardmarket, puis fermez cette fenêtre avant de relancer l’analyse.' if manual else None}


def is_closed_error(error):
    return type(error).__name__=='TargetClosedError' or 'Target page, context or browser has been closed' in str(error)


browser=LocalBrowser()


@asynccontextmanager
async def lifespan(app):
    yield
    if browser.preparing and not browser.preparing.done():
        browser.preparing.cancel()
        await asyncio.gather(browser.preparing,return_exceptions=True)
    await browser.reset()


app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)


@app.middleware('http')
async def local_only(request: Request,call_next):
    from fastapi.responses import JSONResponse
    if request.url.hostname not in ('127.0.0.1','localhost','host.docker.internal'):
        return JSONResponse({'detail':'Local requests only'},status_code=403)
    if request.method!='GET' and request.headers.get('X-TCG-Local')!='browser':
        return JSONResponse({'detail':'Local collector header required'},status_code=403)
    return await call_next(request)


@app.get('/status')
async def status():
    return await browser.status()


@app.post('/prepare')
async def prepare(data: PrepareRequest):
    if not browser.preparing or browser.preparing.done():
        browser.preparing=asyncio.create_task(browser.prepare(data.query,manual=data.manual))
    return await browser.status()


@app.post('/read')
async def read(data: ReadRequest):
    async with browser.lock:
        try:
            return await read_page(data)
        except HTTPException:
            raise
        except BrowserNavigationError as error:
            return {'status':'unavailable','message':str(error)}
        except Exception as error:
            if is_closed_error(error):
                await browser.reset()
                return {'status':'unavailable','message':'Chrome a été fermé pendant la lecture. Relance l’analyse pour le rouvrir avec ton profil conservé.'}
            return {'status':'unavailable','message':'Impossible de lire la page dans Chrome local. Clique sur « Ouvrir la session Chrome locale », puis réessaie.'}


async def read_page(data):
    page=await browser.open(data.url,force=True)
    gate=access_gate(page.url,await page.title())
    if gate:
        return {'status':gate.status,'message':str(gate)+' Termine cette étape dans la fenêtre Chrome dédiée, puis relance l’analyse. Si elle tourne en boucle, utilise ton navigateur habituel pour consulter le site ; sa connexion ne sera pas transmise au collecteur. Tu peux importer tes relevés CSV.'}
    if not BrowserPages.allowed_document(page.url):
        return {'status':'verification_required','message':'Reviens sur la fiche ou les résultats dans la fenêtre Chrome dédiée.'}
    requested,actual=urlsplit(data.url),urlsplit(page.url)
    original_params,actual_params=parse_qs(requested.query),parse_qs(actual.query)
    keys=('_nkw','LH_Sold','LH_Complete','_pgn') if requested.hostname=='www.ebay.fr' else ('searchString','site')
    if requested.hostname!=actual.hostname or requested.path!=actual.path or any(
            original_params.get(key,['1'] if key=='_pgn' else []) != actual_params.get(key,['1'] if key=='_pgn' else []) for key in keys):
        return {'status':'unavailable','message':'La page affichée ne correspond pas à la recherche demandée. Relance l’analyse après la connexion.'}
    if not await page.locator('.s-item,.s-card,.article-row,a[href*="/Products/Singles/"]').count():
        return {'status':'unavailable','message':'La page locale ne contient pas encore d’offres. Vérifie l’onglet Chrome dédié.'}
    html=public_fragment(await page.content())
    return {'status':'ok','html':html,'url':page.url}


if __name__=='__main__':
    asyncio.run(uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8766,log_level='warning')).serve())
