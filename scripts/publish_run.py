"""Curate a public HISTORICAL benchmark run; exclude prompts and source excerpts."""

import argparse
import json
from pathlib import Path

from code_assistant.benchmark import read_jsonl, write_jsonl
from code_assistant.observability import summarize_events
from code_assistant.telemetry import write_json


def publish(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("choose a new publication directory")
    manifest = json.loads((source / "manifest.json").read_text())
    predictions = read_jsonl(source / "predictions.jsonl")
    if len(predictions) != manifest["count"]:
        raise ValueError("publish only a completed historical run")
    destination.mkdir(parents=True)
    write_json(destination / "manifest.json", manifest)
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
    summary = {
        "tasks": len(predictions),
        "model_calls": len(model_calls),
        "input_tokens": sum(e.get("input_tokens") or 0 for e in model_calls),
        "output_tokens": sum(e.get("output_tokens") or 0 for e in model_calls),
        "cached_input_tokens": sum(e.get("cached_input_tokens") or 0 for e in model_calls),
        "builtin_tool_calls": sum(e.get("builtin_tool_calls") or 0 for e in model_calls),
        "transport_reconnects": sum(e.get("transport_reconnects") or 0 for e in model_calls),
        "applicable_patches": sum(e["status"] == "applies" for e in patch_checks),
        "withheld_patches": sum(e["status"] not in {"applies", "empty"} for e in patch_checks),
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
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    publish(args.source, args.destination)
