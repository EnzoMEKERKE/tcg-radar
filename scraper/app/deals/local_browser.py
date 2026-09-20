"""Connect the Docker collector to the user's dedicated local browser, when available."""
import os
import httpx
from .browser import BrowserPages, MarketplaceAccessError


def local_url():
    return os.getenv('DEALS_LOCAL_BROWSER_URL','').rstrip('/')


async def local_status():
    if not local_url(): return {'available':False}
    try:
        async with httpx.AsyncClient(timeout=3,trust_env=False) as client:
            response=await client.get(local_url()+'/status')
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError,ValueError):
        return {'available':False,'message':'Démarre tools/local_deals_browser.py sur ton ordinateur.'}


async def local_prepare(query):
    if not local_url(): return {'available':False}
    try:
        async with httpx.AsyncClient(timeout=5,trust_env=False) as client:
            response=await client.post(local_url()+'/prepare',json={'query':query},headers={'X-TCG-Local':'browser'})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError,ValueError):
        return {'available':False,'message':'Le navigateur local est indisponible. Démarre tools/local_deals_browser.py.'}


class LocalOrBrowserPages:
    def __init__(self):
        self.remote=None
        self.fallback=BrowserPages()

    async def product(self,url):
        if not BrowserPages.allowed_document(url):
            raise ValueError('Unsupported marketplace page')
        if self.remote is None:
            if local_url():
                state = await local_status()
                if not state.get('available'):
                    raise MarketplaceAccessError('unavailable','La session Chrome locale ne répond pas. Relance start-local-browser.ps1 puis ouvre la session Chrome locale. Analyse suspendue pour conserver ta session de connexion.')
                self.remote = True
            else:
                self.remote = False
        if not self.remote:
            return await self.fallback.product(url)
        async with httpx.AsyncClient(timeout=35,trust_env=False) as client:
            response=await client.post(local_url()+'/read',json={'url':url},headers={'X-TCG-Local':'browser'})
            if response.status_code>=500:
                raise MarketplaceAccessError('unavailable','Le service Chrome local a rencontré une erreur. Rouvre la session Chrome locale puis relance l’analyse.')
            response.raise_for_status()
            data=response.json()
        if data.get('status')!='ok':
            raise MarketplaceAccessError(data.get('status','unavailable'),data.get('message','Lecture locale indisponible.'))
        return data['html'],data['url']

    async def close(self):
        # Keep the dedicated local browser open for the next scan.
        await self.fallback.close()
