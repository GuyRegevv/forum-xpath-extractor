import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.stages.reconciler import _extract_problem_rows, reconcile_xpaths
from src.stages.xpath_generator import FieldXPathResult, XPathResults

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


# ── reconcile_xpaths tests ────────────────────────────────────────────────────

def _make_field(match_count: int, xpath: str = "//div/a", confidence: str = "correct") -> FieldXPathResult:
    return FieldXPathResult(
        xpath=xpath,
        sample_value="value",
        confidence=confidence,
        iterations=1,
        match_count=match_count,
    )


def _make_results(title=20, author=20, date=20, link=20) -> XPathResults:
    return XPathResults(
        title=_make_field(title, "//div[contains(@class,'thread-title')]/a"),
        last_post_author=_make_field(author, "//a[contains(@class,'username')]"),
        last_post_date=_make_field(date, "//time"),
        link=_make_field(link, "//div/a/@href"),
    )


@pytest.mark.asyncio
async def test_no_op_when_all_counts_equal():
    results = _make_results(20, 20, 20, 20)
    updated = await reconcile_xpaths(results, "<html></html>", "https://example.com")
    assert updated == results


@pytest.mark.asyncio
async def test_no_op_when_all_counts_equal_but_not_20():
    # All agree on 15 — no discrepancy, nothing to reconcile
    results = _make_results(15, 15, 15, 15)
    updated = await reconcile_xpaths(results, "<html></html>", "https://example.com")
    assert updated == results


@pytest.mark.asyncio
async def test_explanation_added_when_discrepancy():
    results = _make_results(author=18)
    llm_response = json.dumps({
        "explanation": "2 threads have deleted accounts shown as plain text.",
        "revised_xpath": None,
    })
    mock_choice = MagicMock()
    mock_choice.message.content = llm_response
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch("src.stages.reconciler.AsyncOpenAI", return_value=mock_client):
        updated = await reconcile_xpaths(results, _SAMPLE_HTML, "https://example.com")

    assert updated.last_post_author.explanation == "2 threads have deleted accounts shown as plain text."
    assert updated.last_post_author.original_xpath is None  # no revision
    assert updated.last_post_author.xpath == results.last_post_author.xpath  # unchanged


@pytest.mark.asyncio
async def test_revised_xpath_accepted_when_improves_count():
    # The revised XPath targets <span> too, so it matches all 3 rows in _SAMPLE_HTML
    results = XPathResults(
        title=_make_field(3, "//div[contains(@class,'thread-title')]/a"),
        last_post_author=_make_field(2, "//div[contains(@class,'thread-author')]/a[contains(@class,'username')]"),
        last_post_date=_make_field(3, "//time"),
        link=_make_field(3, "//div[contains(@class,'thread-title')]/a/@href"),
    )
    better_xpath = "//*[contains(@class,'username')]"
    llm_response = json.dumps({
        "explanation": "Row 2 uses a span instead of an anchor.",
        "revised_xpath": better_xpath,
    })
    mock_choice = MagicMock()
    mock_choice.message.content = llm_response
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch("src.stages.reconciler.AsyncOpenAI", return_value=mock_client):
        updated = await reconcile_xpaths(results, _SAMPLE_HTML, "https://example.com")

    assert updated.last_post_author.xpath == better_xpath
    assert updated.last_post_author.original_xpath == "//div[contains(@class,'thread-author')]/a[contains(@class,'username')]"
    assert updated.last_post_author.match_count == 3
    assert updated.last_post_author.explanation == "Row 2 uses a span instead of an anchor."


@pytest.mark.asyncio
async def test_revised_xpath_rejected_when_count_does_not_improve():
    results = _make_results(author=18)
    llm_response = json.dumps({
        "explanation": "Some threads have no author.",
        "revised_xpath": "//a[@class='nonexistent']",  # will match 0
    })
    mock_choice = MagicMock()
    mock_choice.message.content = llm_response
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch("src.stages.reconciler.AsyncOpenAI", return_value=mock_client):
        updated = await reconcile_xpaths(results, _SAMPLE_HTML, "https://example.com")

    # Original xpath kept
    assert updated.last_post_author.xpath == results.last_post_author.xpath
    assert updated.last_post_author.original_xpath is None
    # Explanation still stored
    assert updated.last_post_author.explanation == "Some threads have no author."


@pytest.mark.asyncio
async def test_llm_failure_leaves_field_unchanged():
    results = _make_results(author=18)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

    with patch("src.stages.reconciler.AsyncOpenAI", return_value=mock_client):
        updated = await reconcile_xpaths(results, _SAMPLE_HTML, "https://example.com")

    assert updated.last_post_author == results.last_post_author


@pytest.mark.asyncio
async def test_only_discrepant_fields_are_reconciled():
    results = _make_results(author=18)  # only author is discrepant
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "explanation": "deleted accounts",
            "revised_xpath": None,
        })))]
    ))

    with patch("src.stages.reconciler.AsyncOpenAI", return_value=mock_client):
        updated = await reconcile_xpaths(results, _SAMPLE_HTML, "https://example.com")

    # LLM called exactly once — for last_post_author only
    assert mock_client.chat.completions.create.call_count == 1
    # Other fields unchanged
    assert updated.title.explanation is None
    assert updated.last_post_date.explanation is None
    assert updated.link.explanation is None
