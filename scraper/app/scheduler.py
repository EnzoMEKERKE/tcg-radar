"""Optional single-worker periodic collection, with retry after startup failures."""
import asyncio
import logging
import os
import httpx

logging.basicConfig(level=logging.INFO)


async def main():
    interval=max(300,int(os.getenv('CRAWL_INTERVAL_SECONDS','21600')))
    async with httpx.AsyncClient(timeout=7200) as client:
        while True:
            delay=interval
            try:
                response=await client.post('http://scraper:8000/crawl',params={
                    'persist':'true','max_pages':int(os.getenv('CRAWL_MAX_PAGES','250'))})
                response.raise_for_status()
                result=response.json()
                logging.info('Collection finished: %s offers; %s',result['offers'],result.get('ingest'))
            except (httpx.HTTPError,ValueError):
                logging.exception('Collection unavailable; retrying in 60 seconds')
                delay=60
            await asyncio.sleep(delay)


asyncio.run(main())
