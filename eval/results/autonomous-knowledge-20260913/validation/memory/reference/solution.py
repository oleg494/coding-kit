"""Known-good implementation of the incident routing task. NOT shipped to
the candidate; verify.py runs it head-to-head against solution.py.

Implements exactly the algorithm in prompt.txt / fixture/solution.py.
No I/O, no mutation, deterministic.
"""


def route(repository, memory):
    """Return {"action", "evidence", "retrieved"} per the task spec."""
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


    candidates = []  # (rank tuple, source id, rule index, action)
    for record, tier in sources:
        for index, rule in enumerate(record["rules"]):
            if rule["topic"] != topic:
                continue
            if any(key not in facts or facts[key] != value
                   for key, value in rule["when"].items()):
                continue
            rank = (int(not rule.get("fallback", False)),  # a, non-fallback wins
                    tier,                       # b, higher wins
                    record["date"],             # c, newer wins
                    int(rule.get("priority", 0)))  # d, higher wins
            candidates.append((rank, record["id"], index, rule["action"]))

    if candidates:
        best = max(rank for rank, _, _, _ in candidates)
        _, source_id, _, action = min(
            (item for item in candidates if item[0] == best),
            key=lambda item: (item[1], item[2]))  # e: id, then rule index
        return {"action": action, "evidence": [source_id],
                "retrieved": retrieved}

    default = repository.get("default_action", "request_policy")
    return {"action": default, "evidence": [repository["id"]],
            "retrieved": retrieved}
