import importlib.util
import io
import json
import tarfile

import pytest

from code_assistant.benchmark import read_jsonl, run_benchmark, write_jsonl
from code_assistant.config import PROJECT_ROOT, Settings


def historical_fixture(tmp_path):
    tasks = [
        {
            "instance_id": f"demo__demo-{i}",
            "repo": "demo/demo",
            "base_commit": str(i) * 40,
            "problem_statement": "discount incorrectly replaces zero",
        }
        for i in range(1, 3)
    ]
    path = tmp_path / "tasks.jsonl"
    write_jsonl(path, tasks)
    cache = tmp_path / "cache"
    (cache / "archives").mkdir(parents=True)
    for task in tasks:
        archive = cache / "archives" / f"{task['instance_id']}-{task['base_commit']}.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            body = b"def discount(value):\n    return value or 10\n"
            member = tarfile.TarInfo("prefix/billing.py")
            member.size = len(body)
            bundle.addfile(member, io.BytesIO(body))
    return path, cache


def test_parallel_benchmark_resume_preserves_existing_predictions(tmp_path):
    tasks, cache = historical_fixture(tmp_path)
    output = tmp_path / "run"
    settings = Settings(test_executor="disabled")
    original = run_benchmark(tasks, output, cache, settings, workers=2)
    assert len(original) == 2
    prediction_file = output / "predictions.jsonl"
    # Simulate an interruption after one completed instance, retaining its evidence.
    write_jsonl(prediction_file, original[:1])
    resumed = run_benchmark(tasks, output, cache, settings, workers=2, resume=True)
    assert resumed == original
    assert read_jsonl(prediction_file) == original
    with pytest.raises(ValueError, match="configuration changed"):
        run_benchmark(
            tasks,
            output,
            cache,
            settings.model_copy(update={"max_agent_steps": 6}),
            workers=2,
            resume=True,
        )


def load_aggregator():
    spec = importlib.util.spec_from_file_location(
        "patch_aggregate", PROJECT_ROOT / "scripts/aggregate_patch_results.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.aggregate


def test_patch_aggregation_keeps_empty_error_and_missing_in_denominator(tmp_path):
    predictions = tmp_path / "predictions.jsonl"
    write_jsonl(
        predictions,
        [
            {"instance_id": name, "model_patch": "patch" if name == "a" else ""}
            for name in ("a", "b", "c", "d")
        ],
    )
    artifacts = tmp_path / "artifacts"
    write_jsonl(
        artifacts / "one/outcomes.jsonl",
        [
            {"instance_id": "a", "status": "resolved", "resolved": True},
            {"instance_id": "b", "status": "empty_patch", "resolved": False},
            {"instance_id": "c", "status": "infrastructure_error", "resolved": False},
        ],
    )
    report = load_aggregator()(predictions, artifacts)
    assert report["patch_resolution_rate"] == 0.25
    assert report["missing_outcome_ids"] == ["d"]
    assert not report["complete"]
    write_jsonl(
        artifacts / "duplicate/outcomes.jsonl",
        [{"instance_id": "a", "status": "resolved", "resolved": True}],
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_aggregator()(predictions, artifacts)


def test_human_and_official_per_issue_metrics_are_populated(tmp_path):
    from code_assistant.benchmark import incorporate_external_scores, score_predictions

    summary = score_predictions(
        [{"instance_id": "a"}],
        [{"instance_id": "a", "changed_files": ["a.py"]}],
        [{"instance_id": "a"}],
    )
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"resolved_ids": ["a"]}))
    incorporate_external_scores(
        summary, [{"instance_id": "a", "model_patch": "patch"}], harness_report=report
    )
    assert summary["per_issue"][0]["resolved"] is True
