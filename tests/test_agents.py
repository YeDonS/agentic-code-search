import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from code_assistant.agents import ToolCallingAgent, get_model
from code_assistant.config import Settings
from code_assistant.telemetry import RunLogger
from code_assistant.workflow import debug_repository


class ProtocolModel(BaseChatModel):
    responses: list[AIMessage]
    position: int = 0
    _seen: list[Any] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "test-protocol"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._seen.append(list(messages))
        response = self.responses[self.position]
        self.position += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def test_native_tool_call_returns_registered_evidence_to_model(tools, tmp_path):
    model = ProtocolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"path": "billing.py"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Source read; insufficient evidence for a confirmed fix."),
        ]
    )
    agent = ToolCallingAgent(model, tools.settings, RunLogger(tmp_path / "agent", "run"))
    result = agent.run("code_search", {"issue": "discount bug"}, tools.for_agent("code_search"))
    returned = [m for m in model._seen[1] if isinstance(m, ToolMessage)]
    assert returned[0].tool_call_id == "call-1"
    assert json.loads(returned[0].content)["id"] == tools.evidence[0].id
    assert "insufficient" in result


def test_unknown_tool_is_reported_without_execution(tools, tmp_path):
    model = ProtocolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "arbitrary_shell", "args": {}, "id": "call-1", "type": "tool_call"}
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    agent = ToolCallingAgent(model, tools.settings, RunLogger(tmp_path / "agent", "run"))
    agent.run("code_search", {}, tools.for_agent("code_search"))
    assert tools.calls == 0
    assert "unavailable" in str(model._seen[1][-1].content)


def test_model_can_explicitly_abstain_after_reading_source(source_repo, tmp_path):
    abstention = {
        "conclusion": "insufficient_evidence",
        "root_cause": "Cannot establish the root cause.",
        "affected_files": [],
        "evidence_ids": [],
        "suggested_fix": "Need reproduction.",
        "confidence": "low",
        "limitations": ["No reproduction available."],
    }
    model = ProtocolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"path": "billing.py"},
                        "id": "read",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Need reproduction."),
            AIMessage(content=json.dumps(abstention)),
        ]
    )
    result = debug_repository(
        source_repo,
        "There is an issue with the discount",
        Settings(mode="model", runs_dir=tmp_path),
        model=model,
    )
    assert result.status == "insufficient_evidence"
    assert result.diagnosis is None


def test_provider_key_from_dotenv_is_passed_without_logging(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=private-configured-test-key\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    captured = {}

    def factory(model, **kwargs):
        captured.update(kwargs)
        return "model"

    monkeypatch.setattr("code_assistant.agents.init_chat_model", factory)
    settings = Settings(_env_file=env, mode="model")
    assert get_model(settings) == "model"
    assert captured["api_key"] == "private-configured-test-key"


def test_single_conversation_uses_source_tools_and_validates_final_citations(source_repo, tmp_path):
    diagnosis = {
        "conclusion": "identified",
        "root_cause": "Falsey zero gets the default.",
        "affected_files": ["billing.py"],
        "evidence_ids": ["e0001"],
        "suggested_fix": "Check None.",
        "proposed_patch": "",
        "confidence": "medium",
        "limitations": [],
    }
    model = ProtocolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"path": "billing.py"},
                        "id": "read",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content=json.dumps(diagnosis)),
        ]
    )
    result = debug_repository(
        source_repo,
        "zero incorrectly selects default",
        Settings(mode="model", workflow="single", runs_dir=tmp_path),
        model=model,
    )
    assert result.status == "diagnosed" and [r.agent for r in result.routes] == ["single_agent"]
    assert len(model._seen[1]) > len(model._seen[0])


def test_global_model_call_ceiling_survives_repeated_role_invocations(tools, tmp_path):
    settings = tools.settings.model_copy(update={"max_model_calls": 2})
    model = ProtocolModel(responses=[AIMessage(content="done")] * 2)
    agent = ToolCallingAgent(model, settings, RunLogger(tmp_path / "agent", "budget"))
    for _ in range(4):
        agent.run("code_search", {}, [])
    assert agent.calls == model.position == 2
