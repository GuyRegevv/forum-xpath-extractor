import json
import logging
import os
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from src.exceptions import IEExtractionError

logger = logging.getLogger(__name__)

_SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "forum-expert-skill" / "SKILL.md"
)

_TASK_INSTRUCTION = """\
Your task is to analyse the forum HTML below and extract the following fields
from ONE thread item that clearly shows all four fields:

- title: the thread title
- last_post_author: the username of the most recent poster (NOT the original poster)
- last_post_date: the date/time of the most recent post (NOT the thread creation date)
- link: the URL path of the thread. The href attribute is preserved on <a> tags in
  this sanitized format. Extract the href value from the anchor element that contains
  the thread title. Never return an empty string.

For each field, also extract the cue_text — the nearby label text that signals
the field's meaning. If no cue text exists, use an empty string.

Return ONLY a JSON object. No explanation. No markdown. Raw JSON only.
Follow this exact schema:
{
  "title": {"value": "...", "cue_text": "..."},
  "last_post_author": {"value": "...", "cue_text": "..."},
  "last_post_date": {"value": "...", "cue_text": "..."},
  "link": {"value": "...", "cue_text": "..."}
}"""

_CORRECTION_PROMPT = (
    "Your previous response was not valid JSON. "
    "Return only raw JSON, no explanation, no markdown fences."
)


class FieldExtraction(BaseModel):
    value: str
    cue_text: str


class IEOutput(BaseModel):
    title: FieldExtraction
    last_post_author: FieldExtraction
    last_post_date: FieldExtraction
    link: FieldExtraction


def _fix_encoding(text: str) -> str:
    try:
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _fix_ie_output_encoding(result: IEOutput) -> IEOutput:
    return IEOutput(
        title=FieldExtraction(value=_fix_encoding(result.title.value), cue_text=_fix_encoding(result.title.cue_text)),
        last_post_author=FieldExtraction(value=_fix_encoding(result.last_post_author.value), cue_text=_fix_encoding(result.last_post_author.cue_text)),
        last_post_date=FieldExtraction(value=_fix_encoding(result.last_post_date.value), cue_text=_fix_encoding(result.last_post_date.cue_text)),
        link=FieldExtraction(value=_fix_encoding(result.link.value), cue_text=_fix_encoding(result.link.cue_text)),
    )


def _parse_and_validate(content: str) -> IEOutput | None:
    try:
        data = json.loads(content)
        result = IEOutput.model_validate(data)
        return _fix_ie_output_encoding(result)
    except (json.JSONDecodeError, ValidationError):
        return None


async def extract_fields(sanitized_html: str) -> IEOutput:
    """
    Extract thread field values and cue texts from sanitized forum HTML.
    Uses a forum-expert LLM prompt to identify title, last_post_author,
    last_post_date, and link from the thread list.

    Args:
        sanitized_html: Stripped HTML string from Stage 2

    Returns:
        IEOutput: Validated Pydantic model with value + cue_text for each field

    Raises:
        IEExtractionError: If extraction fails after retry
    """
    skill_content = _SKILL_PATH.read_text()
    system_message = skill_content + "\n\n" + _TASK_INSTRUCTION

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": f"# Forum HTML:\n{sanitized_html}"},
    ]

    model = os.getenv("MODEL_NAME", "gpt-4o")
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise IEExtractionError(f"LLM API call failed: {exc}") from exc

    content = response.choices[0].message.content
    result = _parse_and_validate(content)

    if result is None:
        correction_messages = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": _CORRECTION_PROMPT},
        ]
        try:
            retry_response = await client.chat.completions.create(
                model=model,
                messages=correction_messages,
                temperature=0,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise IEExtractionError(f"LLM API call failed on retry: {exc}") from exc

        content = retry_response.choices[0].message.content
        result = _parse_and_validate(content)

        if result is None:
            raise IEExtractionError(
                "IE extraction failed after retry: invalid JSON or schema mismatch"
            )

    # Safety net: if LLM returned empty link despite href being visible, use title as locator
    if not result.link.value and result.title.value:
        result = result.model_copy(
            update={"link": FieldExtraction(value=result.title.value, cue_text="")}
        )

    for field_name in ("title", "last_post_author", "last_post_date", "link"):
        field = getattr(result, field_name)
        if not field.value:
            raise IEExtractionError(f"Empty value for required field: {field_name}")

    logger.info(
        "[IE] Extracted: title=%r author=%r date=%r link=%r",
        result.title.value,
        result.last_post_author.value,
        result.last_post_date.value,
        result.link.value,
    )
    return result
