import pytest
from src.stages.sanitizer import sanitize_html
from src.exceptions import SanitizationError


def test_removes_script_tags():
    html = "<html><body><script>alert(1)</script><p>Hello</p></body></html>"
    result = sanitize_html(html)
    assert "<script" not in result
    assert "alert(1)" not in result
    assert "Hello" in result


def test_removes_style_tags():
    html = "<html><body><style>.foo { color: red; }</style><p>Text</p></body></html>"
    result = sanitize_html(html)
    assert "<style" not in result
    assert "Text" in result


def test_removes_svg_tags():
    html = "<html><body><svg><circle r='10'/></svg><span>Content</span></body></html>"
    result = sanitize_html(html)
    assert "<svg" not in result
    assert "Content" in result


def test_removes_img_tags():
    html = '<html><body><img src="photo.jpg" alt="photo"><p>Below</p></body></html>'
    result = sanitize_html(html)
    assert "<img" not in result
    assert "Below" in result


def test_removes_html_comments():
    html = "<html><body><!-- this is a comment --><p>Visible</p></body></html>"
    result = sanitize_html(html)
    assert "<!--" not in result
    assert "Visible" in result


def test_keeps_a_tags():
    html = '<html><body><a href="/thread/1">Thread title</a></body></html>'
    result = sanitize_html(html)
    assert "<a" in result
    assert "Thread title" in result


def test_keeps_time_tags():
    html = '<html><body><time datetime="2024-01-01">Yesterday</time></body></html>'
    result = sanitize_html(html)
    assert "<time" in result
    assert "Yesterday" in result


def test_returns_non_empty_string():
    html = "<html><body><p>Test</p></body></html>"
    result = sanitize_html(html)
    assert isinstance(result, str)
    assert len(result) > 0


def test_strips_class_attribute():
    html = '<html><body><div class="container"><p class="text">Content</p></div></body></html>'
    result = sanitize_html(html)
    assert "class=" not in result
    assert "Content" in result


def test_strips_id_attribute():
    html = '<html><body><div id="main"><p>Content</p></div></body></html>'
    result = sanitize_html(html)
    assert "id=" not in result
    assert "Content" in result


def test_keeps_href_on_a_tags_strips_other_attributes():
    html = '<html><body><a href="https://example.com" class="link">Link text</a></body></html>'
    result = sanitize_html(html)
    assert 'href="https://example.com"' in result
    assert "class=" not in result
    assert "<a" in result
    assert "Link text" in result


def test_strips_all_attributes_from_any_tag():
    html = '<html><body><span class="foo" data-val="bar" aria-label="baz">Text</span></body></html>'
    result = sanitize_html(html)
    assert "class=" not in result
    assert "data-val=" not in result
    assert "aria-label=" not in result
    assert "Text" in result


def test_removes_empty_span():
    html = "<html><body><span></span><p>Content</p></body></html>"
    result = sanitize_html(html)
    assert "<span" not in result
    assert "Content" in result


def test_removes_whitespace_only_span():
    html = "<html><body><span>   \n  </span><p>Content</p></body></html>"
    result = sanitize_html(html)
    assert "<span" not in result
    assert "Content" in result


def test_keeps_span_with_text():
    html = "<html><body><span>Username</span></body></html>"
    result = sanitize_html(html)
    assert "<span" in result
    assert "Username" in result


def test_keeps_structural_container_even_if_empty_after_stripping():
    # div is a structural container — never removed for being empty
    html = "<html><body><div><p>Text</p></div></body></html>"
    result = sanitize_html(html)
    assert "<div" in result
    assert "Text" in result


def test_cascading_empty_removal():
    # em has no text → removed; then span has no text and no children → removed
    html = "<html><body><span><em></em></span><p>Real</p></body></html>"
    result = sanitize_html(html)
    assert "<em" not in result
    assert "<span" not in result
    assert "Real" in result


def test_preserves_tail_text_when_removing_empty_node():
    # "after" is the tail of <span> — must survive span's removal
    html = "<html><body><p><span></span>after</p></body></html>"
    result = sanitize_html(html)
    assert "after" in result


def test_raises_on_parse_failure(monkeypatch):
    import src.stages.sanitizer as sanitizer_module
    monkeypatch.setattr(sanitizer_module.lxml_html, "fromstring", lambda *a, **kw: (_ for _ in ()).throw(ValueError("boom")))
    with pytest.raises(SanitizationError, match="Failed to parse HTML"):
        sanitize_html("<html><body>ok</body></html>")


def test_raises_on_empty_string():
    with pytest.raises(SanitizationError):
        sanitize_html("")


def test_raises_on_whitespace_only_input():
    with pytest.raises(SanitizationError):
        sanitize_html("   \n  ")


def test_output_is_smaller_than_input():
    html = (
        "<html><body>"
        "<script>var x = 'lots of javascript';</script>"
        "<style>.foo { color: red; font-size: 16px; }</style>"
        '<div class="container" id="main" data-val="something">'
        '<p class="title">Thread title</p>'
        "</div>"
        "</body></html>"
    )
    result = sanitize_html(html)
    assert len(result) < len(html)


def test_deep_copy_does_not_share_state():
    # Calling sanitize_html twice on the same input must produce identical output,
    # proving no shared mutable state leaks between calls.
    html = '<html><body><div class="thread"><p class="title">Title</p></div></body></html>'
    result1 = sanitize_html(html)
    result2 = sanitize_html(html)
    assert result1 == result2


def test_logs_reduction_ratio(caplog):
    import logging
    html = (
        "<html><body>"
        "<script>lots of js code here</script>"
        '<div class="main"><p>Content</p></div>'
        "</body></html>"
    )
    with caplog.at_level(logging.INFO, logger="src.stages.sanitizer"):
        sanitize_html(html)
    assert any("[Sanitizer]" in record.message for record in caplog.records)
    assert any("KB" in record.message for record in caplog.records)
    assert any("reduction" in record.message.lower() for record in caplog.records)


@pytest.mark.integration
async def test_sanitize_altenens_reduces_size():
    from src.stages.renderer import render_page
    rendered = await render_page("https://altenens.is/whats-new/posts/")
    raw_html = rendered["html"]
    result = sanitize_html(raw_html)
    original_kb = len(raw_html) / 1024
    result_kb = len(result) / 1024
    reduction = 1 - (result_kb / original_kb)
    print(f"\n[altenens.is] {original_kb:.1f} KB → {result_kb:.1f} KB ({reduction * 100:.1f}% reduction)")
    assert reduction >= 0.65, f"Expected ≥65% reduction, got {reduction * 100:.1f}%"
    assert result_kb > 5, "Sanitized output too small — something went wrong"


@pytest.mark.integration
async def test_sanitize_blackbiz_reduces_size():
    from src.stages.renderer import render_page
    rendered = await render_page("https://s1.blackbiz.store/whats-new")
    raw_html = rendered["html"]
    result = sanitize_html(raw_html)
    original_kb = len(raw_html) / 1024
    result_kb = len(result) / 1024
    reduction = 1 - (result_kb / original_kb)
    print(f"\n[blackbiz.store] {original_kb:.1f} KB → {result_kb:.1f} KB ({reduction * 100:.1f}% reduction)")
    assert reduction >= 0.70, f"Expected ≥70% reduction, got {reduction * 100:.1f}%"
    assert result_kb > 5, "Sanitized output too small — something went wrong"
