"""Cached catalogue matching; FR and JP remain separate printings."""
import json
import os
import re
import time
import hashlib
import unicodedata
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from pathlib import Path
import httpx
from app.services.normalizer import _flat

CACHE = Path(os.getenv('CATALOG_CACHE', '/tmp/tcg-catalog.json'))


def match_text(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))


def compact(text):
    return re.sub(r'(?<=[a-z])0+(\d)',r'\1',re.sub(r'[- _]','',match_text(text)))


class Catalog:
    def __init__(self, entries=None):
        self.entries = entries or []
        self.status = []
        self.updated = 0
        if entries is None and CACHE.exists():
            try:
                cached = json.loads(CACHE.read_text(encoding='utf-8'))
                self.entries = cached['entries']
                self.updated = cached.get('updated', 0)
                self.status = cached.get('sources', [])
            except (ValueError, OSError, KeyError):
                pass

    async def refresh(self):
        self.status = []
        async with httpx.AsyncClient(timeout=25) as client:
            for locale, language in [('fr', 'FR'), ('ja', 'JP')]:
                url = f'https://api.tcgdex.net/v2/{locale}/sets'
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, list) or not data:
                        raise ValueError('Empty or invalid catalogue')
                    entries = []
                    for row in data:
                        code = row['id'].upper()
                        if code.startswith('A') or 'PROMO' in code:
                            continue
                        aliases = [row['name'], code]
                        if language == 'FR':
                            for prefix, local in [('SV', 'EV'), ('SWSH', 'EB')]:
                                if code.startswith(prefix) and code[len(prefix):].replace('.', '').isdigit():
                                    aliases.append(local + code[len(prefix):])
                        entries.append(dict(game='Pokemon', language=language, code=code,
                                            name=row['name'], aliases=aliases, source=url))
                    merged = {(e['game'], e['language'], e['code']): e for e in self.entries}
                    merged.update({(e['game'], e['language'], e['code']): e for e in entries})
                    self.entries = list(merged.values())
                    self.status.append({'source': url, 'sets': len(entries), 'status': 'ok'})
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    self.status.append({'source': url, 'status': 'error', 'error': str(exc)})
            await self.refresh_publishers(client)
        if any(source['status'] == 'ok' for source in self.status):
            self.updated = time.time()
        self.save()
        return self.status

    def save(self):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        temporary = CACHE.with_suffix('.tmp')
        temporary.write_text(json.dumps({'updated': self.updated, 'entries': self.entries, 'sources': self.status}, ensure_ascii=False), encoding='utf-8')
        temporary.replace(CACHE)

    async def refresh_publishers(self, client):
        sources = [
            ('One Piece','FR','https://fr.onepiece-cardgame.com/products/?page=1&subcategory=boosters'),
            ('One Piece','JP','https://www.onepiece-cardgame.com/products/?page=1&subcategory=boosters'),
            ('Gundam','JP','https://www.gundam-gcg.com/jp/products/list.php'),
            ('Gundam','EN','https://www.gundam-gcg.com/en/products/list.php'),
            ('Yu-Gi-Oh!','FR','https://www.yugioh-card.com/eu/fr/product-category/boosters/'),
            ('Yu-Gi-Oh!','JP','https://www.yugioh-card.com/japan/products/'),
        ]
        for game, language, source in sources:
            entries={}
            queue=[source]
            seen=set()
            try:
                robots_url=urljoin(source,'/robots.txt')
                response=await client.get(robots_url)
                robots=RobotFileParser()
                if response.status_code not in (200,404):
                    raise ValueError('robots.txt unavailable')
                robots.parse(response.text.splitlines() if response.status_code==200 else [])
                while queue and len(seen)<12:
                    url=queue.pop(0)
                    if url in seen or not robots.can_fetch('TCGRadar',url): continue
                    seen.add(url)
                    response=await client.get(url)
                    response.raise_for_status()
                    soup=BeautifulSoup(response.text,'html.parser')
                    for link in soup.select('a[href]'):
                        target=urljoin(url,link['href'])
                        if urlparse(target).netloc != urlparse(source).netloc: continue
                        label=link.get_text(' ',strip=True)
                        heading=link.select_one('h2,h3,h4,.name,.title')
                        if heading: label=heading.get_text(' ',strip=True)
                        if not label:
                            img=link.select_one('img[alt]')
                            if img: label=img.get('alt','')
                        if re.search(r'[?&]page=\d|/page/\d',target) and target not in seen:
                            queue.append(target)
                        if game=='Yu-Gi-Oh!':
                            if not re.search(r'/products/[^/?#]+/?$',urlparse(target).path) or not 5<len(label)<150: continue
                            if any(x in target.lower() for x in ['structure','starter','accessor','sleeve']): continue
                            code='YGO-'+hashlib.sha1(target.encode()).hexdigest()[:12].upper()
                        else:
                            pattern=r'\b(OP|EB|PRB)[- ]?(\d{2})\b' if game=='One Piece' else r'\b(GD)[- ]?(\d{2})\b'
                            match=re.search(pattern,label+' '+target,re.I)
                            if not match or '/products/' not in target: continue
                            code=match[1].upper()+'-'+match[2]
                            if not label or label.upper() in ('VIEW THIS PRODUCT','詳しく見る'): label=code
                        label=re.split(r'Date de sortie|Release Date|発売日|メーカー希望',label)[0].strip()[:170]
                        entries[code]=dict(game=game,language=language,code=code,name=label,
                                           aliases=[label,code,code.replace('-','')],source=target)
                if not entries: raise ValueError('No sets found; keeping cached catalogue')
                # Keep older entries when the publisher only lists recent releases.
                merged={(e['game'],e['language'],e['code']):e for e in self.entries}
                merged.update({(game,language,code):entry for code,entry in entries.items()})
                self.entries=list(merged.values())
                self.status.append({'source':source,'status':'ok','sets':len(entries)})
            except (httpx.HTTPError,ValueError) as exc:
                self.status.append({'source':source,'status':'error','error':str(exc)})

    def match(self, meta):
        text = ' ' + re.sub(r'[^\w]+', ' ', match_text(meta['title'])) + ' '
        hits = []
        for entry in self.entries:
            if entry['game'] != meta['game'] or (meta['language'] and entry['language'] != meta['language']):
                continue
            aliases = [re.sub(r'[^\w]+', ' ', match_text(a)) for a in entry['aliases']]
            compact_code = compact(meta.get('set_code') or '')
            if any(len(a) >= 3 and ' ' + a + ' ' in text for a in aliases) or (compact_code and compact_code in [compact(a) for a in entry['aliases']]):
                hits.append(entry)
        if len(hits) == 1:
            entry = hits[0]
            meta.update(set_code=entry['code'], set_name=entry['name'], language=entry['language'],
                        catalog_source=entry['source'], canonical=True, confidence=100)
        else:
            meta['canonical'] = False
        return meta
