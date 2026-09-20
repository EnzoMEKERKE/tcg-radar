"""Read-only bounded live connector check. Writes local validation evidence."""
import asyncio
import json
import sys
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from app.main import collect
from app.services.catalog import Catalog


async def main():
    if '--inspect' in sys.argv:
        urls=['https://www.ultrajeux.com/type-469-4-boite-de-boosters-francais.html','https://ludotrotter.fr/categorie-produit/magasin/cartes/pokemon/boite-de-booster-pokemon/','https://www.destocktcg.fr/jeux-de-cartes-a-collectionner/pokemon/boite-de-boosters-pokemon/','https://www.nippontcg.fr']
        async with httpx.AsyncClient(timeout=25,follow_redirects=True) as client:
            for index,url in enumerate(urls):
                response=await client.get(url)
                Path(f'inspect-{index}.html').write_text(response.text,encoding='utf-8')
                soup=BeautifulSoup(response.text,'html.parser')
                links=[a for a in soup.select('a[href]') if ('display' in a.get_text().lower() or 'booster' in a.get_text().lower()) and ('produit' in a['href'] or 'product' in a['href'])]
                print(url,[(a.get('href'),a.get_text(' ',strip=True)[:80]) for a in links[:4]])
                if links:
                    page=await client.get(urljoin(url,links[0]['href']))
                    Path(f'product-{index}.html').write_text(page.text,encoding='utf-8')
        return
    catalogue=Catalog()
    await catalogue.refresh()
    if '--catalog-only' in sys.argv:
        print(json.dumps({'sources':catalogue.status,'sets':len(catalogue.entries)},ensure_ascii=True,indent=2))
        return
    items,reports=await collect(35,['UltraJeux','Ludotrotter','DestockTCG','Play-in','Nippon TCG','Japan TCG Direct'])
    result={'catalog':catalogue.status,'sets':len(catalogue.entries),'reports':reports,
            'offers':items}
    Path('live-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='offers'},ensure_ascii=True,indent=2))

asyncio.run(main())
