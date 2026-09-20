import asyncio
import json

import httpx
from app.services.catalog import Catalog
from app.services.catalog_updates import CatalogUpdates, WEEK, RETRY


ENTRY = dict(game='Gundam', language='EN', code='GD-01', name='Newtype Rising', aliases=['GD-01'], source='https://publisher.example/gd01')


def test_weekly_refresh_is_shared_and_survives_restart(tmp_path):
    async def run():
        now = [WEEK * 5]
        calls = []
        published = []
        class Cached:
            entries = [ENTRY]
            updated = now[0] - WEEK - 1
            status = []
            async def refresh(self):
                calls.append('refresh')
                await asyncio.sleep(0)
                Cached.updated = now[0]
                Cached.entries = [ENTRY, dict(ENTRY, code='GD-02')]
                self.status = Cached.status = [{'status': 'ok'}]
        async def publish(entries): published.append(list(entries))
        args = dict(state_path=tmp_path/'state.json', factory=Cached, publisher=publish, clock=lambda: now[0])
        updater = CatalogUpdates(**args)
        assert updater.request()['refreshing']
        first = updater.task
        updater.request()
        assert updater.task is first
        await first
        assert calls == ['refresh'] and len(published[0]) == 2
        assert updater.status()['new_sets'] == 1
        restarted = CatalogUpdates(**args)
        assert not restarted.request()['refreshing'] and restarted.task is None
        now[0] += WEEK
        restarted.request()
        await restarted.task
        assert len(calls) == 2
    asyncio.run(run())


def test_fresh_cache_is_published_without_refetching(tmp_path):
    async def run():
        published=[]
        class Cached:
            entries=[ENTRY]; updated=WEEK*3; status=[]
            async def refresh(self): raise AssertionError('Fresh catalogue must not be fetched')
        async def publish(entries): published.extend(entries)
        updater=CatalogUpdates(tmp_path/'state.json',Cached,publish,lambda:WEEK*3+10)
        updater.request()
        await updater.task
        assert published == [ENTRY]
        assert updater.status()['last_checked']==WEEK*3
    asyncio.run(run())


def test_failed_sources_keep_cache_and_back_off(tmp_path):
    async def run():
        now=[WEEK*5]; calls=[]
        class Cached:
            entries=[ENTRY]; updated=1; status=[]
            async def refresh(self):
                calls.append(True)
                self.status=[{'status':'error'}]
        async def publish(entries): raise AssertionError('No successful refresh')
        updater=CatalogUpdates(tmp_path/'state.json',Cached,publish,lambda:now[0])
        updater.request(); await updater.task
        assert updater.status()['last_error'] and updater.status()['entries']==1
        task=updater.task
        updater.request()
        assert updater.task is task and len(calls)==1
        now[0]+=RETRY
        updater.request(); await updater.task
        assert len(calls)==2
    asyncio.run(run())


def test_ingestion_failure_retries_saved_catalog_without_refetch(tmp_path):
    async def run():
        now=[WEEK*3]; calls=[]
        class Cached:
            entries=[ENTRY]; updated=1; status=[]
            async def refresh(self):
                calls.append('refresh'); Cached.updated=now[0]
                self.status=[{'status':'ok'}]
        async def publish(entries):
            calls.append('publish')
            if calls.count('publish')==1: raise httpx.ConnectError('offline')
        updater=CatalogUpdates(tmp_path/'state.json',Cached,publish,lambda:now[0])
        updater.request(); await updater.task
        now[0]+=RETRY
        updater=CatalogUpdates(tmp_path/'state.json',Cached,publish,lambda:now[0])
        updater.request(); await updater.task
        assert calls==['refresh','publish','publish']
        assert not updater.status()['last_error']
    asyncio.run(run())


def test_catalog_refresh_preserves_archived_sets_and_persists_metadata(tmp_path,monkeypatch):
    path=tmp_path/'catalog.json'
    monkeypatch.setattr('app.services.catalog.CACHE',path)
    old=dict(ENTRY,game='Pokemon',language='FR',code='OLD')
    path.write_text(json.dumps({'updated':123,'entries':[old]}),encoding='utf-8')
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=[{'id':'sv99','name':'New set'}])),**kwargs))
    async def publishers(self,client): pass
    monkeypatch.setattr(Catalog,'refresh_publishers',publishers)
    asyncio.run(Catalog().refresh())
    loaded=Catalog()
    assert any(e['code']=='OLD' for e in loaded.entries)
    assert len(loaded.entries)==3 and loaded.updated>123 and len(loaded.status)==2
