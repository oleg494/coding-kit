"""Faulty control: ignores hidden decision.

Drops every memory record before routing. Correct routing is impossible in
the useful-hidden-decision case, where memory is the only source holding the
residency constraint.
"""


def route(repository, memory):
    """Route using repository authorities only; memory is discarded."""
    return _route_repository_only(repository)


def _route_repository_only(repository):
    facts = repository["facts"]
    topic = repository["topic"]
    candidates = []
    for authority in repository["authorities"]:
        for index, rule in enumerate(authority["rules"]):
            if rule["topic"] != topic:
                continue
            if any(key not in facts or facts[key] != value
                   for key, value in rule["when"].items()):
                continue
            rank = (int(not rule.get("fallback", False)),
                    2, authority["date"], int(rule.get("priority", 0)))
            candidates.append((rank, authority["id"], index, rule["action"]))
    retrieved = []
    if candidates:
        best = max(item[0] for item in candidates)
        _, source_id, _, action = min(
            (item for item in candidates if item[0] == best),
            key=lambda item: (item[1], item[2]))
        return {"action": action, "evidence": [source_id],
                "retrieved": retrieved}
    return {"action": repository.get("default_action", "request_policy"),
            "evidence": [repository["id"]], "retrieved": retrieved}
