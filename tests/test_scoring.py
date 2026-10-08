import csv
import json

import pytest

from code_assistant.benchmark import incorporate_external_scores, score_predictions
from code_assistant.observability import summarize_events
from code_assistant.telemetry import RunLogger


def scoring_fixture():
    tasks = [{"instance_id": "a"}, {"instance_id": "b"}]
    gold = [{"instance_id": t["instance_id"], "changed_files": ["module.py"]} for t in tasks]
    predictions = [
        {
            "instance_id": t["instance_id"],
            "status": "diagnosed",
            "predicted_files": ["module.py"],
            "root_cause": "observed bug",
            "model_patch": "nonempty",
        }
        for t in tasks
    ]
    return score_predictions(tasks, gold, predictions), predictions


def write_reviews(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["instance_id", "root_cause_correct", "reviewer", "rationale"]
        )
        writer.writeheader()
        writer.writerows(rows)


def test_partial_human_review_does_not_generate_accuracy(tmp_path):
    summary, predictions = scoring_fixture()
    path = tmp_path / "review.csv"
    write_reviews(
        path,
        [
            {
                "instance_id": "a",
                "root_cause_correct": "correct",
                "reviewer": "reviewer-1",
                "rationale": "matches gold cause",
            }
        ],
    )
    incorporate_external_scores(summary, predictions, reviews=path)
    assert summary["human_reviewed"] == 1
    assert summary["root_cause_accuracy"] is None


def test_complete_review_uses_full_denominator(tmp_path):
    summary, predictions = scoring_fixture()
    path = tmp_path / "review.csv"
    write_reviews(
        path,
        [
            {
                "instance_id": "a",
                "root_cause_correct": "correct",
                "reviewer": "r1",
                "rationale": "matches",
            },
            {
                "instance_id": "b",
                "root_cause_correct": "partial",
                "reviewer": "r2",
                "rationale": "missing causal step",
            },
        ],
    )
    incorporate_external_scores(summary, predictions, reviews=path)
    assert summary["root_cause_accuracy"] == 0.5


def test_cannot_mark_no_diagnosis_as_correct(tmp_path):
    summary, predictions = scoring_fixture()
    predictions[0]["root_cause"] = None
    path = tmp_path / "review.csv"
    write_reviews(
        path,
        [
            {
                "instance_id": "a",
                "root_cause_correct": "correct",
                "reviewer": "r1",
                "rationale": "matches",
            }
        ],
    )
    with pytest.raises(ValueError, match="missing root-cause"):
        incorporate_external_scores(summary, predictions, reviews=path)


def test_official_report_does_not_silently_drop_unresolved_cases(tmp_path):
    summary, predictions = scoring_fixture()
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"resolved_ids": ["a"]}))
    incorporate_external_scores(summary, predictions, harness_report=path)
    assert summary["patch_resolution_rate"] == 0.5
    predictions[0]["model_patch"] = ""
    with pytest.raises(ValueError, match="nonempty patches"):
        incorporate_external_scores(summary, predictions, harness_report=path)


def test_logging_reports_real_failure_patterns_and_balances(tmp_path):
    logger = RunLogger(tmp_path / "run", "run")
    logger.emit("run_start")
    logger.emit("tool_start")
    logger.emit("tool_end", outcome="error", duration_ms=123)
    logger.emit("search_result", empty=True)
    logger.emit("run_end")
    summary = summarize_events(tmp_path)
    assert summary["failure_patterns"]["empty_search"] == 1
    assert summary["failure_patterns"]["tool_error"] == 1
    assert summary["tool_duration_ms_raw"] == [123]
    assert summary["unpaired_tools"] == summary["unfinished_runs"] == 0
