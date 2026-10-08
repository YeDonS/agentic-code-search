import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from rank_bm25 import BM25Okapi

from code_assistant.config import Settings
from code_assistant.models import Evidence
from code_assistant.telemetry import RunLogger, redact

EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".cache",
    "runs",
    "dist",
    "build",
    "gold",
    ".pytest_cache",
    ".ruff_cache",
}
SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".c",
    ".h",
    ".cpp",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
}
STOPWORDS = set(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "to",
        "of",
        "for",
        "in",
        "on",
        "at",
        "and",
        "or",
        "with",
        "from",
        "this",
        "that",
        "it",
        "as",
        "by",
        "not",
        "do",
        "does",
        "have",
        "has",
        "had",
        "if",
        "can",
        "when",
        "using",
        "use",
        "should",
        "would",
        "but",
        "i",
        "we",
        "you",
        "error",
        "issue",
        "bug",
        "return",
        "returns",
        "expected",
        "actual",
    ]
)


def tokenize(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]{1,80}", text.lower())
    return [
        part
        for token in tokens
        for part in [token, *token.split("_")]
        if part not in STOPWORDS and len(part) > 1
    ]


def safe_file(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or any(part.startswith(".") or part in EXCLUDED for part in path.parts):
        raise ValueError("hidden, excluded, or absolute paths are not allowed")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("file is outside the repository or does not exist")
    if resolved.suffix not in SUFFIXES or resolved.stat().st_size > 500_000:
        raise ValueError("file type or size is outside the source-reading policy")
    return resolved


class RepositoryIndex:
    """Bounded source index built only from the current checkout, without Git history."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.documents: list[tuple[str, str, list[str]]] = []
        self.truncated = False
        total_bytes = 0
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(
                d
                for d in dirs
                if not d.startswith(".")
                and d not in EXCLUDED
                and not (Path(directory) / d).is_symlink()
            )
            for name in sorted(names):
                path = Path(directory) / name
                if name.startswith(".") or path.is_symlink() or path.suffix not in SUFFIXES:
                    continue
                if path.stat().st_size > 500_000:
                    continue
                if len(self.documents) >= 20000 or total_bytes + path.stat().st_size > 80_000_000:
                    self.truncated = True
                    break
                try:
                    content = path.read_text(encoding="utf-8")
                except (UnicodeError, OSError):
                    continue
                if "\x00" in content:
                    continue
                relative = path.relative_to(self.root).as_posix()
                tokens = tokenize(relative) * 3 + tokenize(content)
                if tokens:
                    self.documents.append((relative, content, tokens))
                    total_bytes += path.stat().st_size
            if self.truncated:
                break
        self.bm25 = BM25Okapi([d[2] for d in self.documents]) if self.documents else None

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not 1 <= limit <= 10 or not 1 <= len(query) <= 2000:
            raise ValueError("query must be 1–2000 characters and limit 1–10")
        tokens = tokenize(query)
        if not tokens or self.bm25 is None:
            return []
        scores = self.bm25.get_scores(tokens)
        query_set = set(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: float(scores[i]), reverse=True)
        hits = []
        for index in ranked:
            path, content, document_tokens = self.documents[index]
            if not query_set.intersection(document_tokens):
                continue
            lines = content.splitlines()
            if not lines:
                continue
            best = max(
                range(len(lines)), key=lambda j: len(query_set.intersection(tokenize(lines[j])))
            )
            start, end = max(0, best - 3), min(len(lines), best + 8)
            score = float(scores[index])
            hits.append(
                {
                    "path": path,
                    "start_line": start + 1,
                    "end_line": end,
                    "text": "\n".join(lines[start:end])[:3000],
                    "score": round(score, 5) if math.isfinite(score) else 0,
                }
            )
            if len(hits) == limit:
                break
        return hits


def test_targets(root: Path, targets: list[str]) -> list[str]:
    if not 1 <= len(targets) <= 5:
        raise ValueError("select 1–5 explicit test files or test node IDs")
    for target in targets:
        if len(target) > 300 or target.startswith("-") or any(c in target for c in "\n\r\x00"):
            raise ValueError("invalid test target")
        filename, *nodes = target.split("::")
        path = safe_file(root, filename)
        if path.suffix != ".py" or not (
            path.name.startswith("test_") or path.name.endswith("_test.py")
        ):
            raise ValueError("only explicit Python test files are accepted")
        if any(not re.fullmatch(r"[A-Za-z0-9_\[\].\-]+", node) for node in nodes):
            raise ValueError("invalid pytest node ID")
    return targets


def execute_tests(root: Path, targets: list[str], settings: Settings) -> dict[str, Any]:
    targets = test_targets(root, targets)
    if settings.test_executor == "disabled":
        raise ValueError("test execution is disabled; opt in for a trusted repository")
    pytest_args = ["-m", "pytest", "-q", "-p", "no:cacheprovider", *targets]
    with tempfile.TemporaryDirectory(prefix="code-assistant-test-") as temp:
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": temp,
            "TMPDIR": temp,
            "LANG": "C.UTF-8",
            "PYTHONPATH": str(root),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
        if settings.test_executor == "docker":
            command = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "128",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "--user",
                "65532:65532",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "--mount",
                f"type=bind,src={root},dst=/workspace,readonly",
                "--workdir",
                "/workspace",
                "--env",
                "PYTHONPATH=/workspace",
                "--env",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
                "--env",
                "PYTHONDONTWRITEBYTECODE=1",
                "--cidfile",
                str(Path(temp) / "container-id"),
                settings.test_image,
                "python",
                *pytest_args,
            ]
        else:
            command = [sys.executable, *pytest_args]
        start = time.monotonic()
        status = "completed"
        output_path = Path(temp) / "output.txt"
        with output_path.open("w+b") as output:
            process = subprocess.Popen(
                command,
                cwd=root,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                while process.poll() is None:
                    if time.monotonic() - start > settings.test_timeout:
                        status = "timeout"
                        break
                    if output_path.stat().st_size > 2_000_000:
                        status = "output_limit"
                        break
                    time.sleep(0.05)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                # Killing a docker client does not stop its container; explicitly remove it.
                cid_path = Path(temp) / "container-id"
                if settings.test_executor == "docker" and cid_path.exists():
                    cid = cid_path.read_text().strip()
                    if re.fullmatch(r"[0-9a-f]{64}", cid):
                        subprocess.run(
                            ["docker", "rm", "-f", cid],
                            capture_output=True,
                            timeout=10,
                            check=False,
                        )
            output.seek(0)
            text = output.read(16000).decode("utf-8", errors="replace")
        return {
            "exit_code": process.returncode,
            "status": status,
            "duration_ms": round((time.monotonic() - start) * 1000),
            "output": redact(text),
            "output_truncated": output_path.stat().st_size > 16000,
            "targets": targets,
            "executor": settings.test_executor,
        }


class RepositoryTools:
    def __init__(self, root: Path, settings: Settings, logger: RunLogger):
        self.root, self.settings, self.logger = root.resolve(), settings, logger
        self.index = RepositoryIndex(self.root)
        self.evidence: list[Evidence] = []
        self.test_runs: dict[str, dict[str, Any]] = {}
        self.calls = 0
        self.test_status = "not_run"
        self.logger.emit(
            "index_ready", files=len(self.index.documents), truncated=self.index.truncated
        )

    def add_evidence(self, kind: str, text: str, **fields: Any) -> Evidence:
        # Restored ledgers may have non-contiguous IDs. Never overwrite a citation.
        next_id = (
            max((int(e.id[1:]) for e in self.evidence if re.fullmatch(r"e\d+", e.id)), default=0)
            + 1
        )
        evidence = Evidence(id=f"e{next_id:04d}", kind=kind, text=redact(text), **fields)
        self.evidence.append(evidence)
        return evidence

    def _call(self, name: str, function: Any, **arguments: Any) -> str:
        start = time.monotonic()
        if self.calls >= self.settings.max_tool_calls:
            self.logger.emit("tool_budget_exhausted", tool=name)
            return json.dumps({"error": "tool budget exhausted"})
        self.calls += 1
        self.logger.emit("tool_start", tool=name, tool_call=self.calls)
        try:
            if self.calls > self.settings.max_tool_calls:
                raise ValueError("tool budget exhausted")
            result = function(**arguments)
            self.logger.emit(
                "tool_end",
                tool=name,
                outcome="ok",
                tool_call=self.calls,
                duration_ms=round((time.monotonic() - start) * 1000),
                evidence_count=len(self.evidence),
            )
            return json.dumps(result, ensure_ascii=False)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            self.logger.emit(
                "tool_end",
                tool=name,
                outcome="error",
                tool_call=self.calls,
                error_type=type(error).__name__,
                message=str(error)[:300],
                duration_ms=round((time.monotonic() - start) * 1000),
            )
            return json.dumps({"error": redact(str(error))[:300]})

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        results = []
        for hit in self.index.search(query, limit):
            score = hit.pop("score")
            evidence = self.add_evidence("search", **hit)
            results.append({**evidence.model_dump(), "score": score})
        self.logger.emit("search_result", hit_count=len(results), empty=not results)
        return {"hits": results, "index_truncated": self.index.truncated}

    def read(self, path: str, start_line: int = 1, end_line: int = 80) -> dict[str, Any]:
        if start_line < 1 or end_line < start_line or end_line - start_line >= 120:
            raise ValueError("read a valid range of at most 120 lines")
        file = safe_file(self.root, path)
        lines = file.read_text(encoding="utf-8").splitlines()
        if start_line > len(lines):
            raise ValueError("start_line is beyond the end of the file")
        end_line = min(end_line, len(lines))
        return self.add_evidence(
            "source",
            "\n".join(lines[start_line - 1 : end_line])[:10000],
            path=path,
            start_line=start_line,
            end_line=end_line,
        ).model_dump()

    def run_tests(self, targets: list[str]) -> dict[str, Any]:
        run_id = f"test-{len(self.test_runs) + 1}"
        result = execute_tests(self.root, targets, self.settings)
        self.test_runs[run_id] = result
        if result["status"] != "completed":
            self.test_status = result["status"]
        elif result["exit_code"] == 0:
            self.test_status = "baseline_passed"
        elif result["exit_code"] == 1:
            self.test_status = "baseline_failed"
        else:
            self.test_status = "environment_error"
        evidence = self.add_evidence("test", json.dumps(result, ensure_ascii=False)[:10000])
        self.logger.emit(
            "test_result",
            test_run_id=run_id,
            status=self.test_status,
            exit_code=result["exit_code"],
            duration_ms=result["duration_ms"],
            output_truncated=result["output_truncated"],
        )
        return {**result, "test_run_id": run_id, "evidence_id": evidence.id}

    def logs(self, test_run_id: str) -> dict[str, Any]:
        if test_run_id not in self.test_runs:
            raise ValueError("unknown test run; only this request's test output is available")
        return self.add_evidence("log", self.test_runs[test_run_id]["output"][:10000]).model_dump()

    def for_agent(self, role: str) -> list[Any]:
        @tool
        def search_repository(query: str, limit: int = 5) -> str:
            """Search the current source snapshot with BM25. Returns cited snippets and line numbers."""
            return self._call("search_repository", self.search, query=query, limit=limit)

        @tool
        def read_file(path: str, start_line: int = 1, end_line: int = 80) -> str:
            """Read up to 120 lines from a relative source path and register the evidence."""
            return self._call(
                "read_file", self.read, path=path, start_line=start_line, end_line=end_line
            )

        @tool
        def run_tests(targets: list[str]) -> str:
            """Run explicitly selected pytest files or node IDs. Never accepts a shell command."""
            return self._call("run_tests", self.run_tests, targets=targets)

        @tool
        def inspect_logs(test_run_id: str) -> str:
            """Read the output of a test run from this request; no arbitrary log paths."""
            return self._call("inspect_logs", self.logs, test_run_id=test_run_id)

        if role == "code_search":
            return [search_repository, read_file]
        if role == "test_runner":
            return [read_file, run_tests, inspect_logs]
        if role in {"synthesis", "patch_repair"}:
            return [read_file]
        if role == "single_agent":
            return [search_repository, read_file] + (
                [run_tests, inspect_logs] if self.settings.test_executor != "disabled" else []
            )
        return []
