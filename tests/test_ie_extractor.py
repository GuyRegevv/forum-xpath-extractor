import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from src.stages.ie_extractor import FieldExtraction, IEOutput


# ─── Task 1: Pydantic models ─────────────────────────────────────────────────

def test_field_extraction_stores_value_and_cue_text():
    f = FieldExtraction(value="darkuser99", cue_text="Latest: ")
    assert f.value == "darkuser99"
    assert f.cue_text == "Latest: "


def test_field_extraction_allows_empty_cue_text():
    f = FieldExtraction(value="Thread title", cue_text="")
    assert f.cue_text == ""


def test_ie_output_has_all_four_fields():
    output = IEOutput(
        title=FieldExtraction(value="Thread title", cue_text=""),
        last_post_author=FieldExtraction(value="user123", cue_text="Latest: "),
        last_post_date=FieldExtraction(value="Yesterday at 11:42 PM", cue_text=""),
        link=FieldExtraction(value="/threads/thread.1/", cue_text=""),
    )
    assert output.title.value == "Thread title"
    assert output.last_post_author.cue_text == "Latest: "
    assert output.last_post_date.value == "Yesterday at 11:42 PM"
    assert output.link.value == "/threads/thread.1/"


def test_ie_output_rejects_missing_field():
    with pytest.raises(ValidationError):
        IEOutput(
            title=FieldExtraction(value="Title", cue_text=""),
            last_post_author=FieldExtraction(value="user", cue_text=""),
            # missing last_post_date and link
        )


# ─── helpers ─────────────────────────────────────────────────────────────────

VALID_JSON = json.dumps({
    "title": {"value": "How to configure XenForo permissions", "cue_text": ""},
    "last_post_author": {"value": "darkuser99", "cue_text": "Latest: "},
    "last_post_date": {"value": "Yesterday at 11:42 PM", "cue_text": ""},
    "link": {"value": "/threads/how-to-configure-xenforo-permissions.1234/", "cue_text": ""},
})


def _make_mock_client(*responses: str) -> MagicMock:
    """Build a mock AsyncOpenAI client returning the given responses in sequence."""
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


# ─── Task 2: happy path ───────────────────────────────────────────────────────

from src.stages.ie_extractor import extract_fields


async def test_extract_fields_returns_ie_output_on_valid_response():
    mock_client = _make_mock_client(VALID_JSON)
    with patch("src.stages.ie_extractor.AsyncOpenAI", return_value=mock_client):
        result = await extract_fields("<html><body><p>Thread list</p></body></html>")
    assert isinstance(result, IEOutput)
    assert result.title.value == "How to configure XenForo permissions"
    assert result.last_post_author.value == "darkuser99"
    assert result.last_post_author.cue_text == "Latest: "
    assert result.last_post_date.value == "Yesterday at 11:42 PM"


async def test_extract_fields_includes_html_in_user_message():
    mock_client = _make_mock_client(VALID_JSON)
    html = "<html><body><p>Unique thread content 12345</p></body></html>"
    with patch("src.stages.ie_extractor.AsyncOpenAI", return_value=mock_client):
        await extract_fields(html)
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    user_content = call_kwargs["messages"][-1]["content"]
    assert html in user_content


async def test_extract_fields_uses_model_name_from_env(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "gpt-4-turbo")
    mock_client = _make_mock_client(VALID_JSON)
    with patch("src.stages.ie_extractor.AsyncOpenAI", return_value=mock_client):
        await extract_fields("<html>...</html>")
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4-turbo"


async def test_extract_fields_uses_temperature_zero():
    mock_client = _make_mock_client(VALID_JSON)
    with patch("src.stages.ie_extractor.AsyncOpenAI", return_value=mock_client):
        await extract_fields("<html>...</html>")
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["temperature"] == 0


async def test_extract_fields_sends_system_message_with_skill_content():
    mock_client = _make_mock_client(VALID_JSON)
    with patch("src.stages.ie_extractor.AsyncOpenAI", return_value=mock_client):
        await extract_fields("<html>...</html>")
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 500  # skill file was loaded
