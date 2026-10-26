---
name: verification-before-completion
description: 'Use before claiming work is complete, fixed, passing or ready to merge, and before committing or opening a PR: matching the evidence to the type of claim. Not for writing or choosing the checks themselves (use testing-discipline), for diagnosing a failure (use systematic-debugging), or for judging another agent completed work (use fable-judge).'
license: MIT
metadata:
  version: "6.0.0"
---

# verification-before-completion

This skill is the gate between finished work and the sentence "it works". The check happens before the claim, not after someone challenges it.

Completion claims without applicable verification evidence do not get made. Applicable means the evidence covers this claim, this state and this scope — see OPS §3 for what keeps evidence valid.

## The gate

1. **Name the claim precisely.** Which behavior, artifact or scope is claimed? "Tests pass" and "the suite passes on the merged tree" are different claims.
2. **Name the evidence that can establish it.** Use the table below; the claim and its evidence must be the same kind of thing.
3. **Check whether valid evidence already exists** for the current state. If it does, reuse it and cite its provenance rather than rerunning. If it does not, produce it.
4. **Read the actual output or observation.** Exit code, failure count, rendered result, probe response — not the command's success in general.
5. **Claim only what the evidence shows.** If it shows less than the claim, narrow the claim or report the gap. Both directions count: claiming a suite-wide green you did not run is dishonest, and rerunning an unchanged check with no new failure or concern is ceremony.

## Evidence by claim type

Many checks do not end in an exit code.

| Claim | Evidence | Not sufficient |
|-------|----------|----------------|
| Tests pass | Test run output with 0 failures on the current state | "should pass", a passing subset, a run from before the change |
| Build/compile succeeds | Build command exit 0 | Lint passing, logs that look fine |
| Lint or typecheck clean | That tool's output for the claimed scope | Another tool's clean result, extrapolation from one file |
| Bug fixed | The original symptom re-exercised and now behaving correctly | Code changed, "the fix is obvious" |
| Regression test works | Before-fix failure established, then the behavior re-exercised after | The test merely passing once |
| UI/behavior correct | An observed rendered flow, screenshot, or interactive session | Reading the component code |
| Deploy or service healthy | The consumer path probed, or an independent observer | "The command exited 0" |
| Documentation change | Reading the changed document, or a review of its diff | A passing test suite |
| Requirements met | A line-by-line pass over the request | Tests passing |
| An agent or subagent finished | Inspecting the changed artifacts and exercising the claim | The agent's own success report |

Delete the claim's doubt by checking the smallest observation that can falsify it, not by adding unrelated checks.

## When the evidence cannot be obtained

**Unavailable is not passed, and it is not a failed check either.** When the primary check cannot run — service down, environment missing, permission absent — report it as unavailable, name the prerequisite, and do not retry the same dead service in a loop.

A substitute check counts only if it proves the same contract. If it proves less, narrow the claim to what it does prove and report the required check as unavailable. A narrowed claim is honest; a promoted substitute is not.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "Should work now" | Run the check that proves it, or say it is unverified |
| "I'm confident" | Confidence is not evidence |
| "Just this once" | The exception is how false completion reports start |
| "Linter passed" | A linter does not compile, and its scope is not the build's |
| "Agent said success" | Verify independently; a report is claims, not evidence |
| "I'm tired / want this over" | Exhaustion is not evidence either |
| "Partial check is enough" | Then narrow the claim to that partial scope |
| "Different words, so the rule doesn't apply" | A softer phrasing of "done" is still a completion claim |
| "It passed earlier in this session" | Valid only if the state has not changed since; say which state it covered |
| "CI will catch it" | A future check is not evidence for a present claim |

## Red flags

Pause before the claim when you notice:

- "Should", "probably", "seems to" used as proof instead of a labeled uncertainty
- satisfaction language ("Done", "Perfect", "Great") before any check
- committing, pushing or opening a PR with no evidence for the final state
- trusting someone else's success report, including a subagent's
- extrapolating a partial result to the full claimed scope
- rationalizing that this case is special

## Visible evidence patterns

```
Tests:      [run command] [0 failures] → "These tests pass on this revision"
Build:      [run build] [exit 0]      → "The build succeeds"
Bug fix:    [reproduce before] [recheck after] → "The reported symptom no longer reproduces"
Requirements: re-read request → checklist → verify each → report gaps or completion
Delegation: agent reports success → inspect artifacts → exercise behavior → report actual state
```

State provenance when reusing evidence (which state, which command, which result) so a later reader can tell what was and was not observed. Calibrated uncertainty is a valid report; it is not a substitute for the check.

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: cross-references made local.