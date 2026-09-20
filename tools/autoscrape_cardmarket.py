"""Bounded Cardmarket capture using DrankRock/AutoScrape and its price plugin."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT / 'tools'))
from autoscrape_vendor.cardmarket_parser import CardmarketPricePlugin
from autoscrape_vendor.playwrightPy import scrape_with_playwright
from app.deals.browser import access_gate
from app.deals.parsers import parse_cardmarket
from bs4 import BeautifulSoup

REVISION = 'd5e8afd3f03907ad693451651ab1659fdcb889fb'
FIELDS = ['source', 'title', 'url', 'price', 'currency', 'shipping', 'language',
          'condition', 'card_number', 'set_code', 'variant', 'sold', 'sold_at',
          'observed_at', 'available', 'seller', 'listing_id', 'price_exact']


def product_url(value):
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname == 'www.cardmarket.com'
                 and not parsed.username and not parsed.password and parsed.port in (None, 443)
                 and '/Products/' in parsed.path and '/Search' not in parsed.path)
    except ValueError:
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError('Une URL HTTPS de fiche produit www.cardmarket.com est requise.')
    return value


def extract(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    gate = access_gate(url, soup.title.get_text() if soup.title else '')
    if gate or soup.select_one('#challenge-running, #challenge-form'):
        return {'status': 'verification_required', 'prices': {}, 'offers': []}
    prices = {field.name: field.value for field in CardmarketPricePlugin().parse(html)
              if field.found and not (isinstance(field.value, float) and field.value <= 0)}
    # Only Pokemon singles are supported by the existing deals identity matcher.
    offers = [row.model_dump(mode='json') for row in parse_cardmarket(html, url)] if '/Pokemon/Products/Singles/' in urlsplit(url).path else []
    has_prices = any(key in prices for key in ('lowest_price', 'price_trend', 'avg_30_days', 'avg_7_days', 'avg_1_day'))
    return {'status': 'ok' if offers or has_prices else 'no_verified_data',
            'prices': prices, 'offers': offers}


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    reports = []
    for index, url in enumerate(dict.fromkeys(args.urls)):
        if index and not args.html:
            await asyncio.sleep(3)
        report = {'url': url, 'observed_at': datetime.now(timezone.utc).isoformat()}
        try:
            html = args.html.read_text(encoding='utf-8') if args.html else await scrape_with_playwright(
                url, engine=args.engine, headless=True, timeout=30000,
                user_agents_file=str(args.output / 'user-agents.txt'), simulate_human=False)
            filename = hashlib.sha256(url.encode()).hexdigest()[:16] + '.html'
            (args.output / filename).write_text(html, encoding='utf-8')
            report.update(extract(html, url))
            report['html'] = filename
            report['input'] = 'html_file' if args.html else 'live'
            if args.html:
                for offer in report['offers']:
                    offer['observed_at'] = datetime.fromtimestamp(args.html.stat().st_mtime, timezone.utc).isoformat()
        except Exception as error:
            report.update(status='fetch_failed', error=str(error), prices={}, offers=[])
        reports.append(report)
        print(f"{report['status']}: {url} ({len(report['offers'])} offres)")
    (args.output / 'report.json').write_text(json.dumps(
        {'upstream_revision': REVISION, 'engine': args.engine, 'pages': reports},
        ensure_ascii=False, indent=2), encoding='utf-8')
    with (args.output / 'offers.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction='ignore')
        writer.writeheader()
        for report in reports:
            writer.writerows(report['offers'])
    return 0 if all(report['status'] == 'ok' for report in reports) else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls', nargs='+', type=product_url)
    parser.add_argument('--engine', choices=['playwright', 'playwright-stealth', 'puppeteer-compat'], default='playwright')
    parser.add_argument('--html', type=Path, help='Parse an existing HTML capture instead of fetching')
    parser.add_argument('--output', type=Path, default=ROOT / '.autoscrape')
    args = parser.parse_args()
    if len(args.urls) > 10 or (args.html and len(args.urls) != 1):
        parser.error('10 URL maximum ; une seule URL avec --html.')
    return asyncio.run(run(args))


if __name__ == '__main__':
    raise SystemExit(main())
