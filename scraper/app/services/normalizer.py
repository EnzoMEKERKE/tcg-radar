import re, unicodedata
GAMES={"pokemon":"Pokemon","pokémon":"Pokemon","ポケモン":"Pokemon","one piece":"One Piece","onepiece":"One Piece","ワンピース":"One Piece","yu-gi-oh":"Yu-Gi-Oh!","yugioh":"Yu-Gi-Oh!","遊戯王":"Yu-Gi-Oh!","gundam":"Gundam","ガンダム":"Gundam"}
NOISE=("sleeve","classeur","binder","deck box","playmat","figurine","single card","carte à l'unité","carte a l'unite","starter deck","deck de demarrage","portfolio","accessory","accessoire")

def _flat(s): return unicodedata.normalize('NFKD',s.lower()).encode('ascii','ignore').decode()
def normalize(title:str):
    t=' '.join((title or '').split()); low=t.lower(); flat=_flat(t)
    game=next((v for k,v in GAMES.items() if k in low),None)
    if not game or any(_flat(x) in flat for x in NOISE): return {'game':game,'language':None,'set_code':None,'kind':None,'confidence':0,'title':t}
    lang='JP' if re.search(r'\b(jp|jpn|japanese|japonais|japonaise|japon|ocg)\b',flat) else ('FR' if re.search(r'\b(fr|fra|french|francais|francaise|francais)\b',flat) else ('EN' if re.search(r'\b(en|eng|english|anglais)\b',flat) else None))
    patterns=[r'\b(OP|EB|PRB|ST|BT|EX|GD|M)[- _]?([0-9]{1,3}(?:\.[0-9])?[A-Za-z]?)\b',r'\b(SV|EV|EB|SWSH|S|ME)[- _]?([0-9]{1,2}(?:[.-][0-9])?[A-Za-z]?)\b']
    code=None
    if '日本語' in t: lang='JP'
    if re.search(r'\b(cn|chinese|chinois|ko|korean|coreen)\b',flat): lang='OTHER'
    if game=='Pokemon': patterns=[r'\b(SV|EV|EB|SWSH|S|SM|XY|ME|M)[- _]?([0-9]{1,2}(?:[.\-][0-9])?[A-Za-z]?)\b']
    elif game=='One Piece': patterns=[r'\b(OP|EB|PRB)[- _]?([0-9]{1,2})\b']
    elif game=='Gundam': patterns=[r'\b(GD)[- _]?([0-9]{1,2})\b']
    else: patterns=[]
    for p in patterns:
        m=re.search(p,t,re.I)
        if m: code=m.group(1).upper()+'-'+m.group(2).replace('_','.').upper(); break
    if code and game in ('One Piece','Gundam'): code=code.split('-')[0]+'-'+code.split('-')[1].zfill(2)
    kind='display' if any(x in flat for x in ('display','booster box','booster-box','boite de boosters','boite booster','booster display')) else None
    if not kind and 'box' in flat and ('booster' in flat or code): kind='display'
    if not kind and 'BOX' in t and game and ('パック' in t or code): kind='display'
    case=bool(re.search(r'\b(case|carton)\b',flat))
    count=re.search(r'(?<![\w-])x?(\d{1,3})\s*(?:x\s*)?(?:displays?|booster[- ]?box(?:es)?|boxes|boites)\b',flat)
    if not count: count=re.search(r'(?:display|booster[- ]?box)\s*[x?]\s*(\d{1,3})\b',flat)
    units=int(count[1]) if count else (None if case else 1)
    if units is not None and not 1 <= units <= 100: units=None
    if case or (units and units>1): kind='case'
    if any(x in flat for x in ('bundle','etb','coffret','empty','vide')): kind=None
    boosters=None
    bm=re.search(r'\b(\d{1,3})\s*(?:boosters?|packs?)\b',flat)
    if bm: boosters=int(bm.group(1))
    confidence=35 + (25 if code else 0) + (20 if lang else 0) + (20 if kind else 0)
    return {'game':game,'language':lang,'set_code':code,'kind':kind,'display_count':units,'boosters':boosters,'confidence':confidence,'title':t,'set_name':t}

normalize_title = normalize
