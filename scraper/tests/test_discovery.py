import asyncio
import httpx
import pytest
from app.services.discovery import Discovery, DiscoveryQuery, candidates_from, clean_url, queries_for, relevance_for


def query(**changes):
    return DiscoveryQuery(**dict({'game':'One Piece','name':'Two Legends','code':'OP-08','language':'FR'},**changes))


def test_queries_cover_name_code_language_and_keywords():
    queries=queries_for(query(keywords='livraison France'))
    assert len(queries)==3
    assert '"Two Legends"' in queries[0]
    assert 'OP-08' in queries[1]
    assert all('livraison France' in q for q in queries)
    assert '日本語' in queries_for(query(language='JP'))[2]


def test_provisional_code_not_sent_to_search():
    assert all('UNMATCHED' not in q for q in queries_for(query(code='UNMATCHED-123')))


@pytest.mark.parametrize('url',[
    'javascript:alert(1)','file:///etc/passwd','http://localhost:8080/','https://127.0.0.1/a',
    'https://192.168.1.1/a','http://[::1]/','https://user:password@shop.com/a','http://private.local/a',
    'https://shop.com:9000/a',
])
def test_non_public_links_not_displayed(url):
    assert clean_url(url) is None


def test_deduplicate_tracking_keep_variants_and_favor_new_domains():
    rows=candidates_from([
        {'url':'https://www.ultrajeux.com/a','title':'Known'},
        {'url':'https://niche.example/box?variant=1&utm_source=ads#product','title':'New'},
        {'url':'https://niche.example/box?variant=1','title':'Duplicate'},
        {'url':'https://niche.example/box?variant=2','title':'Second variant'},
    ])
    assert len(rows)==3 and rows[0]['known_store'] is False and rows[-1]['known_store'] is True
    assert all(row['status']=='unverified' and 'price' not in row for row in rows)


def test_domain_diversity():
    rows=candidates_from([{'url':f'https://niche.example/product/{i}'} for i in range(12)])
    assert len(rows)==3


@pytest.mark.parametrize('title,language', [
    ('Display OP08 japonais', 'mismatch'),
    ('OP-08 Two Legends English booster box', 'mismatch'),
    ('Display OP08 EN - Boutique', 'mismatch'),
    ('Display OP08 en stock, livraison France', 'unknown'),
    ('Display OP08 français', 'match'),
    ('Display OP08 FR / JP', 'ambiguous'),
])
def test_language_hints_do_not_confuse_delivery_country_with_product_language(title, language):
    result = relevance_for(title, query())
    assert result['set_match']
    assert result['language_match'] == language


def test_code_boundaries_and_accented_names():
    assert not relevance_for('OP-080 display FR', query())['set_match']
    assert not relevance_for('OP-080 display FR', query(name='OP-08'))['set_match']
    assert relevance_for('Display Evolutions Prismatiques FR', query(name='Évolutions Prismatiques'))['set_match']


def test_rank_before_domain_limit_and_keep_other_languages_available():
    rows = [{'url': f'https://shop.example/{i}', 'title': 'OP08 Japanese display'} for i in range(4)]
    rows.append({'url': 'https://shop.example/fr', 'title': 'OP-08 français case 6 displays'})
    result = candidates_from(rows, query())
    assert len(result) == 3
    assert result[0]['url'].endswith('/fr') and result[0]['packaging'] == 'case'
    assert result[-1]['language_match'] == 'mismatch'
    assert all(row['status'] == 'unverified' and 'price' not in row for row in result)


def test_blank_query_rejected():
    with pytest.raises(ValueError):
        query(name='   ')


def test_searxng_search_cached_and_bounded(tmp_path,monkeypatch):
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY',raising=False)
    monkeypatch.setenv('SEARXNG_URL','http://search:8080')
    calls=[]
    def response(request):
        calls.append(request)
        assert request.url.params['format']=='json'
        return httpx.Response(200,json={'results':[{'url':'https://niche.example/op08','title':'OP08 Display'}]})
    async def run():
        service=Discovery(tmp_path/'cache.sqlite',httpx.MockTransport(response))
        result=await service.search(query())
        assert result['status']=='ok' and len(result['candidates'])==1
        cached=await service.search(query())
        assert cached['cached'] and len(calls)<=6
        # Identical pages must not trigger a third page of the same results.
        assert {r.url.params['pageno'] for r in calls} == {'1', '2'}
    asyncio.run(run())


def test_engine_failure_returns_fallback_without_price(tmp_path,monkeypatch):
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY',raising=False)
    monkeypatch.setenv('SEARXNG_URL','http://search:8080')
    async def run():
        service=Discovery(tmp_path/'cache.sqlite',httpx.MockTransport(lambda r:httpx.Response(429)))
        result=await service.search(query())
        assert result['status']=='unavailable' and not result['candidates'] and len(result['queries'])>=3
    asyncio.run(run())


def test_no_provider_requires_no_network(tmp_path,monkeypatch):
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY',raising=False)
    monkeypatch.delenv('SEARXNG_URL',raising=False)
    def unexpected(request):
        raise AssertionError('Network must not be used')
    result=asyncio.run(Discovery(tmp_path/'cache.sqlite',httpx.MockTransport(unexpected)).search(query()))
    assert result['status']=='unconfigured'


def test_brave_key_not_in_results(tmp_path,monkeypatch):
    monkeypatch.setenv('BRAVE_SEARCH_API_KEY','test-secret')
    def response(request):
        assert request.headers['X-Subscription-Token']=='test-secret'
        return httpx.Response(200,json={'web':{'results':[{'url':'https://niche.example/box','title':'Box'}]}})
    result=asyncio.run(Discovery(tmp_path/'cache.sqlite',httpx.MockTransport(response)).search(query()))
    assert result['status']=='ok' and result['provider']=='brave' and 'test-secret' not in str(result)


def test_http_200_with_blocked_engines_is_not_cached_as_empty(tmp_path,monkeypatch):
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY',raising=False)
    monkeypatch.setenv('SEARXNG_URL','http://search:8080')
    calls=[]
    def response(request):
        calls.append(request)
        return httpx.Response(200,json={'results':[],'unresponsive_engines':[['duckduckgo','CAPTCHA']]})
    async def run():
        service=Discovery(tmp_path/'cache.sqlite',httpx.MockTransport(response))
        first=await service.search(query())
        count=len(calls)
        second=await service.search(query())
        assert first['status']=='unavailable' and first['cache_ttl_seconds']==0
        assert not second['cached'] and len(calls)>count
        assert all(r.url.params['pageno']=='1' for r in calls)
    asyncio.run(run())


def test_adaptive_search_never_exceeds_six_requests(tmp_path,monkeypatch):
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY',raising=False)
    monkeypatch.setenv('SEARXNG_URL','http://search:8080')
    calls=[]
    def response(request):
        calls.append(request)
        return httpx.Response(200,json={'results':[{'url':f'https://shop{len(calls)}.example/box'}]})
    result=asyncio.run(Discovery(tmp_path/'cache.sqlite',httpx.MockTransport(response)).search(query()))
    assert len(calls)==6 and len(result['candidates'])==6
