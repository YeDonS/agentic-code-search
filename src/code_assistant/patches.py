"""Check candidate patch applicability without executing or editing repository code."""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

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
            if body.startswith(("@@ ", "diff --git ", "--- a/", "+++ b/")):
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


def check_patch(root: Path, patch: str, allowed_files: set[str]) -> tuple[str, dict[str, Any]]:
    """Return the checked patch and an audit record. Applicability is NOT test success."""
    audit: dict[str, Any] = {
        "status": "empty",
        "original_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        "hunks_recounted": False,
        "functional_tests_run": False,
    }
    if not patch.strip():
        return "", audit
    if len(patch.encode()) > 500_000 or "GIT binary patch" in patch:
        audit["status"] = "invalid"
        return "", audit
    paths = re.findall(r"^(?:--- a/|\+\+\+ b/)([^\n]+)$", patch, re.M)
    if not paths or any(
        path not in allowed_files
        or Path(path).is_absolute()
        or ".." in Path(path).parts
        or "\\" in path
        or not (root / path).is_file()
        or (root / path).is_symlink()
        or not (root / path).resolve().is_relative_to(root.resolve())
        for path in paths
    ):
        audit["status"] = "unsafe_or_unread_paths"
        return "", audit
    if not shutil.which("git"):
        audit["status"] = "git_unavailable"
        return "", audit
    normalized = recount_hunks(patch)
    audit["hunks_recounted"] = normalized != patch
    audit["submitted_sha256"] = hashlib.sha256(normalized.encode()).hexdigest()
    try:
        # A copy avoids Git's subdirectory filtering and never touches the checkout.
        with tempfile.TemporaryDirectory(prefix="code-assistant-patch-check-") as temporary:
            check_root = Path(temporary)
            for path in set(paths):
                target = check_root / path
                target.parent.mkdir(parents=True, exist_ok=True)
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
    except (OSError, subprocess.TimeoutExpired):
        audit["status"] = "check_error"
        return "", audit
    audit["status"] = "applies" if result.returncode == 0 else "invalid"
    return (normalized if result.returncode == 0 else ""), audit
