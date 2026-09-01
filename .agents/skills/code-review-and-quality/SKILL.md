---
name: code-review-and-quality
description: Conducts multi-axis code review. Use before merging any change. Use when reviewing code written by yourself, another agent, or a human. Use when you need to assess code quality across multiple dimensions before it enters the main branch.
metadata:
  version: "4.0.0"
---

## Overview

Multi-dimensional code review with quality gates. Five axes: correctness, readability, architecture, security, and performance.

**The approval standard:** Approve a change when it definitely improves overall code health, even if it isn't perfect. Perfect code doesn't exist. Don't block a change because it isn't exactly how you would have written it.

## What NOT to Flag

Review noise buries real findings. Never report:

- Theoretical risks — no exploit path in THIS change's reality.
- Defense-in-depth when the primary control suffices.
- Issues in unchanged code (lines outside the diff).
- "Consider library X" — no new-dependency suggestions in review.

## Severity: 3 Values

- **critical** — blocks merge: real bug, broken contract, fraud.
- **warning** — must fix before proceeding; alone not merge-blocking.
- **suggestion** — optional improvement; never blocks.

## Report Format (machine-checkable counts)

End every review with the counts; the verdict is recomputed from them
(`verdict_from_counts` — see fable-judge):

```
counts: critical: N | warning: N | suggestion: N
verdict: <VERIFIED | VERIFIED WITH CAVEATS | REFUTED>
```

## The Five-Axis Review

### 1. Correctness
- Does it match the spec or task requirements?
- Are edge cases handled (null, empty, boundary values)?
- Are error paths handled (not just the happy path)?
- Does it pass all tests? Are the tests actually testing the right things?

### 2. Readability & Simplicity
- Are names descriptive and consistent with project conventions?
- Is the control flow straightforward?
- Could this be done in fewer lines? (1000 lines where 100 suffice is a failure)
- Are abstractions earning their complexity? (Don't generalize until the third use case)
- Are there dead code artifacts: no-op variables, backwards-compat shims, or `// removed` comments?

### 3. Architecture
- Does it follow existing patterns or introduce a new one? If new, is it justified?
- Does it maintain clean module boundaries?
- Is there code duplication that should be shared?
- Are dependencies flowing in the right direction (no circular dependencies)?
- Does this refactor reduce complexity or just relocate it?

### 4. Security
- Is user input validated and sanitized?
- Are secrets kept out of code, logs, and version control?
- Is authentication/authorization checked where needed?
- Are SQL queries parameterized?
- Are outputs encoded to prevent XSS?

### 5. Performance
- Any N+1 query patterns?
- Any unbounded loops or unconstrained data fetching?
- Any synchronous operations that should be async?
- Any missing pagination on list endpoints?

## Change Sizing

```
~100 lines changed   → Good. Reviewable in one sitting.
~300 lines changed   → Acceptable if it's a single logical change.
~1000 lines changed  → Too large. Split it.
```

## Review Process

1. **Understand the Context** — What is this change trying to accomplish?
2. **Review the Tests First** — Tests reveal intent and coverage.
3. **Review the Implementation** — Walk through with five axes.
4. **Categorize Findings** — critical / warning / suggestion (3 values only).
5. **Verify the Verification** — What tests were run? Did the build pass?

## Dead Code Hygiene

After any refactoring, check for orphaned code:
1. Identify code that is now unreachable or unused
2. List it explicitly
3. **Ask before deleting:** "Should I remove these now-unused elements: [list]?"

## Dependency Discipline

Before adding any dependency:
1. Does the existing stack solve this? (Often it does.)
2. How large is the dependency? (Check bundle impact.)
3. Is it actively maintained?
4. Does it have known vulnerabilities?
5. What's the license?

**Rule:** Prefer standard library and existing utilities over new dependencies.