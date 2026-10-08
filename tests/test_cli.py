import json
from types import SimpleNamespace

from typer.testing import CliRunner

from code_assistant import cli
from code_assistant.config import Settings
from code_assistant.models import DebugResponse

runner = CliRunner()


def test_doctor_reports_configuration_without_inference_or_key_disclosure(monkeypatch):
    monkeypatch.setattr(
        cli,
        "Settings",
        lambda **kwargs: Settings(
            _env_file=None, openai_api_key="test-private", model="openai:test-model"
        ),
    )
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["inference_tested"] is False
    assert "test-private" not in result.stdout


def test_doctor_missing_provider_key_exits_nonzero(monkeypatch):
    monkeypatch.setattr(
        cli,
        "Settings",
        lambda **kwargs: Settings(_env_file=None, model="openai:test", openai_api_key=None),
    )
    assert runner.invoke(cli.app, ["doctor"]).exit_code == 1


def test_doctor_cli_status_does_not_expose_login_output(monkeypatch):
    monkeypatch.setattr(cli, "Settings", lambda **kwargs: Settings(model="codex-cli:test"))
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/local/bin/codex")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda args, **kwargs: SimpleNamespace(
            returncode=0, stdout="0.test" if "--version" in args else "private login output"
        ),
    )
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 0 and json.loads(result.stdout)["logged_in"]
    assert "private login output" not in result.stdout


def test_debug_rejects_missing_repository_and_propagates_failed_diagnosis(tmp_path, monkeypatch):
    assert (
        runner.invoke(cli.app, ["debug", str(tmp_path / "missing"), "a reported bug"]).exit_code
        == 2
    )
    monkeypatch.setattr(
        cli,
        "debug_repository",
        lambda *args, **kwargs: DebugResponse(
            run_id="test", mode="model", status="insufficient_evidence"
        ),
    )
    result = runner.invoke(cli.app, ["debug", str(tmp_path), "a reported bug"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "insufficient_evidence"


def test_export_preserves_empty_prediction_and_creates_review_template(tmp_path):
    source = tmp_path / "predictions.jsonl"
    source.write_text(
        json.dumps({"instance_id": "demo__demo-1", "model_patch": "", "root_cause": None}) + "\n"
    )
    target = tmp_path / "swebench.jsonl"
    result = runner.invoke(
        cli.app, ["benchmark", "export", str(source), str(target), "--model-name", "test"]
    )
    assert result.exit_code == 0, result.stdout
    assert json.loads(target.read_text())["model_patch"] == ""
    assert target.with_suffix(".review.csv").exists()


def test_logs_cli_counts_recorded_failure(tmp_path):
    (tmp_path / "events.jsonl").write_text(json.dumps({"event": "agent_step_limit"}) + "\n")
    result = runner.invoke(cli.app, ["logs", str(tmp_path)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["failure_patterns"]["agent_step_limit"] == 1


def test_serve_binds_loopback_and_validates_port(monkeypatch):
    seen = {}
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: seen.update(kwargs))
    assert runner.invoke(cli.app, ["serve", "--port", "8001"]).exit_code == 0
    assert seen == {"host": "127.0.0.1", "port": 8001}
    assert runner.invoke(cli.app, ["serve", "--port", "80"]).exit_code == 2


def test_experiment_plan_cli_freezes_model_and_budget_options(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(json.dumps({"instance_id": "demo__demo-1", "problem_statement": "bug"}) + "\n")
    directory = tmp_path / "plan"
    result = runner.invoke(
        cli.app,
        [
            "experiment",
            "plan",
            str(directory),
            "--model",
            "openai:test",
            "--count",
            "1",
            "--tasks",
            str(tasks),
        ],
    )
    assert result.exit_code == 0, result.stdout
    plan = json.loads((directory / "plan.json").read_text())
    assert plan["shared_settings"]["model"] == "openai:test"
    assert plan["shared_settings"]["max_model_calls"] == 10
