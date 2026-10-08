"""Run pinned SWE-bench 5.0.2 on frozen predictions; no model credentials required.

Run from the repository root in a disposable Linux Docker host. One image is pulled
at a time and its immutable digest is recorded before evaluation. The original pinned
test script and labels are passed directly to the official harness.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pyarrow.parquet as parquet

from code_assistant.benchmark import REVISION, download, read_jsonl, write_jsonl
from code_assistant.telemetry import write_json

HARNESS_VERSION = "5.0.2"
FIELDS = [
    "instance_id",
    "repo",
    "version",
    "image",
    "eval_script",
    "eval_type",
    "log_parser",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if not 0 <= args.shard < args.shards <= 100:
        parser.error("require 0 <= shard < shards <= 100")
    if importlib.metadata.version("swebench") != HARNESS_VERSION:
        raise ValueError(f"install swebench=={HARNESS_VERSION}; harness version must be pinned")
    predictions = read_jsonl(args.predictions)
    ids = [p["instance_id"] for p in predictions]
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError("nonempty unique predictions required")
    source = Path(".cache") / f"swebench-lite-{REVISION}.parquet"
    if not source.exists():
        download(
            f"https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite/resolve/{REVISION}/data/test-00000-of-00001.parquet",
            source,
        )
    provenance = json.loads(Path("benchmarks/provenance.json").read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != provenance["source_sha256"]:
        raise ValueError("pinned dataset checksum mismatch")
    reference = {r["instance_id"]: r for r in parquet.read_table(source).to_pylist()}
    if set(ids) - set(reference):
        raise ValueError("predictions contain instances outside the pinned dataset")
    if args.output.exists():
        raise ValueError(
            "choose a new output path; harness caches must never mix different patches"
        )
    args.output.mkdir(parents=True)
    manifest = {
        "harness_version": HARNESS_VERSION,
        "dataset_revision": REVISION,
        "dataset_sha256": provenance["source_sha256"],
        "predictions_sha256": hashlib.sha256(args.predictions.read_bytes()).hexdigest(),
        "shard": args.shard,
        "shards": args.shards,
        "test_timeout": args.timeout,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "github_sha": os.environ.get("GITHUB_SHA"),
    }
    write_json(args.output / "manifest.json", manifest)
    outcomes = []
    for index, prediction in enumerate(predictions):
        if index % args.shards != args.shard:
            continue
        identifier = prediction["instance_id"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+", identifier):
            raise ValueError("invalid instance ID")
        case = args.output / identifier
        case.mkdir()
        patch_sha256 = hashlib.sha256(prediction.get("model_patch", "").encode()).hexdigest()
        if not prediction.get("model_patch", "").strip():
            outcomes.append(
                {
                    "instance_id": identifier,
                    "status": "empty_patch",
                    "resolved": False,
                    "patch_sha256": patch_sha256,
                }
            )
            write_jsonl(args.output / "outcomes.jsonl", outcomes)
            continue
        row = reference[identifier]
        image = row["image"]
        if not image.startswith("swebench/sweb.eval.x86_64."):
            raise ValueError("unexpected official evaluation image")
        outcome = {
            "instance_id": identifier,
            "status": "infrastructure_error",
            "resolved": False,
            "image": image,
            "patch_sha256": patch_sha256,
        }
        try:
            with (case / "image-pull.log").open("w") as stream:
                subprocess.run(
                    ["docker", "pull", image],
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=600,
                    check=True,
                )
            info = json.loads(
                subprocess.check_output(["docker", "image", "inspect", image], text=True)
            )[0]
            outcome["image_id"] = info["Id"]
            outcome["image_digests"] = info.get("RepoDigests", [])
            write_jsonl(case / "tasks.jsonl", [{k: row[k] for k in FIELDS}])
            write_jsonl(case / "predictions.jsonl", [prediction])
            run_id = f"patch-{os.environ.get('GITHUB_RUN_ID', 'local')}-{args.shard}-{index}"
            command = [
                sys.executable,
                "-m",
                "swebench.harness.run_evaluation",
                "--dataset_name",
                str((case / "tasks.jsonl").resolve()),
                "--predictions_path",
                str((case / "predictions.jsonl").resolve()),
                "--instance_ids",
                identifier,
                "--max_workers",
                "1",
                "--timeout",
                str(args.timeout),
                "--run_id",
                run_id,
                "--report_dir",
                str((case / "summary").resolve()),
            ]
            with (case / "harness.log").open("w") as stream:
                result = subprocess.run(
                    command,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=args.timeout + 180,
                    cwd=case,
                )
            outcome["harness_exit_code"] = result.returncode
            reports = list((case / "summary").glob("*.json"))
            if len(reports) == 1:
                report = json.loads(reports[0].read_text())
                outcome["resolved"] = identifier in report["resolved_ids"]
                outcome["status"] = (
                    "resolved"
                    if outcome["resolved"]
                    else "unresolved"
                    if identifier in report["unresolved_ids"]
                    else "evaluation_error"
                )
                outcome["failure_reason"] = report.get("failure_reasons", {}).get(identifier)
                outcome["infra_failure"] = identifier in report.get("infra_failure_ids", [])
            # Gold test scripts are public upstream data but not part of the published result.
            (case / "tasks.jsonl").unlink(missing_ok=True)
        except (subprocess.SubprocessError, OSError, ValueError) as error:
            outcome["error_type"] = type(error).__name__
        finally:
            subprocess.run(["docker", "image", "rm", "-f", image], capture_output=True, timeout=60)
        outcomes.append(outcome)
        write_jsonl(args.output / "outcomes.jsonl", outcomes)
        print(f"{identifier}: {outcome['status']}", flush=True)


if __name__ == "__main__":
    main()
