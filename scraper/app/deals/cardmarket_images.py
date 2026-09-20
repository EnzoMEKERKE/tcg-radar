"""Optional illustrations, joined only by TCGdex's explicit Cardmarket product ID."""
import asyncio
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import httpx


def card_metadata(card):
    product_id = card.get('pricing', {}).get('cardmarket', {}).get('idProduct')
    image = card.get('image', '')
    if not isinstance(product_id, int) or not isinstance(image, str):
        return None
    parsed = urlsplit(image)
    if parsed.scheme != 'https' or parsed.hostname != 'assets.tcgdex.net' or not parsed.path.startswith('/en/'):
        return None
    return str(product_id), {'image_url': image + '/low.webp', 'image_large': image + '/high.webp',
                             'set_name': card.get('set', {}).get('name', ''),
                             'card_number': str(card.get('localId', '')), 'tcgdex_id': card.get('id', '')}


class CardmarketImages:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('CARDMARKET_IMAGE_CACHE', '/data/cardmarket-images.json'))
        self.cards, self.checked, self.tasks = {}, {}, {}
        self.semaphore = asyncio.Semaphore(4)
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            self.cards, self.checked = saved['cards'], saved['checked']
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def enrich(self, rows):
        for row in rows:
            row.update(self.cards.get(str(row['id']), {}))
        # One lookup per distinct printed card name; never guess an image by name alone.
        names = list(dict.fromkeys(re.split(r'\s*[\[(]', row['name'])[0].strip() for row in rows if 'image_url' not in row))
        for name in names:
            if len(self.tasks) >= 2:
                break
            if name and name not in self.tasks and time.time() - self.checked.get(name, 0) > 604800:
                self.tasks[name] = asyncio.create_task(self.fetch_name(name))
        return bool(self.tasks)

    async def fetch_name(self, name):
        complete = True
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get('https://api.tcgdex.net/v2/en/cards', params={'name': 'eq:' + name})
                response.raise_for_status()
                candidates = response.json()
                if not isinstance(candidates, list):
                    raise ValueError('Invalid TCGdex response')

                async def fetch(card):
                    nonlocal complete
                    card_id = card.get('id', '')
                    if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', card_id) or not card.get('image'):
                        return
                    try:
                        async with self.semaphore:
                            result = await client.get('https://api.tcgdex.net/v2/en/cards/' + card_id)
                            result.raise_for_status()
                            metadata = card_metadata(result.json())
                            if metadata:
                                self.cards[metadata[0]] = metadata[1]
                    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                        complete = False

                # Bounded public metadata enrichment, independent of the price response.
                async with asyncio.timeout(100):
                    await asyncio.gather(*(fetch(card) for card in candidates[-200:]))
        except (httpx.HTTPError, ValueError, TypeError, TimeoutError):
            complete = False
        finally:
            # Retry partial failures after an hour, completed lookups after a week.
            self.checked[name] = time.time() if complete else time.time() - 604800 + 3600
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps({'cards': self.cards, 'checked': self.checked}), encoding='utf-8')
                temporary.replace(self.path)
            except OSError:
                pass
            self.tasks.pop(name, None)
