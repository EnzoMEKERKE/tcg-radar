import os, time, httpx
_CACHE={'at':0,'rates':{}}
FALLBACK={'EUR':1.0,'JPY':0.00575,'USD':0.84,'GBP':1.15,'CHF':1.06,'CAD':0.61}
async def eur_rates():
    ttl=int(os.getenv('FX_TTL_SECONDS','21600'))
    if time.time()-_CACHE['at'] < ttl and _CACHE['rates']: return _CACHE['rates']
    url=os.getenv('FX_URL','https://api.frankfurter.app/latest?from=EUR')
    try:
        async with httpx.AsyncClient(timeout=10) as c: data=(await c.get(url)).json()['rates']
        # endpoint expresses 1 EUR = X currency; invert to currency -> EUR
        rates={'EUR':1.0, **{k:1/float(v) for k,v in data.items() if float(v)>0}}
        _CACHE.update(at=time.time(),rates=rates); return rates
    except Exception: return FALLBACK.copy()
