import pytest

from code_assistant.patches import check_patch, recount_hunks


def test_mechanical_recount_and_apply_check_do_not_modify_source(tmp_path):
    original = "def total(discount):\n    return discount or 10\n"
    (tmp_path / "billing.py").write_text(original)
    candidate = "--- a/billing.py\n+++ b/billing.py\n@@ -1,99 +1,99 @@\n def total(discount):\n-    return discount or 10\n+    return 10 if discount is None else discount\n"
    patch, audit = check_patch(tmp_path, candidate, {"billing.py"})
    assert audit["status"] == "applies"
    assert audit["hunks_recounted"]
    assert not audit["functional_tests_run"]
    assert "@@ -1,2 +1,2 @@" in patch
    assert (tmp_path / "billing.py").read_text() == original


def test_invalid_context_withheld(tmp_path):
    (tmp_path / "x.py").write_text("old = 1\n")
    patch, audit = check_patch(
        tmp_path, "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-missing = 0\n+new = 1\n", {"x.py"}
    )
    assert not patch
    assert audit["status"] == "invalid"
    assert "patch" in audit["error"] and "x.py" in audit["error"]


def test_unread_files_and_parent_paths_withheld(tmp_path):
    patch = "--- a/../secret.py\n+++ b/../secret.py\n@@ -1 +1 @@\n-old\n+new\n"
    assert check_patch(tmp_path, patch, {"../secret.py"})[1]["status"] == "unsafe_or_unread_paths"


def test_recount_handles_multiple_hunks_and_files():
    patch = "--- a/a.py\n+++ b/a.py\n@@ -1,9 +1,9 @@\n-a\n+b\n@@ -10,9 +10,9 @@\n x\n+y\n--- a/b.py\n+++ b/b.py\n@@ -1,9 +1,9 @@\n-a\n+b\n"
    result = recount_hunks(patch)
    assert result.count("@@ -1,1 +1,1 @@") == 2
    assert "@@ -10,1 +10,2 @@" in result


def test_create_delete_and_modify_in_one_patch_leave_snapshot_untouched(tmp_path):
    (tmp_path / "old.py").write_text("old = 1\n")
    (tmp_path / "keep.py").write_text("value = 1\n")
    patch = (
        "--- a/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old = 1\n"
        "--- /dev/null\n+++ b/new/helper.py\n@@ -0,0 +1 @@\n+new = 2\n"
        "--- a/keep.py\n+++ b/keep.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
    )
    checked, audit = check_patch(tmp_path, patch, {"old.py", "new/helper.py", "keep.py"})
    assert checked and audit["status"] == "applies"
    assert audit["created_files"] == ["new/helper.py"]
    assert audit["deleted_files"] == ["old.py"]
    assert (tmp_path / "old.py").read_text() == "old = 1\n"
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("path", ["../escape.py", "/tmp/escape.py", ".env", "new/../../escape.py"])
def test_new_file_cannot_escape_path_policy(tmp_path, path):
    patch = f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+value = 1\n"
    assert not check_patch(tmp_path, patch, {path})[0]


def test_new_file_cannot_follow_in_repository_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    patch = "--- /dev/null\n+++ b/linked/new.py\n@@ -0,0 +1 @@\n+value = 1\n"
    assert check_patch(tmp_path, patch, {"linked/new.py"})[1]["status"] == "unsafe_or_unread_paths"
    assert not (outside / "new.py").exists()


def test_disagreeing_git_headers_and_symlink_modes_are_rejected(tmp_path):
    patch = "diff --git a/escape.py b/escape.py\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+value = 1\n"
    assert not check_patch(tmp_path, patch, {"new.py", "escape.py"})[0]
    patch = "diff --git a/new.py b/new.py\nnew file mode 120000\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+/tmp/secret\n"
    assert not check_patch(tmp_path, patch, {"new.py"})[0]
