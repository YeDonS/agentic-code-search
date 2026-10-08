from code_assistant.context import select_evidence
from code_assistant.models import Evidence


def item(i, kind="search", **kwargs):
    return Evidence(id=f"e{i}", kind=kind, text=f"observation {i}", **kwargs)


def test_search_burst_cannot_evict_read_source_or_test_output():
    evidence = [item(0, "source", path="bug.py"), item(1, "test")]
    evidence += [item(i) for i in range(2, 32)]
    assert all(e.kind == "search" for e in select_evidence(evidence, 24, "recent"))
    selected = select_evidence(evidence, 24, "source_priority")
    assert len(selected) == 24
    assert selected[:2] == evidence[:2]
    assert selected[-1] == evidence[-1]


def test_duplicate_reads_do_not_fill_window_but_latest_id_is_preserved():
    old = item(0, "source", path="bug.py", start_line=1, end_line=5)
    duplicate = old.model_copy(update={"id": "new"})
    evidence = [old, item(1, "source", path="caller.py"), duplicate]
    assert [e.id for e in select_evidence(evidence, 2, "source_priority")] == ["e1", "new"]
    assert evidence[0] == old  # Full ledger remains available for citation validation.
