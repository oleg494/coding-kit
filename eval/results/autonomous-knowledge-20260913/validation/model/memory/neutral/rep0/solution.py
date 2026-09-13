"""Incident routing.

``route`` selects exactly one response action for an incident by ranking the
applicable rules found in repository authorities (tier 2), approved memory
records (tier 1) and unapproved sources of either kind (tier 0).  Memory
records superseded by any repository authority are excluded entirely.

The function is pure: no I/O, no mutation of its arguments, deterministic
output.  Only the Python standard library is used.
"""

from functools import cmp_to_key


def _rules_of(source):
    """Return the source's "rules" list; treat missing/None as empty."""
    rules = source.get("rules")
    return rules if isinstance(rules, list) else []


def _supersedes_of(source):
    """Return the source's "supersedes" list; treat missing/None as empty."""
    ids = source.get("supersedes")
    return ids if isinstance(ids, list) else []


def _when_matches(when, facts):
    """True when every key of ``when`` occurs in ``facts`` with an equal value.

    A missing key never matches.  An empty ``when`` matches vacuously.
    """
    for key, expected in when.items():
        if key not in facts:
            return False
        if facts[key] != expected:
            return False
    return True


def _rank_before(a, b):
    """Comparator: negative when candidate ``a`` ranks better than ``b``."""
    # (a) non-fallback rules before fallback rules
    if a["fallback"] != b["fallback"]:
        return 1 if a["fallback"] else -1
    # (b) higher source tier first
    if a["tier"] != b["tier"]:
        return b["tier"] - a["tier"]
    # (c) newer source date first ("YYYY-MM-DD" strings compare chronologically)
    if a["date"] != b["date"]:
        return 1 if a["date"] < b["date"] else -1
    # (d) higher rule priority first
    if a["priority"] != b["priority"]:
        return b["priority"] - a["priority"]
    # (e) smaller source id first, then smaller rule index within the source
    if a["source_id"] != b["source_id"]:
        return -1 if a["source_id"] < b["source_id"] else 1
    return a["rule_index"] - b["rule_index"]


def route(repository, memory):
    """Route one incident to a single action.

    Returns {"action": str, "evidence": [str], "retrieved": [str]} where
    "retrieved" lists, in input order, the ids of memory records that were
    actually consulted (not superseded, carrying at least one on-topic rule).
    """
    topic = repository.get("topic")
    facts = repository.get("facts") or {}
    authorities = repository.get("authorities") or []
    memory_records = memory or []

    # Step 2: ids of memory records superseded by ANY repository authority.
    # (Memory records' own "supersedes" lists do not exclude anything.)
    superseded = set()
    for authority in authorities:
        for record_id in _supersedes_of(authority):
            superseded.add(record_id)

    # Step 3: remaining memory records carrying at least one on-topic rule.
    retrieved = []
    for record in memory_records:
        if record.get("id") in superseded:
            continue
        if any(rule.get("topic") == topic for rule in _rules_of(record)):
            retrieved.append(record.get("id"))

    # Step 4: applicable rules from all remaining sources.
    # Tier 2 = approved repository authority, 1 = approved memory record,
    # 0 = unapproved source of either kind.
    tiered_sources = [(2 if source.get("approved") else 0, source)
                      for source in authorities]
    tiered_sources += [(1 if source.get("approved") else 0, source)
                       for source in memory_records
                       if source.get("id") not in superseded]

    candidates = []
    for tier, source in tiered_sources:
        source_id = source.get("id")
        source_date = source.get("date") or ""
        for rule_index, rule in enumerate(_rules_of(source)):
            if rule.get("topic") != topic:
                continue
            when = rule.get("when") or {}
            if not _when_matches(when, facts):
                continue
            priority = rule.get("priority")
            if priority is None:
                priority = 0
            candidates.append({
                "fallback": bool(rule.get("fallback", False)),
                "tier": tier,
                "date": source_date,
                "priority": priority,
                "source_id": source_id,
                "rule_index": rule_index,
                "action": rule.get("action"),
            })

    # Step 5: best-first ordering.
    candidates.sort(key=cmp_to_key(_rank_before))

    # Step 6: winner, else the repository default action.
    if candidates:
        winner = candidates[0]
        return {
            "action": winner["action"],
            "evidence": [winner["source_id"]],
            "retrieved": retrieved,
        }

    default_action = repository.get("default_action")
    if default_action is None:
        default_action = "request_policy"
    return {
        "action": default_action,
        "evidence": [repository.get("id")],
        "retrieved": retrieved,
    }
