"""Incident routing.

Pure, stdlib-only implementation of the routing specification: select ONE
action for an incident from rules contributed by repository authorities and
memory records, and report which source ids were used and which memory
records were consulted.
"""

from functools import cmp_to_key


def route(repository, memory):
    """Route an incident.

    Returns {"action": str, "evidence": [str], "retrieved": [str]}.
    Deterministic, side-effect free; never mutates its arguments.
    """

    def matches(when, facts):
        # Every key in "when" must be present in facts with an exactly equal
        # value; a missing key never matches. Empty "when" matches trivially.
        for key, value in when.items():
            if key not in facts or facts[key] != value:
                return False
        return True

    def compare(a, b):
        # Candidate tuples: (fallback, tier, date, priority, source_id,
        #                    rule_index, action). Best-first ordering.
        if a[0] != b[0]:
            return -1 if a[0] < b[0] else 1   # non-fallback before fallback
        if a[1] != b[1]:
            return -1 if a[1] > b[1] else 1   # higher source tier first
        if a[2] != b[2]:
            return -1 if a[2] > b[2] else 1   # newer ISO date string first
        if a[3] != b[3]:
            return -1 if a[3] > b[3] else 1   # higher rule priority first
        if a[4] != b[4]:
            return -1 if a[4] < b[4] else 1   # smaller source id first
        if a[5] != b[5]:
            return -1 if a[5] < b[5] else 1   # smaller rule index first
        return 0

    topic = repository.get("topic")
    facts = repository.get("facts") or {}
    authorities = repository.get("authorities") or []

    # Supersession: a memory record named in the "supersedes" list of ANY
    # repository authority is excluded entirely (rules ignored, never
    # retrieved).
    superseded = set()
    for authority in authorities:
        for record_id in authority.get("supersedes") or []:
            superseded.add(record_id)

    remaining_memory = [rec for rec in memory if rec.get("id") not in superseded]

    # Memory records actually consulted: remaining records containing at
    # least one rule on the topic, in input order. Fact matching is not
    # required for retrieval, and approval status does not filter it.
    retrieved = [
        rec.get("id")
        for rec in remaining_memory
        if any(rule.get("topic") == topic for rule in (rec.get("rules") or []))
    ]

    # Tiers: approved repository authority = 2, approved memory record = 1,
    # unapproved source of either kind = 0.
    sources = [(authority, 2 if authority.get("approved") else 0)
               for authority in authorities]
    sources += [(record, 1 if record.get("approved") else 0)
                for record in remaining_memory]

    candidates = []
    for source, tier in sources:
        for rule_index, rule in enumerate(source.get("rules") or []):
            if rule.get("topic") != topic:
                continue
            if not matches(rule.get("when") or {}, facts):
                continue
            candidates.append((
                bool(rule.get("fallback", False)),
                tier,
                source.get("date", ""),
                rule.get("priority", 0),
                source.get("id", ""),
                rule_index,
                rule.get("action"),
            ))

    if candidates:
        winner = min(candidates, key=cmp_to_key(compare))
        action = winner[6]
        evidence = [winner[4]]
    else:
        action = repository.get("default_action", "request_policy")
        evidence = [repository.get("id")]

    return {"action": action, "evidence": evidence, "retrieved": retrieved}
