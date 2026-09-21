"""Daily public Cardmarket data. Price-guide records are never seller Listings."""
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlencode

import httpx

BASE = 'https://downloads.s3.cardmarket.com/productCatalog/'
CATALOG_URL = BASE + 'productList/products_singles_6.json'
GUIDE_URL = BASE + 'priceGuide/price_guide_6.json'
PRICE_KEYS = ('low', 'avg', 'trend', 'avg1', 'avg7', 'avg30',
              'low-holo', 'avg-holo', 'trend-holo', 'avg1-holo', 'avg7-holo', 'avg30-holo')


def normalized(value):
    return unicodedata.normalize('NFKD', value.lower()).encode('ascii', 'ignore').decode()


def build_snapshot(catalog, guide):
    if not isinstance(catalog.get('products'), list) or not isinstance(guide.get('priceGuides'), list):
        raise ValueError('Format Cardmarket non reconnu')
    for data in (catalog, guide):
        stamp = datetime.fromisoformat(data['createdAt'])
        if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
            raise ValueError('Date Cardmarket invalide')
    prices = {p['idProduct']: p for p in guide['priceGuides'] if isinstance(p.get('idProduct'), int)}
    rows = []
    for product in catalog['products']:
        pid = product.get('idProduct')
        if not isinstance(pid, int) or pid not in prices or not isinstance(product.get('name'), str):
            continue
        values = {key: value if isinstance(value, (int, float)) and not isinstance(value, bool)
                  and math.isfinite(value) and value > 0 else None
                  for key in PRICE_KEYS for value in [prices[pid].get(key)]}
        if not any(value is not None for value in values.values()):
            continue
        rows.append({'id': pid, 'name': product['name'], 'expansion_id': product.get('idExpansion'),
                     'category': product.get('categoryName'), 'currency': 'EUR', 'prices': values})
    if not rows:
        raise ValueError('Le guide Cardmarket ne contient aucun prix exploitable')
    return {'schema': 1, 'fetched_at': datetime.now(timezone.utc).isoformat(),
            'catalog_date': catalog['createdAt'], 'guide_date': guide['createdAt'],
            'catalog_count': len(catalog['products']), 'guide_count': len(guide['priceGuides']), 'rows': rows}


class CardmarketPrices:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('CARDMARKET_PRICE_CACHE', '/data/cardmarket-prices.json'))
        self.snapshot = None
        self.index = []
        self.by_id = {}
        self.task = None
        self.retry_at = 0
        self.error = None
        try:
            snapshot = json.loads(self.path.read_text(encoding='utf-8'))
            if snapshot.get('schema') == 1 and snapshot.get('rows'):
                datetime.fromisoformat(snapshot['fetched_at'])
                datetime.fromisoformat(snapshot['guide_date'])
                self.install(snapshot)
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def install(self, snapshot):
        self.snapshot = snapshot
        self.index = [(row, normalized(row['name'])) for row in snapshot['rows']]
        self.by_id = {str(row['id']): row for row in snapshot['rows']}

    async def download(self, url):
        async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
            async with client.stream('GET', url) as response:
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 60_000_000:
                        raise ValueError('Fichier Cardmarket trop volumineux')
                    chunks.append(chunk)
        return json.loads(b''.join(chunks))

    async def refresh(self):
        try:
            async with asyncio.timeout(60):
                catalog, guide = await asyncio.gather(self.download(CATALOG_URL), self.download(GUIDE_URL))
            snapshot = build_snapshot(catalog, guide)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            temporary.replace(self.path)
            self.install(snapshot)
            self.error = None
        except (OSError, ValueError, KeyError, TypeError, TimeoutError, httpx.HTTPError):
            self.error = 'Le téléchargement Cardmarket a échoué. Nouvelle tentative automatique dans cinq minutes.'
            self.retry_at = time.time() + 300

    def search(self, query='', page=1, limit=24, min_price=None, max_price=None,
               expansion=None, metric='trend', variant='standard', sort='recent'):
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValueError('Le prix minimum doit être inférieur ou égal au maximum.')
        now = datetime.now(timezone.utc)
        age = (now - datetime.fromisoformat(self.snapshot['fetched_at'])).total_seconds() if self.snapshot else float('inf')
        if age >= 86400 and time.time() >= self.retry_at and (self.task is None or self.task.done()):
            self.task = asyncio.create_task(self.refresh())
        refreshing = bool(self.task and not self.task.done())
        if not self.snapshot:
            return {'status': 'loading' if refreshing else 'unavailable', 'rows': [], 'total': 0,
                    'refreshing': refreshing, 'message': self.error or 'Téléchargement du catalogue et du guide Cardmarket…'}
        terms = normalized(query).split()
        matches = [row for row, name in self.index if all(term in name or term == str(row['id']) for term in terms)]
        expansions = {}
        for row in matches:
            if row['expansion_id'] is not None:
                expansions[row['expansion_id']] = expansions.get(row['expansion_id'], 0) + 1
        price_key = metric + ('-holo' if variant == 'holo' else '')
        if expansion is not None:
            matches = [row for row in matches if row['expansion_id'] == expansion]
        if variant == 'holo':
            matches = [row for row in matches if any(row['prices'].get(key) is not None for key in PRICE_KEYS if key.endswith('-holo'))]
        if min_price is not None or max_price is not None:
            matches = [row for row in matches if row['prices'].get(price_key) is not None
                       and (min_price is None or row['prices'][price_key] >= min_price)
                       and (max_price is None or row['prices'][price_key] <= max_price)]
        if sort in ('price_asc', 'price_desc'):
            matches.sort(key=lambda row: (row['prices'].get(price_key) is None,
                (row['prices'].get(price_key) or 0) * (-1 if sort == 'price_desc' else 1), row['id']))
        elif sort == 'name':
            matches.sort(key=lambda row: (normalized(row['name']), row['id']))
        else:
            matches.sort(key=lambda row: row['id'], reverse=True)
        page = min(page, max(1, math.ceil(len(matches)/limit)))
        selected = []
        for row in matches[(page-1)*limit:page*limit]:
            search_name = re.sub(r'\[.*?\]', '', row['name']).strip()
            shown_key = price_key
            if row['prices'].get(shown_key) is None:
                for fallback in (('low-holo', 'avg-holo', 'trend-holo') if variant == 'holo' else ('low', 'avg', 'trend')):
                    if row['prices'].get(fallback) is not None:
                        shown_key = fallback
                        break
            selected.append(dict(row, selected_price=row['prices'].get(shown_key), selected_price_key=shown_key,
                                 product_url='https://www.cardmarket.com/fr/Pokemon/Products?'+urlencode({'idProduct': row['id']}),
                                 search_url='https://www.cardmarket.com/fr/Pokemon/Products/Search?'+urlencode({'searchString': search_name})))
        source_age = (now - datetime.fromisoformat(self.snapshot['guide_date'])).total_seconds()
        return {**{key: value for key, value in self.snapshot.items() if key != 'rows'},
                'status': 'stale' if age >= 86400 or source_age > 172800 else 'ok',
                'refreshing': refreshing, 'message': self.error, 'total': len(matches),
                'indexed_count': len(self.index), 'page': page, 'limit': limit, 'rows': selected,
                'price_key': price_key, 'expansions': [{'id': key, 'count': value} for key, value in sorted(expansions.items())],
                'sources': {'catalog': CATALOG_URL, 'prices': GUIDE_URL}}
