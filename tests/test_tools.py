import json

import pytest

from code_assistant.config import Settings
from code_assistant.tools import RepositoryIndex, execute_tests, safe_file
from code_assistant.tools import test_targets as validate_targets


def test_search_registers_real_line_evidence(tools):
    result = tools.search("compute_discount", 3)
    assert result["hits"][0]["path"] == "billing.py"
    assert "return value or 10" in result["hits"][0]["text"]
    assert result["hits"][0]["start_line"] >= 1
    assert tools.evidence[0].kind == "search"


def test_empty_search_is_explicit(tools):
    assert tools.search("zzqxyunknownsymbol")["hits"] == []


@pytest.mark.parametrize(
    "path", ["../outside.py", "/etc/passwd", ".env", "missing.py", ".git/config"]
)
def test_confined_file_access(source_repo, path):
    with pytest.raises(ValueError):
        safe_file(source_repo, path)


def test_symlink_cannot_escape(source_repo, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("private_value = 42")
    (source_repo / "linked.py").symlink_to(outside)
    with pytest.raises(ValueError):
        safe_file(source_repo, "linked.py")
    assert "linked.py" not in [d[0] for d in RepositoryIndex(source_repo).documents]


def test_hidden_files_are_never_indexed(source_repo):
    assert all(".env" not in d[0] for d in RepositoryIndex(source_repo).documents)


@pytest.mark.parametrize("start,end", [(0, 1), (5, 2), (1, 121), (99, 100)])
def test_invalid_read_ranges(tools, start, end):
    with pytest.raises(ValueError):
        tools.read("billing.py", start, end)


def test_budget_rejects_tool_without_reading(tools):
    tools.settings.max_tool_calls = 1
    assert "error" not in json.loads(tools._call("read_file", tools.read, path="billing.py"))
    result = json.loads(tools._call("read_file", tools.read, path="billing.py"))
    assert result["error"] == "tool budget exhausted"
    assert len(tools.evidence) == 1


@pytest.mark.parametrize(
    "targets", [["-q"], ["../test_a.py"], ["billing.py"], ["test_billing.py::x;touch"], []]
)
def test_command_injection_and_invalid_targets_rejected(source_repo, targets):
    with pytest.raises(ValueError):
        validate_targets(source_repo, targets)


def test_execution_requires_opt_in(source_repo):
    with pytest.raises(ValueError, match="disabled"):
        execute_tests(source_repo, ["test_billing.py"], Settings(test_executor="disabled"))


def test_real_test_execution_sanitizes_env(source_repo, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-test-secret-123")
    (source_repo / "test_env.py").write_text(
        "import os\ndef test_key():\n    assert 'ANTHROPIC_API_KEY' not in os.environ\n"
    )
    result = execute_tests(source_repo, ["test_env.py"], Settings(test_executor="local"))
    assert result["exit_code"] == 0
    assert "1 passed" in result["output"]


def test_test_timeout_kills_process(source_repo):
    (source_repo / "test_sleep.py").write_text(
        "import time\ndef test_hang():\n    time.sleep(20)\n"
    )
    result = execute_tests(
        source_repo, ["test_sleep.py"], Settings(test_executor="local", test_timeout=1)
    )
    assert result["status"] == "timeout"
    assert result["duration_ms"] < 5000
    assert result["exit_code"] != 0


def test_log_access_is_run_scoped(tools):
    with pytest.raises(ValueError, match="unknown test run"):
        tools.logs("../../logs")


def test_test_failure_and_collection_failure_are_distinct(tools):
    tools.settings.test_executor = "local"
    (tools.root / "test_fail.py").write_text("def test_bad():\n    assert False\n")
    tools.run_tests(["test_fail.py"])
    assert tools.test_status == "baseline_failed"
    (tools.root / "test_fail.py").write_text("import missing_package_zzx\n")
    tools.run_tests(["test_fail.py"])
    assert tools.test_status == "environment_error"
