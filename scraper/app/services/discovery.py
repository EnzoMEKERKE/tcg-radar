"""Discover candidate shops by set, without treating search snippets as prices."""
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from app.config.stores import STORES


class DiscoveryQuery(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    game: Literal['Pokemon', 'One Piece', 'Yu-Gi-Oh!', 'Gundam']
    name: str = Field(min_length=1, max_length=180)
    code: str = Field(default='', max_length=50)
    language: Literal['FR', 'JP', 'EN', 'UNK', 'OTHER'] = 'FR'
    keywords: str = Field(default='', max_length=80)
    include_prices: bool = False


def queries_for(query):
    name = ' '.join(query.name.replace('"', '').split())
    name = re.sub(r'\s*\[[A-Za-z0-9 -]+\]', '', name).strip() or name
    code = query.code if not query.code.startswith(('UNKNOWN', 'UNMATCHED-', 'YGO-')) else ''
    identity = f'{query.game} "{name}"'
    by_code = f'{query.game} {code}' if code else identity
    variants = {
        'FR': ['display français acheter', 'boîte de boosters FR', 'case carton displays français'],
        'JP': ['booster box Japanese buy', 'display japonais acheter', 'BOX 日本語 通販'],
        'EN': ['booster box English buy', 'sealed display English', 'case booster boxes English'],
    }.get(query.language, ['display acheter', 'booster box buy', 'case displays'])
    extra = ' '.join(query.keywords.split())
    return list(dict.fromkeys(f'{base} {suffix} {extra}'.strip()
        for base, suffix in [(identity, variants[0]), (by_code, variants[1]), (identity, variants[2])]))


def clean_url(value):
    """Filter display links; product fetching additionally validates and pins public DNS."""
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower().rstrip('.')
        if parts.scheme not in ('https', 'http') or parts.username or parts.password or not host:
            return None
        if parts.port not in (None, 80, 443) or '.' not in host or host.endswith(('.local', '.localhost', '.internal', '.test', '.invalid')) or host == 'localhost':
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                  if not k.lower().startswith('utm_') and k.lower() not in ('gclid', 'fbclid', 'msclkid')]
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or '/', urlencode(params), ''))
    except (TypeError, ValueError):
        return None


def domain_of(url):
    return (urlsplit(url).hostname or '').lower().removeprefix('www.')


def normalized(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()


def relevance_for(title, query):
    """Conservative hints from the title, never evidence of stock or seller reliability."""
    title_words = normalized(title)
    compact_code = re.sub(r'[^a-z0-9]', '', query.code.lower())
    code_pattern = r'(?<![a-z0-9])' + r'[\s-]*'.join(map(re.escape, compact_code)) + r'(?![a-z0-9])'
    code_match = bool(compact_code and not query.code.startswith(('UNKNOWN', 'UNMATCHED-', 'YGO-'))
                      and re.search(code_pattern, title.casefold()))
    name = normalized(query.name)
    name_match = bool(name and re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', title_words))
    # Short names and non-Latin names are still useful when present verbatim.
    name_match = name_match or bool(re.search(r'(?<!\w)' + re.escape(query.name.casefold()) + r'(?!\w)', title.casefold()))
    languages = []
    for language, pattern in {
        'FR': r'\b(fr|francais|francaise|french)\b',
        'JP': r'\b(jp|jpn|japonais|japonaise|japanese)\b',
        'EN': r'\b(anglais|anglaise|english|eng|us)\b|\ben\s*$',
    }.items():
        if (re.search(pattern, title_words) or (language == 'JP' and '日本語' in title)
                or (language == 'EN' and re.search(r'\bEN\b', title))):
            languages.append(language)
    language_match = ('unknown' if not languages or query.language not in ('FR', 'JP', 'EN') else
                      'match' if languages == [query.language] else
                      'ambiguous' if query.language in languages else 'mismatch')
    packaging = 'case' if re.search(r'\b(case|carton)\b', title_words) else (
        'display' if re.search(r'\b(displays?|booster box|boite de boosters)\b', title_words) else 'unknown')
    identity = code_match or name_match
    score = 4 * int(identity) + int(language_match == 'match') + int(packaging != 'unknown')
    return dict(set_match=identity, language_match=language_match, detected_languages=languages,
                packaging=packaging, relevance_score=score,
                relevance='mismatch' if language_match == 'mismatch' else 'likely' if identity else 'uncertain')


def candidates_from(results, query=None, limit=30, domain_limit=3):
    known = {domain_of(store['url']) for store in STORES}
    candidates = {}
    per_domain = {}
    for result in results:
        url = clean_url(result.get('url', ''))
        if not url or url in candidates:
            continue
        domain = domain_of(url)
        candidates[url] = {
            'url': url, 'domain': domain, 'title': str(result.get('title') or domain)[:220],
            'snippet': str(result.get('content') or result.get('description') or '')[:400],
            'known_store': domain in known, 'status': 'unverified',
        }
        if query:
            candidates[url].update(relevance_for(candidates[url]['title'], query))
    # Rank before limiting each domain, so early irrelevant hits do not displace better ones.
    ranked = sorted(candidates.values(), key=lambda item: (
        item.get('relevance') == 'mismatch', -item.get('relevance_score', 0), item['known_store']))
    selected = []
    for item in ranked:
        domain = item['domain']
        if per_domain.get(domain, 0) >= domain_limit:
            continue
        per_domain[domain] = per_domain.get(domain, 0) + 1
        selected.append(item)
        if len(selected) == limit:
            break
    return selected


class Discovery:
    def __init__(self, cache_path=None, transport=None):
        self.path = Path(cache_path or os.getenv('DISCOVERY_CACHE', '/tmp/tcg-discovery.sqlite'))
        self.transport = transport
        self.lock = asyncio.Lock()

    @contextmanager
    def cache(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        try:
            connection.execute('CREATE TABLE IF NOT EXISTS search_cache (key TEXT PRIMARY KEY, expires REAL NOT NULL, payload TEXT NOT NULL)')
            with connection:
                yield connection
        finally:
            connection.close()

    async def search(self, query):
        queries = queries_for(query)
        # A short code query survives catalogue decorations and translated set names.
        if query.code and not query.code.startswith(('UNKNOWN', 'UNMATCHED-', 'YGO-')):
            language = {'FR': 'French', 'JP': 'Japanese', 'EN': 'English'}.get(query.language, '')
            compact_code = re.sub(r'[^a-zA-Z0-9]', '', query.code)
            queries = list(dict.fromkeys([f'{query.game} {compact_code} booster box {language} {query.keywords}'.strip()] + queries))
        pages = max(1, min(5, int(os.getenv('DISCOVERY_PAGES', '3'))))
        limit = max(30, min(200, int(os.getenv('DISCOVERY_MAX_RESULTS', '120'))))
        provider = 'brave' if os.getenv('BRAVE_SEARCH_API_KEY') else 'searxng'
        endpoint = os.getenv('SEARXNG_URL', '').rstrip('/')
        request_limit = 6
        key = hashlib.sha256(json.dumps([7, provider, endpoint, queries, pages, limit, query.model_dump()], ensure_ascii=False).encode()).hexdigest()
        async with self.lock:
            with self.cache() as db:
                cached = db.execute('SELECT payload FROM search_cache WHERE key=? AND expires>?', (key, time.time())).fetchone()
            if cached:
                return dict(json.loads(cached[0]), cached=True)
            result = {'queries': queries, 'candidates': [], 'cached': False, 'provider': provider, 'errors': [], 'searched_at': int(time.time())}
            if provider == 'searxng' and not endpoint:
                result.update(status='unconfigured', message='La recherche intégrée n’est pas configurée. Les liens de recherche web restent disponibles.')
                return result
            rows = []
            successes = 0
            attempted = 0
            semaphore = asyncio.Semaphore(2)
            known_urls = set()
            async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
                async def run_query(index, terms, page):
                    nonlocal successes, attempted
                    if attempted >= request_limit:
                        return False
                    attempted += 1
                    try:
                        async with semaphore:
                            if provider == 'brave':
                                response = await client.get('https://api.search.brave.com/res/v1/web/search',
                                    params={'q': terms, 'count': 20, 'offset': page - 1}, headers={'X-Subscription-Token': os.environ['BRAVE_SEARCH_API_KEY']})
                            else:
                                response = await client.get(endpoint + '/search', params={'q': terms, 'format': 'json', 'categories': 'general', 'pageno': page})
                        response.raise_for_status()
                        data = response.json()
                        found = data.get('web', {}).get('results', []) if provider == 'brave' else data.get('results', [])
                        if not isinstance(found, list):
                            raise ValueError('Invalid search response')
                        rows.extend(row for row in found if isinstance(row, dict))
                        successes += 1
                        urls = {row.get('url') for row in found if isinstance(row, dict) and row.get('url')}
                        new_urls = urls - known_urls
                        known_urls.update(urls)
                        if data.get('unresponsive_engines'):
                            result['errors'].append({'query': index, 'reason': 'Certains moteurs ne répondent pas.'})
                        return bool(new_urls)
                    except (httpx.HTTPError, ValueError, AttributeError):
                        result['errors'].append({'query': index, 'reason': 'Recherche indisponible ou limitée par le moteur.'})
                        return False
                try:
                    async with asyncio.timeout(18):
                        active = list(enumerate(queries))
                        for page in range(1, pages + 1):
                            if not active or attempted >= request_limit:
                                break
                            outcomes = await asyncio.gather(*(run_query(index, terms, page) for index, terms in active))
                            active = [item for item, more in zip(active, outcomes) if more]
                except TimeoutError:
                    result['errors'].append({'reason': 'Certains moteurs ont dépassé le délai de recherche.'})
            result['candidates'] = candidates_from(rows, query, limit=limit, domain_limit=6)
            result['coverage'] = {'search_pages': pages, 'result_limit': limit, 'raw_results': len(rows), 'completed_requests': successes, 'attempted_requests': attempted}
            if query.include_prices:
                from app.services.web_prices import WebPrices
                checked = list(result['candidates'])
                await WebPrices().enrich(result['candidates'], query)
                result['excluded_stock_urls'] = [row['url'] for row in checked if row.get('stock_status') in ('out_of_stock', 'preorder')]
                result['priced_count'] = sum(row.get('price_status') == 'read' for row in result['candidates'])
                result['comparable_count'] = sum(row.get('comparable', False) for row in result['candidates'])
                result['price_basis'] = 'unit_eur_excluding_shipping_and_import'
            result['cache_ttl_seconds'] = 300 if query.include_prices else 3600
            result['status'] = ('partial' if result['candidates'] else 'unavailable') if result['errors'] else ('ok' if successes else 'unavailable')
            if not result['candidates'] and result['errors']:
                result['message'] = 'Les moteurs de recherche sont temporairement indisponibles. Cela ne signifie pas que ce produit est introuvable.'
            # An HTTP 200 carrying only blocked engines is NOT a successful search.
            # Never preserve an empty outage as a five-minute negative result.
            if successes and result['candidates']:
                with self.cache() as db:
                    db.execute('DELETE FROM search_cache WHERE expires<?', (time.time(),))
                    db.execute('INSERT OR REPLACE INTO search_cache VALUES (?,?,?)',
                               (key, time.time()+result['cache_ttl_seconds'], json.dumps(result, ensure_ascii=False)))
                    db.execute('DELETE FROM search_cache WHERE key NOT IN (SELECT key FROM search_cache ORDER BY expires DESC LIMIT 500)')
            else:
                result['cache_ttl_seconds'] = 0
            return result
