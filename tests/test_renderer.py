import pytest
from unittest.mock import patch
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
