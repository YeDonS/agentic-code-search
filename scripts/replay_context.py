"""Replay evidence selection on the original immutable source/search provenance."""

import argparse
import hashlib
import json
from pathlib import Path

from code_assistant.benchmark import read_jsonl
from code_assistant.context import select_evidence
from code_assistant.models import Evidence
from code_assistant.telemetry import write_json


def replay(path: Path):
    rows = []
    for row in read_jsonl(path):
        records = row["evidence_provenance"]
        if any(e["kind"] not in {"source", "search"} for e in records):
            raise ValueError("provenance-only replay requires immutable source/search observations")
        # In the frozen source-only run, equal kind/path/range implies equal
        # source text and truncation policy. This preserves selector deduplication
        # without republishing excerpts or downloading reference solutions.
        evidence = [
            Evidence(**e, text=json.dumps([e["kind"], e["path"], e["start_line"], e["end_line"]]))
            for e in records
        ]

        def sources(es):
            return {(e.path, e.start_line, e.end_line) for e in es if e.kind == "source"}

        available = sources(evidence)
        recent = sources(select_evidence(evidence, 24, "recent"))
        priority = sources(select_evidence(evidence, 24, "source_priority"))
        rows.append(
            {
                "instance_id": row["instance_id"],
                "overflow": len(evidence) > 24,
                "abstained": row["diagnosis"] is None,
                "available_unique_source_reads": len(available),
                "recent_retained_unique_source_reads": len(recent),
                "priority_retained_unique_source_reads": len(priority),
                "recent_dropped": sorted(available - recent),
                "priority_dropped": sorted(available - priority),
                "recent_lost_all_source": bool(available) and not recent,
            }
        )
    return {
        "kind": "deterministic_context_selection_replay_no_llm",
        "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "N": len(rows),
        "scope": "final original ledger equals original synthesis handoff; source-only immutable kind/path/range provenance reconstructs deduplication",
        "overflow_cases": sum(r["overflow"] for r in rows),
        "recent_dropped_source_cases": sum(bool(r["recent_dropped"]) for r in rows),
        "priority_dropped_source_cases": sum(bool(r["priority_dropped"]) for r in rows),
        "recent_lost_all_source_cases": sum(r["recent_lost_all_source"] for r in rows),
        "abstentions_with_partial_source_loss": sum(
            r["abstained"] and bool(r["recent_dropped"]) for r in rows
        ),
        "limitations": "Selection mechanism only: no regenerated diagnoses or functional tests. Partial loss may matter, but no original abstention lost all source; difficulty/search behavior confound the overflow association.",
        "per_issue": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provenance", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = replay(args.provenance)
    write_json(args.destination, result)
    print(json.dumps({k: v for k, v in result.items() if k != "per_issue"}, indent=2))
