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
