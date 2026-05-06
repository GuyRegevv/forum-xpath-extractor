import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.stages.formatter import format_output, PipelineOutput
from src.stages.xpath_generator import FieldXPathResult, XPathResults


def _make_results(
    title_conf="correct",
    author_conf="correct",
    date_conf="correct",
    link_conf="correct",
) -> XPathResults:
    def _field(confidence: str) -> FieldXPathResult:
        return FieldXPathResult(
            xpath="//div[@class='x']",
            sample_value="sample",
            confidence=confidence,
            iterations=1,
        )

    return XPathResults(
        title=_field(title_conf),
        last_post_author=_field(author_conf),
        last_post_date=_field(date_conf),
        link=_field(link_conf),
    )


# ── Status computation ─────────────────────────────────────────────────────────

def test_status_success_when_all_correct(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(_make_results(), "https://example.com/forum")
    assert output.status == "success"


def test_status_partial_when_some_correct(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(_make_results(link_conf="best_effort"), "https://example.com/forum")
    assert output.status == "partial"


def test_status_partial_when_one_failed(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(_make_results(link_conf="failed"), "https://example.com/forum")
    assert output.status == "partial"


def test_status_failed_when_all_best_effort(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(
            _make_results("best_effort", "best_effort", "best_effort", "best_effort"),
            "https://example.com/forum",
        )
    assert output.status == "failed"


def test_status_failed_when_all_failed(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(
            _make_results("failed", "failed", "failed", "failed"),
            "https://example.com/forum",
        )
    assert output.status == "failed"


# ── Summary counts ─────────────────────────────────────────────────────────────

def test_summary_counts_correct(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(_make_results(), "https://example.com/")
    assert output.summary.correct == 4
    assert output.summary.best_effort == 0
    assert output.summary.failed == 0
    assert output.summary.total_fields == 4


def test_summary_counts_mixed(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(
            _make_results("correct", "best_effort", "failed", "correct"),
            "https://example.com/",
        )
    assert output.summary.correct == 2
    assert output.summary.best_effort == 1
    assert output.summary.failed == 1


# ── Fields ─────────────────────────────────────────────────────────────────────

def test_all_four_fields_present(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(_make_results(), "https://example.com/")
    assert set(output.fields.keys()) == {"title", "last_post_author", "last_post_date", "link"}


def test_field_preserves_xpath(tmp_path):
    results = _make_results()
    results.title.xpath = "//div[@class='thread-title']//a"
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(results, "https://example.com/")
    assert output.fields["title"].xpath == "//div[@class='thread-title']//a"


def test_field_preserves_iterations(tmp_path):
    results = _make_results()
    results.last_post_author = FieldXPathResult(
        xpath="//span[@class='author']",
        sample_value="user99",
        confidence="correct",
        iterations=3,
    )
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(results, "https://example.com/")
    assert output.fields["last_post_author"].iterations == 3


def test_empty_sample_value_becomes_none(tmp_path):
    results = _make_results()
    results.link = FieldXPathResult(
        xpath="//a/@href",
        sample_value="",
        confidence="failed",
        iterations=3,
    )
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(results, "https://example.com/")
    assert output.fields["link"].sample_value is None


def test_non_empty_sample_value_preserved(tmp_path):
    results = _make_results()
    results.title = FieldXPathResult(
        xpath="//a",
        sample_value="My Thread",
        confidence="correct",
        iterations=1,
    )
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(results, "https://example.com/")
    assert output.fields["title"].sample_value == "My Thread"


# ── URL stored in output ───────────────────────────────────────────────────────

def test_url_stored_in_output(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(_make_results(), "https://altenens.is/whats-new/posts/")
    assert output.url == "https://altenens.is/whats-new/posts/"


# ── File output ────────────────────────────────────────────────────────────────

def test_json_file_created(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(), "https://example.com/forum")
    files = list(tmp_path.glob("output_*.json"))
    assert len(files) == 1


def test_json_file_name_contains_domain(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(), "https://example.com/forum")
    files = list(tmp_path.glob("output_*.json"))
    assert "example.com" in files[0].name


def test_json_file_is_valid_json(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(), "https://example.com/")
    files = list(tmp_path.glob("output_*.json"))
    data = json.loads(files[0].read_text())
    assert "url" in data
    assert "fields" in data
    assert "summary" in data
    assert "status" in data


def test_json_file_schema_correct(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(), "https://example.com/")
    files = list(tmp_path.glob("output_*.json"))
    data = json.loads(files[0].read_text())
    assert data["status"] == "success"
    assert data["summary"]["total_fields"] == 4
    assert data["summary"]["correct"] == 4
    for field in ("title", "last_post_author", "last_post_date", "link"):
        assert field in data["fields"]
        assert "xpath" in data["fields"][field]
        assert "confidence" in data["fields"][field]
        assert "iterations" in data["fields"][field]


def test_results_dir_created_if_missing(tmp_path):
    target = tmp_path / "nested" / "results"
    with patch("src.stages.formatter._RESULTS_DIR", target):
        format_output(_make_results(), "https://example.com/")
    assert target.exists()


# ── Console output ─────────────────────────────────────────────────────────────

def test_console_output_contains_url(tmp_path, capsys):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(), "https://altenens.is/whats-new/posts/")
    captured = capsys.readouterr().out
    assert "https://altenens.is/whats-new/posts/" in captured


def test_console_output_contains_status(tmp_path, capsys):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(), "https://example.com/")
    captured = capsys.readouterr().out
    assert "SUCCESS" in captured


def test_console_output_contains_check_mark_for_correct(tmp_path, capsys):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(), "https://example.com/")
    captured = capsys.readouterr().out
    assert "✓" in captured


def test_console_output_contains_warning_for_best_effort(tmp_path, capsys):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(link_conf="best_effort"), "https://example.com/")
    captured = capsys.readouterr().out
    assert "⚠" in captured


def test_console_output_contains_x_for_failed(tmp_path, capsys):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(link_conf="failed"), "https://example.com/")
    captured = capsys.readouterr().out
    assert "✗" in captured


def test_console_output_contains_all_field_labels(tmp_path, capsys):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        format_output(_make_results(), "https://example.com/")
    captured = capsys.readouterr().out
    assert "TITLE" in captured
    assert "LAST POST AUTHOR" in captured
    assert "LAST POST DATE" in captured
    assert "LINK" in captured


# ── File write failure ─────────────────────────────────────────────────────────

def test_does_not_raise_on_write_failure(tmp_path, capsys):
    bad_path = Path("/nonexistent_dir_xyz/results")
    with patch("src.stages.formatter._RESULTS_DIR", bad_path):
        output = format_output(_make_results(), "https://example.com/")
    assert isinstance(output, PipelineOutput)


# ── Return type ────────────────────────────────────────────────────────────────

def test_returns_pipeline_output_instance(tmp_path):
    with patch("src.stages.formatter._RESULTS_DIR", tmp_path):
        output = format_output(_make_results(), "https://example.com/")
    assert isinstance(output, PipelineOutput)
