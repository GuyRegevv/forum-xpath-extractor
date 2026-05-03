import logging

from playwright.async_api import async_playwright

from src.exceptions import PageRenderError

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def render_page(url: str) -> dict[str, str]:
    """
    Render a forum URL using Playwright and return the full HTML.

    Args:
        url: Publicly accessible forum URL

    Returns:
        {"html": str, "final_url": str}

    Raises:
        PageRenderError: If the page fails to load entirely
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=_USER_AGENT,
        )
        try:
            page = await context.new_page()
            response = await page.goto(url, wait_until="networkidle", timeout=30000)

            if response is None or response.status >= 400:
                status = response.status if response else "no response"
                raise PageRenderError(f"HTTP {status} for {url}")

            html = await page.content()
            if not html or not html.strip():
                raise PageRenderError("Empty HTML returned")

            final_url = page.url
            logger.info("[Renderer] Rendered %.1f KB from %s", len(html) / 1024, final_url)
            return {"html": html, "final_url": final_url}
        finally:
            await context.close()
            await browser.close()
