import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from src.stages.xpath_generator import (
    ValidationFeedback,
    XPathResult,
    FieldXPathResult,
    XPathResults,
    _parse_xpath_result,
    run_xpath,
    validate_xpath,
    _select_best,
    _generate_single,
    generate_xpaths,
)
from src.stages.ie_extractor import FieldExtraction, IEOutput
from src.exceptions import XPathSyntaxError, XPathGenerationError


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_ie_output(
    title="Thread title",
    author="darkuser99",
    author_cue="Latest: ",
    date="Yesterday at 11:42 PM",
    link="/threads/1/",
) -> IEOutput:
    return IEOutput(
        title=FieldExtraction(value=title, cue_text=""),
        last_post_author=FieldExtraction(value=author, cue_text=author_cue),
        last_post_date=FieldExtraction(value=date, cue_text=""),
        link=FieldExtraction(value=link, cue_text=""),
    )


def _make_field_xpath_result(
    xpath="//a[contains(@class,'title')]",
    sample_value="Thread title",
    confidence="correct",
) -> FieldXPathResult:
    return FieldXPathResult(xpath=xpath, sample_value=sample_value, confidence=confidence)


def _make_mock_client(*responses: str) -> MagicMock:
    mock_resps = []
    for content in responses:
        msg = MagicMock()
        msg.content = content
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        mock_resps.append(resp)
    client = MagicMock()
    client.chat.completions.create = (
        AsyncMock(return_value=mock_resps[0])
        if len(mock_resps) == 1
        else AsyncMock(side_effect=mock_resps)
    )
    return client


# ─── Task 1: models ───────────────────────────────────────────────────────────

def test_validation_feedback_stores_all_fields():
    fb = ValidationFeedback(
        is_correct=True,
        match_count=1,
        matched_values=["darkuser99"],
        feedback_message="Correct",
    )
    assert fb.is_correct is True
    assert fb.match_count == 1
    assert fb.matched_values == ["darkuser99"]


def test_xpath_result_stores_thought_and_xpath():
    r = XPathResult(thought="found it", xpath="//a[@class='title']")
    assert r.thought == "found it"
    assert r.xpath == "//a[@class='title']"


def test_field_xpath_result_stores_all_fields():
    r = FieldXPathResult(xpath="//a", sample_value="hello", confidence="correct")
    assert r.xpath == "//a"
    assert r.sample_value == "hello"
    assert r.confidence == "correct"


def test_xpath_results_has_all_four_fields():
    result = XPathResults(
        title=_make_field_xpath_result(),
        last_post_author=_make_field_xpath_result(
            xpath="//span[@class='author']", sample_value="user"
        ),
        last_post_date=_make_field_xpath_result(xpath="//time", sample_value="Today"),
        link=_make_field_xpath_result(xpath="//a/@href", sample_value="/t/1/"),
    )
    assert result.title.xpath == "//a[contains(@class,'title')]"
    assert result.last_post_author.xpath == "//span[@class='author']"


def test_parse_xpath_result_valid_json():
    content = json.dumps({"thought": "found it", "xpath": "//a"})
    result = _parse_xpath_result(content)
    assert result is not None
    assert result.xpath == "//a"


def test_parse_xpath_result_invalid_json_returns_none():
    assert _parse_xpath_result("not json") is None


def test_parse_xpath_result_missing_field_returns_none():
    content = json.dumps({"thought": "found it"})  # no xpath key
    assert _parse_xpath_result(content) is None


# ─── Task 2: run_xpath ────────────────────────────────────────────────────────

_SAMPLE_HTML = """<html><body>
<div class="thread-list">
  <div class="thread-item">
    <a class="thread-title" href="/threads/42/">My Thread Title</a>
    <span class="author">testuser</span>
    <time class="date">Today</time>
  </div>
</div>
</body></html>"""


def test_run_xpath_returns_text_content():
    values = run_xpath("//span[contains(@class,'author')]", _SAMPLE_HTML)
    assert values == ["testuser"]


def test_run_xpath_attribute_returns_string():
    values = run_xpath("//a[contains(@class,'thread-title')]/@href", _SAMPLE_HTML)
    assert values == ["/threads/42/"]


def test_run_xpath_no_match_returns_empty_list():
    values = run_xpath("//div[@class='nonexistent']", _SAMPLE_HTML)
    assert values == []


def test_run_xpath_invalid_syntax_raises_xpath_syntax_error():
    with pytest.raises(XPathSyntaxError):
        run_xpath("//[invalid", _SAMPLE_HTML)


def test_run_xpath_strips_whitespace():
    html = "<html><body><span>  hello world  </span></body></html>"
    values = run_xpath("//span", html)
    assert values == ["hello world"]


# ─── Task 2: validate_xpath ───────────────────────────────────────────────────

def test_validate_xpath_correct_single_match():
    fb = validate_xpath("//span[contains(@class,'author')]", _SAMPLE_HTML, "testuser")
    assert fb.is_correct is True
    assert "Correct" in fb.feedback_message
    assert fb.match_count == 1


def test_validate_xpath_correct_among_multiple():
    html = "<html><body><a class='t'>Target value</a><a class='t'>Other</a></body></html>"
    fb = validate_xpath("//a[contains(@class,'t')]", html, "Target value")
    assert fb.is_correct is True
    assert "found among" in fb.feedback_message


def test_validate_xpath_zero_matches():
    fb = validate_xpath("//div[@class='absent']", _SAMPLE_HTML, "testuser")
    assert fb.is_correct is False
    assert "Missing" in fb.feedback_message
    assert fb.match_count == 0


def test_validate_xpath_many_matches_still_validates_value():
    # >20 matches no longer hard-rejects; value matching proceeds normally
    many_html = "<html><body>" + "<div>item</div>" * 21 + "</body></html>"
    fb = validate_xpath("//div", many_html, "item")
    assert fb.is_correct is True
    assert fb.match_count == 21


def test_validate_xpath_redundant_no_value_match():
    fb = validate_xpath("//time[contains(@class,'date')]", _SAMPLE_HTML, "NEVER_FOUND_VALUE")
    assert fb.is_correct is False
    assert "Redundant" in fb.feedback_message


def test_validate_xpath_syntax_error_returns_feedback():
    fb = validate_xpath("//[invalid", _SAMPLE_HTML, "testuser")
    assert fb.is_correct is False
    assert "syntax error" in fb.feedback_message.lower()
    assert fb.match_count == 0


def test_validate_xpath_empty_matched_values_not_counted_as_correct():
    html = "<html><body><span class='empty'></span></body></html>"
    fb = validate_xpath("//span[contains(@class,'empty')]", html, "testuser")
    assert fb.is_correct is False


def test_validate_xpath_rejects_hardcoded_value():
    xpath = "//a[contains(@class,'username') and contains(., 'Blackbiz Bot')]"
    fb = validate_xpath(xpath, _SAMPLE_HTML, "Blackbiz Bot")
    assert fb.is_correct is False
    assert "hardcoded" in fb.feedback_message.lower()


def test_validate_xpath_rejects_hardcoded_value_case_insensitive():
    xpath = "//time[contains(., 'A moment ago')]"
    fb = validate_xpath(xpath, _SAMPLE_HTML, "A moment ago")
    assert fb.is_correct is False
    assert "hardcoded" in fb.feedback_message.lower()


def test_validate_xpath_allows_short_value_in_xpath():
    # Values ≤5 chars are not checked — too likely to be a class name fragment
    xpath = "//a[contains(@class,'bot')]"
    fb = validate_xpath(xpath, _SAMPLE_HTML, "bot")
    assert "hardcoded" not in fb.feedback_message.lower()


# ─── Task 3: _select_best ────────────────────────────────────────────────────

def _fb(is_correct: bool, match_count: int, matched: list[str] | None = None) -> ValidationFeedback:
    return ValidationFeedback(
        is_correct=is_correct,
        match_count=match_count,
        matched_values=matched or (["val"] if match_count > 0 else []),
        feedback_message="Correct" if is_correct else "Wrong",
    )


def test_select_best_returns_first_correct():
    attempts = [
        ("//wrong", _fb(False, 0)),
        ("//correct", _fb(True, 15, ["Thread title"])),
        ("//also-correct", _fb(True, 15, ["Thread title"])),
    ]
    result = _select_best(attempts, "title")
    assert result.xpath == "//correct"
    assert result.confidence == "correct"
    assert result.sample_value == "Thread title"
    assert result.match_count == 15


def test_select_best_best_effort_when_no_correct():
    attempts = [
        ("//one-match", _fb(False, 1, ["wrong"])),
        ("//five-matches", _fb(False, 5, ["wrong"] * 5)),
        ("//zero", _fb(False, 0)),
    ]
    result = _select_best(attempts, "title")
    assert result.xpath == "//five-matches"
    assert result.confidence == "best_effort"


def test_select_best_prefers_higher_match_count_for_best_effort():
    # No longer excludes >20; picks highest match count among non-correct attempts
    attempts = [
        ("//broader", _fb(False, 25)),
        ("//closer", _fb(False, 3, ["wrong"] * 3)),
    ]
    result = _select_best(attempts, "title")
    assert result.xpath == "//broader"
    assert result.confidence == "best_effort"
    assert result.match_count == 25


def test_select_best_failed_when_all_zero_matches():
    attempts = [
        ("//first", _fb(False, 0)),
        ("//second", _fb(False, 0)),
        ("//last", _fb(False, 0)),
    ]
    result = _select_best(attempts, "title")
    assert result.xpath == "//last"
    assert result.confidence == "failed"
    assert result.sample_value == ""


def test_select_best_failed_when_all_json_errors():
    attempts = [
        (None, _fb(False, 0)),
        (None, _fb(False, 0)),
    ]
    result = _select_best(attempts, "title")
    assert result.xpath == ""
    assert result.confidence == "failed"


# ─── Task 4: _generate_single ────────────────────────────────────────────────

_LOOP_HTML = """<html><body>
<div class="thread-list">
  <div class="thread-item">
    <a class="thread-title" href="/threads/42/">My Thread Title</a>
    <span class="author">testuser</span>
    <time class="date">Today at 3PM</time>
  </div>
</div>
</body></html>"""

_CORRECT_TITLE_JSON = json.dumps({
    "thought": "The title is in the a.thread-title",
    "xpath": "//a[contains(@class,'thread-title')]",
})
_WRONG_JSON = json.dumps({
    "thought": "wrong guess",
    "xpath": "//div[@class='nonexistent']",
})
_LINK_JSON = json.dumps({
    "thought": "The href is on a.thread-title",
    "xpath": "//a[contains(@class,'thread-title')]/@href",
})


async def test_generate_single_correct_on_first_try():
    client = _make_mock_client(_CORRECT_TITLE_JSON)
    result, iterations = await _generate_single(
        field_name="title",
        field_value="My Thread Title",
        cue_text="",
        condensed_html=_LOOP_HTML,
        raw_html=_LOOP_HTML,
        client=client,
        model="gpt-4o",
        is_link=False,
    )
    assert result.confidence == "correct"
    assert "thread-title" in result.xpath
    assert iterations == 1
    assert client.chat.completions.create.await_count == 1


async def test_generate_single_json_retry_counts_as_iteration():
    client = _make_mock_client("not json", _CORRECT_TITLE_JSON)
    result, iterations = await _generate_single(
        field_name="title",
        field_value="My Thread Title",
        cue_text="",
        condensed_html=_LOOP_HTML,
        raw_html=_LOOP_HTML,
        client=client,
        model="gpt-4o",
        is_link=False,
    )
    assert iterations == 2
    assert client.chat.completions.create.await_count == 2


async def test_generate_single_refines_on_wrong_xpath():
    client = _make_mock_client(_WRONG_JSON, _CORRECT_TITLE_JSON)
    result, iterations = await _generate_single(
        field_name="title",
        field_value="My Thread Title",
        cue_text="",
        condensed_html=_LOOP_HTML,
        raw_html=_LOOP_HTML,
        client=client,
        model="gpt-4o",
        is_link=False,
    )
    assert result.confidence == "correct"
    assert iterations == 2


async def test_generate_single_all_attempts_fail_returns_best_effort_or_failed():
    # Use an expected value that's genuinely absent from the HTML so all
    # attempts fail validation — XPath matches elements, but none contain it.
    _AUTHOR_JSON = json.dumps({"thought": "author", "xpath": "//span[contains(@class,'author')]"})
    _TIME_JSON   = json.dumps({"thought": "date",   "xpath": "//time[contains(@class,'date')]"})
    _ABSENT_JSON = json.dumps({"thought": "absent",  "xpath": "//div[@class='nonexistent']"})
    client = _make_mock_client(_AUTHOR_JSON, _TIME_JSON, _ABSENT_JSON)
    result, iterations = await _generate_single(
        field_name="title",
        field_value="UNIQUE_NOT_IN_HTML_12345",
        cue_text="",
        condensed_html=_LOOP_HTML,
        raw_html=_LOOP_HTML,
        client=client,
        model="gpt-4o",
        is_link=False,
    )
    assert result.confidence in ("best_effort", "failed")
    assert iterations == 3
    assert client.chat.completions.create.await_count == 3


async def test_generate_single_raises_on_api_failure():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("connection failed"))
    with pytest.raises(XPathGenerationError, match="LLM API call failed"):
        await _generate_single(
            field_name="title",
            field_value="My Thread Title",
            cue_text="",
            condensed_html=_LOOP_HTML,
            raw_html=_LOOP_HTML,
            client=client,
            model="gpt-4o",
            is_link=False,
        )


async def test_generate_single_link_field_includes_href_note():
    client = _make_mock_client(_LINK_JSON)
    await _generate_single(
        field_name="link",
        field_value="/threads/42/",
        cue_text="",
        condensed_html=_LOOP_HTML,
        raw_html=_LOOP_HTML,
        client=client,
        model="gpt-4o",
        is_link=True,
    )
    call_kwargs = client.chat.completions.create.call_args.kwargs
    user_content = call_kwargs["messages"][1]["content"]
    assert "/@href" in user_content


async def test_generate_single_sends_system_message():
    client = _make_mock_client(_CORRECT_TITLE_JSON)
    await _generate_single(
        field_name="title",
        field_value="My Thread Title",
        cue_text="",
        condensed_html=_LOOP_HTML,
        raw_html=_LOOP_HTML,
        client=client,
        model="gpt-4o",
        is_link=False,
    )
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["messages"][0]["role"] == "system"
    assert "XPath" in call_kwargs["messages"][0]["content"]


async def test_generate_single_uses_temperature_zero_and_max_tokens_500():
    client = _make_mock_client(_CORRECT_TITLE_JSON)
    await _generate_single(
        field_name="title",
        field_value="My Thread Title",
        cue_text="",
        condensed_html=_LOOP_HTML,
        raw_html=_LOOP_HTML,
        client=client,
        model="gpt-4o",
        is_link=False,
    )
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["max_tokens"] == 500


# ─── Task 5: generate_xpaths ─────────────────────────────────────────────────

_CORRECT_AUTHOR_JSON = json.dumps({
    "thought": "The author is in span.author",
    "xpath": "//span[contains(@class,'author')]",
})
_CORRECT_DATE_JSON = json.dumps({
    "thought": "The date is in time.date",
    "xpath": "//time[contains(@class,'date')]",
})
_CORRECT_LINK_JSON = json.dumps({
    "thought": "The href is on a.thread-title",
    "xpath": "//a[contains(@class,'thread-title')]/@href",
})


async def test_generate_xpaths_returns_xpath_results():
    ie = _make_ie_output(
        title="My Thread Title",
        author="testuser",
        date="Today at 3PM",
        link="/threads/42/",
    )
    client = _make_mock_client(
        _CORRECT_TITLE_JSON,
        _CORRECT_AUTHOR_JSON,
        _CORRECT_DATE_JSON,
        _CORRECT_LINK_JSON,
    )
    with patch("src.stages.xpath_generator.AsyncOpenAI", return_value=client):
        result = await generate_xpaths(_LOOP_HTML, ie, _LOOP_HTML)
    assert isinstance(result, XPathResults)
    assert result.title.confidence == "correct"
    assert result.last_post_author.confidence == "correct"
    assert result.last_post_date.confidence == "correct"
    assert result.link.confidence == "correct"


async def test_generate_xpaths_calls_llm_four_times():
    ie = _make_ie_output(
        title="My Thread Title", author="testuser", date="Today at 3PM", link="/threads/42/",
    )
    client = _make_mock_client(
        _CORRECT_TITLE_JSON, _CORRECT_AUTHOR_JSON, _CORRECT_DATE_JSON, _CORRECT_LINK_JSON,
    )
    with patch("src.stages.xpath_generator.AsyncOpenAI", return_value=client):
        await generate_xpaths(_LOOP_HTML, ie, _LOOP_HTML)
    assert client.chat.completions.create.await_count == 4


async def test_generate_xpaths_raises_on_empty_condensed_html():
    ie = _make_ie_output()
    with pytest.raises(XPathGenerationError, match="empty"):
        await generate_xpaths("", ie, _LOOP_HTML)


async def test_generate_xpaths_raises_on_api_failure():
    ie = _make_ie_output(
        title="My Thread Title", author="testuser", date="Today at 3PM", link="/threads/42/"
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("network error"))
    with patch("src.stages.xpath_generator.AsyncOpenAI", return_value=client):
        with pytest.raises(XPathGenerationError, match="LLM API call failed"):
            await generate_xpaths(_LOOP_HTML, ie, _LOOP_HTML)


async def test_generate_xpaths_uses_model_name_from_env(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "gpt-4-turbo")
    ie = _make_ie_output(
        title="My Thread Title", author="testuser", date="Today at 3PM", link="/threads/42/",
    )
    client = _make_mock_client(
        _CORRECT_TITLE_JSON, _CORRECT_AUTHOR_JSON, _CORRECT_DATE_JSON, _CORRECT_LINK_JSON,
    )
    with patch("src.stages.xpath_generator.AsyncOpenAI", return_value=client):
        await generate_xpaths(_LOOP_HTML, ie, _LOOP_HTML)
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4-turbo"


# ─── Task 6: integration tests ────────────────────────────────────────────────

@pytest.mark.integration
async def test_generate_xpaths_altenens():
    from dotenv import load_dotenv
    load_dotenv()
    from src.stages.renderer import render_page
    from src.stages.sanitizer import sanitize_html
    from src.stages.ie_extractor import extract_fields
    from src.stages.condenser import condense_html

    rendered = await render_page("https://altenens.is/whats-new/posts/")
    sanitized = sanitize_html(rendered["html"])
    ie_output = await extract_fields(sanitized)
    condensed = condense_html(rendered["html"], ie_output)

    result = await generate_xpaths(condensed, ie_output, rendered["html"])

    print(f"\n[altenens.is] XPath results:")
    for field_name in ("title", "last_post_author", "last_post_date", "link"):
        r = getattr(result, field_name)
        print(f"  {field_name:20s}: {r.confidence:12s} | {r.xpath}")
        print(f"  {'':20s}  sample: {r.sample_value!r}")

    correct_count = sum(
        1 for f in ("title", "last_post_author", "last_post_date", "link")
        if getattr(result, f).confidence == "correct"
    )
    assert correct_count >= 2, f"Only {correct_count}/4 fields correct"

    for field_name in ("title", "last_post_author", "last_post_date", "link"):
        r = getattr(result, field_name)
        assert r.xpath, f"{field_name} xpath is empty"

    # Correct xpaths must actually return values from raw HTML
    for field_name in ("title", "last_post_author", "last_post_date", "link"):
        r = getattr(result, field_name)
        if r.confidence == "correct":
            values = run_xpath(r.xpath, rendered["html"])
            assert values, f"Correct {field_name} xpath '{r.xpath}' returns nothing on raw HTML"


@pytest.mark.integration
async def test_generate_xpaths_blackbiz():
    from dotenv import load_dotenv
    load_dotenv()
    from src.stages.renderer import render_page
    from src.stages.sanitizer import sanitize_html
    from src.stages.ie_extractor import extract_fields
    from src.stages.condenser import condense_html

    rendered = await render_page("https://s1.blackbiz.store/whats-new")
    sanitized = sanitize_html(rendered["html"])
    ie_output = await extract_fields(sanitized)
    condensed = condense_html(rendered["html"], ie_output)

    result = await generate_xpaths(condensed, ie_output, rendered["html"])

    print(f"\n[blackbiz.store] XPath results:")
    for field_name in ("title", "last_post_author", "last_post_date", "link"):
        r = getattr(result, field_name)
        print(f"  {field_name:20s}: {r.confidence:12s} | {r.xpath}")
        print(f"  {'':20s}  sample: {r.sample_value!r}")

    for field_name in ("title", "last_post_author", "last_post_date", "link"):
        r = getattr(result, field_name)
        assert r.xpath, f"{field_name} xpath is empty"

    assert result.last_post_author.confidence == "correct", \
        f"last_post_author should be correct, got: {result.last_post_author.confidence}"
