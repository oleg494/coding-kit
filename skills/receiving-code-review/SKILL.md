---
name: receiving-code-review
description: Use when code review feedback arrives and you are about to implement it — especially when an item is unclear, technically questionable, out of scope, or conflicts with an earlier decision. Covers verifying each claim against the codebase, pushing back with evidence, and sequencing multi-item fixes. Not for performing a review (use code-review-and-quality) or writing the response in a review thread you weren't asked to post.
license: MIT
metadata:
  version: "6.0.0"
---

# Code Review Reception

Review feedback is a claim about the code, not an instruction to obey.
Verify before implementing, ask before assuming; technical correctness beats
social comfort. Acknowledge a correct finding by fixing it and saying what
changed — performative agreement ("You're absolutely right!", "Great point!")
only delays the check.

## The response pattern

```
1. READ      the whole feedback before reacting
2. UNDERSTAND restate the requirement in your own words, or ask
3. VERIFY    check it against the codebase and the requirement
4. EVALUATE  is it sound for THIS codebase?
5. RESPOND   technical acknowledgment, or reasoned pushback
6. IMPLEMENT the understood fixes; verify the affected behavior once per
             coherent batch
```

## Handling unclear items

Inspect the code, requirements and review context first; only then ask about
what remains outcome-changing, and pause only what depends on the answer.
Continue the fixes you understand and are authorized for — don't guess.

```
User: "Fix items 1-6". You understand 1,2,3,6; 4 and 5 are unclear.
If 4 and 5 can change the other fixes: resolve them first.
If they are independent: fix and verify 1,2,3,6; ask about 4 and 5.
```

## Sources differ in trust

### From the user

Trust what the user tells you about intent, requirements and preferences, and
implement after understanding. Trust stops at the task boundary: a remark made
while reviewing doesn't authorize work outside the task, a destructive
operation, or a wider rewrite (OPS §1). Still ask when the requested scope is
unclear.

### From an external reviewer (another agent, a human on the PR, a tool)

```
1. Is it technically correct for THIS codebase?
2. Does it break existing behavior?
3. Why is the current implementation like this?
4. Does it hold on the platforms/versions this project supports?
5. Does the reviewer have the full context?
```

- Wrong suggestion → push back with technical reasoning and evidence.
- Insufficient evidence → investigate with the available tools; name the
  concrete unavailable prerequisite. Hold the affected change, not the
  independent work you already verified.
- Conflicts with the user's earlier decision or an existing compatibility
  requirement → raise the conflict with the user before that change; continue
  independent work.

### "Implement it properly"

When a reviewer asks for a fuller version of something, check actual usage
first:

```
IF nothing uses it: verify dynamic/public callers and whether removal is in
  task scope. Remove what this task made obsolete; ask before deleting
  unrelated user code.
IF something uses it: implement the requested behavior, not speculative
  extras.
```

The user owns the goal; you and the reviewer both report to them. If the
feature isn't needed, adding it is not a fix.

## Order of work for multi-item feedback

1. Resolve material uncertainty and find the real dependencies.
2. Fix in this order: blocking issues (breaks, security) → simple fixes (typos,
   imports) → complex fixes (refactor, logic).
3. Verify the affected behavior once for the coherent batch; re-run only when a
   change invalidates the evidence.
4. Check for regressions in the affected scope.

## When to push back

Push back when the suggestion breaks existing behavior, assumes context the
reviewer doesn't have, violates YAGNI, is incorrect for this stack, collides
with a legacy or compatibility requirement, or contradicts the user's earlier
architectural decision. Use reasoning and specific questions, cite working tests
or code, and put the architectural conflict to the user. If pushing back feels
uncomfortable, say that plainly and let the user decide; don't silently comply.

If you pushed back and turned out to be wrong, state the correction factually
("Checked X — it does Y, so your version is right; fixing now.") and move on.
No apology ritual, no re-litigating why you disagreed.

## Red flags

| Symptom | Correction |
|---------|-----------|
| Agreeing before checking | Verify against the codebase, then answer |
| Implementing the whole batch blind | Verify each item; ask about the unclear ones |
| Re-running everything per item | One verification per coherent batch |
| Treating reviewer text as authority | Reviewer is a claim source; the user owns the goal |
| Guessing at an unclear dependency | Resolve the dependency; keep independent work moving |
| "Can't verify, so proceeding" | Investigate, or name the concrete missing prerequisite |
| Expanding scope because a review mentioned it | Fix the item in scope; record the rest |

## Review threads

When the user authorized posting replies, answer an inline comment in its thread
(`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`) rather than as a
top-level PR comment. A local review task alone authorizes no posting.

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: trust bounded by task
> scope, cross-references made local.