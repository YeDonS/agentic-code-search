"""Post-hoc repair of ALL originally withheld candidates, without reference solutions."""

import argparse
import hashlib
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from code_assistant.agents import ToolCallingAgent, get_model
from code_assistant.benchmark import (
    download,
    environment_manifest,
    export_swebench,
    extract_snapshot,
    read_jsonl,
    write_jsonl,
)
from code_assistant.config import Settings
from code_assistant.models import Diagnosis, Evidence
from code_assistant.telemetry import RunLogger, write_json
from code_assistant.tools import RepositoryTools, safe_file
from code_assistant.workflow import check_and_repair_patch


def repair(source: Path, tasks_path: Path, output: Path, cache: Path, model: str, workers: int = 4):
    if output.exists() or not 1 <= workers <= 8:
        raise ValueError("new output directory and 1–8 workers required")
    candidates = read_jsonl(source / "withheld-patches.jsonl")
    diagnoses = {row["instance_id"]: row for row in read_jsonl(source / "diagnoses.jsonl")}
    tasks = {row["instance_id"]: row for row in read_jsonl(tasks_path)}
    identifiers = [row["instance_id"] for row in candidates]
    if len(set(identifiers)) != len(identifiers) or not candidates:
        raise ValueError("unique withheld candidates required")
    if any(row["check"]["status"] != "invalid" for row in candidates):
        raise ValueError("selection must contain only original invalid candidates")
    settings = Settings(
        _env_file=None,
        mode="model",
        model=model,
        test_executor="disabled",
        max_model_calls=6,
        max_agent_steps=3,
        max_tool_calls=8,
        patch_repair_attempts=2,
        codex_transport="https",
    )
    output.mkdir(parents=True, mode=0o700)
    manifest = {
        "kind": "posthoc_invalid_patch_repair_only",
        "created_at": datetime.now(UTC).isoformat(),
        "count": len(candidates),
        "task_ids": identifiers,
        "model": model,
        "environment": environment_manifest(),
        "workers": workers,
        "parent_predictions_sha256": hashlib.sha256(
            (source / "swebench-predictions.jsonl").read_bytes()
        ).hexdigest(),
        "parent_candidates_sha256": hashlib.sha256(
            (source / "withheld-patches.jsonl").read_bytes()
        ).hexdigest(),
        "parent_diagnoses_sha256": hashlib.sha256(
            (source / "diagnoses.jsonl").read_bytes()
        ).hexdigest(),
        "max_model_calls": 6,
        "max_agent_steps": 3,
        "max_tool_calls": 8,
        "patch_repair_attempts": 2,
        "model_timeout": settings.model_timeout,
        "reasoning_effort": settings.codex_reasoning_effort,
        "transport": settings.codex_transport,
        "evidence_policy": settings.evidence_policy,
        "selection": "all withheld invalid candidates, without judge/outcome filtering",
        "actor_inputs": "original issue/diagnosis/candidate, pre-fix source observations, git apply errors only",
        "primary_metric": "official resolved / all originally invalid candidates",
        "limitations": "Outcome-selected exploratory repair study; extra inference budget, not pass@1 or a rerun of the 100-task system.",
    }
    if model.startswith("codex-cli:"):
        import subprocess

        manifest["codex_cli_version"] = subprocess.check_output(
            [settings.codex_executable, "--version"], text=True, timeout=10
        ).strip()
    write_json(output / "manifest.json", manifest)

    def one(row):
        identifier = row["instance_id"]
        directory = output / "agent_runs" / identifier
        logger = RunLogger(directory, identifier, identifier)
        logger.emit("run_start", mode="model", stage="repair_only")
        try:
            task = tasks[identifier]
            archive = cache / "archives" / f"{identifier}-{task['base_commit']}.tar.gz"
            if not archive.exists():
                download(
                    f"https://codeload.github.com/{task['repo']}/tar.gz/{task['base_commit']}",
                    archive,
                )
            logger.emit(
                "snapshot_ready", archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
            )
            with tempfile.TemporaryDirectory(prefix="code-assistant-repair-") as temporary:
                root = Path(temporary) / "repo"
                extract_snapshot(archive, root)
                tools = RepositoryTools(root, settings, logger)
                # Reconstruct the original observations from pinned source and published
                # provenance. No gold patch, test patch or hidden labels enter this path.
                for provenance in diagnoses[identifier]["evidence_provenance"]:
                    if provenance["kind"] not in {"source", "search"}:
                        continue
                    path = safe_file(root.resolve(), provenance["path"])
                    lines = path.read_text().splitlines()
                    text = "\n".join(lines[provenance["start_line"] - 1 : provenance["end_line"]])
                    tools.evidence.append(
                        Evidence(
                            **provenance,
                            text=text[: 10000 if provenance["kind"] == "source" else 3000],
                        )
                    )
                original = Diagnosis.model_validate(diagnoses[identifier]["diagnosis"])
                original.proposed_patch = row["proposed_patch"]
                agent = ToolCallingAgent(get_model(settings), settings, logger)
                result = check_and_repair_patch(
                    original,
                    tools,
                    agent,
                    directory,
                    {"issue": task["problem_statement"], "test_status": "not_run"},
                )
                write_json(
                    directory / "response.json",
                    {
                        "diagnosis": result.model_dump(),
                        "evidence": [e.model_dump() for e in tools.evidence],
                        "routes": [],
                        "test_status": "not_run",
                        "patch_verified": False,
                    },
                )
                prediction = {
                    "instance_id": identifier,
                    "mode": "model",
                    "status": "diagnosed",
                    "predicted_files": result.affected_files,
                    "root_cause": result.root_cause,
                    "model_patch": result.proposed_patch,
                    "root_cause_correct": None,
                    "resolved": None,
                }
                logger.emit(
                    "run_end",
                    status="diagnosed",
                    tool_calls=tools.calls,
                    model_calls=agent.calls,
                    patch_verified=False,
                )
        except Exception as error:
            logger.emit("run_error", error_type=type(error).__name__)
            logger.emit("run_end", status="failed")
            prediction = {
                "instance_id": identifier,
                "status": "failed",
                "model_patch": "",
                "error_type": type(error).__name__,
            }
        return prediction

    predictions = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(one, row) for row in candidates]):
            prediction = future.result()
            predictions.append(prediction)
            with (output / "predictions.jsonl").open("a") as stream:
                stream.write(json.dumps(prediction) + "\n")
            print(
                f"[{len(predictions)}/{len(candidates)}] {prediction['instance_id']}: patch={bool(prediction['model_patch'])}",
                flush=True,
            )
    order = {name: i for i, name in enumerate(identifiers)}
    predictions.sort(key=lambda p: order[p["instance_id"]])
    write_jsonl(output / "predictions.jsonl", predictions)
    export_swebench(
        predictions, output / "swebench-predictions.jsonl", "agentic-posthoc-format-repair"
    )
    write_json(
        output / "completion.json",
        {
            "count": len(predictions),
            "completed_at": datetime.now(UTC).isoformat(),
            "predictions_sha256": hashlib.sha256(
                (output / "predictions.jsonl").read_bytes()
            ).hexdigest(),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tasks", type=Path, default=Path("benchmarks/tasks.jsonl"))
    parser.add_argument("--cache", type=Path, default=Path(".cache"))
    parser.add_argument("--model", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    repair(args.source, args.tasks, args.output, args.cache, args.model, args.workers)
