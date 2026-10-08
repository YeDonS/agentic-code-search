import json

import pytest

from code_assistant.benchmark import environment_manifest, write_jsonl
from code_assistant.experiments import check_comparison, create_plan, run_arm


def test_plan_selection_is_deterministic_without_reading_outcomes(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    write_jsonl(
        tasks, [{"instance_id": f"repo__repo-{i}", "problem_statement": "bug"} for i in range(12)]
    )
    a = create_plan(tasks, tmp_path / "a", "openai:test", count=5)
    b = create_plan(tasks, tmp_path / "b", "openai:test", count=5)
    assert a["task_ids"] == b["task_ids"] and len(set(a["task_ids"])) == 5
    assert a["shared_settings"]["patch_repair_attempts"] == 0
    with pytest.raises(ValueError, match="immutable"):
        create_plan(tasks, tmp_path / "a", "openai:test", count=5)


def test_comparison_rejects_hidden_budget_model_or_task_changes():
    original = {"workflow": "routed", "model": "same", "max_model_calls": 10, "task_ids": ["a"]}
    changed = {**original, "workflow": "single"}
    check_comparison(original, changed, {"workflow"})
    for key, value in [("model", "other"), ("max_model_calls", 11), ("task_ids", ["b"])]:
        with pytest.raises(ValueError, match="unmatched"):
            check_comparison(original, {**changed, key: value}, {"workflow"})


def test_arm_refuses_modified_source_or_task_list_before_model_call(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    write_jsonl(tasks, [{"instance_id": "repo__repo-1", "problem_statement": "bug"}])
    directory = tmp_path / "plan"
    plan = create_plan(tasks, directory, "openai:test", count=1)
    plan["environment"] = {**environment_manifest(), "source_tree_sha256": "changed"}
    (directory / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="source/environment changed"):
        run_arm(directory, "single", tmp_path / "output", tmp_path / "cache")
    assert not (tmp_path / "output").exists()
