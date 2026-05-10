import json
import logging
import os

from lxml import etree as lxml_etree
from lxml import html as lxml_html
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from rapidfuzz import fuzz

from src.exceptions import XPathGenerationError, XPathSyntaxError
from src.stages.ie_extractor import IEOutput

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3

_SYSTEM_PROMPT = """\
You are a pro software engineer specializing in XPath query generation.
Your task is to read the HTML provided and generate ONE XPath expression
that reliably extracts the target value from any page with this structure.

Rules:
1. Never hardcode the target value — not the full string, not a fragment of it.
   Titles, usernames, dates, and URLs are all different on every page.
2. Use contains(@class, 'value') instead of @class='value' for class matching
   — elements often have multiple classes.
3. Never filter on text content. Do not use contains(., '...'), [.='...'], or
   text()='...' to match dynamic values. Navigate to elements using class names,
   tag names, data attributes, and XPath axes only.
   Exception: you MAY use a contains(., '...') predicate on a stable structural
   label (the cue text) to locate an anchor element — never on the target value.
4. If a cue text exists, use it as a structural anchor — traverse from the
   cue text node to the target using XPath axes (following-sibling, parent,
   ancestor, descendant).
5. String functions (contains, starts-with, normalize-space) are allowed on
   attributes only — e.g. contains(@href, '/members/'). Never on text content.
6. Prefer class-based or semantic-attribute-based paths over positional indices.
7. The XPath must work on any page of this forum — imagine it running on 100
   different thread listing pages with completely different content.
8. Always respond in this exact JSON format:
   {"thought": "...", "xpath": "..."}"""

_JSON_CORRECTION_PROMPT = (
    "Your previous response was not valid JSON. "
    'Return only raw JSON in this format: {"thought": "...", "xpath": "..."} '
    "No explanation, no markdown fences."
)


# ── Models ─────────────────────────────────────────────────────────────────────

class ValidationFeedback(BaseModel):
    is_correct: bool
    match_count: int
    matched_values: list[str]
    feedback_message: str


class XPathResult(BaseModel):
    thought: str
    xpath: str


class FieldXPathResult(BaseModel):
    xpath: str
    sample_value: str
    confidence: str  # "correct" | "best_effort" | "failed"
    iterations: int = 1
    match_count: int = 0
    original_xpath: str | None = None
    explanation: str | None = None


class XPathResults(BaseModel):
    title: FieldXPathResult
    last_post_author: FieldXPathResult
    last_post_date: FieldXPathResult
    link: FieldXPathResult


def _parse_xpath_result(content: str) -> XPathResult | None:
    try:
        data = json.loads(content)
        return XPathResult.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        return None


# ── XPath Execution ────────────────────────────────────────────────────────────

def run_xpath(xpath: str, raw_html: str) -> list[str]:
    """Execute an XPath against raw HTML. Returns matched text/attribute values."""
    try:
        tree = lxml_html.fromstring(raw_html)
        results = tree.xpath(xpath)
        values = []
        for r in results:
            if isinstance(r, str):
                values.append(r.strip())
            elif hasattr(r, 'text_content'):
                values.append(r.text_content().strip())
        return values
    except lxml_etree.XPathError as e:
        raise XPathSyntaxError(str(e)) from e


# ── Validation ─────────────────────────────────────────────────────────────────

def validate_xpath(xpath: str, raw_html: str, expected_value: str) -> ValidationFeedback:
    """Evaluate a generated XPath. Returns structured feedback for the LLM."""
    if len(expected_value) > 5 and expected_value.lower() in xpath.lower():
        return ValidationFeedback(
            is_correct=False,
            match_count=0,
            matched_values=[],
            feedback_message=(
                f"Hardcoded value: XPath contains the literal target value '{expected_value}'. "
                "Remove text predicates with specific values and use structural attributes "
                "(class names, data attributes) instead."
            ),
        )

    try:
        matched = run_xpath(xpath, raw_html)
    except XPathSyntaxError as e:
        return ValidationFeedback(
            is_correct=False,
            match_count=0,
            matched_values=[],
            feedback_message=f"XPath syntax error: {e}",
        )

    if not matched:
        return ValidationFeedback(
            is_correct=False,
            match_count=0,
            matched_values=[],
            feedback_message=f"Missing: XPath matched 0 elements. Expected to find: '{expected_value}'",
        )

    if len(matched) > 20:
        logger.debug("[XPathGen] XPath matched %d elements — may be broad", len(matched))

    expected_lower = expected_value.lower().strip()
    for value in matched:
        value_lower = value.lower()
        if value_lower and (expected_lower in value_lower or value_lower in expected_lower):
            msg = "Correct" if len(matched) == 1 else f"Correct (found among {len(matched)} matches)"
            return ValidationFeedback(
                is_correct=True,
                match_count=len(matched),
                matched_values=matched,
                feedback_message=msg,
            )

    for value in matched:
        value_lower = value.lower()
        if value_lower and fuzz.partial_ratio(expected_lower, value_lower) >= 85:
            msg = "Correct" if len(matched) == 1 else f"Correct (found among {len(matched)} matches)"
            return ValidationFeedback(
                is_correct=True,
                match_count=len(matched),
                matched_values=matched,
                feedback_message=msg,
            )

    sample = matched[:3]
    return ValidationFeedback(
        is_correct=False,
        match_count=len(matched),
        matched_values=matched,
        feedback_message=(
            f"Redundant: XPath matched {len(matched)} elements but none contained "
            f"'{expected_value}'. Matched: {sample}"
        ),
    )


# ── Best Result Selector ───────────────────────────────────────────────────────

def _select_best(
    attempts: list[tuple[str | None, ValidationFeedback]],
    field_name: str,
) -> FieldXPathResult:
    """Given all attempts for a field, select the best XPath."""
    # 1. First correct attempt
    for xpath, feedback in attempts:
        if feedback.is_correct and xpath:
            sample = feedback.matched_values[0] if feedback.matched_values else ""
            return FieldXPathResult(xpath=xpath, sample_value=sample, confidence="correct", match_count=feedback.match_count)

    # 2. Highest match count > 0 (best effort)
    best_xpath: str | None = None
    best_count = 0
    best_feedback: ValidationFeedback | None = None
    for xpath, feedback in attempts:
        if xpath and feedback.match_count > best_count:
            best_count = feedback.match_count
            best_xpath = xpath
            best_feedback = feedback

    if best_xpath and best_feedback:
        sample = best_feedback.matched_values[0] if best_feedback.matched_values else ""
        logger.warning("[XPathGen] Field: %s — no correct XPath, using best effort", field_name)
        return FieldXPathResult(xpath=best_xpath, sample_value=sample, confidence="best_effort", match_count=best_feedback.match_count)

    # 3. Last attempt with a non-None xpath (even if 0 matches)
    for xpath, _ in reversed(attempts):
        if xpath:
            logger.warning("[XPathGen] Field: %s — all attempts failed (0 matches), using last", field_name)
            return FieldXPathResult(xpath=xpath, sample_value="", confidence="failed", match_count=0)

    # All attempts were JSON parse failures
    logger.warning("[XPathGen] Field: %s — all attempts returned invalid JSON", field_name)
    return FieldXPathResult(xpath="", sample_value="", confidence="failed")


# ── HTML Snippet Helper ───────────────────────────────────────────────────────

def _html_snippet(html: str, target: str, context_lines: int = 4) -> str:
    """Return lines surrounding the first occurrence of target in html."""
    lines = html.splitlines()
    target_lower = target.lower()
    for i, line in enumerate(lines):
        if target_lower in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            snippet = "\n".join(lines[start:end])
            return f"Relevant HTML where the value appears:\n{snippet}\n"
    return ""


# ── Per-Field Generator ────────────────────────────────────────────────────────

async def _generate_single(
    field_name: str,
    field_value: str,
    cue_text: str,
    condensed_html: str,
    raw_html: str,
    client: AsyncOpenAI,
    model: str,
    is_link: bool = False,
) -> tuple[FieldXPathResult, int]:
    """Run the LLM feedback loop for one field. Returns (result, iteration_count)."""
    link_note = (
        "\nNote: This field is a URL. The XPath must end with /@href to extract the "
        "attribute value, not the text content of the link."
        if is_link
        else ""
    )
    snippet = _html_snippet(condensed_html, field_value)
    initial_prompt = (
        f"Target field: {field_name}\n"
        f"Target value: {field_value}\n"
        f"Cue text: {cue_text}{link_note}\n\n"
        f"HTML context:\n{condensed_html}\n\n"
        f"{snippet}"
        "Generate the XPath for the target field."
    )

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": initial_prompt},
    ]

    attempts: list[tuple[str | None, ValidationFeedback]] = []

    for iteration in range(MAX_ITERATIONS):
        logger.info(
            "[XPathGen] Field: %s | Iteration %d/%d", field_name, iteration + 1, MAX_ITERATIONS
        )

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise XPathGenerationError(f"LLM API call failed: {exc}") from exc

        content = response.choices[0].message.content
        messages.append({"role": "assistant", "content": content})

        xpath_result = _parse_xpath_result(content)
        if xpath_result is None:
            feedback = ValidationFeedback(
                is_correct=False,
                match_count=0,
                matched_values=[],
                feedback_message="Invalid JSON response from LLM",
            )
            attempts.append((None, feedback))
            logger.warning(
                "[XPathGen] Field: %s — invalid JSON on iteration %d", field_name, iteration + 1
            )
            if iteration < MAX_ITERATIONS - 1:
                messages.append({"role": "user", "content": _JSON_CORRECTION_PROMPT})
            continue

        logger.debug("[XPathGen] Thought: %s", xpath_result.thought)
        logger.info("[XPathGen] Generated: %s", xpath_result.xpath)

        feedback = validate_xpath(xpath_result.xpath, raw_html, field_value)
        logger.info("[XPathGen] Validation: %s", feedback.feedback_message)
        attempts.append((xpath_result.xpath, feedback))

        if feedback.is_correct:
            break

        if iteration < MAX_ITERATIONS - 1:
            html_hint = ""
            if feedback.match_count == 0:
                html_hint = _html_snippet(condensed_html, field_value)
            feedback_prompt = (
                f"Your previous XPath was: {xpath_result.xpath}\n"
                f"Validation result: {feedback.feedback_message}\n"
                f"{html_hint}\n"
                "Refine the XPath based on this feedback.\n"
                "The refined XPath must address the issue described.\n"
                'Respond in the same JSON format: {"thought": "...", "xpath": "..."}'
            )
            messages.append({"role": "user", "content": feedback_prompt})

    return _select_best(attempts, field_name), len(attempts)


# ── Entry Point ────────────────────────────────────────────────────────────────

async def generate_xpaths(
    condensed_html: str,
    ie_output: IEOutput,
    raw_html: str,
) -> XPathResults:
    """
    Orchestrate XPath generation for all four fields sequentially.
    Implements the Conversational XPath Evaluator from XPath Agent (2025).

    Args:
        condensed_html: Output of Stage 4 — focused HTML with full attributes
        ie_output:      Validated IE output from Stage 3
        raw_html:       Original rendered HTML from Stage 1 — used for XPath validation

    Returns:
        XPathResults: One XPath + sample_value per field, with confidence level

    Raises:
        XPathGenerationError: If condensed_html is empty, or if the LLM API call fails
    """
    if not condensed_html.strip():
        raise XPathGenerationError("condensed_html is empty — cannot generate XPaths")

    model = os.getenv("MODEL_NAME", "gpt-4o")
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))

    field_specs = [
        ("title",            ie_output.title.value,            ie_output.title.cue_text,            False),
        ("last_post_author", ie_output.last_post_author.value,  ie_output.last_post_author.cue_text, False),
        ("last_post_date",   ie_output.last_post_date.value,    ie_output.last_post_date.cue_text,   False),
        ("link",             ie_output.link.value,              ie_output.link.cue_text,             True),
    ]

    results: dict[str, FieldXPathResult] = {}
    iteration_counts: dict[str, int] = {}

    for field_name, field_value, cue_text, is_link in field_specs:
        result, iterations = await _generate_single(
            field_name=field_name,
            field_value=field_value,
            cue_text=cue_text,
            condensed_html=condensed_html,
            raw_html=raw_html,
            client=client,
            model=model,
            is_link=is_link,
        )
        results[field_name] = result.model_copy(update={"iterations": iterations})
        iteration_counts[field_name] = iterations

    logger.info("[XPathGen] Results summary:")
    for field_name, _, _, _ in field_specs:
        r = results[field_name]
        n = iteration_counts[field_name]
        iterations_str = f"{n} iteration{'s' if n != 1 else ''}"
        if r.confidence == "correct":
            logger.info("  %-20s: CORRECT (%s)", field_name, iterations_str)
        elif r.confidence == "best_effort":
            logger.warning(
                "  %-20s: WARNING — best effort (%s, no correct match)", field_name, iterations_str
            )
        else:
            logger.warning(
                "  %-20s: FAILED — all attempts matched 0 elements (%s)", field_name, iterations_str
            )

    return XPathResults(**results)
