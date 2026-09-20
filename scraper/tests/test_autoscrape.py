import asyncio
from argparse import Namespace, ArgumentTypeError
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import autoscrape_cardmarket as cm
from app.deals.service import parse_csv

URL = 'https://www.cardmarket.com/fr/Pokemon/Products/Singles/Base-Set/Pikachu'
HTML = '''<div class="page-title-container"><h1>Pikachu <span>Base Set</span></h1></div>
<div class="info-list-container"><dl><dt>Tendance des prix</dt><dd>1.234,56 €</dd>
<dt>Prix moyen 7 jours</dt><dd>12,50 €</dd></dl></div>
<div class="article-row" id="article-42"><a href="/fr/Pokemon/Users/Alice">Alice</a>
<div class="price-container"><span class="fw-bold">50,00 €</span></div>
<div class="product-attributes"><span>NM</span><span title="French"></span></div></div>'''


def test_upstream_plugin_and_offers_are_separate():
    result = cm.extract(HTML, URL)
    assert result['status'] == 'ok'
    assert result['prices']['price_trend'] == 1234.56
    assert result['prices']['avg_7_days'] == 12.5
    assert len(result['offers']) == 1
    assert result['offers'][0]['price'] == 50
    assert result['offers'][0]['shipping'] is None


def test_verification_and_empty_page_are_not_prices():
    assert cm.extract('<title>Just a moment...</title>' + HTML, URL)['prices'] == {}
    assert cm.extract('<h1>Unavailable</h1>', URL)['status'] == 'no_verified_data'


@pytest.mark.parametrize('url', ['http://www.cardmarket.com/fr/Pokemon/Products/X',
    'https://evil.com/Products/X', 'https://www.cardmarket.com/fr/Pokemon/Products/Search'])
def test_url_validation(url):
    with pytest.raises(ArgumentTypeError):
        cm.product_url(url)


def test_csv_can_be_imported_and_failure_clears_old_output(tmp_path, monkeypatch):
    async def fetch(*args, **kwargs):
        return HTML
    monkeypatch.setattr(cm, 'scrape_with_playwright', fetch)
    args = Namespace(output=tmp_path, urls=[URL], html=None, engine='playwright')
    assert asyncio.run(cm.run(args)) == 0
    rows = parse_csv((tmp_path / 'offers.csv').read_text(encoding='utf-8-sig'))
    assert len(rows) == 1 and rows[0].seller == 'Alice'
    async def fail(*args, **kwargs):
        raise RuntimeError('HTTP 403')
    monkeypatch.setattr(cm, 'scrape_with_playwright', fail)
    assert asyncio.run(cm.run(args)) == 2
    assert 'Alice' not in (tmp_path / 'offers.csv').read_text(encoding='utf-8-sig')
