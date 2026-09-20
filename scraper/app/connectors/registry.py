"""One production connector factory for all configured merchants."""
from .merchant import MerchantConnector, PROFILES
from app.config.stores import STORES


def make_connector(store, max_pages=250):
    return MerchantConnector(store, max_pages=max_pages)


CONNECTORS = {store['name']: {'store': store, 'dedicated': store['name'] in PROFILES} for store in STORES}
