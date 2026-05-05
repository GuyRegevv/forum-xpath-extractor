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
- link: the URL path of the thread

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


def _parse_and_validate(content: str) -> IEOutput | None:
    try:
        data = json.loads(content)
        return IEOutput.model_validate(data)
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

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=1000,
    )

    content = response.choices[0].message.content
    result = _parse_and_validate(content)

    if result is None:
        raise IEExtractionError("IE extraction failed: invalid JSON or schema mismatch")

    logger.info(
        "[IE] Extracted: title=%r author=%r date=%r link=%r",
        result.title.value,
        result.last_post_author.value,
        result.last_post_date.value,
        result.link.value,
    )
    return result
