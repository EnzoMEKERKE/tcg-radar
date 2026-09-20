import json,re,httpx
from bs4 import BeautifulSoup
from app.services.normalizer import normalize
class GenericConnector:
 def __init__(self,store): self.store=store
 async def crawl(self):
  out=[]
  async with httpx.AsyncClient(follow_redirects=True,timeout=20,headers={'User-Agent':'TCGRadar/1.0 (+price-comparison; respectful crawler)'}) as c:
   try:r=await c.get(self.store['url']); r.raise_for_status()
   except Exception:return out
  soup=BeautifulSoup(r.text,'html.parser')
  for s in soup.select('script[type="application/ld+json"]'):
   try:data=json.loads(s.string or '{}')
   except:continue
   nodes=data if isinstance(data,list) else [data]
   for n in nodes:
    if not isinstance(n,dict):continue
    if n.get('@type')=='Product':
     name=n.get('name',''); meta=normalize(name); offers=n.get('offers',{}); offers=offers[0] if isinstance(offers,list) and offers else offers
     if meta['game'] and meta['kind'] and isinstance(offers,dict): out.append({'store':self.store['name'],'title':name,'url':n.get('url') or self.store['url'],'price':offers.get('price'),'currency':offers.get('priceCurrency',self.store['currency']),'availability':offers.get('availability'),'meta':meta})
  return out
