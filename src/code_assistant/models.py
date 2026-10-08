from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DebugRequest(StrictModel):
    repository: str = Field(min_length=1, max_length=200)
    issue: str = Field(min_length=10, max_length=20000)


class Evidence(StrictModel):
    id: str
    kind: Literal["search", "source", "test", "log"]
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    text: str


class Diagnosis(StrictModel):
    conclusion: Literal["identified", "insufficient_evidence"]
    root_cause: str = Field(min_length=1)
    affected_files: list[str]
    evidence_ids: list[str]
    suggested_fix: str
    proposed_patch: str = ""
    confidence: Literal["low", "medium", "high"]
    limitations: list[str]


class RouteDecision(StrictModel):
    agent: Literal["code_search", "test_runner", "synthesis", "single_agent"]
    reason: str


class DebugResponse(StrictModel):
    run_id: str
    mode: Literal["demo", "model"]
    status: Literal["diagnosed", "insufficient_evidence", "failed"]
    diagnosis: Diagnosis | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    routes: list[RouteDecision] = Field(default_factory=list)
    test_status: str = "not_run"
    patch_verified: bool = False
    error: str | None = None
