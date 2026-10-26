---
name: dead-flag
skill: testing-discipline
trap: a CLI flag was added and documented but never wired to the behavior it promises — nothing exercises it, the suite stays green, the contract lies
expect: the review treats the unwired flag as contract fraud: the parsed-but-unused argument is named as the root cause, and a red end-to-end test that proves the flag changes behavior (e.g. a fake executor capturing the timeout actually passed through) is required before the flag may ship
---

# Scenario: dead flag

You are reviewing a pull request. The task was: "trigger_eval.py needs a
--timeout flag — some executors hang, our budget is 120s per call."

## PR description

"Added --timeout (default 300s, per-call timeout seconds). Help text
updated. All tests pass."

## Diff

```python
# eval/trigger_eval.py
+    ap.add_argument("--timeout", type=int, default=TIMEOUT_DEFAULT,
+                    help="per-call timeout seconds")
     # ... run_query and the executor call are untouched:
     answer = run_prompt(cmd, prompt_for(q["query"]))
```

## CI log

```
39 passed, 1 skipped
```

## Task

Review verdict. Does this PR deliver what the task asked for? What single
check would have caught the problem before merge?
