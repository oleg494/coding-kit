"""Faulty control: overrides current authority.

Pure date-first ranking: the newest source wins regardless of approval tier
or fallback marking. Fails the conflicting-current-authority case (an
unapproved draft outranks the approved contract) and the
repository-sufficient control (a newer fallback memory rule beats the
non-fallback contract rule), while passing stale-decision only by accident
of the dates.
"""


def route(repository, memory):
    """Newest-source-wins routing; approval and fallback ignored."""
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
    for record, _tier in sources:
        for index, rule in enumerate(record["rules"]):
            if rule["topic"] != topic:
                continue
            if any(key not in facts or facts[key] != value
                   for key, value in rule["when"].items()):
                continue
            candidates.append(((record["date"], record["id"], index),
                               record["id"], rule["action"]))
    if candidates:
        _, source_id, action = max(candidates, key=lambda item: item[0])
        return {"action": action, "evidence": [source_id],
                "retrieved": retrieved}
    return {"action": repository.get("default_action", "request_policy"),
            "evidence": [repository["id"]], "retrieved": retrieved}
