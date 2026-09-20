"""Request-triggered weekly refresh: serve durable cache while one task updates it."""
import asyncio
import json
import os
import time
from pathlib import Path

import httpx
from app.services.catalog import Catalog, CACHE

WEEK = 7 * 24 * 60 * 60
RETRY = 60 * 60


class CatalogUpdates:
    def __init__(self, state_path=None, factory=Catalog, publisher=None, clock=time.time):
        self.path = Path(state_path or CACHE.with_name('catalog-refresh.json'))
        self.factory = factory
        self.publisher = publisher or self.publish
        self.clock = clock
        self.task = None

    def read(self):
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def write(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.path)

    def status(self):
        state = self.read()
        catalog = self.factory()
        return dict(state, refreshing=self.task is not None and not self.task.done(),
                    entries=len(catalog.entries), last_checked=catalog.updated or None,
                    next_check=(catalog.updated + WEEK) if catalog.updated else None,
                    interval_seconds=WEEK, sources=catalog.status)

    def request(self, force=False):
        if self.task is not None and not self.task.done():
            return self.status()
        catalog = self.factory()
        state = self.read()
        now = self.clock()
        due = not catalog.entries or now - catalog.updated >= WEEK
        unsynced = state.get('synced_revision') != catalog.updated
        retry_later = state.get('last_error') and now - state.get('last_attempt', 0) < RETRY
        if (due or unsynced or force) and (force or not retry_later):
            self.task = asyncio.create_task(self.run(refresh=due or force))
        return self.status()

    async def run(self, refresh):
        state = self.read()
        state.update(last_attempt=self.clock(), last_error=None)
        self.write(state)
        catalog = self.factory()
        before = {(e['game'], e['language'], e['code']) for e in catalog.entries}
        try:
            if refresh:
                async with asyncio.timeout(180):
                    await catalog.refresh()
                if not any(s['status'] == 'ok' for s in catalog.status):
                    raise ValueError('Sources indisponibles ; catalogue précédent conservé.')
            if not catalog.entries:
                raise ValueError('Aucun catalogue disponible pour le moment.')
            await self.publisher(catalog.entries)
            after = {(e['game'], e['language'], e['code']) for e in catalog.entries}
            state.update(synced_revision=catalog.updated, last_synced=self.clock(),
                         new_sets=len(after-before), last_error=None)
        except (TimeoutError, OSError, ValueError, httpx.HTTPError) as exc:
            state['last_error'] = str(exc) or 'Délai de mise à jour dépassé ; cache conservé.'
        finally:
            self.write(state)

    async def publish(self, entries):
        url = os.getenv('BACKEND_INGEST_URL', 'http://nginx/api/ingest')
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json={'items': [], 'catalog': entries},
                                         headers={'X-Ingest-Token': os.getenv('INGEST_TOKEN', 'dev-change-me')})
            response.raise_for_status()
