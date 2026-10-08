"""Pinned historical tasks, isolated snapshots, and explicitly separate scoring stages."""

import csv
import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import tarfile
import tempfile
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_assistant.config import Settings
from code_assistant.telemetry import RunLogger, write_json
from code_assistant.tools import RepositoryTools, tokenize
from code_assistant.workflow import debug_repository

DATASET = "SWE-bench/SWE-bench_Lite"
REVISION = "b0dde1093fe417d83b7184254edf8199c1f0dff5"
SEED = 2026


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))


def download(url: str, destination: Path, max_bytes: int = 80_000_000) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "agentic-code-search/0.1"})
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as out:
            count = 0
            while chunk := response.read(1_000_000):
                count += len(chunk)
                if count > max_bytes:
                    raise ValueError("download exceeded size limit")
                out.write(chunk)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def production_files(patch: str) -> list[str]:
    paths = re.findall(r"^diff --git a/(\S+) b/(\S+)$", patch, re.M)
    return sorted({new for _, new in paths if not is_test_file(new)})


def is_test_file(path: str) -> bool:
    p = Path(path)
    return (
        any(x in {"test", "tests", "testing"} for x in p.parts)
        or p.name.startswith("test_")
        or p.name.endswith("_test.py")
        or p.name == "conftest.py"
    )


def select_tasks(
    rows: list[dict[str, Any]], count: int = 100, seed: int = SEED
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if (
            row.get("base_commit")
            and row.get("problem_statement")
            and production_files(row["patch"])
        ):
            groups[row["repo"]].append(row)
    for values in groups.values():
        values.sort(key=lambda r: hashlib.sha256(f"{seed}:{r['instance_id']}".encode()).hexdigest())
    selected = []
    position = 0
    while len(selected) < count:
        added = 0
        for repo in sorted(groups):
            if position < len(groups[repo]) and len(selected) < count:
                selected.append(groups[repo][position])
                added += 1
        if not added:
            raise ValueError("not enough eligible historical tasks")
        position += 1
    return selected


def build_dataset(destination: Path, cache: Path, count: int = 100) -> dict[str, Any]:
    import pyarrow.parquet as parquet

    source = cache / f"swebench-lite-{REVISION}.parquet"
    if not source.exists():
        download(
            f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/data/test-00000-of-00001.parquet",
            source,
        )
    rows = parquet.read_table(source).to_pylist()
    selected = select_tasks(rows, count)
    tasks, gold = [], []
    for row in selected:
        pr = row["instance_id"].rsplit("-", 1)[1]
        tasks.append(
            {
                key: row[key]
                for key in ["instance_id", "repo", "base_commit", "problem_statement", "created_at"]
            }
            | {"maintainer_fix_url": f"https://github.com/{row['repo']}/pull/{pr}"}
        )
        gold.append(
            {
                "instance_id": row["instance_id"],
                "patch_sha256": hashlib.sha256(row["patch"].encode()).hexdigest(),
                "test_patch_sha256": hashlib.sha256(row["test_patch"].encode()).hexdigest(),
                "changed_files": production_files(row["patch"]),
                "FAIL_TO_PASS": json.loads(row["FAIL_TO_PASS"])
                if isinstance(row["FAIL_TO_PASS"], str)
                else row["FAIL_TO_PASS"],
                "PASS_TO_PASS": json.loads(row["PASS_TO_PASS"])
                if isinstance(row["PASS_TO_PASS"], str)
                else row["PASS_TO_PASS"],
            }
        )
    write_jsonl(destination / "tasks.jsonl", tasks)
    write_jsonl(destination / "gold" / "reference.jsonl", gold)
    provenance = {
        "dataset": DATASET,
        "revision": REVISION,
        "split": "test",
        "seed": SEED,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "tasks_sha256": hashlib.sha256((destination / "tasks.jsonl").read_bytes()).hexdigest(),
        "reference_sha256": hashlib.sha256(
            (destination / "gold" / "reference.jsonl").read_bytes()
        ).hexdigest(),
        "count": len(tasks),
        "eligible_source_rows": len(rows),
        "selection": "SHA256-ranked per repository, sorted-repository round robin, no result-based filtering",
        "repositories": dict(sorted(Counter(t["repo"] for t in tasks).items())),
        "created_at": datetime.now(UTC).isoformat(),
    }
    write_json(destination / "provenance.json", provenance)
    return provenance


def export_reference(instance_id: str, cache: Path, destination: Path) -> None:
    """Reviewer-only reference export. Never placed in an actor's repository."""
    import pyarrow.parquet as parquet

    source = cache / f"swebench-lite-{REVISION}.parquet"
    if not source.exists():
        download(
            f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/data/test-00000-of-00001.parquet",
            source,
        )
    row = next(
        (r for r in parquet.read_table(source).to_pylist() if r["instance_id"] == instance_id), None
    )
    if row is None:
        raise ValueError("instance ID is not in the pinned source dataset")
    write_json(destination, row)


def environment_manifest() -> dict[str, Any]:
    digest = hashlib.sha256()
    for file in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_tree_sha256": digest.hexdigest(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ["langchain", "langgraph", "fastapi", "numpy", "rank-bm25"]
        },
    }


def extract_snapshot(archive: Path, destination: Path) -> None:
    """Extract only regular files/directories, stripping one archive prefix; never links."""
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    files = 0
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            parts = Path(member.name).parts
            if (
                Path(member.name).is_absolute()
                or len(parts) < 2
                or any(x in {"..", ".git"} for x in parts)
            ):
                continue
            relative = Path(*parts[1:])
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("archive path escapes snapshot")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                total += member.size
                files += 1
                if total > 350_000_000 or member.size > 20_000_000 or files > 40000:
                    raise ValueError("archive extraction size limit exceeded")
                target.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is not None:
                    with source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)


def retrieval_prediction(
    task: dict[str, Any], root: Path, settings: Settings, logger: RunLogger
) -> dict[str, Any]:
    tools = RepositoryTools(root, settings, logger)
    # Actor inputs are issue text and the pre-fix snapshot; no reference patch or labels.
    terms = [term for term, _ in Counter(tokenize(task["problem_statement"])).most_common(35)]
    result = json.loads(
        tools._call("search_repository", tools.search, query=" ".join(terms), limit=10)
    )
    hits = result.get("hits", [])
    files = list(dict.fromkeys(hit["path"] for hit in hits if not is_test_file(hit["path"])))[:5]
    for path in files[:3]:
        hit = next(h for h in hits if h["path"] == path)
        tools._call(
            "read_file",
            tools.read,
            path=path,
            start_line=hit["start_line"],
            end_line=min(hit["start_line"] + 79, hit["end_line"] + 40),
        )
    prediction = {
        "instance_id": task["instance_id"],
        "mode": "retrieval",
        "status": "completed",
        "predicted_files": files,
        "root_cause": None,
        "model_patch": "",
        "evidence": [e.model_dump() for e in tools.evidence],
        "test_status": "not_run",
        "root_cause_correct": None,
        "resolved": None,
    }
    logger.emit(
        "run_end",
        status="completed",
        mode="retrieval",
        tool_calls=tools.calls,
        test_status="not_run",
        patch_verified=False,
    )
    return prediction


def run_benchmark(
    tasks_path: Path,
    output: Path,
    cache: Path,
    settings: Settings,
    mode: str = "retrieval",
    limit: int | None = None,
    workers: int = 1,
    resume: bool = False,
) -> list[dict[str, Any]]:
    tasks = read_jsonl(tasks_path)
    if limit is not None:
        tasks = tasks[:limit]
    if not tasks or mode not in {"retrieval", "model"} or not 1 <= workers <= 8:
        raise ValueError("nonempty task set and retrieval/model mode required")
    if settings.test_executor != "disabled":
        raise ValueError(
            "historical benchmark tests must use the official SWE-bench harness; this diagnostic runner disables execution"
        )
    manifest = {
        "mode": mode,
        "count": len(tasks),
        "task_ids": [t["instance_id"] for t in tasks],
        "tasks_sha256": hashlib.sha256(tasks_path.read_bytes()).hexdigest(),
        "model": settings.model if mode == "model" else None,
        "seed": SEED,
        "created_at": datetime.now(UTC).isoformat(),
        "test_executor": "disabled",
        "max_tool_calls": settings.max_tool_calls,
        "max_search_passes": settings.max_search_passes,
        "max_agent_steps": settings.max_agent_steps,
        "model_timeout": settings.model_timeout,
        "codex_reasoning_effort": settings.codex_reasoning_effort if mode == "model" else None,
        "codex_transport": settings.codex_transport if mode == "model" else None,
        "workers": workers,
        "environment": environment_manifest(),
    }
    if mode == "model" and settings.model.startswith("codex-cli:"):
        import subprocess

        version = subprocess.run(
            [settings.codex_executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        manifest["codex_cli_version"] = version.stdout.strip()
    for task in tasks:
        identifier = task["instance_id"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+", identifier):
            raise ValueError("invalid instance ID")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", task["repo"]) or not re.fullmatch(
            r"[0-9a-f]{40}", task["base_commit"]
        ):
            raise ValueError("invalid repository or base commit")
    if output.exists():
        if not resume:
            raise ValueError(
                "choose a new output directory or --resume the exact frozen configuration"
            )
        previous = json.loads((output / "manifest.json").read_text())
        if any(previous.get(k) != v for k, v in manifest.items() if k != "created_at"):
            raise ValueError(
                "cannot resume: source, tasks, environment, or model configuration changed"
            )
        predictions = (
            read_jsonl(output / "predictions.jsonl")
            if (output / "predictions.jsonl").exists()
            else []
        )
        identifiers = [p["instance_id"] for p in predictions]
        if len(set(identifiers)) != len(identifiers) or set(identifiers) - set(
            manifest["task_ids"]
        ):
            raise ValueError("cannot resume duplicate or unknown predictions")
    else:
        output.mkdir(parents=True, mode=0o700)
        write_json(output / "manifest.json", manifest)
        predictions = []
    completed = {p["instance_id"] for p in predictions}

    def run_one(task: dict[str, Any]) -> dict[str, Any]:
        identifier = task["instance_id"]
        logger = RunLogger(output / "traces" / identifier, identifier, identifier)
        logger.emit("run_start", mode=mode, base_commit=task["base_commit"])
        try:
            archive = cache / "archives" / f"{identifier}-{task['base_commit']}.tar.gz"
            if not archive.exists():
                download(
                    f"https://codeload.github.com/{task['repo']}/tar.gz/{task['base_commit']}",
                    archive,
                )
            logger.emit(
                "snapshot_ready", archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()
            )
            with tempfile.TemporaryDirectory(prefix="code-assistant-snapshot-") as temp:
                root = Path(temp) / "repo"
                extract_snapshot(archive, root)
                if mode == "retrieval":
                    prediction = retrieval_prediction(task, root, settings, logger)
                else:
                    run_settings = settings.model_copy(
                        update={"mode": "model", "runs_dir": output / "agent_runs"}
                    )
                    response = debug_repository(
                        root,
                        task["problem_statement"],
                        run_settings,
                        issue_id=identifier,
                        run_id=identifier,
                    )
                    diagnosis = response.diagnosis
                    prediction = {
                        "instance_id": identifier,
                        "mode": "model",
                        "status": response.status,
                        "predicted_files": diagnosis.affected_files if diagnosis else [],
                        "root_cause": diagnosis.root_cause if diagnosis else None,
                        "model_patch": diagnosis.proposed_patch if diagnosis else "",
                        "root_cause_correct": None,
                        "resolved": None,
                        "test_status": response.test_status,
                    }
                    logger.emit("run_end", status=response.status, mode=mode, patch_verified=False)
        except Exception as error:
            logger.emit("run_error", error_type=type(error).__name__, message=str(error)[:300])
            logger.emit("run_end", status="failed", mode=mode)
            prediction = {
                "instance_id": identifier,
                "mode": mode,
                "status": "failed",
                "predicted_files": [],
                "root_cause": None,
                "model_patch": "",
                "root_cause_correct": None,
                "resolved": None,
                "error_type": type(error).__name__,
            }
        return prediction

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, t) for t in tasks if t["instance_id"] not in completed]
        for future in as_completed(futures):
            prediction = future.result()
            predictions.append(prediction)
            with (output / "predictions.jsonl").open("a") as stream:
                stream.write(json.dumps(prediction, ensure_ascii=False) + "\n")
                stream.flush()
            print(
                f"[{len(predictions)}/{len(tasks)}] {prediction['instance_id']}: {prediction['status']}",
                flush=True,
            )
    order = {t["instance_id"]: i for i, t in enumerate(tasks)}
    predictions.sort(key=lambda p: order[p["instance_id"]])
    write_jsonl(output / "predictions.jsonl", predictions)
    write_json(
        output / "completion.json",
        {
            "completed_at": datetime.now(UTC).isoformat(),
            "count": len(predictions),
            "predictions_sha256": hashlib.sha256(
                (output / "predictions.jsonl").read_bytes()
            ).hexdigest(),
        },
    )
    return predictions


def score_predictions(
    tasks: list[dict[str, Any]], gold: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> dict[str, Any]:
    expected = {t["instance_id"] for t in tasks}
    reference = {g["instance_id"]: g for g in gold}
    submitted = {p["instance_id"]: p for p in predictions}
    if len(submitted) != len(predictions) or set(submitted) - expected or expected - set(reference):
        raise ValueError("duplicate/unknown predictions or missing gold labels")
    rows = []
    for identifier in sorted(expected):
        pred = submitted.get(identifier, {})
        files = list(dict.fromkeys(pred.get("predicted_files", [])))[:5]
        target = set(reference[identifier]["changed_files"])
        hit_ranks = [i + 1 for i, f in enumerate(files) if f in target]
        rows.append(
            {
                "instance_id": identifier,
                "status": pred.get("status", "missing"),
                "hit_at_1": bool(files and files[0] in target),
                "hit_at_5": bool(hit_ranks),
                "reciprocal_rank_at_5": 1 / min(hit_ranks) if hit_ranks else 0,
                "changed_file_recall_at_5": len(set(files) & target) / len(target),
                "root_cause_correct": None,
                "resolved": None,
            }
        )
    count = len(rows)
    if not count:
        raise ValueError("cannot score an empty task set")
    return {
        "expected": count,
        "submitted": len(submitted),
        "failed_or_missing": sum(
            r["status"] in {"missing", "failed", "insufficient_evidence"} for r in rows
        ),
        "file_hit_at_1": sum(r["hit_at_1"] for r in rows) / count,
        "file_hit_at_5": sum(r["hit_at_5"] for r in rows) / count,
        "mrr_at_5": sum(r["reciprocal_rank_at_5"] for r in rows) / count,
        "mean_changed_file_recall_at_5": sum(r["changed_file_recall_at_5"] for r in rows) / count,
        "root_cause_accuracy": None,
        "patch_resolution_rate": None,
        "metric_scope": "file localization against maintainer patches; not semantic correctness or test resolution",
        "per_issue": rows,
    }


def export_review(predictions: list[dict[str, Any]], destination: Path) -> None:
    with destination.open("w", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=["instance_id", "root_cause", "root_cause_correct", "reviewer", "rationale"],
        )
        writer.writeheader()
        for prediction in predictions:
            writer.writerow(
                {
                    "instance_id": prediction["instance_id"],
                    "root_cause": prediction.get("root_cause") or "",
                }
            )


def incorporate_external_scores(
    summary: dict[str, Any],
    predictions: list[dict[str, Any]],
    reviews: Path | None = None,
    harness_report: Path | None = None,
) -> dict[str, Any]:
    """Only external adjudication/test evidence can populate correctness metrics."""
    expected = {row["instance_id"] for row in summary["per_issue"]}
    prediction_map = {p["instance_id"]: p for p in predictions}
    if reviews:
        with reviews.open() as stream:
            rows = list(csv.DictReader(stream))
        seen, judged, correct = set(), set(), set()
        per_issue = {r["instance_id"]: r for r in summary["per_issue"]}
        for row in rows:
            identifier = row["instance_id"]
            if identifier not in expected or identifier in seen:
                raise ValueError("unknown or duplicate human review")
            seen.add(identifier)
            verdict = row["root_cause_correct"].strip()
            if not verdict:
                continue
            if (
                verdict not in {"correct", "partial", "incorrect", "unscorable"}
                or not row["reviewer"].strip()
                or not row["rationale"].strip()
            ):
                raise ValueError("reviews require a valid verdict, named reviewer, and rationale")
            if verdict == "correct" and not prediction_map.get(identifier, {}).get("root_cause"):
                raise ValueError("cannot score a missing root-cause diagnosis as correct")
            judged.add(identifier)
            per_issue[identifier]["root_cause_correct"] = verdict == "correct"
            per_issue[identifier]["human_verdict"] = verdict
            if verdict == "correct":
                correct.add(identifier)
        summary["human_reviewed"] = len(judged)
        summary["root_cause_accuracy"] = (
            len(correct) / len(expected) if judged == expected else None
        )
        summary["reviews_sha256"] = hashlib.sha256(reviews.read_bytes()).hexdigest()
    if harness_report:
        report = json.loads(harness_report.read_text())
        if not isinstance(report.get("resolved_ids"), list):
            raise ValueError("expected an official SWE-bench report with resolved_ids")
        resolved = set(report["resolved_ids"])
        if not resolved.issubset(expected) or len(resolved) != len(report["resolved_ids"]):
            raise ValueError("unknown or duplicate resolved instances")
        if any(not prediction_map.get(i, {}).get("model_patch") for i in resolved):
            raise ValueError("resolved instances must have submitted nonempty patches")
        summary["patch_resolution_rate"] = len(resolved) / len(expected)
        for row in summary["per_issue"]:
            row["resolved"] = row["instance_id"] in resolved
        summary["harness_report_sha256"] = hashlib.sha256(harness_report.read_bytes()).hexdigest()
    return summary


def export_swebench(predictions: list[dict[str, Any]], destination: Path, model_name: str) -> None:
    write_jsonl(
        destination,
        [
            {
                "instance_id": p["instance_id"],
                "model_name_or_path": model_name,
                "model_patch": p.get("model_patch", ""),
            }
            for p in predictions
        ],
    )
