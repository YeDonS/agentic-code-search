import hashlib
import json

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from code_assistant.benchmark import REVISION, write_jsonl
from code_assistant.codex_model import CodexCliModel
from code_assistant.config import Settings
from code_assistant.review import review_predictions


def test_automated_judge_never_claims_human_accuracy(tmp_path, monkeypatch):
    import pyarrow as arrow
    import pyarrow.parquet as parquet

    cache = tmp_path / "cache"
    cache.mkdir()
    gold = [
        {"instance_id": name, "problem_statement": "bug", "patch": "maintainer fix"}
        for name in ("a", "b", "c")
    ]
    parquet.write_table(arrow.Table.from_pylist(gold), cache / f"swebench-lite-{REVISION}.parquet")
    predictions = tmp_path / "predictions.jsonl"
    write_jsonl(
        predictions,
        [
            {"instance_id": "a", "root_cause": "complete cause"},
            {"instance_id": "b", "root_cause": "partial cause"},
            {"instance_id": "c", "root_cause": None},
        ],
    )
    digest = hashlib.sha256(predictions.read_bytes()).hexdigest()
    calls = []

    def generate(self, messages, **kwargs):
        payload = json.loads(messages[1].content)
        calls.append(payload)
        assert self.response_schema is not None
        assert not self.bound_tools
        verdict = (
            "correct" if payload["prediction"]["root_cause"] == "complete cause" else "partial"
        )
        message = AIMessage(
            content=json.dumps(
                {"verdict": verdict, "rationale": "Comparison with frozen maintainer fix."}
            )
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    monkeypatch.setattr(CodexCliModel, "_generate", generate)
    summary = review_predictions(
        predictions,
        tmp_path / "review",
        cache,
        Settings(mode="model", model="codex-cli:test"),
        workers=2,
    )
    assert summary["automated_root_cause_match_rate"] == 1 / 3
    assert summary["root_cause_accuracy"] is None
    assert summary["human_review"] is False
    assert len(calls) == 2
    assert hashlib.sha256(predictions.read_bytes()).hexdigest() == digest
