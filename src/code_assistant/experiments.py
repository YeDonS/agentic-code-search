"""Predeclared, paired source-only experiments; official grading runs after freezing."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_assistant.benchmark import (
    environment_manifest,
    export_swebench,
    read_jsonl,
    run_benchmark,
    write_jsonl,
)
from code_assistant.config import Settings
from code_assistant.telemetry import write_json

ARMS = {
    "routed_recent": {"workflow": "routed", "evidence_policy": "recent"},
    "routed_source": {"workflow": "routed", "evidence_policy": "source_priority"},
    "single": {"workflow": "single", "evidence_policy": "source_priority"},
}
COMPARISONS = {
    "architecture": ("routed_source", "single", {"workflow"}),
    "evidence_window": ("routed_source", "routed_recent", {"evidence_policy"}),
}


def create_plan(tasks: Path, destination: Path, model: str, count: int = 20, seed: int = 20261008):
    if destination.exists():
        raise ValueError("plan is immutable; choose a new directory")
    rows = read_jsonl(tasks)
    if not 1 <= count <= len(rows) or len({r["instance_id"] for r in rows}) != len(rows):
        raise ValueError("invalid count or duplicate task IDs")
    # Selection does not inspect diagnoses, patches, judge labels or official outcomes.
    selected = sorted(
        rows,
        key=lambda r: hashlib.sha256(f"controls:{seed}:{r['instance_id']}".encode()).hexdigest(),
    )[:count]
    destination.mkdir(parents=True)
    write_jsonl(destination / "tasks.jsonl", selected)
    plan = {
        "kind": "exploratory_paired_source_only_ablation",
        "created_at": datetime.now(UTC).isoformat(),
        "selection": "lowest SHA256(controls:seed:instance_id), no outcome filtering",
        "seed": seed,
        "count": count,
        "parent_tasks_sha256": hashlib.sha256(tasks.read_bytes()).hexdigest(),
        "tasks_sha256": hashlib.sha256((destination / "tasks.jsonl").read_bytes()).hexdigest(),
        "task_ids": [r["instance_id"] for r in selected],
        "environment": environment_manifest(),
        "shared_settings": {
            "mode": "model",
            "model": model,
            "test_executor": "disabled",
            "max_model_calls": 10,
            "max_agent_steps": 10,
            "max_tool_calls": 18,
            "max_search_passes": 1,
            "evidence_limit": 24,
            "patch_repair_attempts": 0,
            "model_timeout": 120,
            "codex_reasoning_effort": "medium",
            "codex_transport": "https",
        },
        "arms": ARMS,
        "primary_metric": "official resolved count / full selected N, including abstentions and errors",
        "secondary_metrics": [
            "applicable patches",
            "abstentions",
            "model/tool calls",
            "reported tokens",
            "latency",
            "source evidence retained at synthesis",
        ],
        "hypotheses": {
            "architecture": "routed_source resolves more than single; null: no improvement",
            "evidence_window": "routed_source retains more read source and resolves more than routed_recent; null: no improvement",
        },
        "budget_scope": "identical call/tool ceilings, not identical consumed tokens or monetary cost",
        "architecture_allocation": "routed search reserves 3 of 10 calls for synthesis; single has one conversation with all 10",
        "execution_order": "arms in declared order, no outcome-dependent reruns; one stochastic run per task/arm",
        "limitations": [
            "Small exploratory subset, not proof of superiority or a SWE-bench leaderboard submission.",
            "The original 100-task frame is repository-balanced and public; training contamination is uncontrolled.",
            "No test-runner participation in these source-only arms; live three-agent benefit is not measured.",
            "Same call ceilings can consume different token counts; costs must be reported alongside quality.",
        ],
    }
    write_json(destination / "plan.json", plan)
    return plan


def run_arm(
    plan_directory: Path,
    arm: str,
    output: Path,
    cache: Path,
    workers: int = 4,
    resume: bool = False,
):
    plan = json.loads((plan_directory / "plan.json").read_text())
    if arm not in plan["arms"] or plan["arms"] != ARMS:
        raise ValueError("unknown or modified arm definitions")
    tasks = plan_directory / "tasks.jsonl"
    if hashlib.sha256(tasks.read_bytes()).hexdigest() != plan["tasks_sha256"]:
        raise ValueError("planned tasks changed")
    if environment_manifest() != plan["environment"]:
        raise ValueError("source/environment changed after plan; freeze a new plan")
    settings = Settings(_env_file=None, **plan["shared_settings"], **plan["arms"][arm])
    predictions = run_benchmark(
        tasks, output, cache, settings, "model", workers=workers, resume=resume
    )
    export_swebench(predictions, output / "swebench-predictions.jsonl", f"agentic-controls-{arm}")
    write_json(
        output / "experiment.json",
        {
            "arm": arm,
            "plan_sha256": hashlib.sha256((plan_directory / "plan.json").read_bytes()).hexdigest(),
            "predictions_sha256": hashlib.sha256(
                (output / "swebench-predictions.jsonl").read_bytes()
            ).hexdigest(),
        },
    )
    return predictions


def check_comparison(left: dict[str, Any], right: dict[str, Any], allowed: set[str]) -> None:
    ignored = {"created_at"}
    differences = {
        key
        for key in left.keys() | right.keys()
        if key not in ignored and left.get(key) != right.get(key)
    }
    if differences != allowed:
        raise ValueError(f"unmatched comparison: configuration differences {sorted(differences)}")


def summarize_comparisons(directory: Path) -> dict[str, Any]:
    """Require complete, hash-bound official results; never substitute an LLM judge."""
    result = {"kind": "exploratory_paired_results", "comparisons": {}}
    for name, (left_name, right_name, allowed) in COMPARISONS.items():
        left, right = directory / left_name, directory / right_name
        left_manifest = json.loads((left / "manifest.json").read_text())
        right_manifest = json.loads((right / "manifest.json").read_text())
        check_comparison(left_manifest, right_manifest, allowed)
        reports = []
        for path in (left, right):
            report = json.loads((path / "official-evaluation/results.json").read_text())
            expected_hash = hashlib.sha256(
                (path / "swebench-predictions.jsonl").read_bytes()
            ).hexdigest()
            if not report["complete"] or report["predictions_sha256"] != expected_hash:
                raise ValueError("official report is incomplete or refers to different predictions")
            reports.append(report)
        ids = left_manifest["task_ids"]
        if any(set(r["submitted_ids"]) != set(ids) for r in reports):
            raise ValueError("official grading task sets do not match the plan")
        a, b = (set(r["resolved_ids"]) for r in reports)
        result["comparisons"][name] = {
            "left": left_name,
            "right": right_name,
            "N": len(ids),
            "left_resolved": len(a),
            "right_resolved": len(b),
            "both_resolved": len(a & b),
            "left_only": sorted(a - b),
            "right_only": sorted(b - a),
            "neither_resolved": sorted(set(ids) - a - b),
            "resolution_rate_difference": (len(a) - len(b)) / len(ids),
            "interpretation": "Descriptive paired pilot; no claim of causal superiority or population significance.",
        }
    return result
