import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def playwright_mock_factory():
    """
    Returns a factory function that builds a fully mocked Playwright async
    context stack. Use to avoid repeating the deep mock wiring in every test.

    Usage:
        mock_acm, mock_page, mock_response = playwright_mock_factory(
            html="<html>...</html>",
            final_url="https://example.com/",
            status=200,
        )
    Then patch: patch("src.stages.renderer.async_playwright", return_value=mock_acm)
    """
    def _factory(
        html: str = "<html><body>test content</body></html>",
        final_url: str = "https://example.com/",
        status: int = 200,
    ):
        mock_response = MagicMock()
        mock_response.status = status

        mock_page = AsyncMock()
        mock_page.url = final_url
        mock_page.content = AsyncMock(return_value=html)
        mock_page.goto = AsyncMock(return_value=mock_response)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_p = MagicMock()
        mock_p.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_acm = AsyncMock()
        mock_acm.__aenter__ = AsyncMock(return_value=mock_p)
        mock_acm.__aexit__ = AsyncMock(return_value=False)

        return mock_acm, mock_page, mock_response

    return _factory
