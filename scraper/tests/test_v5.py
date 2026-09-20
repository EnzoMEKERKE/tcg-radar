import asyncio
import json
import httpx
import pytest
from bs4 import BeautifulSoup
from app.services.normalizer import normalize
from app.services.catalog import Catalog
from app.services.shipping import shipping_for
from app.connectors.merchant import MerchantConnector


@pytest.mark.parametrize('title,kind,count',[
    ('One Piece OP-08 Display Japanese','display',1),
    ('Pokemon SV8a JP case 12 booster boxes','case',12),
    ('Pokemon ME06 FR Case (x6 Displays)','case',6),
    ('One Piece OP-09 FR display x12','case',12),
    ('One Piece OP-09 JP sealed case','case',None),
    ('Pokemon EV08 FR display 36 boosters','display',1),
    ('Pokemon display ETB bundle',None,1),
    ('Pokemon empty display box',None,1),
])
def test_packaging(title,kind,count):
    row=normalize(title)
    assert row['kind']==kind
    assert row['display_count']==count


def test_language_not_guessed_from_store():
    assert normalize('Pokemon SV8a display')['language'] is None
    assert normalize('Pokemon SV8a Chinese display')['language']=='OTHER'


def test_code_game_scoping():
    assert normalize('Pokemon EB03 FR Display')['set_code']=='EB-03'
    assert normalize('One Piece EB03 FR Display')['set_code']=='EB-03'
    assert normalize('Gundam GD1 EN booster box')['set_code']=='GD-01'
    assert normalize('One Piece ST01 starter deck')['kind'] is None


def entry(language,code,name,aliases):
    return dict(game='Pokemon',language=language,code=code,name=name,aliases=aliases,source='https://catalog.example/sets')


def test_canonical_match_language_and_alias():
    catalog=Catalog([entry('FR','SV08','Étincelles Déferlantes',['Étincelles Déferlantes','EV08']),entry('JP','SV8','Super Electric Breaker',['SV8'])])
    row=catalog.match(normalize('Pokemon EV08 display FR'))
    assert (row['set_code'],row['language'],row['canonical'])==('SV08','FR',True)
    row=catalog.match(normalize('Pokemon Étincelles Déferlantes display FR'))
    assert row['set_code']=='SV08'
    assert not catalog.match(normalize('Pokemon EV08 display JP'))['canonical']


def test_ambiguous_match_not_canonical():
    catalog=Catalog([entry(lang,'SV08','Shared',['Shared','SV08']) for lang in ['FR','JP']])
    assert not catalog.match(normalize('Pokemon Shared display'))['canonical']


def test_shipping_threshold(monkeypatch):
    monkeypatch.setenv('SHIPPING_RULES_JSON',json.dumps({'Test':{'flat_eur':6,'free_above_eur':100}}))
    assert shipping_for({'name':'Test'},99)==6
    assert shipping_for({'name':'Test'},100)==0
    assert shipping_for({'name':'Unknown'},100) is None
    monkeypatch.setenv('SHIPPING_RULES_JSON','')
    assert shipping_for({'name':'Test'},100) is None


def connector(name='Test'):
    return MerchantConnector({'name':name,'url':'https://shop.test','country':'FR','currency':'EUR'},max_pages=3)


def test_jsonld_graph_and_shipping():
    product={'@type':['Product'],'name':'Pokemon EV08 FR display','offers':{'price':'100.00','priceCurrency':'EUR','availability':'https://schema.org/InStock','shippingDetails':{'shippingDestination':{'addressCountry':'FR'},'shippingRate':{'currency':'EUR','value':'5.75'}}}}
    soup=BeautifulSoup('<script type="application/ld+json">'+json.dumps({'@graph':[product]})+'</script>','html.parser')
    row=connector().parse_product(soup,'https://shop.test/product/display')[0]
    assert row['price']==100 and row['in_stock'] and row['shipping_eur']==5.75


@pytest.mark.parametrize('availability,stock',[(None,False),('https://schema.org/OutOfStock',False),('https://schema.org/PreOrder',False),('https://schema.org/InStock',True)])
def test_stock_is_explicit(availability,stock):
    product={'@type':'Product','name':'One Piece OP08 JP display','offers':{'price':90,'availability':availability}}
    soup=BeautifulSoup('<script type="application/ld+json">'+json.dumps(product)+'</script>','html.parser')
    assert connector().parse_product(soup,'https://shop.test/a')[0]['in_stock']==stock


def test_aggregate_price_not_a_real_offer():
    product={'@type':'Product','name':'One Piece OP08 JP display','offers':{'lowPrice':10,'@type':'AggregateOffer'}}
    soup=BeautifulSoup('<script type="application/ld+json">'+json.dumps(product)+'</script>','html.parser')
    assert connector().parse_product(soup,'https://shop.test/a')==[]


def test_ultrajeux_microdata():
    soup=BeautifulSoup('<h1>Pokémon - Boite de Boosters Français - Display 36 Boosters ME05</h1><meta itemprop="price" content="249.90"><meta itemprop="availability" content="InStock">','html.parser')
    row=connector('UltraJeux').parse_product(soup,'https://shop.test/a')[0]
    assert row['price']==249.9 and row['in_stock'] and row['meta']['language']=='FR'


def test_ludotrotter_sale_and_case():
    soup=BeautifulSoup('<li class="product product-type-simple instock"><a class="woocommerce-LoopProduct-link" href="/produit/case"><h2>Pokemon Case (x6 Displays) ME06 FR</h2></a><span class="price"><del><span class="amount">1 200,00 €</span></del><ins><span class="amount">999,00 €</span></ins></span></li>','html.parser')
    row=connector('Ludotrotter').parse_product(soup,'https://shop.test/category')[0]
    assert row['price']==999 and row['meta']['display_count']==6


def test_shopify_variants_preserved():
    async def run():
        c=connector();c.robots.parse([])
        response={'products':[{'title':'Pokemon SV8a JP booster box','handle':'box','variants':[{'id':1,'title':'1 display','price':'50','available':True},{'id':2,'title':'case 12 displays','price':'550','available':False}]}]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=response))) as client:
            rows=await c.shopify(client)
        assert len(rows)==2 and rows[0]['url']!=rows[1]['url']
        assert rows[1]['meta']['display_count']==12 and not rows[1]['in_stock']
    asyncio.run(run())


def test_robots_and_request_budget():
    async def run():
        c=connector();c.robots.parse(['User-agent: *','Disallow: /private'])
        calls=[]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:(calls.append(r.url) or httpx.Response(200,text='ok')))) as client:
            assert await c.get(client,'https://shop.test/private') is None
            assert await c.get(client,'https://other.test/a') is None
            for _ in range(5): await c.get(client,'https://shop.test/public')
        assert len(calls)==3
    asyncio.run(run())
