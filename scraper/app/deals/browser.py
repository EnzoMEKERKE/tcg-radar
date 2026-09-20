"""Read public marketplace pages in a fresh Chromium session, without account access."""
import asyncio
import re
from urllib.parse import urlsplit
import httpx


class MarketplaceAccessError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def access_gate(url, title=''):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    if host == 'signin.ebay.fr' or (host in ('ebay.fr','www.ebay.fr') and parsed.path.lower() in ('/signin', '/login')):
        return MarketplaceAccessError('login_required','eBay demande une connexion pour accéder à cette recherche.')
    if parsed.path == '/splashui/challenge' or any(word in title.lower() for word in ('just a moment','attention required','pardon our interruption','security measure','captcha')):
        return MarketplaceAccessError('verification_required','La plateforme demande une vérification dans le navigateur ; aucune annonce n’a été lue sur cette page.')
    return None


class BrowserPages:
    def __init__(self):
        self.driver = self.browser = self.context = None
        self.requests = 0
        self.access_denied = None

    @staticmethod
    def allowed_document(url):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None,443):
            return False
        return (parsed.hostname == 'www.ebay.fr' and (parsed.path in ('/', '/splashui/challenge') or bool(re.fullmatch(r'/sch/(?:\d+/)?i\.html',parsed.path)))) or (
            parsed.hostname == 'www.cardmarket.com' and parsed.path.startswith('/fr/Pokemon/Products/'))

    async def start(self):
        if self.context is not None:
            return
        from playwright.async_api import async_playwright
        if self.driver:
            await self.close()
        self.driver = await async_playwright().start()
        self.browser = await self.driver.chromium.launch(headless=True)
        self.context = await self.browser.new_context(locale='fr-FR', viewport={'width':1440,'height':1000},service_workers='block')

        async def guard(route):
            request = route.request
            parsed = urlsplit(request.url)
            if request.is_navigation_request() and request.frame == request.frame.page.main_frame:
                gate = access_gate(request.url)
                if gate and gate.status == 'login_required':
                    self.access_denied = gate
                    return await route.abort()
            browser_check = parsed.hostname == 'www.ebay.fr' and parsed.path == '/splashui/challenge' and request.method == 'POST'
            if (request.method != 'GET' and not browser_check) or parsed.scheme != 'https':
                return await route.abort()
            if request.is_navigation_request():
                allowed = self.allowed_document(request.url)
            else:
                # Marketplace assets only. The site's own browser-check POST is allowed,
                # but account actions, purchases and telemetry POSTs are blocked.
                domains = ('ebay.fr','ebay.com','ebaystatic.com','ebayimg.com','cardmarket.com','mkmcdn.com')
                host = parsed.hostname or ''
                allowed = any(host == domain or host.endswith('.'+domain) for domain in domains)
                if any(part in parsed.path.lower() for part in ('checkout','watchlistadd','addtocart','/cart','/signin','/login')):
                    allowed = False
            if not allowed or request.resource_type in ('image','media','font'):
                return await route.abort()
            await route.continue_()

        await self.context.route('**/*', guard)
        await self.context.route_web_socket('**/*',lambda socket:socket.close())

    async def product(self,url):
        if not self.allowed_document(url):
            raise ValueError('Unsupported marketplace page')
        self.requests += 1
        self.access_denied = None
        page = None
        try:
            async with asyncio.timeout(38):
                await self.start()
                page = await self.context.new_page()
                response = await page.goto(url,wait_until='domcontentloaded',timeout=25000)
                if self.access_denied:
                    raise self.access_denied
                gate = access_gate(page.url,await page.title())
                if gate and gate.status == 'verification_required' and response and response.status >= 400:
                    raise gate
                if response and response.status >= 400:
                    httpx.Response(response.status,request=httpx.Request('GET',url)).raise_for_status()
                # Let ordinary page JavaScript populate listings. No challenge solving.
                try:
                    await page.wait_for_selector('.s-item, .s-card, .article-row, a[href*="/Products/Singles/"]',timeout=6000)
                except Exception:
                    pass
                await page.wait_for_timeout(500)
                if self.access_denied:
                    raise self.access_denied
                gate = access_gate(page.url,await page.title())
                if gate:
                    raise gate
                if not self.allowed_document(page.url):
                    raise ValueError('Unsupported marketplace redirect: '+urlsplit(page.url).path)
                return await page.content(),page.url
        except (ValueError,TimeoutError,httpx.HTTPError):
            raise
        except Exception as error:
            if self.access_denied:
                raise self.access_denied from error
            raise OSError('Browser page unavailable') from error
        finally:
            if page:
                await page.close()

    async def close(self):
        try:
            if self.browser: await self.browser.close()
        finally:
            if self.driver: await self.driver.stop()
            self.context = self.browser = self.driver = None
