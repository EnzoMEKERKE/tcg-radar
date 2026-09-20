"""Real Chromium fixture and read-only live collection; run inside scraper image."""
import asyncio
import json
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from app.connectors.merchant import MerchantConnector
from app.main import collect


async def main():
    c = MerchantConnector({'name': 'Fixture', 'url': 'https://shop.test', 'currency': 'EUR'}, 20)
    c.robots.parse(['User-agent: *', 'Disallow: /private'])
    visited = []
    def response(request):
        visited.append(request.url.path)
        return httpx.Response(200, json={'@type': 'Product', 'name': 'One Piece OP09 FR display', 'offers': {'price': 99, 'priceCurrency': 'EUR', 'availability': 'https://schema.org/InStock'}})
    html = '''<h1>Loading</h1><script>
    fetch('/data').then(r=>r.json()).then(data=>{let s=document.createElement('script');s.type='application/ld+json';s.textContent=JSON.stringify(data);document.body.appendChild(s)});
    fetch('/private');fetch('https://other.test/data');
    </script>'''
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            rendered = await c.browser.render(c, client, c.base + '/box', html)
        rows = c.parse_product(BeautifulSoup(rendered, 'html.parser'), c.base + '/box')
        assert len(rows) == 1 and rows[0]['price'] == 99
        assert visited == ['/data'] and c.blocked == 2 and c.browser.errors == 0
    finally:
        await c.browser.close()
    print('Chromium: JS product extracted; disallowed and off-domain requests blocked.', flush=True)
    items, reports = await collect(60, ['Ludotrotter', 'UltraJeux', 'Japan TCG Direct'])
    result = {'offers': len(items), 'reports': reports, 'items': items}
    Path('/validation/expanded-live.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'offers': len(items), 'reports': reports}), flush=True)


asyncio.run(main())
