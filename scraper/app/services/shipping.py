import json
import os


def shipping_for(store, price_eur):
    """Configured France delivery rules. Unknown remains unknown."""
    rules = json.loads(os.getenv('SHIPPING_RULES_JSON') or '{}')
    rule = rules.get(store['name'], store.get('shipping_rule', {}))
    if not rule or rule.get('destination', 'FR') != 'FR':
        return None
    threshold = rule.get('free_above_eur')
    if threshold is not None and price_eur >= float(threshold):
        return 0.0
    fee = rule.get('flat_eur')
    return max(0, float(fee)) if fee is not None else None
