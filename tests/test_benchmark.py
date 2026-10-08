import hashlib
import io
import json
import tarfile

import pytest

from code_assistant.benchmark import (
    extract_snapshot,
    production_files,
    read_jsonl,
    score_predictions,
    select_tasks,
)
from code_assistant.config import PROJECT_ROOT


def test_committed_100_tasks_are_pinned_and_separated_from_gold():
    directory = PROJECT_ROOT / "benchmarks"
    tasks = read_jsonl(directory / "tasks.jsonl")
    gold = read_jsonl(directory / "gold" / "reference.jsonl")
    provenance = json.loads((directory / "provenance.json").read_text())
    assert len(tasks) == len(gold) == provenance["count"] == 100
    assert len({t["instance_id"] for t in tasks}) == 100
    assert {t["instance_id"] for t in tasks} == {g["instance_id"] for g in gold}
    assert all(
        not {"patch", "test_patch", "FAIL_TO_PASS", "changed_files"}.intersection(t) for t in tasks
    )
    assert (
        hashlib.sha256((directory / "tasks.jsonl").read_bytes()).hexdigest()
        == provenance["tasks_sha256"]
    )
    assert (
        hashlib.sha256((directory / "gold" / "reference.jsonl").read_bytes()).hexdigest()
        == provenance["reference_sha256"]
    )
    assert len(provenance["revision"]) == 40


def test_selection_is_repeatable_and_covers_repositories():
    rows = [
        {
            "instance_id": f"r{repo}__r-{i}",
            "repo": f"r{repo}/r",
            "patch": "diff --git a/module.py b/module.py\n",
            "base_commit": "a" * 40,
            "problem_statement": "bug",
        }
        for repo in range(3)
        for i in range(6)
    ]
    selected = select_tasks(rows, 9)
    assert selected == select_tasks(list(reversed(rows)), 9)
    assert all(sum(r["repo"] == f"r{repo}/r" for r in selected) == 3 for repo in range(3))


def test_scoring_keeps_failures_and_missing_in_denominator():
    tasks = [{"instance_id": str(i)} for i in range(3)]
    gold = [{"instance_id": str(i), "changed_files": ["module.py"]} for i in range(3)]
    predictions = [
        {"instance_id": "0", "predicted_files": ["other.py", "module.py"], "status": "completed"},
        {"instance_id": "1", "predicted_files": [], "status": "failed"},
    ]
    score = score_predictions(tasks, gold, predictions)
    assert score["expected"] == 3
    assert score["file_hit_at_5"] == 1 / 3
    assert score["mrr_at_5"] == 0.5 / 3
    assert score["failed_or_missing"] == 2
    assert score["root_cause_accuracy"] is None
    assert score["patch_resolution_rate"] is None


def test_duplicate_predictions_rejected():
    with pytest.raises(ValueError):
        score_predictions(
            [{"instance_id": "a"}],
            [{"instance_id": "a", "changed_files": ["x.py"]}],
            [{"instance_id": "a"}, {"instance_id": "a"}],
        )


def test_patch_labels_exclude_tests():
    patch = "diff --git a/pkg/module.py b/pkg/module.py\ndiff --git a/tests/test_module.py b/tests/test_module.py\n"
    assert production_files(patch) == ["pkg/module.py"]


def test_archive_cannot_extract_links_or_parent_paths(tmp_path):
    archive = tmp_path / "sample.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        normal = tarfile.TarInfo("prefix/module.py")
        normal.size = 7
        bundle.addfile(normal, io.BytesIO(b"x = 42\n"))
        bad = tarfile.TarInfo("prefix/../../escaped.py")
        bad.size = 1
        bundle.addfile(bad, io.BytesIO(b"x"))
        link = tarfile.TarInfo("prefix/linked.py")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        bundle.addfile(link)
    destination = tmp_path / "snapshot"
    extract_snapshot(archive, destination)
    assert (destination / "module.py").read_text() == "x = 42\n"
    assert not (destination / "linked.py").exists()
    assert not (tmp_path / "escaped.py").exists()
