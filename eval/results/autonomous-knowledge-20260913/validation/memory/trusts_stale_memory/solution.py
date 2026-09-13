"""Faulty control: trusts stale memory.

Ignores supersession entirely and ranks any memory record above every
repository authority. Fails the stale-decision case (routes emit_v1) and the
repository-sufficient control (steals evidence from the contract), while
accidentally passing the useful-hidden-decision case.
"""


def route(repository, memory):
    """Memory-first routing; supersession ignored."""
    facts = repository["facts"]
    topic = repository["topic"]
    sources = [(record, 3 if record["approved"] else 0) for record in memory]
    sources += [(authority, 2) for authority in repository["authorities"]]
    retrieved = [record["id"] for record, tier in sources
                 if tier in (1, 3)
                 and any(rule["topic"] == topic
                         for rule in record["rules"])]
    candidates = []
    for record, tier in sources:
        for index, rule in enumerate(record["rules"]):
            if rule["topic"] != topic:
                continue
            if any(key not in facts or facts[key] != value
                   for key, value in rule["when"].items()):
                continue
            rank = (int(not rule.get("fallback", False)), tier,
                    record["date"], int(rule.get("priority", 0)))
            candidates.append((rank, record["id"], index, rule["action"]))
    if candidates:
        best = max(item[0] for item in candidates)
        _, source_id, _, action = min(
            (item for item in candidates if item[0] == best),
            key=lambda item: (item[1], item[2]))
        return {"action": action, "evidence": [source_id],
                "retrieved": retrieved}
    return {"action": repository.get("default_action", "request_policy"),
            "evidence": [repository["id"]], "retrieved": retrieved}
