import pytest
from unittest.mock import AsyncMock, patch
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from src.stages.renderer import render_page


async def test_render_page_returns_html_and_final_url(playwright_mock_factory):
    mock_acm, _, _ = playwright_mock_factory(
        html="<html><body>forum content</body></html>",
        final_url="https://example.com/threads/",
    )
    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        result = await render_page("https://example.com/threads/")

    assert result["html"] == "<html><body>forum content</body></html>"
    assert result["final_url"] == "https://example.com/threads/"


async def test_render_page_uses_networkidle_wait_strategy(playwright_mock_factory):
    mock_acm, mock_page, _ = playwright_mock_factory()
    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        await render_page("https://example.com/")

    mock_page.goto.assert_awaited_once()
    call_kwargs = mock_page.goto.call_args.kwargs
    assert call_kwargs.get("wait_until") == "networkidle"


async def test_render_page_sets_1920x1080_viewport(playwright_mock_factory):
    mock_acm, _, _ = playwright_mock_factory()
    mock_browser = mock_acm.__aenter__.return_value.chromium.launch.return_value
    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        await render_page("https://example.com/")

    ctx_kwargs = mock_browser.new_context.call_args.kwargs
    assert ctx_kwargs["viewport"] == {"width": 1920, "height": 1080}


async def test_render_page_sets_realistic_user_agent(playwright_mock_factory):
    mock_acm, _, _ = playwright_mock_factory()
    mock_browser = mock_acm.__aenter__.return_value.chromium.launch.return_value
    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        await render_page("https://example.com/")

    ctx_kwargs = mock_browser.new_context.call_args.kwargs
    assert "Mozilla" in ctx_kwargs["user_agent"]
    assert "Chrome" in ctx_kwargs["user_agent"]


from src.exceptions import PageRenderError


async def test_non_2xx_status_raises_with_code_and_url(playwright_mock_factory):
    mock_acm, _, _ = playwright_mock_factory(status=404)
    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        with pytest.raises(PageRenderError) as exc_info:
            await render_page("https://example.com/missing")
    assert "404" in str(exc_info.value)
    assert "https://example.com/missing" in str(exc_info.value)


async def test_500_status_raises_page_render_error(playwright_mock_factory):
    mock_acm, _, _ = playwright_mock_factory(status=500)
    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        with pytest.raises(PageRenderError) as exc_info:
            await render_page("https://example.com/")
    assert "500" in str(exc_info.value)


async def test_empty_html_raises_page_render_error(playwright_mock_factory):
    mock_acm, _, _ = playwright_mock_factory(html="   ")
    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        with pytest.raises(PageRenderError) as exc_info:
            await render_page("https://example.com/")
    assert "Empty HTML" in str(exc_info.value)


async def test_networkidle_timeout_falls_back_to_domcontentloaded(playwright_mock_factory):
    mock_acm, mock_page, mock_response = playwright_mock_factory(
        html="<html><body>fallback content</body></html>",
        final_url="https://example.com/",
    )
    mock_page.goto = AsyncMock(side_effect=[
        PlaywrightTimeoutError("networkidle timed out"),
        mock_response,
    ])

    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        result = await render_page("https://example.com/")

    assert result["html"] == "<html><body>fallback content</body></html>"
    assert mock_page.goto.await_count == 2
    second_call_kwargs = mock_page.goto.call_args_list[1].kwargs
    assert second_call_kwargs.get("wait_until") == "domcontentloaded"


async def test_both_wait_strategies_timeout_raises_page_render_error(playwright_mock_factory):
    mock_acm, mock_page, _ = playwright_mock_factory()
    mock_page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("timeout"))

    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        with pytest.raises(PageRenderError):
            await render_page("https://example.com/")


async def test_context_and_browser_closed_on_error(playwright_mock_factory):
    mock_acm, _, _ = playwright_mock_factory(status=500)
    mock_browser = mock_acm.__aenter__.return_value.chromium.launch.return_value
    mock_context = mock_browser.new_context.return_value

    with patch("src.stages.renderer.async_playwright", return_value=mock_acm):
        with pytest.raises(PageRenderError):
            await render_page("https://example.com/")

    mock_context.close.assert_awaited_once()
    mock_browser.close.assert_awaited_once()
