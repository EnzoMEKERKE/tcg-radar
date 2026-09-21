"""Bounded, asynchronous collection; blocked sources are reported, not treated as empty."""
import asyncio
import random
import time
from urllib.parse import urlencode, urlsplit, urljoin, parse_qs, urlunsplit
from bs4 import BeautifulSoup
import httpx
from .browser import BrowserPages, MarketplaceAccessError
from .local_browser import LocalOrBrowserPages
from .parsers import parse_ebay, parse_cardmarket, product_links, cardmarket_next_page
from .identity import identity
from .discovery import card_search_name, sold_searches


class Collector:
    def __init__(self, pages=None):
        self.pages = pages or LocalOrBrowserPages()
        self.reports = []
        self.rows = []
        self.requests = 0
        self.stopped_sources = set()
        self.product_count = 0
        self.next_read_at = 0
        self.read_delay = 20 if pages is None else 0
        self.on_progress = None

    async def read(self,url,source):
        if source in self.stopped_sources:
            self.reports.append({'source':source,'status':'blocked','message':'Collecte non lancée : accès déjà refusé par cette plateforme.','url':url})
            return None
        self.requests += 1
        try:
            if self.on_progress:
                await self.on_progress(source)
            await asyncio.sleep(max(0,self.next_read_at-time.monotonic()))
            self.next_read_at = time.monotonic()+self.read_delay+random.uniform(0,self.read_delay*0.75)
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
            # An empty search is not proof that the whole marketplace is blocked.
            empty_search = (source=='cardmarket' and '/Products/Search?' in url and
                            error.status=='unavailable' and 'ne contient pas encore' in str(error))
            if not empty_search:
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
        links = []
        seen_search = set()
        search_url = url
        search_truncated = False
        for search_page in range(settings.pages):
            if search_url in seen_search or len(links) >= settings.max_cards-self.product_count:
                break
            seen_search.add(search_url)
            html = await self.read(search_url,'cardmarket')
            if html is None:
                if not links: return
                break
            found = product_links(html,search_url)
            for candidate in found:
                if candidate not in links:
                    links.append(candidate)
                if len(links) >= settings.max_cards-self.product_count:
                    break
            next_search = cardmarket_next_page(html,search_url)
            if not next_search and len(found) >= 30:
                parts = urlsplit(search_url)
                params = parse_qs(parts.query)
                try:
                    params['site'] = [str(int(params.get('site',['1'])[0])+1)]
                    next_search = urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(params,doseq=True),''))
                except ValueError:
                    pass
            if next_search and next_search not in seen_search:
                search_truncated = search_page == settings.pages-1 or len(links) >= settings.max_cards-self.product_count
            if not next_search or not found: break
            search_url = next_search
            await asyncio.sleep(0.4)
        count = 0
        truncated = search_truncated
        seen_offers = set()
        for link in links:
            self.product_count += 1
            visited = set()
            for _ in range(settings.pages):
                if link in visited: break
                visited.add(link)
                html = await self.read(link,'cardmarket')
                if html is None: break
                rows = parse_cardmarket(html,link)
                fresh = []
                for row in rows:
                    key = (urlsplit(row.url).path, row.listing_id or row.seller,
                           row.language, row.condition, row.variant, row.price)
                    if key not in seen_offers:
                        seen_offers.add(key)
                        fresh.append(row)
                rows = fresh
                self.rows.extend(rows)
                count += len(rows)
                target = cardmarket_next_page(html,link)
                if not target: break
                if _ == settings.pages-1:
                    truncated = True
                link = target
                await asyncio.sleep(0.4)
        self.reports.append({'source':'cardmarket','status':'partial' if truncated else 'ok' if count else 'no_verified_rows',
            'count':count,'shipping_count':sum(r.shipping is not None for r in self.rows if r.source=='cardmarket'),
            'message':f'{count} offres de vendeurs lues sur {len(links)} fiches.' +
                (' Il reste des pages : augmentez la limite de pages pour poursuivre la collecte.' if truncated else '')})

    async def collect(self,settings):
        # First discover SOLD cards, then look for the same card on the other market.
        ebay_query=settings.query
        if not ebay_query and settings.language!='ALL':
            words={'JP':'japonais','FR':'francais','EN':'english','DE':'deutsch','IT':'italiano','ES':'espanol','KR':'korean','CN':'chinese'}
            ebay_query='pokemon '+words[settings.language]
        await self.ebay(ebay_query,settings,True)
        await self.ebay(ebay_query,settings,False)
        if settings.query:
            await self.cardmarket(card_search_name(settings.query) or settings.query,settings)
        else:
            seeds = sold_searches(self.rows,settings.language)
            if seeds:
                for query in seeds[:settings.max_cards]:
                    if self.product_count >= settings.max_cards: break
                    await self.cardmarket(query,settings)
                    if 'cardmarket' in self.stopped_sources: break
            else:
                self.reports.append({'source':'cardmarket','status':'no_verified_rows','message':'Aucune vente avec une langue confirmée ne permet de choisir les cartes à rechercher sur Cardmarket.'})
        return self.rows

    async def close(self):
        close = getattr(self.pages,'close',None)
        if close:
            await close()
