"""Broad search hints only; these never establish that two cards are identical."""
import re
from .identity import flat, language_of


def card_search_name(title):
    text=flat(title)
    if re.search(r'\b(psa|pca|bgs|cgc|graded|gradee|grade|lot|bundle|proxy|replica|custom)\b',text):
        return ''
    text=re.sub(r'\b(nouvelle annonce|nintendo|the pokemon company|pokemon|jcc|tcg|carte|card|cards|cartes)\b',' ',text)
    text=re.sub(r'\b(?:sv\d+[a-z]?|m\d+[a-z]?|swsh\d+)\b',' ',text)
    # Descriptive listing titles often continue with rarity, number or condition.
    text=re.split(r'\b(?:\d|ar\b|sar\b|sir\b|holo\b|full art\b|set\b|deck\b|near mint\b|nm\b|fr\b|jp\b|jap\b|japanese\b|japonais\b|japonaise\b)',text,maxsplit=1)[0]
    return ' '.join(re.findall(r"[a-z]+(?:['-][a-z]+)*",text))[:80].strip()


def sold_searches(rows,language):
    found={}
    for row in rows:
        actual=row.language if row.language!='UNKNOWN' else language_of(row.title)
        if not row.sold or row.source!='ebay' or actual=='UNKNOWN' or (language!='ALL' and actual!=language):
            continue
        name=card_search_name(row.title)
        if name:
            found.setdefault(name,name)
    return list(found)
