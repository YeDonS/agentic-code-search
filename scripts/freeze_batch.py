"""Freeze a completed task interval for official evaluation while inference continues."""

import argparse
import hashlib
import json
from pathlib import Path

from code_assistant.benchmark import export_swebench, read_jsonl, write_jsonl
from code_assistant.telemetry import write_json


def freeze(source: Path, destination: Path, start: int, stop: int, batch: int) -> None:
    manifest = json.loads((source / "manifest.json").read_text())
    if destination.exists() or not 0 <= start < stop <= manifest["count"]:
        raise ValueError("new destination and valid nonempty task interval required")
    predictions = read_jsonl(source / "predictions.jsonl")
    rows = {r["instance_id"]: r for r in predictions}
    if len(rows) != len(predictions):
        raise ValueError("duplicate predictions")
    identifiers = manifest["task_ids"][start:stop]
    if set(identifiers) - set(rows):
        raise ValueError("batch has unfinished tasks; never freeze placeholders")
    selected = [rows[identifier] for identifier in identifiers]
    destination.mkdir(parents=True)
    write_jsonl(destination / "predictions.jsonl", selected)
    export_swebench(
        selected, destination / "swebench-predictions.jsonl", "agentic-code-search-gpt-6.1-sol"
    )
    write_json(
        destination / "manifest.json",
        {
            "kind": "frozen_inference_batch",
            "batch": batch,
            "start": start,
            "stop": stop,
            "count": len(selected),
            "parent_manifest_sha256": hashlib.sha256(
                (source / "manifest.json").read_bytes()
            ).hexdigest(),
            "predictions_sha256": hashlib.sha256(
                (destination / "predictions.jsonl").read_bytes()
            ).hexdigest(),
            "parent_configuration": manifest,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--stop", type=int, required=True)
    parser.add_argument("--batch", type=int, required=True)
    args = parser.parse_args()
    freeze(args.source, args.destination, args.start, args.stop, args.batch)
