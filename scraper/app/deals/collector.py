"""Bounded, asynchronous collection; blocked sources are reported, not treated as empty."""
import asyncio
from urllib.parse import urlencode, urlsplit, urljoin
from bs4 import BeautifulSoup
import httpx
from .browser import BrowserPages, MarketplaceAccessError
from .local_browser import LocalOrBrowserPages
from .parsers import parse_ebay, parse_cardmarket, product_links
from .identity import identity


class Collector:
    def __init__(self, pages=None):
        self.pages = pages or LocalOrBrowserPages()
        self.reports = []
        self.rows = []
        self.requests = 0
        self.stopped_sources = set()
        self.product_count = 0

    async def read(self,url,source):
        if source in self.stopped_sources:
            self.reports.append({'source':source,'status':'blocked','message':'Collecte non lancée : accès déjà refusé par cette plateforme.','url':url})
            return None
        self.requests += 1
        try:
            async with asyncio.timeout(40):
                html, final = await self.pages.product(url)
            soup = BeautifulSoup(html,'html.parser')
            title = soup.title.get_text().lower() if soup.title else ''
            if any(word in title for word in ('attention required','access denied','robot','captcha','error page','security measure','just a moment')):
                self.stopped_sources.add(source)
                self.reports.append({'source':source,'status':'blocked','message':'La plateforme bloque la lecture automatique.','url':url})
                return None
            return html
        except MarketplaceAccessError as error:
            self.stopped_sources.add(source)
            self.reports.append({'source':source,'status':error.status,'message':str(error),'url':url})
        except httpx.HTTPStatusError as error:
            code = error.response.status_code
            if code in (401,403,429): self.stopped_sources.add(source)
            mode = ' dans le navigateur' if isinstance(self.pages,BrowserPages) else ''
            self.reports.append({'source':source,'status':'blocked' if code in (401,403,429) else 'error','message':f'Lecture refusée ou indisponible{mode} (HTTP {code}).','url':url})
        except (ValueError,TimeoutError,OSError,httpx.HTTPError) as error:
            self.stopped_sources.add(source)
            message = 'Lecture de cette page refusée par robots.txt.' if str(error)=='Path disallowed' else 'Connexion ou page indisponible.'
            if str(error)=='Browser verification required':
                message = 'Le navigateur est arrêté sur une vérification demandée par la plateforme.'
            self.reports.append({'source':source,'status':'unavailable','message':message,'url':url})
        return None

    async def ebay(self,query,settings,sold):
        source = 'ebay_sold' if sold else 'ebay_active'
        seen = set()
        count = 0
        for page in range(1,settings.pages+1):
            params = {'_nkw':query or 'pokemon carte','_sacat':'183454','_ipg':60,'_pgn':page}
            params.update({'LH_Sold':1,'LH_Complete':1} if sold else {'LH_BIN':1,'_sop':15})
            url = 'https://www.ebay.fr/sch/i.html?'+urlencode(params)
            html = await self.read(url,source)
            if html is None: break
            rows = parse_ebay(html,sold)
            fresh = [r for r in rows if r.url not in seen]
            for row in fresh: seen.add(row.url)
            self.rows.extend(fresh)
            count += len(fresh)
            if not fresh: break
            await asyncio.sleep(0.4)
        if count or not any(r['source']==source for r in self.reports):
            self.reports.append({'source':source,'status':'ok' if count else 'no_verified_rows','count':count,
                                 'message':f'{count} ventes datées lues.' if sold and count else f'{count} annonces exploitables lues.'})

    async def cardmarket(self,query,settings):
        base = 'https://www.cardmarket.com/fr/Pokemon'
        url = base+'/Products/Search?'+urlencode({'searchString':query}) if query else base+'/Products/Singles?sortBy=popularity&sortDir=desc'
        html = await self.read(url,'cardmarket')
        if html is None: return
        links = product_links(html,url)[:max(0,settings.max_cards-self.product_count)]
        count = 0
        for link in links:
            self.product_count += 1
            visited = set()
            for _ in range(settings.pages):
                if link in visited: break
                visited.add(link)
                html = await self.read(link,'cardmarket')
                if html is None: break
                rows = parse_cardmarket(html,link)
                self.rows.extend(rows)
                count += len(rows)
                soup = BeautifulSoup(html,'html.parser')
                following = soup.select_one('a[rel="next"]')
                if not following: break
                target = urljoin(link,following.get('href',''))
                if urlsplit(target).hostname != 'www.cardmarket.com' or urlsplit(target).path != urlsplit(link).path: break
                link = target
                await asyncio.sleep(0.4)
        self.reports.append({'source':'cardmarket','status':'ok' if count else 'no_verified_rows','count':count,'message':f'{count} offres de vendeurs lues sur {len(links)} fiches.'})

    async def collect(self,settings):
        # First discover SOLD cards, then look for the same card on the other market.
        await self.ebay(settings.query,settings,True)
        await self.ebay(settings.query,settings,False)
        if settings.query:
            await self.cardmarket(settings.query,settings)
        else:
            seeds = {}
            for row in self.rows:
                key,_ = identity(row)
                if key:
                    seeds.setdefault(key[:4], key[0]+' '+key[1])
            if seeds:
                for query in list(seeds.values())[:settings.max_cards]:
                    if self.product_count >= settings.max_cards: break
                    await self.cardmarket(query,settings)
                    if 'cardmarket' in self.stopped_sources: break
            else:
                await self.cardmarket('',settings)
        return self.rows

    async def close(self):
        close = getattr(self.pages,'close',None)
        if close:
            await close()
