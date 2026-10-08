"""Check candidate patch applicability without executing or editing repository code."""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from code_assistant.telemetry import redact

HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")


def recount_hunks(patch: str) -> str:
    """Repair only mechanical hunk lengths; preserve every context and changed line."""
    lines = patch.splitlines()
    for index, line in enumerate(lines):
        match = HUNK.fullmatch(line)
        if not match:
            continue
        old = new = 0
        for body in lines[index + 1 :]:
            if body.startswith(
                ("@@ ", "diff --git ", "--- a/", "+++ b/", "--- /dev/null", "+++ /dev/null")
            ):
                break
            if body.startswith(" "):
                old += 1
                new += 1
            elif body.startswith("-"):
                old += 1
            elif body.startswith("+"):
                new += 1
            elif body.startswith("\\ No newline at end of file"):
                continue
            else:
                break
        lines[index] = f"@@ -{match[1]},{old} +{match[2]},{new} @@{match[3]}"
    return "\n".join(lines) + "\n"


def patch_paths(patch: str) -> list[tuple[str | None, str | None]]:
    """Accept ordinary text modifications, creations and deletions, never renames/modes."""
    if re.search(
        r"^(?:rename |copy |old mode |new mode |deleted file mode (?!100644)|new file mode (?!100644))",
        patch,
        re.M,
    ):
        raise ValueError("renames, copies and special file modes are not supported")
    if re.search(r"^index .* (?:120000|160000)$", patch, re.M):
        raise ValueError("symlink and gitlink index modes are not supported")
    lines = patch.splitlines()
    pairs = []
    for i, line in enumerate(lines):
        if not line.startswith("--- "):
            continue
        if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
            raise ValueError("unpaired unified diff headers")
        old, new = line[4:], lines[i + 1][4:]
        if old != "/dev/null" and not old.startswith("a/"):
            raise ValueError("old header must use a/ or /dev/null")
        if new != "/dev/null" and not new.startswith("b/"):
            raise ValueError("new header must use b/ or /dev/null")
        pair = (None if old == "/dev/null" else old[2:], None if new == "/dev/null" else new[2:])
        if not any(pair) or (all(pair) and pair[0] != pair[1]):
            raise ValueError("empty paths and renames are not supported")
        pairs.append(pair)
    if not pairs or len({old or new for old, new in pairs}) != len(pairs):
        raise ValueError("missing or duplicate file headers")
    # Git metadata must describe exactly the same paths as the authoritative headers.
    metadata = re.findall(r"^diff --git a/(\S+) b/(\S+)$", patch, re.M)
    if patch.count("diff --git ") != len(metadata):
        raise ValueError("unsupported git path quoting")
    if metadata and metadata != [(old or new, new or old) for old, new in pairs]:
        raise ValueError("git and unified diff paths disagree")
    return pairs


def check_patch(root: Path, patch: str, allowed_files: set[str]) -> tuple[str, dict[str, Any]]:
    """Return the checked patch and an audit record. Applicability is NOT test success."""
    root = root.resolve()
    audit: dict[str, Any] = {
        "status": "empty",
        "original_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        "hunks_recounted": False,
        "functional_tests_run": False,
        "error": None,
    }
    if not patch.strip():
        return "", audit
    if len(patch.encode()) > 500_000 or "GIT binary patch" in patch:
        audit["status"] = "invalid"
        audit["error"] = "patch exceeds size limit or contains binary data"
        return "", audit
    try:
        pairs = patch_paths(patch)
    except ValueError as error:
        audit.update(status="invalid", error=str(error))
        return "", audit
    paths = {old or new for old, new in pairs}
    if any(
        path not in allowed_files
        or Path(path).is_absolute()
        or any(part.startswith(".") for part in Path(path).parts)
        or "\\" in path
        or any(c in path for c in "\x00\t\r")
        or (root / path).is_symlink()
        or not (root / path).resolve().is_relative_to(root.resolve())
        or any(
            (root / Path(*Path(path).parts[:i])).is_symlink()
            or (
                (root / Path(*Path(path).parts[:i])).exists()
                and not (root / Path(*Path(path).parts[:i])).is_dir()
            )
            for i in range(1, len(Path(path).parts))
        )
        for path in paths
    ):
        audit["status"] = "unsafe_or_unread_paths"
        audit["error"] = "patch path is undeclared, hidden, linked or outside the repository"
        return "", audit
    if any(
        (old is not None and not (root / old).is_file()) or (old is None and (root / new).exists())
        for old, new in pairs
    ):
        audit.update(
            status="invalid", error="patch creation/deletion headers do not match the snapshot"
        )
        return "", audit
    if not shutil.which("git"):
        audit["status"] = "git_unavailable"
        return "", audit
    normalized = recount_hunks(patch)
    audit["created_files"] = [new for old, new in pairs if old is None]
    audit["deleted_files"] = [old for old, new in pairs if new is None]
    audit["hunks_recounted"] = normalized != patch
    audit["submitted_sha256"] = hashlib.sha256(normalized.encode()).hexdigest()
    try:
        # A copy avoids Git's subdirectory filtering and never touches the checkout.
        with tempfile.TemporaryDirectory(prefix="code-assistant-patch-check-") as temporary:
            check_root = Path(temporary)
            for path in paths:
                target = check_root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                if (root / path).is_file():
                    shutil.copyfile(root / path, target)
            environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            environment.update(
                GIT_CEILING_DIRECTORIES=str(check_root.parent),
                GIT_CONFIG_NOSYSTEM="1",
                GIT_CONFIG_GLOBAL=os.devnull,
            )
            result = subprocess.run(
                ["git", "apply", "--check", "--whitespace=nowarn", "-"],
                input=normalized,
                text=True,
                cwd=check_root,
                capture_output=True,
                timeout=10,
                env=environment,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        audit["status"] = "check_error"
        audit["error"] = type(error).__name__
        return "", audit
    audit["status"] = "applies" if result.returncode == 0 else "invalid"
    if result.returncode:
        audit["error"] = redact(result.stderr.strip())[:3000] or "git apply check failed"
    return (normalized if result.returncode == 0 else ""), audit
