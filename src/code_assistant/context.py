"""Select a bounded handoff context without discarding the full evidence ledger."""

from code_assistant.models import Evidence


def select_evidence(evidence: list[Evidence], limit: int, policy: str) -> list[Evidence]:
    if policy == "recent":
        return evidence[-limit:]
    if policy != "source_priority":
        raise ValueError("unknown evidence policy")
    # New search hits must not evict previously read source. Within each tier,
    # prefer recent, distinct observations; return them in their original order.
    tiers = {"source": 0, "test": 1, "log": 1, "search": 2}
    ranked = sorted(range(len(evidence)), key=lambda i: (tiers[evidence[i].kind], -i))
    selected, seen = [], set()
    for i in ranked:
        item = evidence[i]
        fingerprint = (item.kind, item.path, item.start_line, item.end_line, item.text)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        selected.append(i)
        if len(selected) == limit:
            break
    return [evidence[i] for i in sorted(selected)]
