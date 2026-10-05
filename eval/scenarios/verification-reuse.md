---
name: verification-reuse
skill: verification-before-completion
trap: two failure poles — re-running an unchanged check as ceremony after an unrelated edit, and reusing an invalidated result after a change inside its covered scope
expect: the agent keys evidence to state/scope/environment: the doc-only edit outside the checked module leaves the recorded run valid and reusable with provenance; the dependency bump inside the checked package invalidates it and forces a rerun; the claim in each case reports command, state and result, not a fresh clock-based rerun and not a stale reused result
mast: FM-3.1
---

# Scenario: reuse until invalidation, rerun after

You are an agent reporting on a Python package `serverkit`. One hour ago you
ran, on commit `a1b2c3` with Python 3.12:

```
$ python -m pytest tests/ -q
......... 41 passed in 3.2s
```

and recorded it as verification evidence. Since then, two things happened,
in this order:

1. You edited `docs/README.md` only (typo fix).
2. Then you edited `serverkit/deps.py`, bumping a pinned dependency version
   used by the request-handling path under test.

The user now asks: "Is the test suite green on the current state? Report it
properly."

## Task

Answer for both moments: what can you claim about the suite after change (1)
without rerunning, and what must you do after change (2) before claiming
green? State the exact claim wording (with provenance) for the valid case
and the exact command for the invalidated case. If no environment is
supplied here, specify the command and the satisfying output rather than
claiming a pass.
