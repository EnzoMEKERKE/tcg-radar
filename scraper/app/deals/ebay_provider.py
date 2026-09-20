"""Optional ScrapingBee transport for eBay; keys and account cookies are never exported."""
import os
from urllib.parse import urlsplit, parse_qs

from bs4 import BeautifulSoup
import httpx

from .browser import MarketplaceAccessError, access_gate


class ScrapingBeePages:
    def __init__(self, key=None, transport=None, max_requests=6):
        self.key = key if key is not None else os.getenv('SCRAPINGBEE_API_KEY', '')
        self.transport = transport
        self.max_requests = max_requests
        self.requests = 0

    @staticmethod
    def allowed(url):
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.hostname == 'www.ebay.fr'
                and parsed.path == '/sch/i.html' and not parsed.username
                and not parsed.password and parsed.port in (None,443))

    async def product(self, url):
        if not self.allowed(url):
            raise ValueError('Unsupported eBay search')
        if not self.key:
            raise MarketplaceAccessError('provider_unconfigured', 'ScrapingBee sélectionné, mais sa clé API n’est pas configurée.')
        if self.requests >= self.max_requests:
            raise MarketplaceAccessError('provider_budget', 'Limite de six appels ScrapingBee atteinte pour cette analyse.')
        self.requests += 1
        try:
            async with httpx.AsyncClient(timeout=34, transport=self.transport, follow_redirects=False) as client:
                response = await client.get('https://app.scrapingbee.com/api/v1/',
                    headers={'Authorization': 'Bearer '+self.key},
                    params={'url':url, 'render_js':'true', 'premium_proxy':'true',
                            'country_code':'fr', 'timeout':'30000', 'wait':'1500',
                            'transparent_status_code':'true'})
        except httpx.HTTPError:
            raise MarketplaceAccessError('provider_unavailable', 'ScrapingBee ne répond pas dans le délai de collecte.') from None
        if response.status_code in (401,402):
            raise MarketplaceAccessError('provider_account', 'ScrapingBee refuse la requête : vérifiez la clé et les crédits du compte.')
        if response.status_code != 200:
            raise MarketplaceAccessError('provider_error', f'ScrapingBee n’a pas obtenu la recherche eBay (HTTP {response.status_code}).')
        final = response.headers.get('spb-resolved-url', url)
        soup = BeautifulSoup(response.text, 'html.parser')
        gate = access_gate(final, soup.title.get_text() if soup.title else '')
        if gate:
            raise gate
        if not self.allowed(final):
            raise MarketplaceAccessError('login_required', 'La recherche eBay a été redirigée ; aucune annonce n’est validée.')
        original, resolved = parse_qs(urlsplit(url).query), parse_qs(urlsplit(final).query)
        if original.get('LH_Sold') == ['1'] and any(resolved.get(key) != ['1'] for key in ('LH_Sold','LH_Complete')):
            raise MarketplaceAccessError('provider_error', 'eBay n’a pas conservé les filtres de ventes terminées.')
        return response.text, final

    async def close(self):
        pass
