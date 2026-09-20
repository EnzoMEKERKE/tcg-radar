import asyncio
import csv
import io
from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from app.deals.models import Listing, Settings, ImportRequest
from app.deals.identity import identity, language_of, condition_of
from app.deals.analyzer import analyze
from app.deals.parsers import parse_ebay, parse_cardmarket, date_of
from app.deals.service import DealsService, parse_csv, CSV_FIELDS

NOW = datetime.now(timezone.utc)


def listing(source='ebay', price=100, sold=False, identifier=1, **changes):
    data=dict(source=source,title='Pokémon Pikachu 25/102 holo FR NM',price=price,
              url=f'https://www.ebay.fr/itm/{100000000000+identifier}' if source=='ebay' else 'https://www.cardmarket.com/fr/Pokemon/Products/Singles/Base-Set/Pikachu',
              shipping=2,language='FR',condition='NM',sold=sold,sold_at=NOW-timedelta(days=1) if sold else None,
              observed_at=NOW,seller='Seller'+str(identifier),listing_id=str(identifier))
    data.update(changes)
    return Listing(**data)


def sample():
    return [listing('cardmarket',50),listing('cardmarket',60,identifier=2),listing('ebay',30,identifier=4)]+[listing('ebay',price,True,i) for i,price in enumerate([100,110,120],10)]


def test_both_directions_net_margin_and_reference_evidence():
    result=analyze(sample(),Settings(),now=NOW)
    assert result['deal_count']==2
    first,second=result['deals']
    assert first['direction']=='cm_to_ebay' and first['reference_price']==110
    assert first['net_profit']==35.06 and first['roi']==67.4
    assert second['direction']=='ebay_to_cm' and second['reference_price']==50
    assert second['reference_kind']=='active_lowest' and second['confidence']=='asking_prices_only'
    assert len(first['evidence'])==3


@pytest.mark.parametrize('changes',[
    {'title':'Pokémon Pikachu 26/102 holo FR NM'}, {'title':'Pokémon Pikachu 25/130 holo FR NM'},
    {'title':'Pokémon Pikachu 25/102 reverse FR NM'}, {'language':'JP'}, {'condition':'MT'},
    {'title':'Pokémon Pikachu 25/102 holo FR NM PSA 10'}, {'currency':'USD'},
    {'title':'Pokémon Pikachu 25/102 FR NM'}, {'condition':'UNKNOWN'}, {'set_code':'other-set'},
    {'title':'Pokémon Pikachu 25/102 holo FR NM lot'}, {'available':False},
    {'observed_at':NOW-timedelta(days=2)}, {'price_exact':False},
])
def test_different_or_uncertain_cards_never_create_deal(changes):
    rows=[listing('cardmarket',20,**changes)]+sample()[3:]
    assert analyze(rows,Settings(language='ALL',condition_min='PO'),now=NOW)['deal_count']==0


def test_min_sales_duplicates_old_sales_and_hidden_best_offer():
    rows=[listing('cardmarket',20),listing(sold=True,identifier=8)]
    assert not analyze(rows+[rows[1]]*9,Settings(),now=NOW)['deals']
    for change in ({'sold_at':None},{'sold_at':NOW-timedelta(days=91)},{'price_exact':False}):
        rows=[listing('cardmarket',20)]+[listing(sold=True,identifier=i,**change) for i in range(3)]
        assert not analyze(rows,Settings(),now=NOW)['deals']


def test_unknown_shipping_and_fees_change_profit():
    rows=[listing('cardmarket',50,shipping=None)]+sample()[3:]
    deal=analyze(rows,Settings(),now=NOW)['deals'][0]
    assert deal['shipping_estimated'] and deal['buy_shipping']==3
    assert not analyze(rows,Settings(other_costs=100),now=NOW)['deals']


def test_language_and_condition_are_not_guessed_from_platform():
    assert language_of('Pokemon Pikachu 25/102')=='UNKNOWN'
    assert language_of('Pokemon FR Japanese')=='UNKNOWN'
    assert condition_of('Used')=='UNKNOWN'
    assert condition_of('Near Mint')=='NM'
    assert condition_of('Light Played')=='LP'


@pytest.mark.parametrize('changes',[{'card_number':'26/102'},{'variant':'reverse'},{'language':'JP'}])
def test_conflicting_metadata_rejected(changes):
    key,reason=identity(listing(**changes))
    assert key is None and reason=='identite_contradictoire'


def test_cm_partial_number_uses_confirmed_full_title_number():
    key,reason=identity(listing(card_number='025'))
    assert not reason and key[1]=='25/102'


def test_browser_only_allows_marketplace_search_and_product_documents():
    from app.deals.browser import BrowserPages
    assert BrowserPages.allowed_document('https://www.ebay.fr/sch/i.html?_nkw=pikachu')
    assert BrowserPages.allowed_document('https://www.cardmarket.com/fr/Pokemon/Products/Singles/Base-Set/Pikachu')
    for url in ['http://www.ebay.fr/sch/i.html','https://127.0.0.1/','https://www.ebay.fr/checkout','https://www.ebay.fr:9000/sch/i.html','https://evil.example/sch/i.html']:
        assert not BrowserPages.allowed_document(url)


def test_login_and_verification_are_reported_separately():
    from app.deals.browser import access_gate
    assert access_gate('https://signin.ebay.fr/ws/eBayISAPI.dll?SignIn').status=='login_required'
    assert access_gate('https://www.ebay.fr/splashui/challenge').status=='verification_required'
    assert access_gate('https://www.cardmarket.com/fr/Pokemon/Products/Search','Just a moment...').status=='verification_required'
    assert access_gate('https://www.ebay.fr/sch/i.html','Pikachu en vente') is None


def test_login_required_is_not_a_successful_empty_scan(tmp_path):
    class Collector:
        def __init__(self): self.rows=[];self.requests=1;self.reports=[]
        async def collect(self,settings):
            self.reports=[{'source':'ebay_sold','status':'login_required','message':'Connexion requise.'}]
    async def run():
        service=DealsService(tmp_path/'gate.sqlite',Collector)
        job=service.start(Settings())
        await service.tasks[job['id']]
        assert service.status(job['id'])['status']=='unavailable'
    asyncio.run(run())


def test_new_ebay_cards_remove_accessibility_text_and_read_shipping():
    html='''<li class="s-card"><a class="s-card__link" href="https://www.ebay.fr/itm/123456789012"></a><div class="s-card__title"><span>Pikachu 25/102 holo FR NM</span><span class="clipped">La page s'ouvre dans une nouvelle fenêtre</span></div><span class="s-card__price">50,00 EUR</span><div class="s-card__attribute-row">+2,78 EUR pour la livraison</div></li>'''
    row=parse_ebay(html)[0]
    assert row.title=='Pikachu 25/102 holo FR NM' and row.shipping==2.78


def test_blocked_sold_search_does_not_disable_active_ebay():
    from app.deals.collector import Collector
    import httpx
    class Pages:
        async def product(self,url):
            if 'LH_Sold' in url:
                httpx.Response(403,request=httpx.Request('GET',url)).raise_for_status()
            return '<li class="s-card"><a class="s-card__link" href="https://www.ebay.fr/itm/123456789012"></a><h3>Pikachu 25/102 holo FR NM</h3><span class="s-card__price">50 EUR</span></li>',url
    async def run():
        collector=Collector(Pages())
        await collector.ebay('Pikachu',Settings(pages=1),True)
        await collector.ebay('Pikachu',Settings(pages=1),False)
        assert len(collector.rows)==1 and collector.rows[0].sold is False
        assert collector.reports[-1]['source']=='ebay_active' and collector.reports[-1]['status']=='ok'
    asyncio.run(run())


def test_collector_reports_blocked_sources_without_false_empty_success():
    import httpx
    from app.deals.collector import Collector
    class Pages:
        async def product(self,url):
            response=httpx.Response(403,request=httpx.Request('GET',url))
            response.raise_for_status()
    async def run():
        collector=Collector(Pages())
        await collector.collect(Settings(query='Pikachu'))
        assert not collector.rows
        assert collector.requests==3
        assert {r['source'] for r in collector.reports}=={'ebay_sold','ebay_active','cardmarket'}
        assert all(r['status']=='blocked' for r in collector.reports)
    asyncio.run(run())


def test_ebay_parser_requires_sold_date_and_skips_range_and_negotiated():
    def html(price='99,90 EUR',sold='Vendu le 18 sept. 2026',extra=''):
        return f'<li class="s-item"><h3 class="s-item__title">Pokemon Pikachu 25/102 holo FR NM</h3><a class="s-item__link" href="https://www.ebay.fr/itm/123456789012"></a><span class="s-item__price">{price}</span><span class="s-item__title--tag">{sold}</span>{extra}</li>'
    rows=parse_ebay(html(),True)
    assert rows[0].price==99.90 and rows[0].sold and rows[0].language=='FR'
    assert rows[0].shipping is None and rows[0].condition=='NM'
    assert not parse_ebay(html(sold=''),True)
    assert not parse_ebay(html(price='10,00 EUR à 100,00 EUR'),True)
    assert not parse_ebay(html(price='99,90'),True)
    assert not parse_ebay(html(extra='10 enchères'),False)
    assert not parse_ebay(html(extra='Best offer accepted'),True)[0].price_exact
    assert date_of('Sold Sep 18, 2026').month==9
    assert date_of('Vendu le 18 juillet 2026').month==7


def test_cardmarket_reads_seller_condition_and_language():
    html='''<h1>Pikachu 25/102 Holo</h1><div class="article-row" id="article-42"><a href="/fr/Pokemon/Users/Alice">Alice</a><div class="price-container"><span class="fw-bold">50,00 €</span></div><div class="product-attributes"><span>NM</span><span data-original-title="French"></span></div></div>'''
    rows=parse_cardmarket(html,'https://www.cardmarket.com/fr/Pokemon/Products/Singles/Base-Set/Pikachu')
    assert len(rows)==1 and rows[0].seller=='Alice' and rows[0].language=='FR' and rows[0].condition=='NM'
    assert rows[0].shipping is None


def as_csv(rows):
    stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=CSV_FIELDS);writer.writeheader()
    for row in rows:writer.writerow({k:v for k,v in row.model_dump(mode='json').items() if k in CSV_FIELDS})
    return stream.getvalue()


def test_import_validation_and_persistent_analysis(tmp_path):
    content=as_csv(sample())
    rows=parse_csv(content)
    assert len(rows)==6 and all(r.provenance=='imported' for r in rows)
    service=DealsService(tmp_path/'cache.sqlite')
    result=service.imported(ImportRequest(csv=content))
    assert result['deal_count']==2
    reloaded=DealsService(tmp_path/'cache.sqlite').status(result['id'])
    assert reloaded['deals']==result['deals']
    with pytest.raises(ValueError):parse_csv('price,title\n20,Test')
    with pytest.raises(ValueError):parse_csv(content.replace('ebay.fr','evil.example'))
    with pytest.raises(ValueError):parse_csv(content.replace('100.0','NaN'))
    with pytest.raises(ValidationError):Settings(ebay_fee_pct=float('nan'))


def test_failed_scan_reports_failure_and_preserves_cache(tmp_path):
    class Collector:
        def __init__(self): self.rows=[];self.requests=2;self.reports=[]
        async def collect(self,settings):
            self.reports=[{'source':'ebay_sold','status':'blocked','message':'HTTP 403'}]
    async def run():
        service=DealsService(tmp_path/'cache.sqlite',Collector)
        job=service.start(Settings())
        await service.tasks[job['id']]
        result=service.status(job['id'])
        assert result['status']=='unavailable' and result['reports'][0]['status']=='blocked'
        cached=service.start(Settings())
        assert cached['cached'] and cached['id']==job['id']
        assert service.start(Settings(min_profit=8))['id']!=job['id']
        await asyncio.gather(*service.tasks.values())
    asyncio.run(run())


def test_deals_http_import_and_reload(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    monkeypatch.setattr(main,'deals',DealsService(tmp_path/'http.sqlite'))
    with TestClient(main.app) as client:
        response=client.post('/deals/import',json={'csv':as_csv(sample()),'settings':{}})
        assert response.status_code==200
        data=response.json()
        assert data['deal_count']==2
        assert client.get('/deals/status/'+data['id']).json()['deals']==data['deals']
        assert client.post('/deals/import',json={'csv':'wrong\nvalue'}).status_code==422
        assert client.post('/deals/search',json={'pages':1000}).status_code==422
        assert client.get('/deals/status/missing').status_code==404
