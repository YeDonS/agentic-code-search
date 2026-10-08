import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SECRET_KEY = re.compile(r"key|token|secret|password|credential", re.I)


def redact(text: str) -> str:
    for name, value in os.environ.items():
        if SECRET_KEY.search(name) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    return re.sub(r"\b(?:sk-|gh[pousr]_)[A-Za-z0-9_\-]{12,}", "[REDACTED]", text)


class RunLogger:
    """One JSONL stream per run. Never logs prompts, source text, or model reasoning."""

    def __init__(self, directory: Path, run_id: str, issue_id: str | None = None):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "events.jsonl"
        self.run_id = run_id
        self.issue_id = issue_id
        self.lock = threading.Lock()

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "issue_id": self.issue_id,
            "event": event,
            **fields,
        }
        line = redact(json.dumps(record, ensure_ascii=False, default=str))
        with self.lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(line + "\n")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(redact(json.dumps(value, ensure_ascii=False, indent=2, default=str)) + "\n")
