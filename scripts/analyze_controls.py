"""Describe paired controls, actual budgets and the source-retention mechanism."""

import argparse
import json
from collections import Counter
from pathlib import Path

from code_assistant.benchmark import read_jsonl
from code_assistant.experiments import ARMS, summarize_comparisons
from code_assistant.telemetry import write_json


def analyze(directory: Path):
    result = summarize_comparisons(directory)
    result["arms"] = {}
    for arm in ARMS:
        path = directory / arm
        manifest = json.loads((path / "manifest.json").read_text())
        predictions = read_jsonl(path / "predictions.jsonl")
        events = read_jsonl(path / "trace-events.jsonl")
        provenance = {
            row["instance_id"]: row["evidence_provenance"]
            for row in read_jsonl(path / "diagnoses.jsonl")
        }
        ends = {e["issue_id"]: e for e in events if e["event"] == "run_end" and "model_calls" in e}
        for identifier in manifest["task_ids"]:
            if (
                ends[identifier]["model_calls"] > manifest["max_model_calls"]
                or ends[identifier]["tool_calls"] > manifest["max_tool_calls"]
            ):
                raise ValueError("observed call ceiling violation")
        first = {}
        for e in events:
            if e["event"] == "evidence_selection" and e.get("recipient") == "synthesis":
                first.setdefault(e["issue_id"], e)
        mechanism = []
        for identifier, selection in first.items():
            records = provenance[identifier][: selection["available"]]
            sources = [e for e in records if e["kind"] == "source"]

            def fingerprint(e):
                return e["path"], e["start_line"], e["end_line"]

            available = {fingerprint(e) for e in sources}
            retained = {fingerprint(e) for e in sources if e["id"] in selection["selected_ids"]}
            mechanism.append(
                {
                    "instance_id": identifier,
                    "available_records": selection["available"],
                    "available_unique_source_reads": len(available),
                    "retained_unique_source_reads": len(retained),
                    "dropped_unique_source_reads": sorted(available - retained),
                }
            )
        official = json.loads((path / "official-evaluation/results.json").read_text())
        result["arms"][arm] = {
            "N": len(predictions),
            "status_counts": dict(Counter(p["status"] for p in predictions)),
            "applicable_patches": sum(bool(p["model_patch"]) for p in predictions),
            "official_resolved": len(official["resolved_ids"]),
            "official_status_counts": dict(Counter(p["status"] for p in official["per_issue"])),
            "usage": json.loads((path / "model-usage.json").read_text()),
            "call_ceilings_verified": True,
            "source_handoff_mechanism": {
                "scope": "first synthesis handoff; unique immutable path/line-range observations; continuous single-agent history has no handoff",
                "handoffs": len(mechanism),
                "overflow_cases": sum(
                    e["available_records"] > manifest["evidence_limit"] for e in mechanism
                ),
                "unique_source_drop_cases": sum(
                    bool(e["dropped_unique_source_reads"]) for e in mechanism
                ),
                "per_issue": mechanism,
            },
        }
    result["limits"] = [
        "20-task exploratory subset with one stochastic run per arm; no superiority claim.",
        "Equal call/tool ceilings do not imply equal actual tokens or cost.",
        "Provider errors and timeouts remain in the denominator; they confound small differences.",
        "Arms ran sequentially; other repair inference overlapped part of the first two arms, so raw latency is not a controlled speed comparison.",
        "Source-retention counts demonstrate the mechanism, not causality for functional outcomes.",
    ]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    summary = analyze(args.directory)
    write_json(args.destination, summary)
    print(json.dumps(summary["comparisons"], indent=2))
