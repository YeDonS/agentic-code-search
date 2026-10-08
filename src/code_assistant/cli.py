import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from code_assistant import benchmark
from code_assistant.config import BENCHMARK_ROOT, DEMO_ISSUE, DEMO_REPO, Settings
from code_assistant.observability import summarize_events
from code_assistant.telemetry import write_json
from code_assistant.workflow import debug_repository

app = typer.Typer(no_args_is_help=True)
bench = typer.Typer(no_args_is_help=True)
app.add_typer(bench, name="benchmark")
experiment = typer.Typer(no_args_is_help=True)
app.add_typer(experiment, name="experiment")


@app.command()
def doctor():
    """Check model access configuration without displaying or extracting credentials."""
    settings = Settings(mode="model")
    result = {"model": settings.model, "test_executor": settings.test_executor}
    if settings.model.startswith("codex-cli:"):
        available = bool(shutil.which(settings.codex_executable))
        result["cli_installed"] = available
        if available:
            version = subprocess.run(
                [settings.codex_executable, "--version"], capture_output=True, text=True, timeout=10
            )
            login = subprocess.run(
                [settings.codex_executable, "login", "status"], capture_output=True, timeout=10
            )
            result.update(
                cli_version=version.stdout.strip(),
                logged_in=login.returncode == 0,
                transport=settings.codex_transport,
            )
        ready = available and result.get("logged_in", False)
    else:
        key = (
            settings.anthropic_api_key
            if settings.model.startswith("anthropic:")
            else settings.openai_api_key
            if settings.model.startswith("openai:")
            else None
        )
        ready = key is not None
        result["provider_key_configured"] = ready
    result["configuration_ready"] = bool(ready)
    result["inference_tested"] = False
    typer.echo(json.dumps(result, indent=2))
    if not ready:
        raise typer.Exit(1)


@app.command()
def demo():
    """Run the scripted, synthetic checkout scenario with real baseline tests."""
    settings = Settings(mode="demo", test_executor="local")
    response = debug_repository(DEMO_REPO, DEMO_ISSUE, settings)
    typer.echo(response.model_dump_json(indent=2))
    if response.status != "diagnosed" or response.test_status != "baseline_failed":
        raise typer.Exit(1)


@app.command()
def debug(
    repository: Path,
    issue: str,
    executor: Annotated[
        str, typer.Option(help="disabled, local (trusted code), or docker")
    ] = "disabled",
):
    """Diagnose a repository with a real tool-calling model; requires provider credentials."""
    settings = Settings(mode="model", test_executor=executor)
    if not repository.is_dir():
        raise typer.BadParameter("repository does not exist")
    response = debug_repository(repository.resolve(), issue, settings)
    typer.echo(response.model_dump_json(indent=2))
    if response.status != "diagnosed":
        raise typer.Exit(1)


@app.command()
def serve(port: Annotated[int, typer.Option(min=1024, max=65535)] = 8000):
    """Start FastAPI on loopback; interactive API docs are at /docs."""
    import uvicorn

    uvicorn.run("code_assistant.api:app", host="127.0.0.1", port=port)


@app.command()
def logs(directory: Path):
    """Summarize run events and concrete failure patterns without reading source or prompts."""
    typer.echo(json.dumps(summarize_events(directory), indent=2))


@bench.command("build")
def build(destination: Path = Path("benchmarks"), cache: Path = Path(".cache")):
    """Rebuild the fixed 100-issue set from a pinned upstream parquet snapshot."""
    typer.echo(json.dumps(benchmark.build_dataset(destination, cache), indent=2))


@bench.command("run")
def run(
    output: Path,
    mode: str = "retrieval",
    limit: Annotated[int | None, typer.Option(min=1)] = None,
    tasks: Path = BENCHMARK_ROOT / "tasks.jsonl",
    cache: Path = Path(".cache"),
    workers: Annotated[int, typer.Option(min=1, max=8)] = 1,
    resume: bool = False,
):
    """Run retrieval or real-model diagnostics on isolated pre-fix source snapshots."""
    settings = Settings(test_executor="disabled")
    benchmark.run_benchmark(tasks, output, cache, settings, mode, limit, workers, resume)
    task_rows = benchmark.read_jsonl(tasks)
    if limit is not None:
        task_rows = task_rows[:limit]
    summary = benchmark.score_predictions(
        task_rows,
        benchmark.read_jsonl(tasks.parent / "gold" / "reference.jsonl"),
        benchmark.read_jsonl(output / "predictions.jsonl"),
    )
    write_json(output / "scores.json", summary)
    typer.echo(json.dumps({k: v for k, v in summary.items() if k != "per_issue"}, indent=2))


@bench.command("export")
def export(predictions: Path, destination: Path, model_name: str = "agentic-code-search"):
    """Export patches to the official SWE-bench predictions format and a human review CSV."""
    rows = benchmark.read_jsonl(predictions)
    benchmark.export_swebench(rows, destination, model_name)
    benchmark.export_review(rows, destination.with_suffix(".review.csv"))
    typer.echo(str(destination))


@bench.command("review")
def review(
    predictions: Path,
    output: Path,
    cache: Path = Path(".cache"),
    workers: Annotated[int, typer.Option(min=1, max=8)] = 4,
):
    """Compare FROZEN root causes with gold using a labeled automated LLM reviewer."""
    from code_assistant.review import review_predictions

    summary = review_predictions(predictions, output, cache, Settings(mode="model"), workers)
    typer.echo(json.dumps(summary, indent=2))


@bench.command("reference")
def reference(instance_id: str, destination: Path, cache: Path = Path(".cache")):
    """Export upstream gold for a reviewer AFTER predictions have been frozen."""
    benchmark.export_reference(instance_id, cache, destination)
    typer.echo(str(destination))


@bench.command("score")
def score(
    predictions: Path,
    destination: Path,
    tasks: Path = BENCHMARK_ROOT / "tasks.jsonl",
    reviews: Path | None = None,
    harness_report: Path | None = None,
):
    """Score localization; import complete human reviews or official harness results separately."""
    rows = benchmark.read_jsonl(predictions)
    summary = benchmark.score_predictions(
        benchmark.read_jsonl(tasks),
        benchmark.read_jsonl(tasks.parent / "gold" / "reference.jsonl"),
        rows,
    )
    benchmark.incorporate_external_scores(summary, rows, reviews, harness_report)
    write_json(destination, summary)
    typer.echo(json.dumps({k: v for k, v in summary.items() if k != "per_issue"}, indent=2))


@experiment.command("plan")
def experiment_plan(
    destination: Path,
    model: Annotated[str, typer.Option()],
    count: Annotated[int, typer.Option(min=1)] = 20,
    tasks: Path = BENCHMARK_ROOT / "tasks.jsonl",
    seed: int = 20261008,
):
    """Freeze an outcome-independent paired ablation before inference."""
    from code_assistant.experiments import create_plan

    typer.echo(json.dumps(create_plan(tasks, destination, model, count, seed), indent=2))


@experiment.command("run")
def experiment_run(
    plan: Path,
    arm: str,
    output: Path,
    cache: Path = Path(".cache"),
    workers: Annotated[int, typer.Option(min=1, max=8)] = 4,
    resume: bool = False,
):
    """Run one frozen arm with identical shared model/call/tool budget ceilings."""
    from code_assistant.experiments import run_arm

    run_arm(plan, arm, output, cache, workers, resume)


@experiment.command("summarize")
def experiment_summary(directory: Path, destination: Path):
    """Compare paired arms only after complete official grading."""
    from code_assistant.experiments import summarize_comparisons

    summary = summarize_comparisons(directory)
    write_json(destination, summary)
    typer.echo(json.dumps(summary, indent=2))
