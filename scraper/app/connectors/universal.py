import asyncio, json, re
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
from app.services.normalizer import normalize

UA='TCGRadar/5.0 (+price-comparison)'
PRODUCT_HINTS=('display','booster box','booster-box','box','pokemon','pokémon','one-piece','one piece','yu-gi','yugioh','gundam')

class UniversalConnector:
    def __init__(self, store, max_pages=250):
        self.store=store; self.base=store['url'].rstrip('/'); self.max_pages=max_pages
        self.headers={'User-Agent':UA,'Accept-Language':'fr-FR,fr;q=0.9,en;q=0.7'}

    async def crawl(self):
        async with httpx.AsyncClient(follow_redirects=True,timeout=25,headers=self.headers) as c:
            if not await self._allowed(c): return []
            # Fast paths first. Shopify public catalogue is dramatically cheaper than browser crawling.
            offers=await self._shopify(c)
            if offers: return self._dedupe(offers)
            urls=await self._discover_urls(c)
            sem=asyncio.Semaphore(8)
            async def one(u):
                async with sem: return await self._product_page(c,u)
            rows=await asyncio.gather(*(one(u) for u in urls[:self.max_pages]))
            return self._dedupe([x for group in rows for x in group])

    async def _allowed(self,c):
        try:
            r=await c.get(urljoin(self.base,'/robots.txt'))
            if r.status_code>=400:return True
            rp=RobotFileParser(); rp.set_url(urljoin(self.base,'/robots.txt')); rp.parse(r.text.splitlines())
            return rp.can_fetch(UA,self.base+'/')
        except Exception:return True

    async def _shopify(self,c):
        out=[]
        for page in range(1,41): # <=10k products; hard safety bound
            try:r=await c.get(f'{self.base}/products.json',params={'limit':250,'page':page})
            except Exception:return []
            if r.status_code!=200 or 'json' not in r.headers.get('content-type',''): return [] if page==1 else out
            try: products=r.json().get('products',[])
            except Exception:return [] if page==1 else out
            if not products: break
            for p in products:
                title=p.get('title',''); meta=normalize(title)
                if not (meta.get('game') and meta.get('kind')): continue
                variants=p.get('variants') or []
                available=[v for v in variants if v.get('available',True)] or variants
                prices=[]
                for v in available:
                    try: prices.append(float(v.get('price')))
                    except: pass
                if not prices: continue
                handle=p.get('handle','')
                out.append(self._offer(title,urljoin(self.base,f'/products/{handle}'),min(prices),self.store.get('currency','EUR'),any(v.get('available',True) for v in variants),meta,'shopify'))
        return out

    async def _discover_urls(self,c):
        found=[]; seen=set(); queue=[urljoin(self.base,'/sitemap.xml'),urljoin(self.base,'/sitemap_index.xml'),urljoin(self.base,'/wp-sitemap.xml')]
        while queue and len(found)<self.max_pages:
            u=queue.pop(0)
            if u in seen:continue
            seen.add(u)
            try:r=await c.get(u)
            except:continue
            if r.status_code!=200:continue
            soup=BeautifulSoup(r.text,'xml')
            locs=[x.get_text(strip=True) for x in soup.find_all('loc')]
            for loc in locs:
                low=loc.lower()
                if ('sitemap' in low and low.endswith(('.xml','.xml.gz'))) and len(seen)+len(queue)<80: queue.append(loc)
                elif any(h in low for h in PRODUCT_HINTS) or '/product/' in low or '/produit/' in low or '/products/' in low:
                    if urlparse(loc).netloc==urlparse(self.base).netloc: found.append(loc)
        if found:return list(dict.fromkeys(found))[:self.max_pages]
        # Fallback: homepage/category links only; no uncontrolled recursive spidering.
        try:r=await c.get(self.base)
        except:return []
        soup=BeautifulSoup(r.text,'html.parser')
        for a in soup.select('a[href]'):
            u=urljoin(self.base,a['href']); low=(u+' '+a.get_text(' ',strip=True)).lower()
            if urlparse(u).netloc==urlparse(self.base).netloc and any(h in low for h in PRODUCT_HINTS):found.append(u)
        return list(dict.fromkeys(found))[:self.max_pages]

    async def _product_page(self,c,url):
        try:r=await c.get(url)
        except:return []
        if r.status_code!=200:return []
        soup=BeautifulSoup(r.text,'html.parser'); out=[]
        for s in soup.select('script[type="application/ld+json"]'):
            try:data=json.loads(s.string or '{}')
            except:continue
            stack=data if isinstance(data,list) else [data]
            while stack:
                n=stack.pop()
                if isinstance(n,dict) and '@graph' in n: stack.extend(n['@graph']); continue
                if not isinstance(n,dict) or n.get('@type')!='Product':continue
                title=n.get('name',''); meta=normalize(title)
                if not (meta.get('game') and meta.get('kind')):continue
                offers=n.get('offers',{}); offers=offers if isinstance(offers,list) else [offers]
                for o in offers:
                    if not isinstance(o,dict):continue
                    price=o.get('price') or o.get('lowPrice')
                    try:price=float(str(price).replace(',','.'))
                    except:continue
                    avail=str(o.get('availability','')).lower(); in_stock=not any(x in avail for x in ('outofstock','soldout','discontinued'))
                    out.append(self._offer(title,n.get('url') or url,price,o.get('priceCurrency',self.store.get('currency','EUR')),in_stock,meta,'jsonld'))
        return out

    def _offer(self,title,url,price,currency,in_stock,meta,source):
        return {'store':self.store['name'],'store_country':self.store.get('country'),'title':title,'url':url,'price':price,'currency':currency,'in_stock':in_stock,'meta':meta,'source':source}
    def _dedupe(self,rows):
        d={}
        for x in rows:
            k=(x.get('url'),x.get('price'),x.get('currency')); d[k]=x
        return list(d.values())
