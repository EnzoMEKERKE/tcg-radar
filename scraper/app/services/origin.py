"""Shipping origin is evidence, never a deduction from language, currency or TLD."""
import re
import unicodedata
from datetime import date
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

EU = set('FR DE BE NL ES IT PT AT IE LU FI SE DK PL CZ SK SI HR HU RO BG GR CY MT LT LV EE'.split())
COUNTRIES = {
    'FR': ('France', r'france(?: metropolitaine)?'), 'JP': ('Japon', r'japan|japon'),
    'US': ('États-Unis', r'united states|usa|etats-unis'), 'GB': ('Royaume-Uni', r'united kingdom|uk|royaume-uni'),
    'DE': ('Allemagne', r'germany|allemagne'), 'BE': ('Belgique', r'belgium|belgique'),
    'NL': ('Pays-Bas', r'netherlands|pays-bas'), 'ES': ('Espagne', r'spain|espagne'),
    'IT': ('Italie', r'italy|italie'), 'PT': ('Portugal', r'portugal'),
    'PL': ('Pologne', r'poland|pologne'), 'CH': ('Suisse', r'switzerland|suisse'),
    'AT': ('Autriche', r'austria|autriche'), 'IE': ('Irlande', r'ireland|irlande'),
    'LU': ('Luxembourg', r'luxembourg'), 'FI': ('Finlande', r'finland|finlande'),
    'SE': ('Suède', r'sweden|suede'), 'DK': ('Danemark', r'denmark|danemark'),
    'CZ': ('Tchéquie', r'czech republic|czechia|tchequie'), 'SK': ('Slovaquie', r'slovakia|slovaquie'),
    'SI': ('Slovénie', r'slovenia|slovenie'), 'HR': ('Croatie', r'croatia|croatie'),
    'HU': ('Hongrie', r'hungary|hongrie'), 'RO': ('Roumanie', r'romania|roumanie'),
    'BG': ('Bulgarie', r'bulgaria|bulgarie'), 'GR': ('Grèce', r'greece|grece'),
    'CY': ('Chypre', r'cyprus|chypre'), 'MT': ('Malte', r'malta|malte'),
    'LT': ('Lituanie', r'lithuania|lituanie'), 'LV': ('Lettonie', r'latvia|lettonie'),
    'EE': ('Estonie', r'estonia|estonie'),
    'CN': ('Chine', r'china|chine'), 'HK': ('Hong Kong', r'hong kong'),
    'CA': ('Canada', r'canada'), 'AU': ('Australie', r'australia|australie'),
}
CUSTOMS_SOURCE = 'https://www.douane.gouv.fr/demarche/vous-achetez-sur-internet'

# Reviewed merchant declarations, not independent guarantees. Expire after 90 days.
# Destination-specific: US DDP promises must NEVER be applied to France.
REVIEWED = {
    'nippontcg.fr': dict(country='FR', tax='unknown', checked='2026-09-19',
        url='https://www.nippontcg.fr/', summary='La boutique annonce une livraison depuis la France.'),
    'japantcgdirect.com': dict(country='JP', tax='extra', checked='2026-09-19',
        url='https://japantcgdirect.com/policies/shipping-policy',
        summary='Départ du Japon ; pour l’Union européenne, la TVA d’import reste à la charge du destinataire.'),
    'japanese-tcg.com': dict(country=None, tax='unknown', checked='2026-09-19',
        url='https://japanese-tcg.com/',
        summary='Stocks au Japon et aux États-Unis. Les engagements de droits inclus concernent les États-Unis ; la France reste à confirmer.'),
}


def folded(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def describe(country=None, tax='unknown', sources=None, status='unknown'):
    region = 'EU' if country in EU else 'outside_eu' if country else 'unknown'
    if region == 'EU':
        tax = 'eu'
        message = 'Pas de frais d’import normalement attendus en France métropolitaine pour un envoi depuis l’UE, hors territoires à régime particulier.'
    elif tax == 'included':
        message = 'Frais d’import annoncés inclus pour la France ; vérifier cette prise en charge au paiement.'
    elif tax == 'extra':
        message = 'TVA d’import à prévoir ; droits éventuels et frais du transporteur peuvent s’ajouter.'
    elif region == 'outside_eu':
        tax = 'possible'
        message = 'Envoi hors UE : TVA, droits éventuels et frais du transporteur possibles. Leur prépaiement n’est pas confirmé.'
    else:
        message = 'Pays de départ non confirmé : impossible de conclure sur les frais d’import.'
    return dict(country=country, country_label=COUNTRIES.get(country, (country,))[0] if country else 'À confirmer',
                region=region, status=status, tax_status=tax, tax_message=message,
                destination='FR_METROPOLITAN', sources=sources or [], customs_source=CUSTOMS_SOURCE)


def origin_for(url, html=None):
    host = (urlsplit(url).hostname or '').removeprefix('www.')
    reviewed = REVIEWED.get(host)
    if reviewed and not 0 <= (date.today() - date.fromisoformat(reviewed['checked'])).days <= 90:
        reviewed = None
    country = reviewed['country'] if reviewed else None
    tax = reviewed['tax'] if reviewed else 'unknown'
    sources = [dict(url=reviewed['url'], evidence=reviewed['summary'], checked_at=reviewed['checked'], kind='reviewed_policy')] if reviewed else []
    status = 'merchant_declared' if country else 'conflicting' if reviewed else 'unknown'
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        for node in soup.select('script, style, noscript, nav'):
            node.decompose()
        text = re.sub(r'\s+', ' ', soup.get_text(' ', strip=True))
        found = {}
        # Require an actual shipping statement, never "Japanese cards", an address,
        # "made in Japan", delivery TO a country, or a merchant's name.
        for sentence in re.findall(r'[^.!?;\n]+[.!?;]?', text):
            simple = folded(sentence)
            if sentence.rstrip().endswith('?'):
                continue
            if re.search(r'\b(not|never|may|might|if|example|ne|pas|peut|peuvent|selon|soit|or|ou)\b', simple):
                continue
            for code, (_, name) in COUNTRIES.items():
                prefix = r'(?:ships?|shipped|shipping|dispatched)\s+(?:directly\s+)?from\s+(?:(?:our|the)\s+(?:warehouse|headquarters)\s+in\s+)?'
                french = r'(?:expedie\w*|envoi\w*|livraison)(?:\s+rapide)?\s+(?:depuis|de)\s+(?:la\s+|le\s+)?'
                if re.search(r'\b(?:'+prefix+'|'+french+')(?:'+name+r')\b', simple):
                    found[code] = sentence.strip()[:240]
        if found:
            codes = set(found)
            if country:
                codes.add(country)
            sources += [dict(url=url, evidence=evidence, checked_at=date.today().isoformat(), kind='page_statement') for evidence in dict.fromkeys(found.values())]
            country = next(iter(codes)) if len(codes) == 1 and status != 'conflicting' else None
            status = 'merchant_declared' if country else 'conflicting'
            if not country:
                tax = 'unknown'
    result = describe(country, tax, sources, status)
    if status == 'conflicting':
        result['tax_message'] = 'Plusieurs pays de départ sont annoncés : vérifier celui de cette offre et les frais au paiement.'
    return result


def policy_links(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    found = []
    for anchor in soup.select('a[href]'):
        target = urljoin(url, anchor['href']).split('#')[0]
        label = folded(anchor.get_text(' ', strip=True) + ' ' + target)
        if urlsplit(target).netloc == urlsplit(url).netloc and re.search(r'shipping|livraison|expedition|delivery|\bfaq\b', label):
            if not re.search(r'cart|checkout|add.to|login', target, re.I):
                found.append(target)
    return list(dict.fromkeys(found))[:2]


def merge_origins(current, additional):
    if not additional['sources']:
        return current
    countries = {x['country'] for x in (current, additional) if x['country']}
    sources = list({(s['url'], s['evidence']): s for x in (current, additional) for s in x['sources']}.values())
    if len(countries) > 1 or any(x['status'] == 'conflicting' for x in (current, additional)):
        return describe(sources=sources, status='conflicting')
    country = next(iter(countries), None)
    tax = 'extra' if any(x['tax_status'] == 'extra' for x in (current, additional)) else 'included' if any(x['tax_status'] == 'included' for x in (current, additional)) else 'unknown'
    return describe(country, tax, sources, 'merchant_declared' if country else 'unknown')
