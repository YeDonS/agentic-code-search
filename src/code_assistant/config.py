from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent
DEMO_REPO = PROJECT_ROOT / "examples" / "checkout"
if not DEMO_REPO.is_dir():
    DEMO_REPO = PACKAGE_ROOT / "_fixtures" / "checkout"
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks"
if not BENCHMARK_ROOT.is_dir():
    BENCHMARK_ROOT = PACKAGE_ROOT / "_benchmarks"
DEMO_ISSUE = "Passing discount=0 to calculate_total(100, discount=0) returns 90 instead of 100."


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASSISTANT_", env_file=".env", extra="ignore")

    mode: Literal["demo", "model"] = "demo"
    model: str = "anthropic:claude-sonnet-4-5-20250929"
    workspace_root: Path = DEMO_REPO.parent
    runs_dir: Path = Path("runs")
    api_token: SecretStr | None = None
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    test_executor: Literal["disabled", "local", "docker"] = "disabled"
    test_image: str = "code-assistant-test:local"
    test_timeout: int = Field(default=30, ge=1, le=300)
    max_search_passes: int = Field(default=2, ge=1, le=4)
    max_agent_steps: int = Field(default=5, ge=1, le=10)
    max_tool_calls: int = Field(default=18, ge=1, le=50)
    model_timeout: int = Field(default=120, ge=1, le=300)
    codex_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    codex_executable: str = "codex"
    codex_transport: Literal["auto", "https"] = "auto"

    def repository(self, name: str) -> Path:
        if not name or Path(name).is_absolute():
            raise ValueError("repository must be a relative directory under the workspace")
        root = self.workspace_root.resolve()
        path = (root / name).resolve()
        if path == root or not path.is_relative_to(root) or not path.is_dir():
            raise ValueError("repository is outside the workspace or does not exist")
        return path
