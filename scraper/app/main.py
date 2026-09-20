from fastapi import FastAPI, Query, HTTPException
from app.config.stores import STORES
from app.connectors.registry import make_connector, PROFILES
from app.services.catalog import Catalog
from app.services.fx import eur_rates
from app.services.shipping import shipping_for
from app.services.discovery import Discovery, DiscoveryQuery
from app.services.catalog_updates import CatalogUpdates
from app.deals.models import Settings as DealSettings, ImportRequest
from app.deals.service import DealsService
import asyncio
import os
import httpx

app = FastAPI(title='TCG Radar Collector', version='5.0')
lock = asyncio.Lock()
last_run = {}
discovery = Discovery()
catalog_updates = CatalogUpdates()
deals = DealsService()


@app.get('/deals/browser')
async def browser_status():
    from app.deals.local_browser import local_status
    return await local_status()


@app.post('/deals/browser')
async def prepare_browser(settings: DealSettings):
    from app.deals.local_browser import local_prepare
    return await local_prepare(settings.query)


@app.post('/deals/search')
async def search_deals(settings: DealSettings):
    try:
        return deals.start(settings)
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.get('/deals/status/{job_id}')
def deals_status(job_id: str):
    result = deals.status(job_id)
    if result is None:
        raise HTTPException(404, 'Analyse introuvable')
    return result


@app.post('/deals/import')
def import_deals(request: ImportRequest):
    try:
        return deals.imported(request)
    except ValueError as error:
        raise HTTPException(422, str(error))


@app.post('/discover')
async def discover(query: DiscoveryQuery):
    if discovery.lock.locked():
        raise HTTPException(409, 'A search is already running')
    catalog_updates.request()
    result = await discovery.search(query)
    return dict(result, catalog_status=catalog_updates.status())

@app.get('/health')
def health():
    return {'ok': True, 'stores': len(STORES), 'collector': 'merchant-v5'}

@app.get('/stores')
def stores():
    return [dict(s, connector='dedicated' if s['name'] in PROFILES else 'structured') for s in STORES]

@app.get('/status')
def status():
    return last_run

@app.get('/catalog')
def catalog():
    return Catalog().entries


@app.get('/catalog/status')
def catalog_status():
    return catalog_updates.status()


@app.post('/catalog/refresh')
async def refresh_catalog(force: bool = False):
    return catalog_updates.request(force=force)

async def collect(max_pages, selected=None):
    semaphore = asyncio.Semaphore(int(os.getenv('STORE_CONCURRENCY', '4')))
    async def run(store):
        async with semaphore:
            connector = make_connector(store, max_pages=max_pages)
            try:
                items = await connector.crawl()
                return items, dict(store=store['name'], offers=len(items), requests=connector.requests,
                                   failures=connector.failures, blocked=connector.blocked,
                                   browser_pages=connector.browser.pages, browser_errors=connector.browser.errors,
                                     budget_exhausted=connector.requests >= max_pages,
                                     remaining_urls=connector.remaining_urls,
                                   status='ok' if items else 'empty')
            except Exception as error:
                return [], dict(store=store['name'], offers=0, status='error', error=str(error))
    results = await asyncio.gather(*(run(s) for s in STORES if not selected or s['name'] in selected))
    return [x for items, report in results for x in items], [report for items, report in results]

async def enrich(items, catalogue):
    rates = await eur_rates()
    output = []
    for item in items:
        store = next(s for s in STORES if s['name'] == item['store'])
        currency = item.get('currency', 'EUR').upper()
        if currency not in rates:
            continue
        item['store_url'] = store['url']
        item['price_eur'] = round(float(item['price']) * rates[currency], 2)
        configured_shipping = shipping_for(store, item['price_eur'])
        item['shipping_eur'] = configured_shipping if configured_shipping is not None else item.get('shipping_eur')
        item['meta'] = catalogue.match(item['meta'])
        origin = item.get('shipping_origin', {})
        item['vat_included'] = origin.get('tax_status') in ('eu', 'included')
        item['landed_cost_confidence'] = 'medium' if item['shipping_eur'] is not None else 'low'
        output.append(item)
    return output

@app.post('/crawl')
async def crawl(max_pages: int = Query(1000, ge=1, le=1000), persist: bool = False,
                stores: str = '', refresh_catalog: bool = True):
    if lock.locked():
        raise HTTPException(409, 'A crawl is already running')
    selected = [s.strip() for s in stores.split(',') if s.strip()]
    if set(selected) - {s['name'] for s in STORES}:
        raise HTTPException(400, 'Unknown store name')
    async with lock:
        catalogue = Catalog()
        if refresh_catalog:
            catalog_updates.request()
            if catalog_updates.task is not None:
                await asyncio.shield(catalog_updates.task)
            catalogue = Catalog()
        items, reports = await collect(max_pages, selected)
        flat = await enrich(items, catalogue)
        result = {'stores': len(reports), 'offers': len(flat), 'reports': reports,
                  'catalog_sources': catalogue.status, 'items': flat}
        if persist:
            url = os.getenv('BACKEND_INGEST_URL', 'http://nginx/api/ingest')
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(url, json={'items': flat, 'catalog': catalogue.entries},
                                                 headers={'X-Ingest-Token': os.getenv('INGEST_TOKEN', 'dev-change-me')})
                    response.raise_for_status()
                    result['ingest'] = response.json()
            except httpx.HTTPError as error:
                raise HTTPException(502, f'Collection succeeded, ingestion failed: {error}') from error
        last_run.clear()
        last_run.update({k: v for k, v in result.items() if k != 'items'})
        return result
