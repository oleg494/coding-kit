"""Starter stub for the incident routing task. Replace the body of route().

SPEC (identical to prompt.txt)
-----------------------------
def route(repository, memory): pure function, stdlib only, no I/O, no
mutation of arguments, deterministic.

repository: {"id": str, "topic": str, "facts": dict, "authorities": list,
             optional "default_action": str}
authority / memory record: {"id": str, "date": "YYYY-MM-DD",
                            "approved": bool, "supersedes": [str],
                            "rules": [rule]}
rule: {"topic": str, "when": dict, "action": str, optional "priority": int,
       optional "fallback": bool}

Source tiers: approved repository authority = 2, approved memory record = 1,
unapproved source of either kind = 0.

Algorithm:
1. Collect rule sources: every authority and every memory record.
2. Supersession: a memory record whose "id" appears in the "supersedes" list
   of any repository authority is excluded entirely (rules ignored, never
   listed in "retrieved").
3. "retrieved": ids, in input order, of the remaining memory records with at
   least one rule whose topic equals repository["topic"].
4. Candidates: topic-matching rules from remaining sources whose "when"
   mapping matches "facts" exactly (every key present with an equal value).
5. Rank best-first: non-fallback before fallback; higher tier; newer date;
   higher priority; smaller source id; smaller rule index.
6. Winner: {"action": rule action, "evidence": [source id]}. No candidate:
   {"action": default_action or "request_policy",
    "evidence": [repository["id"]]}.

Return: {"action": str, "evidence": [str], "retrieved": [str]}.
"""


def route(repository, memory):
    """Select one incident response action. See module docstring."""
    raise NotImplementedError("implement route per the spec in this docstring")
