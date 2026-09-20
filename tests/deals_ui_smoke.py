"""Isolated browser fixtures, never stored in the production deals cache."""
import json
import sys
import threading
from datetime import datetime, timezone, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scraper'))
from app.deals.models import Listing, Settings
from app.deals.analyzer import analyze

preview=ROOT/'.validation/preview'
for name in ['v5.js','v5.css','ui.css','deals.js','deals.css','deals-template.csv']:
    (preview/name).write_bytes((ROOT/'app/public'/name).read_bytes())
server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(preview)))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
now=datetime.now(timezone.utc)
rows=[Listing(source='cardmarket',title='Pikachu 25/102 holo FR NM',url='https://www.cardmarket.com/fr/Pokemon/Products/Singles/Base-Set/Pikachu',price=50,shipping=2,language='FR',condition='NM',seller='Fixture',provenance='imported')]
rows += [Listing(source='ebay',title='Pikachu 25/102 holo FR NM',url=f'https://www.ebay.fr/itm/{100000000000+i}',price=price,language='FR',condition='NM',sold=True,sold_at=now-timedelta(days=i+1),provenance='imported') for i,price in enumerate([100,110,120])]
result=dict(analyze(rows,Settings()),id='a'*32,status='complete',message='Analyse de contrôle.',reports=[{'source':'import','status':'ok','message':'4 observations importées.'}])
errors=[]
calls=[]
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1100})
    page.on('pageerror',lambda e:errors.append(str(e)))
    def api(route):
        url=route.request.url
        if url.endswith('/api/deals/browser'):
            data={'available':True,'pages':[{'source':'ebay_sold','status':'login_required','items':0}]}
        elif url.endswith('/api/deals/search'):
            calls.append(route.request.post_data_json)
            data={'id':'a'*32,'status':'running','message':'Analyse en cours…','deals':[]}
        elif '/api/deals/status/' in url:
            data=result
        elif url.endswith('/api/deals/import'):
            assert 'source,title' in route.request.post_data_json['csv']
            data=result
        else:
            data=[]
        route.fulfill(content_type='application/json',body=json.dumps(data))
    page.route('**/api/**',api)
    page.goto(base+'/deals.html')
    page.wait_for_function("document.querySelector('#local-browser-status').textContent.includes('connecte-toi')")
    page.get_by_role('button',name='Ouvrir la session Chrome locale').click()
    page.get_by_role('button',name='Analyser les bonnes affaires',exact=True).click()
    page.wait_for_selector('.deal-profit',timeout=10000)
    assert calls[0]['language']=='FR' and calls[0]['min_sales']==3
    assert '35,06' in page.locator('.deal-profit').inner_text()
    page.get_by_text('Calcul de la marge et références').click()
    assert page.locator('.deal-evidence a').count()==3
    assert 'import utilisateur' in page.locator('#deals-list').inner_text()
    page.screenshot(path=str(ROOT/'.validation/deals-desktop.png'),full_page=True)
    page.reload()
    page.wait_for_selector('.deal-profit')
    page.locator('#deals-file').set_input_files({'name':'releves.csv','mimeType':'text/csv','buffer':b'source,title\nebay,test'})
    page.get_by_role('button',name='Importer et analyser avec les filtres ci-dessus').click()
    page.wait_for_selector('.deal-profit')
    blocked={'id':'a'*32,'status':'unavailable','message':'Collecte incomplète.','reports':[{'source':'cardmarket','status':'verification_required','message':'Vérification requise.','url':'https://www.cardmarket.com/fr/Pokemon/Products/Search?searchString=Pikachu'}],'deals':[],'excluded':{}}
    result.clear();result.update(blocked)
    page.reload()
    page.wait_for_selector('.deal-source.issue')
    assert page.get_by_role('link',name='Ouvrir cette recherche dans mon navigateur').get_attribute('href').startswith('https://www.cardmarket.com/')
    assert 'ne permettent pas de conclure' in page.locator('#deals-list').inner_text()
    assert not page.locator('.deal-profit').count()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(ROOT/'.validation/deals-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
server.shutdown()
print('PASS: integrated deals UI, async scan, margin evidence, persisted job, CSV import, blocked source, mobile layout; no JavaScript errors')
