import asyncio
import pytest
from app.services.origin import origin_for, merge_origins, policy_links, describe
from app.services.web_prices import WebPrices
from app.services.discovery import DiscoveryQuery


@pytest.mark.parametrize('text', [
    'Japanese Pokemon display. Made in Japan. Livraison en France.',
    'Boutique française, prix EUR TTC, adresse Paris France.',
    'We do not ship from Japan.', 'Orders may ship from Japan.',
    'We ship from Japan or Germany.', 'Ships to Japan.',
    'Do you ship from Japan? No.', 'Expédié depuis la France ?',
])
def test_no_origin_guessed(text):
    row = origin_for('https://shop.fr/product', '<p>'+text+'</p>')
    assert row['country'] is None and row['tax_status'] == 'unknown'


@pytest.mark.parametrize('text,country,tax', [
    ('Expédié depuis la France.', 'FR', 'eu'),
    ('Livraison rapide depuis la France.', 'FR', 'eu'),
    ('All orders are dispatched from our headquarters in Japan.', 'JP', 'possible'),
    ('Ships from Germany.', 'DE', 'eu'),
    ('Ships from Switzerland.', 'CH', 'possible'),
    ('Ships from United Kingdom.', 'GB', 'possible'),
])
def test_explicit_shipping_statements(text, country, tax):
    row = origin_for('https://shop.example/product', '<p>'+text+'</p>')
    assert row['country'] == country and row['tax_status'] == tax
    assert row['sources'][0]['url'] == 'https://shop.example/product'


def test_conflicts_do_not_claim_no_tax():
    first = origin_for('https://shop.example/product', 'Ships from France.')
    second = origin_for('https://shop.example/shipping', 'Ships from Japan.')
    row = merge_origins(first, second)
    assert row['country'] is None and row['tax_status'] == 'unknown'
    assert len(row['sources']) == 2


def test_reviewed_sources_destination_and_multiple_warehouses():
    assert origin_for('https://www.nippontcg.fr/product')['country'] == 'FR'
    row = origin_for('https://japantcgdirect.com/products/box')
    assert row['country'] == 'JP' and row['tax_status'] == 'extra'
    # US-inclusive duties cannot become a promise for France.
    row = origin_for('https://japanese-tcg.com/product', 'Ships from Japan. Duties included for USA.')
    assert row['country'] is None and row['tax_status'] == 'unknown'
    assert origin_for('https://nippontcg.fr.evil.example/product')['country'] is None


def test_policy_links_same_domain_only():
    html = '<a href="/shipping">Shipping</a><a href="https://evil.example/shipping">Shipping</a><a href="/checkout?shipping=1">Shipping</a><a href="/faq">FAQ</a>'
    assert policy_links(html, 'https://shop.example/product') == ['https://shop.example/shipping', 'https://shop.example/faq']


def test_policy_enrichment_shared_per_domain_even_without_price(monkeypatch):
    async def rates(): return {'EUR': 1}
    monkeypatch.setattr('app.services.web_prices.eur_rates', rates)
    calls = []
    class Pages:
        async def product(self, url):
            calls.append(url)
            return ('<p>Ships from Japan.</p>' if url.endswith('/shipping') else '<a href="/shipping">Shipping</a>'), url
    rows = [{'url': 'https://shop.example/'+str(i)} for i in range(3)]
    query = DiscoveryQuery(game='One Piece', name='OP09', code='OP09')
    result = asyncio.run(WebPrices(Pages()).enrich(rows, query))
    assert all(row['shipping_origin']['country'] == 'JP' for row in result)
    assert calls.count('https://shop.example/shipping') == 1
    assert all(row['price_status'] == 'unavailable' for row in result)
