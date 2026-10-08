---
name: verification-before-completion
description: Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires applicable verification evidence (run when no valid evidence exists; valid prior evidence reusable for the unchanged state) before making any success claims; evidence before assertions always
license: MIT
metadata:
  version: "4.8.0"
---

# Verification Before Completion

## Overview

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT APPLICABLE VERIFICATION EVIDENCE
```

"Applicable" means evidence valid for the current checked state:
revision/snapshot, exact command, scope, environment, run timestamp.
Reuse existing evidence until an invalidation condition occurs (code
change, failure, or unresolved concern) and report that provenance instead
of treating the chat turn as a clock; a fresh invocation is required only
when no valid evidence for the checked state exists.
## The Gate Function

```
BEFORE claiming a verified result:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute that command completely when no applicable evidence exists
   for the current checked state — "complete" means no truncated or partial
   run of the check that proves THIS claim, not every check the repo has
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying. Reusing evidence that is still valid
for the checked state (same revision, no invalidating change/failure/concern)
is not skipping — but claiming without either is lying.
```

**Scope is part of honesty, in both directions.** Claiming a suite-wide
green you did not run is a lie; re-running an unchanged check with no new
changes, failures, or unresolved concerns is ceremony, not verification.
Broaden when scope warrants: shared code touched, or a failure the targeted
check exposed.

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures on checked state | Unchecked assumption, "should pass" |
| Linter clean | Linter output: 0 errors | Extrapolating to the claim's scope; a different check's output for that scope |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | Inspect changed artifacts and exercise the claimed behavior | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags - Investigate Before Claiming Success

- Presenting "should", "probably" or "seems to" as proof, rather than explicitly labeled uncertainty
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Extrapolating a partial check to the full claimed scope without narrowing the claim
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves only its own scope: narrow the claim to it, or run the full check |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
PASS: Use applicable before-fix failure evidence, then exercise the same behavior after the fix. For a regression-test claim, establish that the test detects the defect, using an isolated pre-fix copy if needed; never revert the user's tree.
If before-fix evidence is unavailable, report that limitation and the narrower after-fix observation. Do not claim a demonstrated red-green regression.
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
PASS: Agent reports success -> inspect the changed artifacts -> verify the claimed behavior -> report actual state
❌ Trust agent report
```

## When To Apply

Apply before a completion or correctness claim, commit, PR or integration.
Planning, delegation and a task transition do not themselves require running
unrelated checks. Reuse evidence only while it covers the checked state;
an independent judge may rerun it to establish independent observation.
Calibrated uncertainty is valid reporting, never a substitute for proof.

**Unavailable ≠ passed ≠ failed.** When the primary check cannot run
(service down, environment missing), report it as unavailable. An
alternative check substitutes only if it actually proves the same contract;
if it proves less, explicitly narrow the claim to what it does prove and
report the required check as unavailable — never report the original claim
as verified. Do not retry the same dead service in a loop.

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: cross-references made local.