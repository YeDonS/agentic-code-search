import hashlib
import importlib.util
import json
import sys

import pytest

from code_assistant.config import PROJECT_ROOT


def curator(monkeypatch):
    monkeypatch.syspath_prepend(str(PROJECT_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "official_curator", PROJECT_ROOT / "scripts/curate_official.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.curate


def test_official_curation_binds_patch_report_and_workflow_identity(tmp_path, monkeypatch):
    predictions = tmp_path / "predictions.jsonl"
    patch = "candidate"
    predictions.write_text(json.dumps({"instance_id": "demo__demo-1", "model_patch": patch}) + "\n")
    shard = tmp_path / "artifacts/patch-shard-0"
    case = shard / "demo__demo-1/logs"
    case.mkdir(parents=True)
    (shard / "manifest.json").write_text(json.dumps({"github_run_id": "123", "test_timeout": 600}))
    (shard / "outcomes.jsonl").write_text(
        json.dumps(
            {
                "instance_id": "demo__demo-1",
                "status": "resolved",
                "resolved": True,
                "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
            }
        )
        + "\n"
    )
    report = case / "report.json"
    report.write_text(json.dumps({"demo__demo-1": {"resolved": False}}))
    function = curator(monkeypatch)
    url = "https://github.com/YeDonS/agentic-code-search/actions/runs/123"
    with pytest.raises(ValueError, match="grade disagree"):
        function(predictions, tmp_path / "artifacts", tmp_path / "bad-grade", url)
    report.write_text(json.dumps({"demo__demo-1": {"resolved": True}}))
    (case / "test_output.txt").write_text(
        ">>>>> Start Test Output\n1 passed\n=======\n>>>>> End Test Output\n"
    )
    result = function(predictions, tmp_path / "artifacts", tmp_path / "public", url)
    assert result["complete"] and result["patch_resolution_rate"] == 1
    assert (
        "[test summary] ======="
        in (tmp_path / "public/demo__demo-1/test-output-excerpt.txt").read_text()
    )
    with pytest.raises(ValueError, match="run ID"):
        function(
            predictions, tmp_path / "artifacts", tmp_path / "wrong-run", url.replace("123", "124")
        )
