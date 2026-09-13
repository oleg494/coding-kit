"""Deliberately faulty control: mutates its input arguments.

Behaviorally correct routing (this is the honest algorithm), but route()
writes into the repository facts dict it was given. The extra key does not
affect any rule match ("when" only inspects its own keys), so all case
checks pass and ONLY the no_input_mutation check fails — demonstrating the
verifier detects in-place mutation of passed arguments.
"""


def route(repository, memory):
    """Correct routing, but mutates repository["facts"] in place."""
    repository["facts"]["_audited_by_router"] = True  # the defect

    facts = repository["facts"]
    topic = repository["topic"]
    superseded = set()
    for authority in repository["authorities"]:
        superseded.update(authority.get("supersedes", ()))
    sources = [(authority, 2) for authority in repository["authorities"]]
    memory_sources = []
    for record in memory:
        if record["id"] not in superseded:
            entry = (record, 1 if record["approved"] else 0)
            sources.append(entry)
            memory_sources.append(entry)
    retrieved = [record["id"] for record, _ in memory_sources
                 if any(rule["topic"] == topic for rule in record["rules"])]
    candidates = []
    for record, tier in sources:
        for index, rule in enumerate(record["rules"]):
            if rule["topic"] != topic:
                continue
            if any(key not in facts or facts[key] != value
                   for key, value in rule["when"].items()):
                continue
            rank = (int(not rule.get("fallback", False)),
                    tier, record["date"], int(rule.get("priority", 0)))
            candidates.append((rank, record["id"], index, rule["action"]))
    if candidates:
        best = max(item[0] for item in candidates)
        _, source_id, _, action = min(
            (item for item in candidates if item[0] == best),
            key=lambda item: (item[1], item[2]))
        return {"action": action, "evidence": [source_id],
                "retrieved": retrieved}
    default = repository.get("default_action", "request_policy")
    return {"action": default, "evidence": [repository["id"]],
            "retrieved": retrieved}
