import logging
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from src.stages.xpath_generator import XPathResults

logger = logging.getLogger(__name__)

_RESULTS_DIR = Path("results")

_CONFIDENCE_ICON = {
    "correct": "✓",
    "best_effort": "⚠",
    "failed": "✗",
}

_FIELD_LABELS = {
    "title": "TITLE",
    "last_post_author": "LAST POST AUTHOR",
    "last_post_date": "LAST POST DATE",
    "link": "LINK",
}


class FieldOutput(BaseModel):
    xpath: str
    sample_value: Optional[str]
    confidence: Literal["correct", "best_effort", "failed"]
    iterations: int
    match_count: int
    original_xpath: Optional[str] = None
    explanation: Optional[str] = None


class SummaryOutput(BaseModel):
    total_fields: int
    correct: int
    best_effort: int
    failed: int


class PipelineOutput(BaseModel):
    url: str
    status: Literal["success", "partial", "failed"]
    fields: dict[str, FieldOutput]
    summary: SummaryOutput


def _compute_status(summary: SummaryOutput) -> Literal["success", "partial", "failed"]:
    if summary.correct == summary.total_fields:
        return "success"
    if summary.correct > 0:
        return "partial"
    return "failed"


def _print_summary(output: PipelineOutput, file_path: str) -> None:
    sep = "━" * 49
    status_label = output.status.upper()
    correct = output.summary.correct
    total = output.summary.total_fields
    print(f"\n{sep}")
    print(" Forum XPath Extractor — Results")
    print(sep)
    print(f" URL     : {output.url}")
    print(f" Status  : {status_label} ({correct}/{total} fields correct)")
    print(sep)

    for field_name in ("title", "last_post_author", "last_post_date", "link"):
        field = output.fields[field_name]
        icon = _CONFIDENCE_ICON[field.confidence]
        label = _FIELD_LABELS[field_name]
        iters = field.iterations
        sample = field.sample_value or "(none)"
        print(f"\n {label}")
        print(f"   XPath  : {field.xpath}")
        print(f"   Sample : {sample}")
        print(f"   {icon} {field.confidence} ({iters} iteration{'s' if iters != 1 else ''}, {field.match_count} matches)")
        if field.original_xpath:
            print(f"   ↳ Revised from: {field.original_xpath}")
        if field.explanation:
            print(f"   ℹ {field.explanation}")

    print(f"\n{sep}")
    print(f" Full JSON output saved to: {file_path}")
    print(sep)


def format_output(xpath_results: XPathResults, url: str) -> PipelineOutput:
    """
    Assemble the final pipeline output from Stage 5 results.
    Prints a human-readable summary to stdout.
    Saves the full JSON to ./results/.

    Args:
        xpath_results: Output from Stage 5
        url: The original input URL

    Returns:
        PipelineOutput: Validated Pydantic model — also serialized to JSON file
    """
    fields: dict[str, FieldOutput] = {}
    correct = best_effort = failed = 0

    for field_name in ("title", "last_post_author", "last_post_date", "link"):
        r = getattr(xpath_results, field_name)
        sample = r.sample_value if r.sample_value else None
        fields[field_name] = FieldOutput(
            xpath=r.xpath,
            sample_value=sample,
            confidence=r.confidence,
            iterations=r.iterations,
            match_count=r.match_count,
            original_xpath=r.original_xpath,
            explanation=r.explanation,
        )
        if r.confidence == "correct":
            correct += 1
        elif r.confidence == "best_effort":
            best_effort += 1
        else:
            failed += 1

    summary = SummaryOutput(
        total_fields=4,
        correct=correct,
        best_effort=best_effort,
        failed=failed,
    )
    status = _compute_status(summary)
    output = PipelineOutput(url=url, status=status, fields=fields, summary=summary)

    domain = urlparse(url).netloc or "unknown"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"output_{domain}_{timestamp}.json"

    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = _RESULTS_DIR / filename
        file_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")
        file_path_str = str(file_path)
    except Exception as exc:
        logger.warning("[Formatter] Could not write results file: %s", exc)
        file_path_str = filename
        print(output.model_dump_json(indent=2))

    _print_summary(output, file_path_str)
    logger.info("[Formatter] Status=%s correct=%d/4", status, correct)

    return output
