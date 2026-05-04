import pytest
from src.stages.sanitizer import sanitize_html


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


def test_strips_href_from_a_tags_but_keeps_a():
    html = '<html><body><a href="https://example.com" class="link">Link text</a></body></html>'
    result = sanitize_html(html)
    assert "href=" not in result
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
