"""Render JavaScript through the merchant's bounded, robots-aware HTTP client."""
import asyncio
import os


class BrowserRenderer:
    def __init__(self):
        self.driver = self.browser = None
        self.pages = 0
        self.errors = 0
        self.disabled = False
        self.limit = max(0, min(50, int(os.getenv('BROWSER_MAX_PAGES', '10'))))

    async def render(self, connector, client, url, html):
        if self.disabled or self.pages >= self.limit:
            return html
        self.pages += 1
        context = None
        try:
            from playwright.async_api import async_playwright
            async with asyncio.timeout(20):
                if self.browser is None:
                    self.driver = await async_playwright().start()
                    self.browser = await self.driver.chromium.launch(headless=True)
                context = await self.browser.new_context(service_workers='block', user_agent=connector.headers['User-Agent'])
                resource_count = 0

                async def route_request(route):
                    nonlocal resource_count
                    request = route.request
                    if request.method != 'GET' or request.resource_type in ('image', 'media', 'font'):
                        return await route.abort()
                    if request.url == url and request.resource_type == 'document':
                        return await route.fulfill(status=200, content_type='text/html', body=html)
                    if resource_count >= 12:
                        return await route.abort()
                    resource_count += 1
                    response = await connector.get(client, request.url)
                    if response is None:
                        return await route.abort()
                    await route.fulfill(status=200, content_type=response.headers.get('content-type', 'text/plain'), body=response.content)

                await context.route('**/*', route_request)
                await context.route_web_socket('**/*', lambda ws: ws.close())
                page = await context.new_page()
                await page.goto(url, wait_until='domcontentloaded', timeout=12000)
                # A bounded scroll also triggers lazy product grids.
                for _ in range(3):
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await page.wait_for_timeout(500)
                return await page.content()
        except Exception:
            self.errors += 1
            if self.browser is None:
                self.disabled = True
            return html
        finally:
            if context:
                await context.close()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.driver:
            await self.driver.stop()
