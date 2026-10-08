from pathlib import Path

import pytest

from code_assistant.config import Settings
from code_assistant.telemetry import RunLogger
from code_assistant.tools import RepositoryTools


@pytest.fixture
def source_repo(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    (root / "billing.py").write_text("def compute_discount(value):\n    return value or 10\n")
    (root / "test_billing.py").write_text("def test_value():\n    assert True\n")
    (root / ".env").write_text("SECRET=do-not-read")
    return root


@pytest.fixture
def tools(source_repo: Path, tmp_path):
    settings = Settings(runs_dir=tmp_path / "runs", test_executor="disabled")
    return RepositoryTools(source_repo, settings, RunLogger(tmp_path / "logs", "test"))
