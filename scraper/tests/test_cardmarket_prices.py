import asyncio
from datetime import datetime, timedelta, timezone
import json

from app.deals.cardmarket_prices import CardmarketPrices, build_snapshot, CATALOG_URL


def documents():
    stamp=datetime.now(timezone.utc).isoformat()
    return ({'createdAt':stamp,'products':[
        {'idProduct':1,'name':'Pikachu [Spark]','idExpansion':10},
        {'idProduct':2,'name':'Charizard','idExpansion':20},
        {'idProduct':3,'name':'Pikachu','idExpansion':30}]},
        {'createdAt':stamp,'priceGuides':[{'idProduct':1,'low':0.2,'trend':8.79,'avg1':None,'trend-holo':36.37},
                                       {'idProduct':2,'low':-1,'trend':float('nan')}]})


def test_join_keeps_real_ids_and_unknown_prices():
    snapshot=build_snapshot(*documents())
    assert len(snapshot['rows'])==1
    row=snapshot['rows'][0]
    assert row['id']==1 and row['prices']['trend']==8.79
    assert row['prices']['avg1'] is None
    assert row['prices']['trend-holo']==36.37
    assert 'seller' not in row and 'language' not in row


def test_download_persist_reload_and_filter(tmp_path):
    async def scenario():
        store=CardmarketPrices(tmp_path/'prices.json')
        async def download(url):
            return documents()[0 if url==CATALOG_URL else 1]
        store.download=download
        assert store.search('Pikachu')['status']=='loading'
        task=store.task
        store.search('Pikachu')
        assert store.task is task
        await task
        assert store.search('pikachu')['total']==1
        assert store.search('charizard')['total']==0
        assert store.search('1')['rows'][0]['id']==1
        reloaded=CardmarketPrices(store.path)
        assert reloaded.search()['indexed_count']==1
        assert reloaded.task is None
    asyncio.run(scenario())


def test_failed_refresh_preserves_old_data_and_backs_off(tmp_path):
    async def scenario():
        store=CardmarketPrices(tmp_path/'prices.json')
        old=build_snapshot(*documents())
        old['fetched_at']=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
        old['guide_date']=old['fetched_at']
        store.install(old)
        async def fail(url):
            raise ValueError('bad response')
        store.download=fail
        result=store.search('Pikachu')
        assert result['status']=='stale' and result['rows']
        await store.task
        task=store.task
        result=store.search()
        assert store.task is task and result['message'] and result['rows']
    asyncio.run(scenario())


def test_pagination_and_corrupt_cache(tmp_path):
    path=tmp_path/'prices.json';path.write_text('{',encoding='utf-8')
    store=CardmarketPrices(path)
    assert store.snapshot is None
    store.install(build_snapshot(*documents()))
    assert store.search(page=2,limit=1)['page']==1


def test_price_filters_holo_sort_and_facets(tmp_path):
    store=CardmarketPrices(tmp_path/'prices.json')
    snapshot=build_snapshot(*documents())
    row=snapshot['rows'][0]
    snapshot['rows'] += [dict(row,id=2,name='Pikachu B',expansion_id=20,prices={**row['prices'],'trend':3}),
                         dict(row,id=3,name='Pikachu C',prices={**row['prices'],'trend':None})]
    store.install(snapshot)
    assert [r['id'] for r in store.search(sort='price_asc')['rows']]==[2,1,3]
    assert [r['id'] for r in store.search(sort='price_desc')['rows']]==[1,2,3]
    assert store.search(min_price=5,max_price=10)['total']==1
    assert store.search(variant='holo',min_price=30,max_price=40)['total']==3
    assert store.search(metric='low',max_price=1)['total']==3
    result=store.search(expansion=20)
    assert result['total']==1 and len(result['expansions'])==2
    import pytest
    with pytest.raises(ValueError):store.search(min_price=10,max_price=1)


def test_image_mapping_requires_product_id_and_trusted_asset():
    from app.deals.cardmarket_images import card_metadata
    card={'name':'Pikachu','image':'https://assets.tcgdex.net/en/base/base1/58',
          'pricing':{'cardmarket':{'idProduct':273753}},'set':{'name':'Base Set'},'localId':'58'}
    key,metadata=card_metadata(card)
    assert key=='273753' and metadata['image_url'].endswith('/low.webp')
    assert card_metadata({**card,'pricing':{}}) is None
    assert card_metadata({**card,'image':'https://evil.example/card.png'}) is None


def test_image_cache_survives_restart(tmp_path):
    from app.deals.cardmarket_images import CardmarketImages
    path=tmp_path/'images.json'
    path.write_text(json.dumps({'cards':{'1':{'image_url':'https://assets.tcgdex.net/en/base/base1/58/low.webp'}},'checked':{}}))
    images=CardmarketImages(path)
    rows=[{'id':1,'name':'Pikachu'}]
    assert not images.enrich(rows)
    assert rows[0]['image_url']
