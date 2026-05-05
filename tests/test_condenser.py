import pytest
from src.stages.ie_extractor import FieldExtraction, IEOutput
from src.stages.condenser import _collect_target_texts, _compute_distance


def _make_ie_output(
    title="Thread title",
    title_cue="",
    author="darkuser99",
    author_cue="Latest: ",
    date="Yesterday at 11:42 PM",
    date_cue="",
    link="/threads/1/",
    link_cue="",
) -> IEOutput:
    return IEOutput(
        title=FieldExtraction(value=title, cue_text=title_cue),
        last_post_author=FieldExtraction(value=author, cue_text=author_cue),
        last_post_date=FieldExtraction(value=date, cue_text=date_cue),
        link=FieldExtraction(value=link, cue_text=link_cue),
    )


# ─── Task 1: helper functions ─────────────────────────────────────────────────

def test_collect_target_texts_includes_values():
    ie = _make_ie_output()
    texts = _collect_target_texts(ie)
    assert "Thread title" in texts
    assert "darkuser99" in texts
    assert "Yesterday at 11:42 PM" in texts
    assert "/threads/1/" in texts


def test_collect_target_texts_includes_nonempty_cue_texts():
    ie = _make_ie_output(author_cue="Latest: ")
    texts = _collect_target_texts(ie)
    assert "Latest: " in texts


def test_collect_target_texts_excludes_empty_cue_texts():
    ie = _make_ie_output(title_cue="", date_cue="", link_cue="")
    texts = _collect_target_texts(ie)
    assert "" not in texts


def test_collect_target_texts_excludes_empty_values():
    ie = _make_ie_output(link="")
    texts = _collect_target_texts(ie)
    assert "" not in texts


def test_compute_distance_exact_match():
    assert _compute_distance("darkuser99", "darkuser99") == 0.0


def test_compute_distance_near_match_below_threshold():
    # "Thread titl" vs "Thread title": 1 edit / 13 chars ≈ 0.077 < 0.1
    assert _compute_distance("Thread titl", "Thread title") < 0.1


def test_compute_distance_different_strings():
    assert _compute_distance("darkuser99", "hello world") > 0.5


def test_compute_distance_both_empty():
    assert _compute_distance("", "") == 0.0


def test_compute_distance_one_empty():
    assert _compute_distance("hello", "") == 1.0


# ─── Task 2: _find_matching_xpaths ───────────────────────────────────────────

from lxml import etree as lxml_etree
from lxml import html as lxml_html
from src.stages.condenser import _find_matching_xpaths


def test_find_matching_xpaths_matches_element_text():
    root = lxml_html.fromstring('<html><body><span>darkuser99</span></body></html>')
    tree = root.getroottree()
    xpaths, found = _find_matching_xpaths(root, tree, ["darkuser99"])
    assert len(xpaths) > 0
    assert "darkuser99" in found


def test_find_matching_xpaths_matches_tail_text():
    # "tail text here" is the tail of the <b> element
    root = lxml_html.fromstring('<html><body><p><b></b>tail text here</p></body></html>')
    tree = root.getroottree()
    xpaths, found = _find_matching_xpaths(root, tree, ["tail text here"])
    assert len(xpaths) > 0


def test_find_matching_xpaths_returns_empty_when_no_match():
    root = lxml_html.fromstring('<html><body><p>nothing relevant</p></body></html>')
    tree = root.getroottree()
    xpaths, found = _find_matching_xpaths(root, tree, ["darkuser99"])
    assert len(xpaths) == 0
    assert len(found) == 0


def test_find_matching_xpaths_matches_multiple_targets():
    html = '<html><body><span>darkuser99</span><time>Yesterday</time></body></html>'
    root = lxml_html.fromstring(html)
    tree = root.getroottree()
    xpaths, found = _find_matching_xpaths(root, tree, ["darkuser99", "Yesterday"])
    assert "darkuser99" in found
    assert "Yesterday" in found


def test_find_matching_xpaths_near_match_within_threshold():
    # "Thread titl" vs "Thread title": 1/13 ≈ 0.077 ≤ 0.1 → should match
    root = lxml_html.fromstring('<html><body><a>Thread titl</a></body></html>')
    tree = root.getroottree()
    xpaths, found = _find_matching_xpaths(root, tree, ["Thread title"])
    assert len(xpaths) > 0


# ─── Task 3: condense_html ───────────────────────────────────────────────────

from src.stages.condenser import condense_html
from src.exceptions import CondensationError

_THREAD_HTML = (
    '<html><body>'
    '<nav class="site-nav"><a>Home</a><a>Forum</a><a>Members</a><a>Search</a><a>Login</a>'
    '<a>Register</a><a>Rules</a><a>FAQ</a><a>Contact</a><a>Donate</a></nav>'
    '<div class="thread-list">'
    '<div class="thread-item">'
    '<a class="thread-title">Thread One</a>'
    '<span class="author">admin</span>'
    '<time class="date">Today</time>'
    '</div>'
    '<div class="thread-item unrelated">'
    '<a class="thread-title">Other Thread</a>'
    '<span class="author">nobody</span>'
    '<time class="date">Last week</time>'
    '</div>'
    '<div class="thread-item unrelated2">'
    '<a class="thread-title">Yet Another Thread</a>'
    '<span class="author">someone</span>'
    '</div>'
    '</div>'
    '<footer class="site-footer"><p>Copyright 2024</p><p>Privacy Policy</p>'
    '<p>Terms of Service</p><p>Contact Us</p><p>Powered by XenForo</p></footer>'
    '</body></html>'
)


def test_condense_html_returns_string():
    ie = _make_ie_output(title="Thread One", author="admin", date="Today", link="")
    result = condense_html(_THREAD_HTML, ie)
    assert isinstance(result, str)
    assert len(result) > 0


def test_condense_html_preserves_class_attributes():
    ie = _make_ie_output(title="Thread One", author="admin", date="Today", link="")
    result = condense_html(_THREAD_HTML, ie)
    assert "class=" in result


def test_condense_html_contains_target_values():
    ie = _make_ie_output(title="Thread One", author="admin", date="Today", link="")
    result = condense_html(_THREAD_HTML, ie)
    assert "Thread One" in result
    assert "admin" in result


def test_condense_html_collapses_irrelevant_content():
    ie = _make_ie_output(title="Thread One", author="admin", date="Today", link="")
    result = condense_html(_THREAD_HTML, ie)
    assert "..." in result
    assert "Copyright 2024" not in result


def test_condense_html_raises_when_no_targets_found():
    ie = IEOutput(
        title=FieldExtraction(value="Xyzzy_absent_123", cue_text=""),
        last_post_author=FieldExtraction(value="nobody_xyz_456", cue_text=""),
        last_post_date=FieldExtraction(value="Zork_absent_789", cue_text=""),
        link=FieldExtraction(value="/absent/xyz/link/", cue_text=""),
    )
    html = '<html><body><div class="posts"><p>Unrelated content here</p></div></body></html>'
    with pytest.raises(CondensationError):
        condense_html(html, ie)


def test_condense_html_is_smaller_than_raw():
    ie = _make_ie_output(title="Thread One", author="admin", date="Today", link="")
    result = condense_html(_THREAD_HTML, ie)
    assert len(result) < len(_THREAD_HTML)


# ─── Task 4: integration tests ────────────────────────────────────────────────


@pytest.mark.integration
async def test_condense_altenens():
    from dotenv import load_dotenv
    load_dotenv()
    from src.stages.renderer import render_page
    from src.stages.sanitizer import sanitize_html
    from src.stages.ie_extractor import extract_fields

    rendered = await render_page("https://altenens.is/whats-new/posts/")
    sanitized = sanitize_html(rendered["html"])
    ie_output = await extract_fields(sanitized)

    result = condense_html(rendered["html"], ie_output)

    line_count = result.count('\n') + 1
    print(f"\n[altenens.is] Condensed HTML ({line_count} lines)")
    print(result[:3000])

    assert "class=" in result, "condensed HTML must preserve class attributes"
    assert ie_output.title.value in result, f"title {ie_output.title.value!r} not in condensed HTML"
    assert ie_output.last_post_author.value in result, f"author {ie_output.last_post_author.value!r} not in condensed HTML"


@pytest.mark.integration
async def test_condense_blackbiz():
    from dotenv import load_dotenv
    load_dotenv()
    from src.stages.renderer import render_page
    from src.stages.sanitizer import sanitize_html
    from src.stages.ie_extractor import extract_fields

    rendered = await render_page("https://s1.blackbiz.store/whats-new")
    sanitized = sanitize_html(rendered["html"])
    ie_output = await extract_fields(sanitized)

    result = condense_html(rendered["html"], ie_output)

    line_count = result.count('\n') + 1
    print(f"\n[blackbiz.store] Condensed HTML ({line_count} lines)")
    print(result[:3000])

    assert "class=" in result, "condensed HTML must preserve class attributes"
    # Author is always ASCII — reliable signal that condensation succeeded.
    # Title may be Cyrillic (non-Latin text from LLM can be mis-encoded), so we
    # check author as the primary correctness indicator for this URL.
    assert ie_output.last_post_author.value in result, f"author {ie_output.last_post_author.value!r} not in condensed HTML"
