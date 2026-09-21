"""Strict successor to pokedeals-v2's fuzzy card normalizer.

Different numbers, finishes, languages and exact condition grades never merge.
Missing identity information stays visible in coverage, not in profitable deals.
"""
import re
import unicodedata

CONDITIONS = {'PO':1, 'PL':2, 'LP':3, 'GD':4, 'EX':5, 'NM':6, 'MT':7}
LANGUAGES = {
    'FR':r'fr|vf|french|francais|francaise', 'EN':r'en|eng|english|anglais',
    'JP':r'jp|jpn|jap|japanese|japonais|japonaise|japan', 'DE':r'de|german|deutsch|allemand',
    'IT':r'it|italian|italien|italiano', 'ES':r'es|spanish|espagnol',
    'KR':r'kr|korean|coreen', 'CN':r'cn|chinese|chinois',
}
NUMBER = re.compile(r'\b([a-z]{0,3}\d{1,4})\s*/\s*([a-z]{0,3}\d{1,4})\b', re.I)
SET = re.compile(r'\b(?:sv\d+[a-z]?|swsh\d+|sm\d+[a-z]?|xy\d+|s\d+[a-z]|base set|set de base)\b', re.I)
VARIANTS = [
    ('reverse', r'reverse(?: holo)?'), ('non-holo', r'non[ -]?holo'),
    ('first-edition', r'1st edition|first edition|premiere edition|edition 1'),
    ('shadowless', r'shadowless'), ('holo', r'holo(?:graphic|graphique)?'),
    ('sir', r'\bsir\b|special illustration rare'), ('sar', r'\bsar\b|special art rare'),
    ('alt-art', r'alt(?:ernate)? art'), ('full-art', r'full art'), ('promo', r'\bpromo\b'),
]


def flat(value):
    return unicodedata.normalize('NFKD', value.lower()).encode('ascii', 'ignore').decode()


def language_candidates(title):
    # Lowercase de/en/it/es are ordinary words, not proof of a card's language.
    value = flat(title)
    matches = set()
    flags = {'FR':'🇫🇷', 'EN':'🇬🇧🇺🇸', 'JP':'🇯🇵', 'DE':'🇩🇪',
             'IT':'🇮🇹', 'ES':'🇪🇸', 'KR':'🇰🇷', 'CN':'🇨🇳'}
    for lang, pattern in LANGUAGES.items():
        words = '|'.join(word for word in pattern.split('|') if word not in ('de','en','it','es'))
        if re.search(r'\b(?:'+words+r')\b', value) or re.search(r'\b'+lang+r'\b', title):
            matches.add(lang)
        if any(flags[lang][i:i+2] in title for i in range(0,len(flags[lang]),2)):
            matches.add(lang)
    if re.search(r'\b(?:jap|jpn|japanese|japonais|japonaise)\b', value):
        matches.add('JP')
    return matches


def language_of(title):
    matches = list(language_candidates(title))
    return matches[0] if len(matches) == 1 else 'UNKNOWN'


def condition_of(text):
    text = flat(text)
    for pattern, value in [(r'near mint|\bnm\b', 'NM'), (r'light(?:ly)? played|\blp\b','LP'),
                           (r'\bmint\b|\bmt\b','MT'), (r'excellent|\bex\b','EX'),
                           (r'\bgood\b|\bgd\b','GD'), (r'\bplayed\b|\bpl\b','PL'), (r'poor|\bpo\b','PO')]:
        if re.search(pattern, text):
            return value
    return 'UNKNOWN'


def identity(listing):
    text = flat(listing.title)
    if re.search(r'\b(psa|bgs|cgc|pca|ace|graded|gradee|lot|bundle|booster|display|proxy|replica|reprint|custom|fake)\b|\bx\s*\d+\b', text):
        return None, 'lot_gradee_ou_reproduction'
    candidates = language_candidates(listing.title)
    if len(candidates) > 1:
        return None, 'langue_ambigue'
    language = listing.language if listing.language != 'UNKNOWN' else language_of(listing.title)
    detected_language = language_of(listing.title)
    if listing.language != 'UNKNOWN' and detected_language != 'UNKNOWN' and detected_language != listing.language:
        return None, 'identite_contradictoire'
    condition = listing.condition
    if language == 'UNKNOWN' or condition not in CONDITIONS:
        return None, 'langue_ou_etat_inconnu'
    number = listing.card_number.strip().lower().replace(' ', '')
    match = NUMBER.search(text)
    if number and match:
        title_number = match[0].replace(' ', '')
        compact = lambda n: re.sub(r'(?<!\d)0+(?=\d)', '', n)
        if compact(number) not in (compact(title_number),compact(title_number.split('/')[0])):
            return None, 'identite_contradictoire'
        number = title_number
    number = number or (match[0].replace(' ', '') if match else '')
    code = flat(listing.set_code).strip() or (SET.search(text)[0] if SET.search(text) else '')
    if code == 'set de base':
        code = 'base set'
    if not number or ('/' not in number and not code):
        return None, 'numero_ou_extension_manquant'
    # Retain the denominator: 4/102 and 4/130 are different printings.
    number = re.sub(r'(?<!\d)0+(?=\d)', '', number)
    variants = []
    rest = text
    for name, pattern in VARIANTS:
        if re.search(pattern, rest):
            variants.append(name)
            rest = re.sub(pattern, '', rest)
    variant = flat(listing.variant).strip() or '+'.join(sorted(variants))
    if listing.variant and variants and variant != '+'.join(sorted(variants)):
        return None, 'identite_contradictoire'
    if not variant:
        return None, 'variante_non_confirmee'
    rest = NUMBER.sub('', rest)
    rest = SET.sub('', rest)
    if listing.source == 'cardmarket':
        rest = re.sub(r'\(\s*[a-z]{1,5}\s*\d{1,4}\s*\)', '', rest)
        rest = re.sub(r'\bcartes?\b', '', rest)
        if code:
            rest = rest.replace(code, '').replace('set de base', '')
    for pattern in LANGUAGES.values():
        rest = re.sub(r'\b(?:'+pattern+r')\b', '', rest)
    rest = re.sub(r'\b(pokemon|tcg|card|carte|near mint|mint|nm|mt|excellent|good|light played|played|lp|gd|pl|po|free shipping|livraison gratuite)\b', '', rest)
    rest = re.sub(r'\b\d+\b', '', rest)
    # Name is conservative; no fuzzy merge of different Pokémon.
    name = ' '.join(re.sub(r'[^a-z0-9]+', ' ', rest).split())
    if not name:
        return None, 'nom_non_identifie'
    return (name, number, code, variant, language, condition), None
