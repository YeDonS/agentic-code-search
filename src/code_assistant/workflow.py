import uuid
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from code_assistant.agents import ToolCallingAgent, get_model
from code_assistant.config import DEMO_ISSUE, DEMO_REPO, Settings
from code_assistant.models import DebugResponse, Diagnosis, RouteDecision
from code_assistant.patches import check_patch
from code_assistant.telemetry import RunLogger, redact, write_json
from code_assistant.tools import RepositoryTools


class State(TypedDict):
    search_passes: int
    test_attempted: bool
    next_agent: str
    findings: list[str]
    routes: list[dict[str, str]]
    diagnosis: dict[str, Any] | None
    status: str


def choose_route(state: State, tools: RepositoryTools, settings: Settings) -> RouteDecision:
    has_source = any(e.kind == "source" for e in tools.evidence)
    if state["search_passes"] == 0:
        return RouteDecision(agent="code_search", reason="initial_repository_search")
    if tools.calls >= settings.max_tool_calls:
        return RouteDecision(agent="synthesis", reason="global_tool_budget_reached")
    if not has_source and state["search_passes"] < settings.max_search_passes:
        return RouteDecision(agent="code_search", reason="source_evidence_missing_refine_search")
    if has_source and not state["test_attempted"] and settings.test_executor != "disabled":
        return RouteDecision(
            agent="test_runner", reason="source_found_attempt_focused_reproduction"
        )
    if (
        tools.test_status == "baseline_failed"
        and state["search_passes"] < settings.max_search_passes
    ):
        return RouteDecision(agent="code_search", reason="failed_test_refine_source_hypothesis")
    return RouteDecision(agent="synthesis", reason="evidence_ready_or_search_budget_reached")


def validate_diagnosis(diagnosis: Diagnosis, tools: RepositoryTools) -> bool:
    cited = {e.id: e for e in tools.evidence}
    if not diagnosis.evidence_ids or any(i not in cited for i in diagnosis.evidence_ids):
        return False
    sources = [cited[i] for i in diagnosis.evidence_ids if cited[i].kind == "source"]
    source_paths = {e.path for e in sources}
    return bool(
        sources
        and diagnosis.affected_files
        and set(diagnosis.affected_files).issubset(source_paths)
    )


def debug_repository(
    root: Path,
    issue: str,
    settings: Settings,
    *,
    model: BaseChatModel | None = None,
    issue_id: str | None = None,
    run_id: str | None = None,
) -> DebugResponse:
    if settings.mode == "demo" and (root.resolve() != DEMO_REPO.resolve() or issue != DEMO_ISSUE):
        raise ValueError(
            "demo mode accepts only the bundled checkout repository and exact demo issue; use model mode for other issues"
        )
    run_id = run_id or uuid.uuid4().hex
    directory = settings.runs_dir / run_id
    logger = RunLogger(directory, run_id, issue_id)
    logger.emit("run_start", mode=settings.mode, test_executor=settings.test_executor)
    tools = RepositoryTools(root, settings, logger)

    def payload(state: State) -> dict[str, Any]:
        return {
            "issue": issue,
            "findings": state["findings"][-4:],
            "evidence": [e.model_dump() for e in tools.evidence[-24:]],
            "test_status": tools.test_status,
            "index_truncated": tools.index.truncated,
        }

    try:
        agent = ToolCallingAgent(model or get_model(settings), settings, logger)

        def route(state: State) -> dict[str, Any]:
            decision = choose_route(state, tools, settings)
            logger.emit(
                "route",
                agent=decision.agent,
                reason=decision.reason,
                search_passes=state["search_passes"],
                tool_calls=tools.calls,
            )
            return {
                "next_agent": decision.agent,
                "routes": [*state["routes"], decision.model_dump()],
            }

        def search(state: State) -> dict[str, Any]:
            finding = agent.run("code_search", payload(state), tools.for_agent("code_search"))
            return {
                "search_passes": state["search_passes"] + 1,
                "findings": [*state["findings"], finding],
            }

        def test(state: State) -> dict[str, Any]:
            finding = agent.run("test_runner", payload(state), tools.for_agent("test_runner"))
            return {"test_attempted": True, "findings": [*state["findings"], finding]}

        def synthesize(state: State) -> dict[str, Any]:
            if not any(e.kind == "source" for e in tools.evidence):
                logger.emit("insufficient_evidence", reason="no_source_read")
                return {"diagnosis": None, "status": "insufficient_evidence"}
            answer = agent.run("synthesis", payload(state), [])
            answer = answer.strip()
            if answer.startswith("```json") and answer.endswith("```"):
                answer = answer[7:-3].strip()
            try:
                diagnosis = Diagnosis.model_validate_json(answer)
            except ValueError:
                logger.emit("invalid_synthesis", reason="schema_validation_failed")
                return {"diagnosis": None, "status": "insufficient_evidence"}
            if diagnosis.conclusion == "insufficient_evidence":
                logger.emit("insufficient_evidence", reason="model_abstained")
                return {"diagnosis": None, "status": "insufficient_evidence"}
            if not validate_diagnosis(diagnosis, tools):
                logger.emit("invalid_synthesis", reason="unregistered_or_unread_citation")
                return {"diagnosis": None, "status": "insufficient_evidence"}
            original_patch = diagnosis.proposed_patch
            diagnosis.proposed_patch, audit = check_patch(
                root, original_patch, set(diagnosis.affected_files)
            )
            logger.emit("patch_check", **audit)
            write_json(directory / "patch-check.json", audit)
            if original_patch:
                write_json(directory / "candidate-patch.json", {"proposed_patch": original_patch})
            if original_patch and not diagnosis.proposed_patch:
                diagnosis.limitations.append(
                    f"Candidate patch was withheld: applicability check status {audit['status']}."
                )
            return {"diagnosis": diagnosis.model_dump(), "status": "diagnosed"}

        graph = StateGraph(State)
        graph.add_node("router", route)
        graph.add_node("code_search", search)
        graph.add_node("test_runner", test)
        graph.add_node("synthesis", synthesize)
        graph.add_edge(START, "router")
        graph.add_conditional_edges(
            "router",
            lambda s: s["next_agent"],
            {role: role for role in ["code_search", "test_runner", "synthesis"]},
        )
        graph.add_edge("code_search", "router")
        graph.add_edge("test_runner", "router")
        graph.add_edge("synthesis", END)
        state = graph.compile().invoke(
            {
                "search_passes": 0,
                "test_attempted": False,
                "next_agent": "",
                "findings": [],
                "routes": [],
                "diagnosis": None,
                "status": "insufficient_evidence",
            },
            config={"recursion_limit": 20},
        )
        response = DebugResponse(
            run_id=run_id,
            mode=settings.mode,
            status=state["status"],
            diagnosis=state["diagnosis"],
            evidence=tools.evidence,
            routes=state["routes"],
            test_status=tools.test_status,
        )
    except Exception as error:
        logger.emit("run_error", error_type=type(error).__name__, message=redact(str(error))[:300])
        response = DebugResponse(
            run_id=run_id,
            mode=settings.mode,
            status="failed",
            evidence=tools.evidence,
            test_status=tools.test_status,
            error=f"{type(error).__name__}: see local run events for details",
        )
    logger.emit(
        "run_end",
        status=response.status,
        tool_calls=tools.calls,
        test_status=response.test_status,
        patch_verified=False,
    )
    write_json(directory / "response.json", response.model_dump())
    return response
