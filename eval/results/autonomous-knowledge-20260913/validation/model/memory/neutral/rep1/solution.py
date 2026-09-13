"""Incident routing.

Pure routing of an incident to a single response action, selected from rules
supplied by repository authorities and memory records, applying supersession,
source tiering, and deterministic tie-breaking. Standard library only.
"""

import functools

__all__ = ["route"]


def route(repository, memory):
    """Resolve one action for an incident.

    Returns {"action": str, "evidence": [str], "retrieved": [str]}.
    Pure: performs no I/O and never mutates its arguments.
    """
    topic = repository.get("topic")
    facts = repository.get("facts") or {}
    authorities = list(repository.get("authorities") or [])
    memory_records = list(memory or [])

    # Step 2: supersession -- a memory record named in the "supersedes" list of
    # ANY repository authority is excluded entirely (rules ignored, never
    # reported as retrieved). Authorities themselves are never excluded.
    superseded = set()
    for authority in authorities:
        for superseded_id in authority.get("supersedes") or []:
            superseded.add(superseded_id)
    remaining_memory = [
        record for record in memory_records if record.get("id") not in superseded
    ]

    # Step 3: retrieved -- ids, in input order, of remaining memory records that
    # own at least one rule on the incident topic (regardless of applicability).
    retrieved = []
    for record in remaining_memory:
        for rule in record.get("rules") or []:
            if rule.get("topic") == topic:
                retrieved.append(record.get("id"))
                break

    # Step 4: collect candidate rules from all remaining sources.
    def source_tier(source, is_authority):
        if not source.get("approved"):
            return 0
        return 2 if is_authority else 1

    def condition_matches(when):
        # Every key in "when" must be present in facts with an exactly equal
        # value (== on JSON scalars); a missing key never matches.
        for key, expected in (when or {}).items():
            if key not in facts or facts[key] != expected:
                return False
        return True

    candidates = []
    sources = [(authority, True) for authority in authorities]
    sources += [(record, False) for record in remaining_memory]
    for sequence, (source, is_authority) in enumerate(sources):
        tier = source_tier(source, is_authority)
        date = source.get("date", "")
        source_id = source.get("id")
        for rule_index, rule in enumerate(source.get("rules") or []):
            if rule.get("topic") != topic:
                continue
            if not condition_matches(rule.get("when")):
                continue
            priority = rule.get("priority")
            if priority is None:
                priority = 0
            candidates.append(
                {
                    "source_id": source_id,
                    "date": date,
                    "tier": tier,
                    "priority": priority,
                    "fallback": bool(rule.get("fallback", False)),
                    "rule_index": rule_index,
                    "sequence": sequence,
                    "action": rule.get("action"),
                }
            )

    # Steps 5 & 6: rank best-first and resolve.
    def best_first(left, right):
        # Negative when `left` ranks better than `right`.
        if left["fallback"] != right["fallback"]:
            return -1 if not left["fallback"] else 1  # (a) non-fallback first
        if left["tier"] != right["tier"]:
            return right["tier"] - left["tier"]  # (b) higher tier first
        if left["date"] != right["date"]:
            return 1 if left["date"] < right["date"] else -1  # (c) newer first
        if left["priority"] != right["priority"]:
            return right["priority"] - left["priority"]  # (d) higher priority
        if left["source_id"] != right["source_id"]:
            return -1 if left["source_id"] < right["source_id"] else 1  # (e)
        if left["rule_index"] != right["rule_index"]:
            return left["rule_index"] - right["rule_index"]
        return left["sequence"] - right["sequence"]  # stable final tiebreak

    if candidates:
        winner = min(candidates, key=functools.cmp_to_key(best_first))
        action = winner["action"]
        evidence = [winner["source_id"]]
    else:
        default_action = repository.get("default_action")
        if default_action is None:
            default_action = "request_policy"
        action = default_action
        evidence = [repository.get("id")]

    return {"action": action, "evidence": evidence, "retrieved": retrieved}
