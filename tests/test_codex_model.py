import json
import subprocess

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from code_assistant.agents import get_model
from code_assistant.codex_model import CodexCliModel, CodexModelError, parse_events
from code_assistant.config import Settings


def events(content, *, activity=None):
    records = [{"type": "thread.started", "thread_id": "local-test"}]
    if activity:
        records.append({"type": "item.started", "item": {"type": activity}})
    records.extend(
        [
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps(content)},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 40},
            },
        ]
    )
    return "\n".join(json.dumps(r) for r in records)


def fake_process(monkeypatch, output, captured):
    monkeypatch.setattr("code_assistant.codex_model.shutil.which", lambda _: "/bin/codex")

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            captured["command"] = command
            captured["cwd"] = kwargs["cwd"]
            captured["schema"] = json.loads((kwargs["cwd"] / "response-schema.json").read_text())
            self.output = kwargs["stdout"]

        def communicate(self, request=None, timeout=None):
            captured["request"] = json.loads(request)
            self.output.write(output.encode())

    monkeypatch.setattr("code_assistant.codex_model.subprocess.Popen", Process)


def test_provider_dispatch_uses_local_login_adapter():
    model = get_model(Settings(mode="model", model="codex-cli:gpt-6.1-sol"))
    assert isinstance(model, CodexCliModel)
    assert model.model_name == "gpt-6.1-sol"


def test_structured_application_tool_call_and_isolated_cli(tools, monkeypatch):
    captured = {}
    fake_process(
        monkeypatch,
        events(
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "read_file",
                        "arguments": '{"path":"billing.py"}',
                    }
                ],
            }
        ),
        captured,
    )
    model = CodexCliModel(model_name="gpt-6.1-sol").bind_tools(tools.for_agent("code_search"))
    response = model.invoke(
        [SystemMessage(content="ROLE: code_search"), HumanMessage(content="bug")]
    )
    assert response.tool_calls[0]["args"] == {"path": "billing.py"}
    assert response.usage_metadata["input_token_details"]["cache_read"] == 40
    assert response.response_metadata["builtin_tool_calls"] == 0
    assert captured["cwd"] != tools.root
    assert str(tools.root) not in json.dumps(captured["request"])
    assert "--ignore-user-config" in captured["command"]
    assert "--ephemeral" in captured["command"]
    assert 'web_search="disabled"' in captured["command"]
    assert captured["schema"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "activity",
    ["command_execution", "file_change", "mcp_tool_call", "web_search", "unknown_new_tool"],
)
def test_builtin_tool_activity_fails_closed(activity):
    with pytest.raises(CodexModelError, match="forbidden built-in"):
        parse_events(events({"content": "done"}, activity=activity))


def test_reconnect_errors_are_accepted_only_if_turn_completes():
    data = (
        json.dumps({"type": "error", "message": "reconnecting"})
        + "\n"
        + events({"content": "done"})
    )
    assert parse_events(data)[2] == 1
    with pytest.raises(CodexModelError, match="completed"):
        parse_events(json.dumps({"type": "error"}))


def test_unavailable_application_tool_is_rejected(monkeypatch):
    fake_process(
        monkeypatch,
        events(
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "arbitrary_shell",
                        "arguments": "{}",
                    }
                ],
            }
        ),
        {},
    )
    with pytest.raises(CodexModelError, match="invalid application"):
        CodexCliModel(model_name="model").invoke([HumanMessage(content="bug")])


def test_synthesis_uses_strict_diagnosis_schema(monkeypatch):
    captured = {}
    diagnosis = {"root_cause": "fixture response"}
    fake_process(monkeypatch, events(diagnosis), captured)
    result = CodexCliModel(model_name="model").invoke([SystemMessage(content="ROLE: synthesis")])
    assert json.loads(result.content) == diagnosis  # workflow performs semantic/schema validation
    schema = captured["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert "proposed_patch" in schema["required"]


def test_timeout_kills_process_group(monkeypatch):
    monkeypatch.setattr("code_assistant.codex_model.shutil.which", lambda _: "/bin/codex")
    killed = []

    class Process:
        pid = 12345
        count = 0

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, *args, **kwargs):
            self.count += 1
            if self.count == 1:
                raise subprocess.TimeoutExpired("codex", 1)

    monkeypatch.setattr("code_assistant.codex_model.subprocess.Popen", Process)
    monkeypatch.setattr("code_assistant.codex_model.os.killpg", lambda pid, _: killed.append(pid))
    with pytest.raises(CodexModelError, match="timeout"):
        CodexCliModel(model_name="model", timeout=1).invoke([HumanMessage(content="bug")])
    assert killed == [12345]


def test_failure_categories_never_expose_arbitrary_provider_text():
    from code_assistant.codex_model import failure_category

    assert (
        failure_category("private-key: xyz; error code context_length_exceeded") == "context_limit"
    )
    assert failure_category("private source snippet and arbitrary diagnostic") == "unknown"
    assert failure_category("429 rate limit") == "rate_or_quota"
