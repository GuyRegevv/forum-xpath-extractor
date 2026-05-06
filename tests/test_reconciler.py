import pytest
from src.stages.reconciler import _extract_problem_rows

# Three thread rows. Row 2 has a <span> instead of <a> for the author.
_SAMPLE_HTML = """
<html><body>
<div class="threadList">
  <div class="row">
    <div class="thread-title"><a href="/t/1">Thread 1</a></div>
    <div class="thread-author"><a class="username">user1</a></div>
  </div>
  <div class="row">
    <div class="thread-title"><a href="/t/2">Thread 2</a></div>
    <div class="thread-author"><span class="username">deleted</span></div>
  </div>
  <div class="row">
    <div class="thread-title"><a href="/t/3">Thread 3</a></div>
    <div class="thread-author"><a class="username">user3</a></div>
  </div>
</div>
</body></html>
"""

_TITLE_XPATH = "//div[contains(@class,'thread-title')]/a"
_AUTHOR_XPATH = "//div[contains(@class,'thread-author')]/a[contains(@class,'username')]"


def test_returns_list():
    result = _extract_problem_rows(_SAMPLE_HTML, _TITLE_XPATH, _AUTHOR_XPATH)
    assert isinstance(result, list)


def test_finds_one_problem_row():
    result = _extract_problem_rows(_SAMPLE_HTML, _TITLE_XPATH, _AUTHOR_XPATH)
    assert len(result) == 1


def test_problem_row_contains_deleted_span():
    result = _extract_problem_rows(_SAMPLE_HTML, _TITLE_XPATH, _AUTHOR_XPATH)
    assert "deleted" in result[0]


def test_problem_row_is_the_second_row():
    result = _extract_problem_rows(_SAMPLE_HTML, _TITLE_XPATH, _AUTHOR_XPATH)
    assert "Thread 2" in result[0]


def test_returns_empty_when_all_rows_match():
    # All rows have an <a class="username"> — no problem rows
    html = """
    <html><body><div class="list">
      <div class="row"><div class="t"><a href="/1">T1</a></div><a class="username">u1</a></div>
      <div class="row"><div class="t"><a href="/2">T2</a></div><a class="username">u2</a></div>
    </div></body></html>
    """
    result = _extract_problem_rows(
        html,
        "//div[contains(@class,'t')]/a",
        "//a[contains(@class,'username')]",
    )
    assert result == []


def test_returns_empty_when_title_xpath_finds_nothing():
    result = _extract_problem_rows(_SAMPLE_HTML, "//div[@class='absent']/a", _AUTHOR_XPATH)
    assert result == []


def test_strips_text_suffix_from_xpath():
    # /text() suffix must be stripped before running at element level
    result = _extract_problem_rows(
        _SAMPLE_HTML,
        _TITLE_XPATH + "/text()",
        _AUTHOR_XPATH + "/text()",
    )
    assert len(result) == 1


def test_strips_attr_suffix_from_xpath():
    # /@href suffix must be stripped before running at element level
    result = _extract_problem_rows(
        _SAMPLE_HTML,
        _TITLE_XPATH + "/@href",
        _AUTHOR_XPATH,
    )
    assert len(result) == 1


def test_problem_row_is_serialized_html_string():
    result = _extract_problem_rows(_SAMPLE_HTML, _TITLE_XPATH, _AUTHOR_XPATH)
    assert isinstance(result[0], str)
    assert "<div" in result[0]
