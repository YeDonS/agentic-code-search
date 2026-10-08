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


def test_unread_files_and_parent_paths_withheld(tmp_path):
    patch = "--- a/../secret.py\n+++ b/../secret.py\n@@ -1 +1 @@\n-old\n+new\n"
    assert check_patch(tmp_path, patch, {"../secret.py"})[1]["status"] == "unsafe_or_unread_paths"


def test_recount_handles_multiple_hunks_and_files():
    patch = "--- a/a.py\n+++ b/a.py\n@@ -1,9 +1,9 @@\n-a\n+b\n@@ -10,9 +10,9 @@\n x\n+y\n--- a/b.py\n+++ b/b.py\n@@ -1,9 +1,9 @@\n-a\n+b\n"
    result = recount_hunks(patch)
    assert result.count("@@ -1,1 +1,1 @@") == 2
    assert "@@ -10,1 +10,2 @@" in result
