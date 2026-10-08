"""Publish complete hash-checked official outcomes and compact durable test evidence."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from aggregate_patch_results import aggregate

from code_assistant.telemetry import write_json


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def curate(predictions: Path, artifacts: Path, destination: Path, workflow: str):
    if destination.exists() or not re.fullmatch(
        r"https://github.com/YeDonS/agentic-code-search/actions/runs/\d+", workflow
    ):
        raise ValueError("new destination and exact evaluation workflow URL required")
    result = aggregate(predictions, artifacts)
    if not result["complete"]:
        raise ValueError("cannot curate incomplete official evaluation")
    manifests = [json.loads(p.read_text()) for p in sorted(artifacts.glob("*/manifest.json"))]
    run_id = workflow.rsplit("/", 1)[1]
    if not manifests or any(
        str(m["github_run_id"]) != run_id or m["test_timeout"] != 600 for m in manifests
    ):
        raise ValueError("official run ID or fixed test timeout mismatch")
    for row in result["per_issue"]:
        if row.get("patch_sha256") is None:
            raise ValueError("official outcome missing patch identity")
    write_json(destination / "results.json", result)
    write_json(
        destination / "manifest.json",
        {
            "workflow_url": workflow,
            "harness_version": "5.0.2",
            "test_timeout_seconds": 600,
            "predictions_sha256": sha(predictions),
            "results_sha256": sha(destination / "results.json"),
            "shards": manifests,
            "patches_changed_after_freeze": False,
            "raw_artifacts": "GitHub Actions patch-shard-* artifacts (30-day retention); reports/excerpts/log hashes retained here",
        },
    )
    for outcome in result["per_issue"]:
        identifier = outcome["instance_id"]
        case = destination / identifier
        write_json(case / "outcome.json", outcome)
        if outcome["status"] == "empty_patch":
            continue
        matches = [p for p in artifacts.glob(f"*/{identifier}") if p.is_dir()]
        if len(matches) != 1:
            raise ValueError("missing or duplicate raw case artifact")
        raw = matches[0]
        reports = list(raw.glob("logs/**/report.json"))
        if len(reports) > 1:
            raise ValueError("duplicate harness report")
        if outcome["status"] in {"resolved", "unresolved"} and len(reports) != 1:
            raise ValueError("graded outcome requires its official report")
        if reports:
            grade = json.loads(reports[0].read_text())[identifier]
            if grade["resolved"] is not outcome["resolved"]:
                raise ValueError("official report and shard grade disagree")
            shutil.copyfile(reports[0], case / "report.json")
        summaries = list(raw.glob("summary/*.json"))
        if len(summaries) == 1:
            shutil.copyfile(summaries[0], case / "harness-summary.json")
        outputs = list(raw.glob("logs/**/test_output.txt"))
        excerpt = None
        if len(outputs) == 1:
            lines = outputs[0].read_text(errors="replace").splitlines()
            first = next(
                (i for i, line in enumerate(lines) if ">>>>> Start Test Output" in line), 0
            )
            stop = next(
                (i for i in range(first + 1, len(lines)) if ">>>>> End Test Output" in lines[i]),
                len(lines) - 1,
            )
            start = max(first, stop - 159)
            body = [line.rstrip() for line in lines[start : stop + 1]]
            # Do not accidentally introduce conflict markers into the Git tree.
            body = [
                "[test summary] " + line
                if re.match(r"^(?:<{7}|={7}(?:\s|$)|>{7}(?:\s|$))", line)
                else line
                for line in body
            ]
            (case / "test-output-excerpt.txt").write_text("\n".join(body) + "\n")
            excerpt = {
                "raw_sha256": sha(outputs[0]),
                "raw_lines": len(lines),
                "start_line": start + 1,
                "stop_line": stop + 1,
                "truncated": start > first,
                "trailing_whitespace_removed": True,
                "git_marker_lines_prefixed_for_display": True,
            }
        write_json(
            case / "raw-log-manifest.json",
            {
                "workflow_url": workflow,
                "artifact_name": raw.parent.name,
                "files": {
                    p.relative_to(raw).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size}
                    for p in sorted(raw.rglob("*"))
                    if p.is_file()
                },
                "excerpt": excerpt,
            },
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--workflow", required=True)
    args = parser.parse_args()
    report = curate(args.predictions, args.artifacts, args.destination, args.workflow)
    print(
        json.dumps({k: report[k] for k in ["total_instances", "patch_resolution_rate", "complete"]})
    )
