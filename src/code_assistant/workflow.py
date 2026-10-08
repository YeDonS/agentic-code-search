import uuid
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from code_assistant.agents import ToolCallingAgent, get_model
from code_assistant.config import DEMO_ISSUE, DEMO_REPO, Settings
from code_assistant.context import select_evidence
from code_assistant.models import DebugResponse, Diagnosis, RouteDecision
from code_assistant.patches import check_patch, patch_paths
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
    try:
        creations = {new for old, new in patch_paths(diagnosis.proposed_patch) if old is None}
    except ValueError:
        creations = set()
    return bool(
        sources
        and diagnosis.affected_files
        and set(diagnosis.affected_files).issubset(source_paths | creations)
    )


def parse_diagnosis(answer: str) -> Diagnosis:
    answer = answer.strip()
    if answer.startswith("```json") and answer.endswith("```"):
        answer = answer[7:-3].strip()
    return Diagnosis.model_validate_json(answer)


def check_and_repair_patch(
    diagnosis: Diagnosis,
    tools: RepositoryTools,
    agent: ToolCallingAgent,
    directory: Path,
    context: dict[str, Any],
) -> Diagnosis:
    """Bounded, pre-evaluation format repair; never receives gold or test outcomes."""
    original = diagnosis.proposed_patch
    candidate = original
    checked, audit = check_patch(tools.root, candidate, set(diagnosis.affected_files))
    attempts = [{"candidate": candidate, "audit": audit}]
    tools.logger.emit("patch_check", attempt=0, **audit)
    for attempt in range(1, tools.settings.patch_repair_attempts + 1):
        if audit["status"] != "invalid" or agent.calls >= tools.settings.max_model_calls:
            break
        tools.logger.emit("patch_repair_start", attempt=attempt)
        answer = agent.run(
            "patch_repair",
            {
                **context,
                "evidence": [
                    e.model_dump()
                    for e in select_evidence(
                        tools.evidence,
                        tools.settings.evidence_limit,
                        tools.settings.evidence_policy,
                    )
                ],
                "diagnosis": {**diagnosis.model_dump(), "proposed_patch": candidate},
                "apply_error": audit["error"],
                "attempt": attempt,
            },
            tools.for_agent("patch_repair"),
        )
        try:
            repaired = parse_diagnosis(answer)
        except ValueError:
            tools.logger.emit("patch_repair_invalid_response", attempt=attempt)
            attempts.append({"candidate": None, "audit": {"status": "invalid_response"}})
            continue
        candidate = repaired.proposed_patch
        # Repair cannot silently change the diagnosis or its declared file scope.
        checked, audit = check_patch(tools.root, candidate, set(diagnosis.affected_files))
        attempts.append({"candidate": candidate, "audit": audit})
        tools.logger.emit("patch_check", attempt=attempt, **audit)
    diagnosis.proposed_patch = checked
    summary = {
        **audit,
        "initial_status": attempts[0]["audit"]["status"],
        "repair_attempts": len(attempts) - 1,
        "recovered": attempts[0]["audit"]["status"] == "invalid" and bool(checked),
    }
    write_json(directory / "patch-check.json", summary)
    write_json(directory / "patch-attempts.json", attempts)
    if original:
        write_json(directory / "candidate-patch.json", {"proposed_patch": original})
    if original and not checked:
        diagnosis.limitations.append(
            f"Candidate patch was withheld: applicability check status {audit['status']}."
        )
    return diagnosis


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
    logger.emit(
        "run_start",
        mode=settings.mode,
        test_executor=settings.test_executor,
        workflow=settings.workflow,
    )
    tools = RepositoryTools(root, settings, logger)

    def payload(state: State) -> dict[str, Any]:
        selected = select_evidence(
            tools.evidence, settings.evidence_limit, settings.evidence_policy
        )
        logger.emit(
            "evidence_selection",
            recipient=state["next_agent"] if settings.workflow == "routed" else "single_agent",
            policy=settings.evidence_policy,
            available=len(tools.evidence),
            selected_ids=[e.id for e in selected],
            available_source=sum(e.kind == "source" for e in tools.evidence),
            selected_source=sum(e.kind == "source" for e in selected),
        )
        return {
            "issue": issue,
            "findings": state["findings"][-4:],
            "evidence": [e.model_dump() for e in selected],
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
            finding = agent.run(
                "code_search",
                payload(state),
                tools.for_agent("code_search"),
                reserve_calls=min(3, settings.max_model_calls - 1),
            )
            return {
                "search_passes": state["search_passes"] + 1,
                "findings": [*state["findings"], finding],
            }

        def test(state: State) -> dict[str, Any]:
            finding = agent.run(
                "test_runner", payload(state), tools.for_agent("test_runner"), reserve_calls=1
            )
            return {"test_attempted": True, "findings": [*state["findings"], finding]}

        def finish(answer: str, state: State) -> dict[str, Any]:
            if not any(e.kind == "source" for e in tools.evidence):
                logger.emit("insufficient_evidence", reason="no_source_read")
                return {"diagnosis": None, "status": "insufficient_evidence"}
            try:
                diagnosis = parse_diagnosis(answer)
            except ValueError:
                logger.emit("invalid_synthesis", reason="schema_validation_failed")
                return {"diagnosis": None, "status": "insufficient_evidence"}
            if diagnosis.conclusion == "insufficient_evidence":
                logger.emit("insufficient_evidence", reason="model_abstained")
                return {"diagnosis": None, "status": "insufficient_evidence"}
            if not validate_diagnosis(diagnosis, tools):
                logger.emit("invalid_synthesis", reason="unregistered_or_unread_citation")
                return {"diagnosis": None, "status": "insufficient_evidence"}
            diagnosis = check_and_repair_patch(diagnosis, tools, agent, directory, payload(state))
            return {"diagnosis": diagnosis.model_dump(), "status": "diagnosed"}

        def synthesize(state: State) -> dict[str, Any]:
            answer = agent.run("synthesis", payload(state), tools.for_agent("synthesis"))
            return finish(answer, state)

        def single(state: State) -> dict[str, Any]:
            logger.emit("route", agent="single_agent", reason="single_conversation_baseline")
            answer = agent.run("single_agent", payload(state), tools.for_agent("single_agent"))
            return {
                **finish(answer, state),
                "routes": [{"agent": "single_agent", "reason": "single_conversation_baseline"}],
            }

        graph = StateGraph(State)
        graph.add_node("router", route)
        graph.add_node("code_search", search)
        graph.add_node("test_runner", test)
        graph.add_node("synthesis", synthesize)
        graph.add_node("single_agent", single)
        graph.add_edge(START, "single_agent" if settings.workflow == "single" else "router")
        graph.add_conditional_edges(
            "router",
            lambda s: s["next_agent"],
            {role: role for role in ["code_search", "test_runner", "synthesis"]},
        )
        graph.add_edge("code_search", "router")
        graph.add_edge("test_runner", "router")
        graph.add_edge("synthesis", END)
        graph.add_edge("single_agent", END)
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
        model_calls=agent.calls if "agent" in locals() else 0,
        test_status=response.test_status,
        patch_verified=False,
    )
    write_json(directory / "response.json", response.model_dump())
    return response
