import json
from collections import Counter
from pathlib import Path
from typing import Any


def summarize_events(directory: Path) -> dict[str, Any]:
    paths = sorted(directory.rglob("events.jsonl"))
    events = [
        json.loads(line) for path in paths for line in path.read_text().splitlines() if line.strip()
    ]
    counts = Counter(event["event"] for event in events)
    durations = [e["duration_ms"] for e in events if e["event"] == "tool_end"]
    return {
        "trace_files": len(paths),
        "event_counts": dict(counts),
        "route_reasons": dict(Counter(e["reason"] for e in events if e["event"] == "route")),
        "failure_patterns": {
            "empty_search": sum(
                e["event"] == "search_result" and e.get("empty", False) for e in events
            ),
            "tool_error": sum(
                e["event"] == "tool_end" and e.get("outcome") == "error" for e in events
            ),
            "environment_error": sum(
                e["event"] == "test_result" and e.get("status") == "environment_error"
                for e in events
            ),
            "test_timeout": sum(
                e["event"] == "test_result" and e.get("status") == "timeout" for e in events
            ),
            "index_truncated": sum(
                e["event"] == "index_ready" and e.get("truncated", False) for e in events
            ),
            "invalid_synthesis": counts["invalid_synthesis"],
            "agent_step_limit": counts["agent_step_limit"],
            "run_error": counts["run_error"],
            "model_budget_exhausted": counts["model_budget_exhausted"],
            "tool_budget_exhausted": counts["tool_budget_exhausted"],
            "patch_repair_invalid_response": counts["patch_repair_invalid_response"],
        },
        "tool_duration_ms_raw": durations,
        "unpaired_tools": counts["tool_start"] - counts["tool_end"],
        "unfinished_runs": counts["run_start"] - counts["run_end"],
    }
