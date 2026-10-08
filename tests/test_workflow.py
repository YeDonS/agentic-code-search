import json
import shutil
import subprocess

import pytest

from code_assistant.config import DEMO_ISSUE, DEMO_REPO, Settings
from code_assistant.models import Diagnosis
from code_assistant.workflow import choose_route, debug_repository, validate_diagnosis


def test_demo_gathers_evidence_and_real_failure(tmp_path):
    result = debug_repository(
        DEMO_REPO, DEMO_ISSUE, Settings(runs_dir=tmp_path, test_executor="local")
    )
    assert result.status == "diagnosed"
    assert result.test_status == "baseline_failed"
    assert result.patch_verified is False
    assert [r.agent for r in result.routes] == [
        "code_search",
        "test_runner",
        "code_search",
        "synthesis",
    ]
    assert "1 failed, 2 passed" in next(e.text for e in result.evidence if e.kind == "log")
    events = [
        json.loads(x) for x in (tmp_path / result.run_id / "events.jsonl").read_text().splitlines()
    ]
    assert events[0]["event"] == "run_start"
    assert events[-1]["event"] == "run_end"
    assert sum(e["event"] == "tool_start" for e in events) == sum(
        e["event"] == "tool_end" for e in events
    )
    assert all("text" not in e and "prompt" not in e for e in events)


def test_no_execution_when_disabled(tmp_path):
    result = debug_repository(
        DEMO_REPO, DEMO_ISSUE, Settings(runs_dir=tmp_path, test_executor="disabled")
    )
    assert result.status == "diagnosed"
    assert result.test_status == "not_run"
    assert "test_runner" not in [r.agent for r in result.routes]


def test_budget_cannot_be_bypassed_by_model(tmp_path):
    result = debug_repository(
        DEMO_REPO, DEMO_ISSUE, Settings(runs_dir=tmp_path, max_tool_calls=1, test_executor="local")
    )
    assert result.status == "insufficient_evidence"
    assert result.diagnosis is None
    assert result.test_status == "not_run"


def test_demo_cannot_impersonate_general_debugger(source_repo, tmp_path):
    with pytest.raises(ValueError, match="demo mode accepts only"):
        debug_repository(source_repo, DEMO_ISSUE, Settings(runs_dir=tmp_path))


def test_hallucinated_evidence_is_rejected(tools):
    source = tools.read("billing.py")
    diagnosis = Diagnosis(
        conclusion="identified",
        root_cause="fallback",
        affected_files=["billing.py"],
        evidence_ids=[source["id"]],
        suggested_fix="check None",
        confidence="medium",
        limitations=[],
    )
    assert validate_diagnosis(diagnosis, tools)
    assert not validate_diagnosis(
        diagnosis.model_copy(update={"evidence_ids": ["invented"]}), tools
    )
    assert not validate_diagnosis(
        diagnosis.model_copy(update={"affected_files": ["not_read.py"]}), tools
    )


def test_search_snippet_alone_is_not_source_read(tools):
    hit = tools.search("compute_discount")["hits"][0]
    diagnosis = Diagnosis(
        conclusion="identified",
        root_cause="fallback",
        affected_files=["billing.py"],
        evidence_ids=[hit["id"]],
        suggested_fix="check None",
        confidence="medium",
        limitations=[],
    )
    assert not validate_diagnosis(diagnosis, tools)


def test_new_file_header_cannot_bypass_read_citation_for_existing_file(tools):
    source = tools.read("billing.py")
    diagnosis = Diagnosis(
        conclusion="identified",
        root_cause="Need a helper.",
        affected_files=["helper.py"],
        evidence_ids=[source["id"]],
        suggested_fix="Create a helper.",
        confidence="medium",
        limitations=[],
        proposed_patch="--- /dev/null\n+++ b/helper.py\n@@ -0,0 +1 @@\n+value = 1\n",
    )
    assert validate_diagnosis(diagnosis, tools)
    (tools.root / "helper.py").write_text("existing = 1\n")
    assert not validate_diagnosis(diagnosis, tools)


def test_provider_failure_is_reported_without_secrets(source_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-value-test-123")
    monkeypatch.setattr(
        "code_assistant.workflow.get_model",
        lambda s: (_ for _ in ()).throw(RuntimeError("private-value-test-123")),
    )
    result = debug_repository(
        source_repo,
        "A genuine bug report with enough text",
        Settings(mode="model", runs_dir=tmp_path),
    )
    assert result.status == "failed"
    assert "private-value" not in (tmp_path / result.run_id / "events.jsonl").read_text()
    assert "private-value" not in result.error


def test_router_refines_missing_evidence(tools):
    state = {"search_passes": 1, "test_attempted": False}
    assert (
        choose_route(state, tools, tools.settings).reason == "source_evidence_missing_refine_search"
    )
    state["search_passes"] = tools.settings.max_search_passes
    assert choose_route(state, tools, tools.settings).agent == "synthesis"


def test_demo_patch_applies_and_repairs_fixture_in_separate_copy(tmp_path):
    result = debug_repository(DEMO_REPO, DEMO_ISSUE, Settings(runs_dir=tmp_path / "runs"))
    target = tmp_path / "patch-check"
    shutil.copytree(DEMO_REPO, target)
    check = subprocess.run(
        ["git", "apply", "--check", "-"],
        input=result.diagnosis.proposed_patch,
        text=True,
        capture_output=True,
        cwd=target,
    )
    assert check.returncode == 0, check.stderr
    subprocess.run(
        ["git", "apply", "-"],
        input=result.diagnosis.proposed_patch,
        text=True,
        cwd=target,
        check=True,
    )
    from code_assistant.tools import execute_tests

    test_result = execute_tests(target, ["tests/test_checkout.py"], Settings(test_executor="local"))
    assert test_result["exit_code"] == 0
    assert "3 passed" in test_result["output"]
    assert result.patch_verified is False  # The application itself only ran baseline tests.
