"""Bidirectional PokéDeals comparison, using auditable net-margin assumptions."""
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from statistics import median
from urllib.parse import urlsplit
import re
from .identity import identity, CONDITIONS


def observation_id(row):
    if row.source == 'ebay':
        match = re.search(r'/itm/(?:[^/]+/)?(\d+)', urlsplit(row.url).path)
        return ('ebay', match[1] if match else row.url.split('?')[0], row.sold)
    return ('cardmarket', row.url.split('?')[0], row.listing_id or row.seller, row.language, row.condition, row.variant)


def analyze(listings, settings, now=None):
    now = now or datetime.now(timezone.utc)
    rejected = Counter()
    groups = defaultdict(list)
    unique = {}
    for row in listings:
        key = observation_id(row)
        if key not in unique or row.observed_at > unique[key].observed_at:
            unique[key] = row
    for row in unique.values():
        key, reason = identity(row)
        if reason:
            rejected[reason] += 1
            continue
        if row.currency != 'EUR':
            rejected['devise_non_eur'] += 1
            continue
        if not row.price_exact:
            rejected['prix_negocie_ou_approximatif'] += 1
            continue
        if settings.language != 'ALL' and key[4] != settings.language:
            continue
        if CONDITIONS[key[5]] < CONDITIONS[settings.condition_min]:
            continue
        if row.sold:
            if row.source != 'ebay' or not row.sold_at or not now-timedelta(days=settings.sales_days) <= row.sold_at <= now:
                rejected['vente_non_datee_ou_ancienne'] += 1
                continue
        elif not row.available or row.observed_at < now-timedelta(hours=24):
            rejected['offre_indisponible_ou_ancienne'] += 1
            continue
        groups[key].append(row)

    deals = []
    for key, rows in groups.items():
        cm = [r for r in rows if r.source == 'cardmarket' and not r.sold]
        active = [r for r in rows if r.source == 'ebay' and not r.sold]
        sold = [r for r in rows if r.source == 'ebay' and r.sold]
        for direction, buys, references in [('cm_to_ebay', cm, sold), ('ebay_to_cm', active, cm)]:
            if settings.direction not in ('all', direction) or not buys or not references:
                continue
            if direction == 'cm_to_ebay' and len(sold) < settings.min_sales:
                rejected['echantillon_ventes_insuffisant'] += 1
                continue
            buy = min(buys, key=lambda r: r.price+(r.shipping if r.shipping is not None else settings.buy_shipping))
            buy_shipping = buy.shipping if buy.shipping is not None else settings.buy_shipping
            # Sold reference excludes collected shipping; seller shipping cost is subtracted separately.
            # CM is a competing asking price, NEVER labelled a completed sale.
            reference = median(r.price for r in references) if direction == 'cm_to_ebay' else min(r.price for r in references)
            target = reference*(1-settings.safety_pct/100)
            fee_pct = settings.ebay_fee_pct if direction == 'cm_to_ebay' else settings.cm_fee_pct
            fees = target*fee_pct/100+settings.fixed_fee
            acquisition = buy.price+buy_shipping+settings.other_costs
            costs = acquisition+fees+settings.sell_shipping+settings.packaging
            profit = target-costs
            roi = profit/acquisition*100
            if profit < settings.min_profit or roi < settings.min_roi:
                continue
            evidence = sorted(references, key=lambda r:r.sold_at or r.observed_at, reverse=True)
            deals.append({
                'direction':direction, 'card_name':buy.title, 'card_number':key[1], 'set_code':key[2],
                'variant':key[3], 'language':key[4], 'condition':key[5], 'buy_url':buy.url,
                'buy_source':buy.source, 'sell_source':'ebay' if direction=='cm_to_ebay' else 'cardmarket',
                'buy_price':round(buy.price,2), 'buy_shipping':round(buy_shipping,2),
                'shipping_estimated':buy.shipping is None, 'reference_price':round(reference,2),
                'reference_kind':'sold_median' if direction=='cm_to_ebay' else 'active_lowest',
                'reference_count':len(references), 'sale_target':round(target,2),
                'fees':round(fees,2), 'sell_shipping':settings.sell_shipping, 'packaging':settings.packaging,
                'other_costs':settings.other_costs, 'acquisition_cost':round(acquisition,2),
                'net_profit':round(profit,2), 'roi':round(roi,1), 'observed_at':buy.observed_at.isoformat(),
                'provenance':buy.provenance, 'confidence':'sales_sample' if direction=='cm_to_ebay' else 'asking_prices_only',
                'evidence':[{'url':r.url,'price':r.price,'language':key[4],'date':(r.sold_at or r.observed_at).isoformat(),'provenance':r.provenance} for r in evidence[:50]],
            })
    deals.sort(key=lambda d:d['net_profit'], reverse=True)
    return {'deals':deals, 'deal_count':len(deals), 'listing_count':len(unique), 'matched_groups':len(groups),
            'excluded':dict(rejected), 'settings':settings.model_dump(), 'analyzed_at':now.isoformat()}
