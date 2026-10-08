import json

from langchain_core.messages import AIMessage
from test_agents import ProtocolModel

from code_assistant.agents import ToolCallingAgent
from code_assistant.models import Diagnosis
from code_assistant.workflow import check_and_repair_patch

BAD = "--- a/billing.py\n+++ b/billing.py\n@@ -1 +1 @@\n-missing = 0\n+return_value = 1\n"
GOOD = "--- a/billing.py\n+++ b/billing.py\n@@ -1,2 +1,2 @@\n def compute_discount(value):\n-    return value or 10\n+    return 10 if value is None else value\n"


def diagnosis(tools, patch=BAD):
    return Diagnosis(
        conclusion="identified",
        root_cause="A falsey explicit zero is replaced by the default.",
        affected_files=["billing.py"],
        evidence_ids=[tools.read("billing.py")["id"]],
        suggested_fix="Check None explicitly.",
        proposed_patch=patch,
        confidence="high",
        limitations=[],
    )


def test_apply_feedback_and_source_read_recover_patch_without_mutating_checkout(tools, tmp_path):
    initial = diagnosis(tools)
    model = ProtocolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"path": "billing.py"},
                        "id": "verify",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content=initial.model_copy(update={"proposed_patch": GOOD}).model_dump_json()
            ),
        ]
    )
    agent = ToolCallingAgent(model, tools.settings, tools.logger)
    result = check_and_repair_patch(initial, tools, agent, tmp_path / "audit", {"issue": "zero"})
    assert result.proposed_patch == GOOD
    assert result.root_cause == initial.root_cause
    assert "patch failed" in json.loads(model._seen[0][1].content)["apply_error"]
    assert agent.calls == 2
    audit = json.loads((tmp_path / "audit/patch-check.json").read_text())
    assert audit["recovered"] and audit["repair_attempts"] == 1
    assert (tools.root / "billing.py").read_text().endswith("return value or 10\n")


def test_repair_stops_at_attempt_limit_and_keeps_original_candidate(tools, tmp_path):
    initial = diagnosis(tools)
    model = ProtocolModel(responses=[AIMessage(content=initial.model_dump_json())] * 2)
    result = check_and_repair_patch(
        initial,
        tools,
        ToolCallingAgent(model, tools.settings, tools.logger),
        tmp_path / "audit",
        {},
    )
    assert not result.proposed_patch
    attempts = json.loads((tmp_path / "audit/patch-attempts.json").read_text())
    assert len(attempts) == 3 and all(a["candidate"] == BAD for a in attempts)


def test_valid_or_unsafe_patch_never_spends_repair_model_calls(tools, tmp_path):
    for patch in [GOOD, BAD.replace("billing.py", "../outside.py")]:
        model = ProtocolModel(responses=[])
        agent = ToolCallingAgent(model, tools.settings, tools.logger)
        check_and_repair_patch(diagnosis(tools, patch), tools, agent, tmp_path / "audit", {})
        assert agent.calls == 0


def test_repair_respects_remaining_global_model_budget(tools, tmp_path):
    tools.settings.max_model_calls = 2
    initial = diagnosis(tools)
    model = ProtocolModel(responses=[AIMessage(content=initial.model_dump_json())])
    agent = ToolCallingAgent(model, tools.settings, tools.logger)
    agent.calls = 1
    result = check_and_repair_patch(initial, tools, agent, tmp_path / "audit", {})
    assert not result.proposed_patch and agent.calls == 2


def test_failed_model_correction_preserves_diagnosis_and_attempt_audit(
    tools, tmp_path, monkeypatch
):
    initial = diagnosis(tools)
    agent = ToolCallingAgent(ProtocolModel(responses=[]), tools.settings, tools.logger)
    monkeypatch.setattr(
        agent, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("safe provider failure"))
    )
    result = check_and_repair_patch(initial, tools, agent, tmp_path / "audit", {})
    assert result.root_cause == initial.root_cause and not result.proposed_patch
    attempts = json.loads((tmp_path / "audit/patch-attempts.json").read_text())
    assert len(attempts) == 3 and attempts[-1]["audit"]["status"] == "model_error"
    assert (
        json.loads((tmp_path / "audit/candidate-patch.json").read_text())["proposed_patch"] == BAD
    )
