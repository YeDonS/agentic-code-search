"""Curate a public HISTORICAL benchmark run; exclude prompts and source excerpts."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from code_assistant.benchmark import read_jsonl, write_jsonl
from code_assistant.observability import summarize_events
from code_assistant.telemetry import write_json


def publish(source: Path, destination: Path, source_commit: str | None = None) -> None:
    if destination.exists():
        raise ValueError("choose a new publication directory")
    manifest = json.loads((source / "manifest.json").read_text())
    predictions = read_jsonl(source / "predictions.jsonl")
    if len(predictions) != manifest["count"]:
        raise ValueError("publish only a completed historical run")
    if len({p["instance_id"] for p in predictions}) != len(predictions) or set(
        p["instance_id"] for p in predictions
    ) != set(manifest["task_ids"]):
        raise ValueError("publication task IDs do not match the manifest")
    if source_commit:
        if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            raise ValueError("source commit must be a full Git SHA")
        files = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", source_commit, "src/code_assistant"], text=True
        ).splitlines()
        digest = hashlib.sha256()
        for name in sorted(
            p
            for p in files
            if Path(p).parent.as_posix() == "src/code_assistant" and p.endswith(".py")
        ):
            digest.update(Path(name).name.encode())
            digest.update(subprocess.check_output(["git", "show", f"{source_commit}:{name}"]))
        if digest.hexdigest() != manifest["environment"]["source_tree_sha256"]:
            raise ValueError("source commit does not match frozen inference fingerprint")
    destination.mkdir(parents=True)
    write_json(destination / "manifest.json", manifest)
    if source_commit:
        write_json(
            destination / "source-proof.json",
            {"source_commit": source_commit, "source_tree_sha256": digest.hexdigest()},
        )
    for name in ("swebench-predictions.jsonl", "experiment.json"):
        if (source / name).exists():
            shutil.copyfile(source / name, destination / name)
    for name in ("scores.json", "completion.json"):
        if (source / name).exists():
            write_json(destination / name, json.loads((source / name).read_text()))
    write_jsonl(
        destination / "predictions.jsonl",
        [{k: v for k, v in p.items() if k != "evidence"} for p in predictions],
    )
    events = [row for file in sorted(source.rglob("events.jsonl")) for row in read_jsonl(file)]
    # Event logger deliberately records no prompts/source/hidden reasoning.
    write_jsonl(destination / "trace-events.jsonl", events)
    write_json(destination / "log-audit.json", summarize_events(source))
    model_calls = [e for e in events if e["event"] == "model_response"]
    patch_checks = [e for e in events if e["event"] == "patch_check"]
    final_checks = [
        json.loads(p.read_text()) for p in (source / "agent_runs").glob("*/patch-check.json")
    ]
    requests = sum(e["event"] == "model_request" for e in events)
    run_counters = [
        e["model_calls"] for e in events if e["event"] == "run_end" and "model_calls" in e
    ]
    complete_counters = len(run_counters) == len(predictions)
    observed_calls = requests or (sum(run_counters) if complete_counters else len(model_calls))
    summary = {
        "tasks": len(predictions),
        "model_calls": observed_calls,
        "model_call_scope": "requests"
        if requests
        else "complete run counters"
        if complete_counters
        else "completed responses only; failed invocations may be missing",
        "successful_model_responses": len(model_calls),
        "failed_model_calls": observed_calls - len(model_calls)
        if requests or complete_counters
        else None,
        "failed_runs": sum(p["status"] == "failed" for p in predictions),
        "token_scope": "provider-reported usage from completed responses; failed calls may have unknown usage",
        "input_tokens": sum(e.get("input_tokens") or 0 for e in model_calls),
        "output_tokens": sum(e.get("output_tokens") or 0 for e in model_calls),
        "cached_input_tokens": sum(e.get("cached_input_tokens") or 0 for e in model_calls),
        "builtin_tool_calls": sum(e.get("builtin_tool_calls") or 0 for e in model_calls),
        "transport_reconnects": sum(e.get("transport_reconnects") or 0 for e in model_calls),
        "applicable_patches": sum(bool(p.get("model_patch")) for p in predictions),
        "withheld_patches": sum(e["status"] not in {"applies", "empty"} for e in final_checks),
        "patch_check_attempts": len(patch_checks),
        "repair_attempts": sum(e.get("repair_attempts", 0) for e in final_checks),
        "recovered_patches": sum(e.get("recovered", False) for e in final_checks),
        "model_duration_ms": sum(e["duration_ms"] for e in model_calls),
    }
    write_json(destination / "model-usage.json", summary)
    diagnoses = []
    for path in sorted((source / "agent_runs").glob("*/response.json")):
        response = json.loads(path.read_text())
        diagnoses.append(
            {
                "instance_id": path.parent.name,
                "diagnosis": response["diagnosis"],
                "evidence_provenance": [
                    {k: e.get(k) for k in ("id", "kind", "path", "start_line", "end_line")}
                    for e in response["evidence"]
                ],
                "routes": response["routes"],
                "test_status": response["test_status"],
                "patch_verified": response["patch_verified"],
            }
        )
    write_jsonl(destination / "diagnoses.jsonl", diagnoses)
    for path in sorted((source / "agent_runs").glob("*/patch-attempts.json")):
        write_json(
            destination / "attempts" / f"{path.parent.name}.json", json.loads(path.read_text())
        )
    for path in sorted((source / "agent_runs").glob("*/patch-check.json")):
        write_json(
            destination / "checks" / f"{path.parent.name}.json", json.loads(path.read_text())
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    publish(args.source, args.destination, args.source_commit)
