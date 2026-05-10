import json
import logging
import os
import re
import statistics

from lxml import etree as lxml_etree
from lxml import html as lxml_html
from openai import AsyncOpenAI
from pydantic import BaseModel

from src.stages.xpath_generator import FieldXPathResult, XPathResults, run_xpath, validate_xpath
from src.exceptions import XPathSyntaxError

logger = logging.getLogger(__name__)

MAX_RECONCILE_ITERATIONS = 2

_SYSTEM_PROMPT_TOO_FEW = """\
You are an XPath diagnostics expert. You are given a forum page where one XPath
selector is returning fewer matches than expected.

Your job is to:
1. Examine the HTML rows that the selector is missing
2. Explain in one to three sentences why those rows are not matched
3. If possible, provide a revised XPath that matches all rows

Rules for revised XPath:
- Do not hardcode specific text values
- Use contains(@class, 'value') for class matching
- The XPath must generalise to any page of this forum
- If no reliable generalised XPath exists, set revised_xpath to null

Always respond in this exact JSON format:
{"explanation": "...", "revised_xpath": "..." or null}"""

_SYSTEM_PROMPT_TOO_BROAD = """\
You are an XPath diagnostics expert. You are given a forum page where one XPath
selector is returning too many matches — it is matching multiple elements per
thread row instead of one.

Your job is to:
1. Examine the example row and what the XPath matches within it
2. Explain in one to three sentences why the XPath is over-matching
3. Provide a narrower XPath that matches exactly one element per thread row

Rules for revised XPath:
- Do not hardcode specific text values
- Use contains(@class, 'value') for class matching
- The XPath must generalise to any page of this forum
- If no reliable narrower XPath exists, set revised_xpath to null

Always respond in this exact JSON format:
{"explanation": "...", "revised_xpath": "..." or null}"""


class ReconcilerResponse(BaseModel):
    explanation: str
    revised_xpath: str | None


def _to_element_xpath(xpath: str) -> str:
    """Strip trailing /text() or /@attr and string() wrappers so the XPath returns elements."""
    xpath = re.sub(r'^string\((.*)\)$', r'\1', xpath.strip())
    return re.sub(r'/(text\(\)|@\w+)$', '', xpath)


def _find_row_containers(tree, etree, ref_elements: list) -> list:
    """
    Walk up from each reference element until the parent contains >1 reference element.
    At that point the child is the row container. Works on any DOM structure.
    """
    ref_path_set = {etree.getpath(el) for el in ref_elements}
    row_containers = []
    seen: set[str] = set()

    for el in ref_elements:
        current = el
        parent = el.getparent()
        while parent is not None:
            parent_path = etree.getpath(parent)
            count = sum(1 for p in ref_path_set if p.startswith(parent_path + "/"))
            if count > 1:
                current_path = etree.getpath(current)
                if current_path not in seen:
                    seen.add(current_path)
                    row_containers.append(current)
                break
            current = parent
            parent = parent.getparent()

    return row_containers


def _extract_problem_rows(
    raw_html: str, reference_xpath: str, flagged_xpath: str
) -> tuple[list[str], list[str]]:
    """
    Return (problem_rows, good_rows) where:
    - problem_rows: rows matched by reference_xpath but not flagged_xpath
    - good_rows: up to 2 rows matched by both (sent to LLM for structural comparison)
    """
    tree = lxml_html.fromstring(raw_html.encode("utf-8"))
    etree = tree.getroottree()

    ref_elements = tree.xpath(_to_element_xpath(reference_xpath))
    if not ref_elements:
        return [], []

    row_containers = _find_row_containers(tree, etree, ref_elements)
    relative_xpath = "." + _to_element_xpath(flagged_xpath)

    problem_rows: list[str] = []
    good_rows: list[str] = []
    for row_el in row_containers:
        try:
            html = lxml_etree.tostring(row_el, encoding="unicode", method="html")
            if row_el.xpath(relative_xpath):
                good_rows.append(html)
            else:
                problem_rows.append(html)
        except Exception:
            continue

    return problem_rows, good_rows[:2]


def _extract_over_matched_example(
    raw_html: str, reference_xpath: str, flagged_xpath: str
) -> tuple[str | None, list[str]]:
    """
    Return (row_html, matched_values) for the first row where flagged_xpath matches >1 element.
    Used to show the LLM exactly what a too-broad XPath is over-matching within a single row.
    """
    tree = lxml_html.fromstring(raw_html.encode("utf-8"))
    etree = tree.getroottree()

    ref_elements = tree.xpath(_to_element_xpath(reference_xpath))
    if not ref_elements:
        return None, []

    row_containers = _find_row_containers(tree, etree, ref_elements)
    relative_flagged = "." + _to_element_xpath(flagged_xpath)

    for row_el in row_containers:
        try:
            matches = row_el.xpath(relative_flagged)
            if len(matches) > 1:
                row_html = lxml_etree.tostring(row_el, encoding="unicode", method="html")
                matched_values: list[str] = []
                for m in matches:
                    if isinstance(m, str):
                        matched_values.append(m.strip())
                    elif hasattr(m, "text_content"):
                        matched_values.append(m.text_content().strip())
                return row_html, matched_values[:5]
        except Exception:
            continue

    return None, []


def _build_too_few_prompt(
    field_name: str,
    field: FieldXPathResult,
    all_results: XPathResults,
    reference_count: int,
    reference_field_name: str,
    problem_rows: list[str],
    good_rows: list[str],
    url: str,
) -> str:
    missing = reference_count - field.match_count
    good_section = ""
    if good_rows:
        good_html = "\n\n".join(good_rows)
        good_section = (
            f"HTML of {len(good_rows)} rows that ARE matched by the current XPath (for comparison):\n\n"
            f"{good_html}\n\n"
        )
    problem_html = "\n\n".join(problem_rows)
    return (
        f"Forum URL: {url}\n\n"
        f"Reference count: {reference_count} thread rows (from {reference_field_name} XPath).\n\n"
        f"Field under investigation: {field_name}\n"
        f"Current XPath: {field.xpath}\n"
        f"Current match count: {field.match_count} (missing {missing} rows)\n\n"
        f"All XPaths for context:\n"
        f"  title            ({all_results.title.match_count} matches): {all_results.title.xpath}\n"
        f"  last_post_author ({all_results.last_post_author.match_count} matches): {all_results.last_post_author.xpath}\n"
        f"  last_post_date   ({all_results.last_post_date.match_count} matches): {all_results.last_post_date.xpath}\n"
        f"  link             ({all_results.link.match_count} matches): {all_results.link.xpath}\n\n"
        f"{good_section}"
        f"HTML of the {len(problem_rows)} rows matched by the reference XPath but NOT by the current XPath:\n\n"
        f"{problem_html}\n\n"
        "Why does the current XPath miss these rows? Can you provide a better XPath?"
    )


def _build_too_broad_prompt(
    field_name: str,
    field: FieldXPathResult,
    all_results: XPathResults,
    reference_count: int,
    row_html: str,
    matched_in_row: list[str],
    url: str,
) -> str:
    ratio = field.match_count / reference_count if reference_count else 0
    return (
        f"Forum URL: {url}\n\n"
        f"Expected count: ~{reference_count} thread rows on this page.\n\n"
        f"Field under investigation: {field_name}\n"
        f"Current XPath: {field.xpath}\n"
        f"Current match count: {field.match_count} (~{ratio:.1f}x more than expected — too broad)\n\n"
        f"All XPaths for context:\n"
        f"  title            ({all_results.title.match_count} matches): {all_results.title.xpath}\n"
        f"  last_post_author ({all_results.last_post_author.match_count} matches): {all_results.last_post_author.xpath}\n"
        f"  last_post_date   ({all_results.last_post_date.match_count} matches): {all_results.last_post_date.xpath}\n"
        f"  link             ({all_results.link.match_count} matches): {all_results.link.xpath}\n\n"
        f"Example thread row HTML:\n\n{row_html}\n\n"
        f"What the current XPath matches within this row: {matched_in_row}\n\n"
        "The XPath is matching multiple elements per row instead of one. "
        "Provide a narrower XPath that selects exactly the correct field value per thread row."
    )


async def _run_reconcile_loop(
    field_name: str,
    field: FieldXPathResult,
    updated: XPathResults,
    prompt: str,
    system_prompt: str,
    raw_html: str,
    client: AsyncOpenAI,
    model: str,
    accept_if_improved: bool,
) -> tuple[FieldXPathResult, XPathResults]:
    """
    Run the reconciler feedback loop for one field.
    accept_if_improved=True  → too-few case, accept when new_count > old_count
    accept_if_improved=False → too-broad case, accept when new_count < old_count
    Returns (updated_field, updated_results).
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    last_explanation: str | None = None
    accepted_revision: dict | None = None

    for iteration in range(MAX_RECONCILE_ITERATIONS):
        logger.info(
            "[Reconciler] %s | Iteration %d/%d", field_name, iteration + 1, MAX_RECONCILE_ITERATIONS
        )

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            rec = ReconcilerResponse.model_validate(data)
        except Exception as exc:
            logger.warning("[Reconciler] %s: LLM call failed: %s", field_name, exc)
            break

        last_explanation = rec.explanation
        logger.info("[Reconciler] %s explanation: %s", field_name, rec.explanation)

        if not rec.revised_xpath:
            logger.info("[Reconciler] %s: LLM found no better XPath", field_name)
            break

        feedback: str | None = None
        try:
            new_matches = run_xpath(rec.revised_xpath, raw_html)
            new_count = len(new_matches)
            count_ok = new_count > field.match_count if accept_if_improved else new_count < field.match_count

            if count_ok:
                validation = validate_xpath(rec.revised_xpath, raw_html, field.sample_value)
                if validation.is_correct:
                    accepted_revision = {
                        "original_xpath": field.xpath,
                        "xpath": rec.revised_xpath,
                        "match_count": new_count,
                        "sample_value": new_matches[0] if new_matches else "",
                    }
                    direction = "improved" if accept_if_improved else "narrowed"
                    logger.info(
                        "[Reconciler] %s: revised XPath %s count %d → %d and value validated",
                        field_name, direction, field.match_count, new_count,
                    )
                    break
                else:
                    feedback = (
                        f"Your revised XPath matched {new_count} elements but none contained "
                        f"'{field.sample_value}'. Matched: {validation.matched_values[:3]}."
                    )
                    logger.info(
                        "[Reconciler] %s iteration %d: value check failed — %s",
                        field_name, iteration + 1, validation.feedback_message,
                    )
            else:
                if accept_if_improved:
                    feedback = f"Your revised XPath matched {new_count} elements — not more than the original {field.match_count}."
                else:
                    feedback = f"Your revised XPath matched {new_count} elements — not fewer than the original {field.match_count}."
                logger.info(
                    "[Reconciler] %s iteration %d: count did not improve (%d)",
                    field_name, iteration + 1, new_count,
                )
        except XPathSyntaxError as exc:
            feedback = f"Your revised XPath has a syntax error: {exc}."
            logger.warning("[Reconciler] %s: revised XPath syntax error: %s", field_name, exc)

        if feedback and iteration < MAX_RECONCILE_ITERATIONS - 1:
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": (
                    feedback + "\n"
                    'Respond in the same JSON format: {"explanation": "...", "revised_xpath": "..." or null}'
                ),
            })

    updates: dict = {}
    if last_explanation:
        updates["explanation"] = last_explanation
    if accepted_revision:
        updates.update(accepted_revision)
    updated_field = field.model_copy(update=updates) if updates else field
    return updated_field, updated.model_copy(update={field_name: updated_field})


async def reconcile_xpaths(
    xpath_results: XPathResults,
    raw_html: str,
    url: str,
) -> XPathResults:
    """
    Detect match-count discrepancies across fields and fire targeted LLM diagnostics.
    Handles both directions:
    - Too few: field matches fewer rows than expected → show missing rows
    - Too broad: field matches many more rows than others → show over-matched example

    Never raises — all errors are logged and original results returned.
    """
    field_names = ("title", "last_post_author", "last_post_date", "link")
    counts = [getattr(xpath_results, n).match_count for n in field_names]
    median_count = statistics.median(counts)

    # Exclude outlier-high counts so they don't inflate the reference and cause false too-few flags
    valid_counts = [c for c in counts if c <= 2 * median_count] if median_count > 0 else counts
    reference_count = max(valid_counts) if valid_counts else max(counts)

    # Reference field: highest valid count, prefer title > link > date > author on ties
    reference_field_name = next(
        n for n in ("title", "link", "last_post_date", "last_post_author")
        if getattr(xpath_results, n).match_count == reference_count
    )

    # Too-broad: count significantly above median — XPath catches multiple elements per row
    too_broad = [
        name for name in field_names
        if median_count > 0
        and getattr(xpath_results, name).match_count > 2 * median_count
        and getattr(xpath_results, name).confidence == "correct"
    ]

    # Too-few: count below the (outlier-filtered) reference
    discrepant = [
        name for name in field_names
        if getattr(xpath_results, name).match_count < reference_count
        and getattr(xpath_results, name).confidence == "correct"
    ]

    for name in field_names:
        f = getattr(xpath_results, name)
        if f.match_count < reference_count and f.confidence != "correct":
            logger.warning(
                "[Reconciler] Skipping %s — count discrepancy but Stage 5 confidence is '%s', "
                "sample value unverified so count-fixing would be meaningless",
                name, f.confidence,
            )

    if not too_broad and not discrepant:
        return xpath_results

    logger.info("[Reconciler] Reference count: %d (from %s)", reference_count, reference_field_name)
    if too_broad:
        logger.info("[Reconciler] Too-broad fields: %s", ", ".join(
            f"{n} ({getattr(xpath_results, n).match_count} matches, expected ~{reference_count})"
            for n in too_broad
        ))
    if discrepant:
        logger.info("[Reconciler] Fields to investigate (too few): %s", ", ".join(
            f"{n} ({getattr(xpath_results, n).match_count}/{reference_count})"
            for n in discrepant
        ))

    model = os.getenv("MODEL_NAME", "gpt-4o")
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))

    updated = xpath_results

    # Fix too-broad fields first so reference counts are clean for the too-few pass
    for field_name in too_broad:
        field = getattr(updated, field_name)
        reference_xpath = getattr(updated, reference_field_name).xpath

        row_html, matched_in_row = _extract_over_matched_example(raw_html, reference_xpath, field.xpath)
        if not row_html:
            logger.warning("[Reconciler] Could not extract over-matched example for %s — skipping", field_name)
            continue

        logger.info(
            "[Reconciler] Extracted over-matched example for %s (%d values matched in one row)",
            field_name, len(matched_in_row),
        )

        prompt = _build_too_broad_prompt(
            field_name, field, updated, reference_count, row_html, matched_in_row, url
        )
        _, updated = await _run_reconcile_loop(
            field_name, field, updated, prompt, _SYSTEM_PROMPT_TOO_BROAD,
            raw_html, client, model, accept_if_improved=False,
        )

    # Fix too-few fields
    for field_name in discrepant:
        field = getattr(updated, field_name)
        reference_xpath = getattr(updated, reference_field_name).xpath

        problem_rows, good_rows = _extract_problem_rows(raw_html, reference_xpath, field.xpath)
        if not problem_rows:
            logger.warning("[Reconciler] Could not extract problem rows for %s — skipping", field_name)
            continue

        logger.info(
            "[Reconciler] Extracted %d problem rows, %d comparison rows for %s",
            len(problem_rows), len(good_rows), field_name,
        )

        prompt = _build_too_few_prompt(
            field_name, field, updated, reference_count, reference_field_name,
            problem_rows, good_rows, url,
        )
        _, updated = await _run_reconcile_loop(
            field_name, field, updated, prompt, _SYSTEM_PROMPT_TOO_FEW,
            raw_html, client, model, accept_if_improved=True,
        )

    return updated
