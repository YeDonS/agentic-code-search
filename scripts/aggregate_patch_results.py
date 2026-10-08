"""Conserve the full prediction denominator when combining official harness shards."""

import argparse
import hashlib
import json
from pathlib import Path

from code_assistant.benchmark import read_jsonl
from code_assistant.telemetry import write_json


def aggregate(predictions: Path, artifacts: Path) -> dict:
    submitted = read_jsonl(predictions)
    expected = {p["instance_id"] for p in submitted}
    if len(expected) != len(submitted) or not expected:
        raise ValueError("unique nonempty predictions required")
    rows = [row for file in artifacts.rglob("outcomes.jsonl") for row in read_jsonl(file)]
    ids = [row["instance_id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) - expected:
        raise ValueError("duplicate or unknown shard outcomes")
    missing = sorted(expected - set(ids))
    resolved = sorted(
        r["instance_id"] for r in rows if r["status"] == "resolved" and r["resolved"] is True
    )
    unresolved = sorted(r["instance_id"] for r in rows if r["status"] == "unresolved")
    errors = sorted(
        r["instance_id"]
        for r in rows
        if r["status"] in {"infrastructure_error", "evaluation_error"}
    )
    empty = sorted(r["instance_id"] for r in rows if r["status"] == "empty_patch")
    return {
        "schema_version": 1,
        "harness_version": "5.0.2",
        "total_instances": len(expected),
        "submitted_ids": sorted(expected),
        "resolved_ids": resolved,
        "unresolved_ids": unresolved,
        "error_ids": errors,
        "empty_patch_ids": empty,
        "missing_outcome_ids": missing,
        "completed_ids": sorted(resolved + unresolved),
        "patch_resolution_rate": len(resolved) / len(expected),
        "complete": not missing,
        "predictions_sha256": hashlib.sha256(predictions.read_bytes()).hexdigest(),
        "per_issue": sorted(rows, key=lambda r: r["instance_id"]),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = aggregate(args.predictions, args.artifacts)
    write_json(args.destination, result)
    print(json.dumps({k: v for k, v in result.items() if k != "per_issue"}, indent=2))
    if not result["complete"]:
        raise SystemExit("Missing shard outcomes; retain failures and rerun missing shards")
