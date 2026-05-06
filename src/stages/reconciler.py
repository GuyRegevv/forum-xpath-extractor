import json
import logging
import os
import re

from lxml import etree as lxml_etree
from lxml import html as lxml_html
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from src.stages.xpath_generator import FieldXPathResult, XPathResults, run_xpath
from src.exceptions import XPathSyntaxError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
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


class ReconcilerResponse(BaseModel):
    explanation: str
    revised_xpath: str | None


def _to_element_xpath(xpath: str) -> str:
    """Strip trailing /text() or /@attr so the XPath returns elements."""
    return re.sub(r'/(text\(\)|@\w+)$', '', xpath)


def _extract_problem_rows(raw_html: str, title_xpath: str, flagged_xpath: str) -> list[str]:
    """
    Return serialized HTML of thread rows matched by title_xpath but not flagged_xpath.
    """
    tree = lxml_html.fromstring(raw_html.encode("utf-8"))
    etree = tree.getroottree()

    title_elements = tree.xpath(_to_element_xpath(title_xpath))
    if not title_elements:
        return []

    # Build absolute paths for each title element
    paths = [etree.getpath(el).split("/") for el in title_elements]

    # Find the depth at which paths first diverge — that is the row level
    min_depth = min(len(p) for p in paths)
    diverge_depth = min_depth - 1
    for i in range(1, min_depth):
        if len(set(p[i] for p in paths)) > 1:
            diverge_depth = i
            break

    # Collect unique row container elements
    row_containers = []
    seen = set()
    for path_parts in paths:
        if len(path_parts) > diverge_depth:
            row_path = "/" + "/".join(path_parts[1:diverge_depth + 1])
            if row_path not in seen:
                seen.add(row_path)
                results = tree.xpath(row_path)
                if results:
                    row_containers.append(results[0])

    # Build relative version of flagged xpath
    relative_xpath = "." + _to_element_xpath(flagged_xpath)

    # Return rows where the flagged xpath has no match
    problem_rows = []
    for row_el in row_containers:
        try:
            if not row_el.xpath(relative_xpath):
                problem_rows.append(
                    lxml_etree.tostring(row_el, encoding="unicode", method="html")
                )
        except Exception:
            continue

    return problem_rows


def _build_prompt(
    field_name: str,
    field: FieldXPathResult,
    all_results: XPathResults,
    reference_count: int,
    problem_rows: list[str],
    url: str,
) -> str:
    problem_html = "\n\n".join(problem_rows)
    missing = reference_count - field.match_count
    return (
        f"Forum URL: {url}\n\n"
        f"Reference count: {reference_count} thread rows (from title XPath).\n\n"
        f"Field under investigation: {field_name}\n"
        f"Current XPath: {field.xpath}\n"
        f"Current match count: {field.match_count} (missing {missing} rows)\n\n"
        f"All XPaths for context:\n"
        f"  title            ({all_results.title.match_count} matches): {all_results.title.xpath}\n"
        f"  last_post_author ({all_results.last_post_author.match_count} matches): {all_results.last_post_author.xpath}\n"
        f"  last_post_date   ({all_results.last_post_date.match_count} matches): {all_results.last_post_date.xpath}\n"
        f"  link             ({all_results.link.match_count} matches): {all_results.link.xpath}\n\n"
        f"HTML of the {len(problem_rows)} rows matched by title but NOT by the current XPath:\n\n"
        f"{problem_html}\n\n"
        "Why does the current XPath miss these rows? Can you provide a better XPath?"
    )


async def reconcile_xpaths(
    xpath_results: XPathResults,
    raw_html: str,
    url: str,
) -> XPathResults:
    """
    Detect match-count discrepancies across fields and fire a targeted LLM
    diagnostic for each discrepant field. Returns updated XPathResults where
    reconciled fields have an explanation and optionally a revised XPath.

    Never raises — all errors are logged and the original results returned.
    """
    reference_count = max(
        xpath_results.title.match_count,
        xpath_results.last_post_author.match_count,
        xpath_results.last_post_date.match_count,
        xpath_results.link.match_count,
    )

    field_names = ("title", "last_post_author", "last_post_date", "link")
    discrepant = [
        name for name in field_names
        if getattr(xpath_results, name).match_count < reference_count
    ]

    if not discrepant:
        return xpath_results

    logger.info("[Reconciler] Reference count: %d", reference_count)
    logger.info("[Reconciler] Fields to investigate: %s", ", ".join(
        f"{n} ({getattr(xpath_results, n).match_count}/{reference_count})"
        for n in discrepant
    ))

    model = os.getenv("MODEL_NAME", "gpt-4o")
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    updated = xpath_results

    for field_name in discrepant:
        field = getattr(updated, field_name)

        problem_rows = _extract_problem_rows(
            raw_html, updated.title.xpath, field.xpath
        )

        if not problem_rows:
            logger.warning("[Reconciler] Could not extract problem rows for %s — skipping", field_name)
            continue

        logger.info("[Reconciler] Extracted %d problem rows for %s", len(problem_rows), field_name)

        prompt = _build_prompt(field_name, field, updated, reference_count, problem_rows, url)

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)
            rec = ReconcilerResponse.model_validate(data)
        except Exception as exc:
            logger.warning("[Reconciler] Failed for %s: %s", field_name, exc)
            continue

        logger.info("[Reconciler] %s explanation: %s", field_name, rec.explanation)

        updated_field = field.model_copy(update={"explanation": rec.explanation})

        if rec.revised_xpath:
            try:
                new_matches = run_xpath(rec.revised_xpath, raw_html)
                new_count = len(new_matches)
                if new_count > field.match_count:
                    sample = new_matches[0] if new_matches else ""
                    updated_field = updated_field.model_copy(update={
                        "original_xpath": field.xpath,
                        "xpath": rec.revised_xpath,
                        "match_count": new_count,
                        "sample_value": sample,
                    })
                    logger.info(
                        "[Reconciler] %s: revised XPath improved count %d → %d",
                        field_name, field.match_count, new_count,
                    )
                else:
                    logger.info(
                        "[Reconciler] %s: revised XPath count %d did not improve on %d, keeping original",
                        field_name, new_count, field.match_count,
                    )
            except XPathSyntaxError as exc:
                logger.warning("[Reconciler] %s: revised XPath syntax error: %s", field_name, exc)

        updated = updated.model_copy(update={field_name: updated_field})

    return updated
