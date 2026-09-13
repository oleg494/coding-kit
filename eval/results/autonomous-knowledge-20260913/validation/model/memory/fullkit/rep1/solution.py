"""Incident routing: pure, deterministic policy-rule selection.

Selects one response action for an incident from policy rules contributed by
repository authorities (approved contracts/runbooks) and memory records
(persisted notes/decisions/drafts), applying supersession, topic filtering,
fact matching, and the tier/date/priority tiebreak order from the spec.
"""

from functools import cmp_to_key


def _matches(when, facts):
    """True when every key of `when` is present in `facts` with an equal value.

    A missing fact key never matches. An empty `when` matches vacuously.
    """
    for key, expected in when.items():
        if key not in facts or facts[key] != expected:
            return False
    return True


def route(repository, memory):
    """Return {"action": str, "evidence": [str], "retrieved": [str]}.

    Pure: no I/O, no mutation of arguments, fully deterministic.
    """
    topic = repository["topic"]
    facts = repository.get("facts") or {}
    authorities = repository.get("authorities") or []

    # Supersession: only repository authorities can supersede, and only
    # memory records are excluded by it (entirely: rules and "retrieved").
    superseded = set()
    for authority in authorities:
        for superseded_id in authority.get("supersedes") or []:
            superseded.add(superseded_id)

    # Collect sources: (source_id, date, tier, rules).
    # Tiers: 2 approved authority, 1 approved memory, 0 unapproved either.
    sources = []
    for authority in authorities:
        tier = 2 if authority.get("approved") else 0
        sources.append(
            (authority["id"], authority.get("date", ""), tier,
             authority.get("rules") or [])
        )
    for record in memory:
        if record["id"] in superseded:
            continue
        tier = 1 if record.get("approved") else 0
        sources.append(
            (record["id"], record.get("date", ""), tier,
             record.get("rules") or [])
        )

    # "retrieved": remaining memory records (input order) holding at least
    # one rule on the topic — regardless of approval or fact matching.
    retrieved = [
        record["id"]
        for record in memory
        if record["id"] not in superseded
        and any(rule.get("topic") == topic
                for rule in (record.get("rules") or []))
    ]

    # Candidates: topic-matching rules whose "when" condition matches facts.
    # (fallback, tier, date, priority, source_id, rule_index, action)
    candidates = []
    for source_id, date, tier, rules in sources:
        for rule_index, rule in enumerate(rules):
            if rule.get("topic") != topic:
                continue
            if not _matches(rule.get("when") or {}, facts):
                continue
            candidates.append((
                bool(rule.get("fallback", False)),
                tier,
                date,
                rule.get("priority", 0),
                source_id,
                rule_index,
                rule["action"],
            ))

    if not candidates:
        return {
            "action": repository.get("default_action", "request_policy"),
            "evidence": [repository["id"]],
            "retrieved": retrieved,
        }

    def _better(a, b):
        # Best-first comparator: negative when a ranks before b.
        if a[0] != b[0]:
            return -1 if not a[0] else 1      # non-fallback before fallback
        if a[1] != b[1]:
            return b[1] - a[1]                # higher tier first
        if a[2] != b[2]:
            return 1 if a[2] < b[2] else -1   # newer ISO date first
        if a[3] != b[3]:
            return b[3] - a[3]                # higher priority first
        if a[4] != b[4]:
            return -1 if a[4] < b[4] else 1   # smaller source id first
        return a[5] - b[5]                    # smaller rule index first

    winner = sorted(candidates, key=cmp_to_key(_better))[0]
    return {
        "action": winner[6],
        "evidence": [winner[4]],
        "retrieved": retrieved,
    }
