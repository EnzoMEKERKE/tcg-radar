"""Browser validation against real Twig output exported by the PHP integration test."""
import json
import threading
from datetime import date,timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
preview=ROOT/'.validation/preview'
for name in ['v5.js','v5.css','ui.css']:
    (preview/name).write_bytes((ROOT/'app/public'/name).read_bytes())
server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(preview)))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
errors=[]
catalog_calls=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda error:errors.append(str(error)))
    def api(route):
        if '/api/catalog' in route.request.url:
            catalog_calls.append(route.request.method)
            sets=[{'id':990,'game':'Gundam','language':'EN','code':'GD-01','name':'Newtype Rising','offers':0},
                  {'id':991,'game':'Gundam','language':'JP','code':'GD-01','name':'Newtype Rising','offers':0}]
            if len(catalog_calls)>1:
                sets.append({'id':992,'game':'Gundam','language':'EN','code':'GD-02','name':'Dual Impact','offers':0})
            data={'sets':sets,'status':{'refreshing':False,'last_checked':1789761092,'new_sets':0}}
        elif '/discover' in route.request.url:
            assert route.request.post_data_json['keywords']=='livraison France'
            if route.request.url.endswith('/api/discover'):
                assert route.request.post_data_json['code'] in ['OP-08','OP-09']
                assert route.request.post_data_json['name']==('OP-09' if route.request.post_data_json['code']=='OP-09' else 'One Piece OP-08 FR case 6 displays')
                assert route.request.post_data_json['game']=='One Piece'
            data={'status':'partial','cached':False,'priced_count':2,'comparable_count':2,'candidates':[
                {'url':'https://niche.example/display','title':'Boutique de niche','domain':'niche.example','known_store':False,'snippet':'<img src=x onerror=alert(1)> Display OP-08','status':'unverified','set_match':True,'language_match':'match','detected_languages':['FR'],'packaging':'display','price_status':'read','price':120,'currency':'EUR','unit_price_eur':120,'display_count':1,'in_stock':True,'comparable':True},
                {'url':'https://known.example/display','title':'Boutique suivie','domain':'known.example','known_store':True,'snippet':'Case scellée','status':'unverified','language_match':'match','price_status':'read','price':540,'currency':'EUR','unit_price_eur':90,'display_count':6,'in_stock':True,'comparable':True},
                {'url':'https://japan.example/display','title':'Display japonais','domain':'japan.example','known_store':False,'snippet':'Version japonaise','status':'unverified','language_match':'mismatch','detected_languages':['JP']},
            ]}
        elif '/history' in route.request.url:
            points=[{'day':str(date.today()-timedelta(days=day)),'price':102+day,'shippingKnown':True} for day in [6,5,3,2,1,0]]
            data={'points':points}
        elif '/best' in route.request.url:
            data={'price':102,'shippingKnown':True}
        else:
            data=[{'product_id':1,'set_name':'Set de contrôle','language':'FR','store':'Fixture shop','previous_cost':110,'new_cost':102,'percent':7.3,'created_at':str(date.today())}]
        if '/discover' in route.request.url:
            data['candidates'][0]['shipping_origin'] = {'country':'FR','country_label':'France','region':'EU','tax_message':'Pas de frais d’import normalement attendus.', 'sources':[{'url':'https://niche.example/shipping','evidence':'Livraison depuis la France.','checked_at':'2026-09-19'}]}
            data['candidates'][1]['shipping_origin'] = {'country':'JP','country_label':'Japon','region':'outside_eu','tax_message':'TVA d’import à prévoir.', 'sources':[]}
        route.fulfill(json=data)
    page.route('**/api/**',api)
    page.goto(base+'/index.html')
    page.wait_for_selector('.card')
    page.wait_for_function("document.querySelector('#catalog-status').textContent.includes('7 jours')")
    page.locator('#discovery-game').select_option('Gundam')
    assert page.locator('#discovery-language').input_value()=='EN'
    assert page.locator('#discovery-set option').count()==2
    assert 'GD-01' in page.locator('#discovery-set').inner_text()
    page.locator('#discovery-language').select_option('JP')
    assert page.locator('#discovery-set option').count()==2
    page.locator('#discovery-language').select_option('FR')
    assert page.locator('#discovery-set option').count()==1
    page.locator('#q').fill('introuvable')
    assert page.locator('#no-results').is_visible()
    page.locator('#reset-filters').click()
    assert page.locator('.card:not(.hidden)').count()==1
    page.locator('#discovery-game').select_option('One Piece')
    assert page.locator('#discovery-set option').count()==2
    page.locator('#discovery-language').select_option('JP')
    assert page.locator('#discovery-set option').count()==1
    assert not page.locator('#set-choice-offers').is_visible()
    page.locator('#discovery-language').select_option('FR')
    page.locator('#discovery-set').select_option(index=1)
    assert '1 offre(s)' in page.locator('#set-choice-offers').inner_text()
    assert not page.locator('#discovery-name').is_visible()
    page.locator('#discovery-keywords').fill('livraison France')
    page.get_by_role('button',name='Rechercher les offres sur le web').click()
    page.wait_for_selector('.discovery-result')
    assert page.locator('#discovery-set').input_value()=='1'
    assert page.locator('.discovery-result').count()==2
    assert '90' in page.locator('.web-price').first.inner_text()
    assert '540' in page.locator('.discovery-result').first.inner_text()
    assert 'Certains moteurs' in page.locator('#discovery-status').inner_text()
    assert 'Expédition : Japon' in page.locator('.discovery-result').first.inner_text()
    page.locator('#discovery-origin').select_option('EU')
    assert page.locator('.discovery-result').count()==1
    assert 'Expédition : France' in page.locator('.discovery-result').inner_text()
    page.get_by_text('Sources de l’expédition', exact=True).click()
    assert page.get_by_role('link',name='Source marchand').get_attribute('href')=='https://niche.example/shipping'
    page.locator('#discovery-origin').select_option('outside_eu')
    assert page.locator('.discovery-result').count()==1
    assert 'TVA d’import à prévoir' in page.locator('.discovery-result').inner_text()
    page.locator('#discovery-origin').select_option('')
    page.locator('#discovery-origin').select_option('unknown')
    assert page.locator('.discovery-result').count()==0
    assert 'masqués par les filtres' in page.locator('#discovery-results').inner_text()
    page.locator('#discovery-reset').click()
    assert page.locator('.discovery-result').count()==3
    page.locator('#discovery-other').uncheck()
    page.locator('#discovery-new').check()
    assert page.locator('.discovery-result').count()==1
    page.locator('#discovery-other').check()
    assert page.locator('.discovery-result').count()==2
    assert page.locator('.language-mismatch').count()==1
    assert 'OP-08' in page.locator('.search-links a').first.get_attribute('href')
    page.locator('#discovery-manual').check()
    assert page.locator('#discovery-set').is_disabled()
    page.locator('#discovery-name').fill('OP-09')
    page.get_by_role('button',name='Rechercher les offres sur le web').click()
    page.wait_for_selector('.discovery-result')
    assert 'OP-09' in page.locator('.search-links a').first.get_attribute('href')
    page.locator('#discovery-manual').uncheck()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(preview/'explore-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    page.screenshot(path=str(preview/'catalogue.png'),full_page=True)
    page.goto(base+'/set.html')
    page.wait_for_selector('#chart svg circle')
    page.get_by_role('button',name='90 j',exact=True).click()
    page.wait_for_function("document.querySelector('[data-days=\"90\"]').getAttribute('aria-pressed') === 'true'")
    page.locator('#target').fill('105')
    page.get_by_role('button',name='Surveiller ce set').click()
    page.wait_for_function("document.querySelector('#watch-status').textContent.includes('Seuil atteint')")
    page.reload()
    page.wait_for_function("document.querySelector('#watch-status').textContent.includes('Seuil atteint')")
    page.get_by_role('button',name='Supprimer',exact=True).click()
    assert page.locator('#watch-status').inner_text()=='Surveillance supprimée.'
    assert page.locator('.search-links a').count()==6
    page.locator('#discovery-keywords').fill('livraison France')
    page.get_by_role('button',name='Chercher de nouvelles boutiques').click()
    page.wait_for_selector('.discovery-result')
    assert page.locator('.discovery-result .offer-cta').count()==2
    assert '90' in page.locator('.web-price').first.inner_text()
    assert page.locator('.discovery-result img').count()==0
    page.screenshot(path=str(preview/'set.png'),full_page=True)
    page.locator('#show-alerts').click()
    assert page.locator('dialog').is_visible()
    page.locator('#close-alerts').click()
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(preview/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors,errors
    browser.close()
server.shutdown()
print('PASS: browser search, chart periods, target persistence, alerts, set discovery, mobile layout; no JavaScript errors')
