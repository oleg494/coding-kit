---
name: code-review-and-quality
description: Use when performing a code review — your own, another agent's, or a human's — or dispatching an independent reviewer at a merge boundary or before a major change lands. Covers scope (diff vs whole-system), five review axes, severity counts, the recomputable verdict. Not for received feedback (use receiving-code-review), blast-radius/rename graphs (use code-graph-review), or an adversarial audit of a finished-work claim (use fable-judge).
license: MIT
metadata:
  version: "6.0.0"
---

# Code Review and Quality

Review answers two questions: does this change meet its requirements, and does
it leave the code healthier. Use the same axes whether you are reviewing
someone else's work or arranging a review of your own.

**Approval standard:** approve when the change definitely improves overall code
health, even if it isn't perfect. Don't block because it isn't how you would
have written it.

## Scope: diff-review vs whole-system audit

State the scope before reporting, because it decides what counts as a finding.

- **Diff-review (default for a PR, branch or task gate):** changed lines and
  their direct blast radius. Apply the exclusions below to unchanged code.
- **Whole-system audit (security, architecture, repository audit):** system-wide
  invariants across the codebase, not limited by the diff boundary.

## What not to flag in diff-review

Noise buries real findings. In diff-review scope, don't report:

- Theoretical risks with no exploit path in this change's reality.
- Defense-in-depth when the primary control already suffices.
- Unrelated pre-existing issues. An unchanged caller does come into scope when
  this change makes it fail: the affected path, not line ownership, sets scope.
- "Consider library X" — a review is not the place to add dependencies.

## Severity: three values

- **critical** — blocks merge: real bug, broken contract, fraud.
- **warning** — material finding that should be resolved; alone it doesn't
  block unless the accumulated quality threshold says so.
- **suggestion** — optional improvement; never blocks.

## Report format: counts and a recomputable verdict

End every review with the counts and the verdict derived from them. The verdict
is arithmetic, not a mood; `fable-judge` carries the full adversarial semantics.

```
counts: critical: N | warning: N | suggestion: N
verdict: <VERIFIED | VERIFIED WITH CAVEATS | REFUTED>
```

```
verdict_from_counts(0, 0) == "VERIFIED"
verdict_from_counts(0, 2) == "VERIFIED"
verdict_from_counts(0, 3) == "VERIFIED WITH CAVEATS"
verdict_from_counts(0, 0, unverified=1) == "VERIFIED WITH CAVEATS"
verdict_from_counts(1, 4) == "REFUTED"
```

`critical > 0` → REFUTED; else any unjudged material claim or `warning > 2` →
VERIFIED WITH CAVEATS; else VERIFIED. A clean report with two warnings is an
approval. Name the requirements or paths you could not judge and why; an
unexamined path is not an approval.

## The five axes

### 1. Correctness
- Does it match the spec or task requirements?
- Are edge cases handled (null, empty, boundary values)?
- Are error paths handled, not just the happy path?
- Do the tests pass, and do they test the right thing?
- For reachable inputs the spec doesn't mention, judge against the stated
  contract and reasonable consumer expectations: spec silence doesn't excuse a
  crash. That is not license for speculative features or unrelated hardening.

### 2. Readability and simplicity
- Are names descriptive and consistent with project conventions?
- Is the control flow straightforward?
- Could this be fewer lines? (1000 lines where 100 do the job is a failure)
- Are abstractions earning their complexity? (Don't generalize until the third
  use case.)
- Dead artifacts: no-op variables, compatibility shims, `// removed` comments.

### 3. Architecture
- Does it follow existing patterns, or introduce a new one? If new, is that
  justified?
- Are module boundaries clean, dependencies flowing in one direction?
- Is duplicated code that should be shared?
- Does this refactor reduce complexity or just relocate it?

### 4. Security
- Is input validated and sanitized?
- Are secrets kept out of code, logs and version control?
- Are authentication and authorization checked where needed?
- Are queries parameterized and outputs encoded for their sink?

### 5. Performance
- N+1 query patterns?
- Unbounded loops or unconstrained data fetching?
- Synchronous work that should be async?
- Missing pagination on list endpoints?

## Change sizing (heuristics, not gates)

Rough review-cost signals for one logical change; overrides come from the repo,
the reviewer's capacity and how coupled the parts are.

```
~100 lines changed   → reviewable in one sitting
~300 lines changed   → acceptable for a single logical change
~1000 lines changed  → split before review
```

## Review process

1. **Understand the context** — what is this change trying to accomplish?
2. **Read the tests first** — they reveal intent and coverage.
3. **Walk the implementation** through the five axes.
4. **Categorize** each finding as critical / warning / suggestion.
5. **Verify the verification** — what actually ran, on which state.

## Requesting an independent review

Independent review is worth it when a merge or approval boundary requires
signoff, when evidence has stalled, when a complex defect persists, or when the
change has a consequential trust or compatibility boundary. For parallel work,
review each contribution and the integrated behavior; one integrated review may
cover coupled tasks, so don't require a fresh blocking review after every worker
or microstep. For a small bounded change, proportionate inline review suffices
unless the host, the user or the merge policy requires independent signoff.

Follow the host's delegation rules and use its real reviewer name and
capabilities; a skill cannot create a missing reviewer, and requesting a review
authorizes no commit, push or merge (OPS §1).

**The brief.** The reviewer needs the work product and its constraints, not the
whole session transcript:

- **Goal:** requested behavior, acceptance criteria, explicit non-goals.
- **Scope:** diff-review or whole-system audit, changed files, coupled
  interfaces, relevant source context.
- **Compared states:** the real baseline and candidate. For uncommitted work
  hand over the working-tree diff or before/after snapshots; never invent SHAs
  or create commits to fill a template.
- **Evidence:** commands and observed results, checked state, reproduction
  steps, known gaps. A dry run is not a behavior result.
- **Output:** findings with severity, file/line, contract impact and supporting
  evidence, closing with the counts and verdict above.

In a diff-review, ask the reviewer to suppress hypothetical or unrelated
findings; whole-system audits keep their broader invariant scope.

**When no reviewer exists** (no subagent, no second model, no human available):
finish the reachable implementation and verification, do the axes pass
yourself, and report that independent signoff was unavailable. Don't claim
signoff you didn't get, and don't cross a boundary that requires it.

## Acting on findings

- Check every finding against the actual contract and source; push back with
  evidence when it is wrong (see `receiving-code-review`).
- Repair material in-scope defects and verify the repair. A suggestion doesn't
  become a blocker or a new requirement.
- Resolve outcome-changing ambiguity before dependent changes; continue with
  independent authorized fixes meanwhile.
- Keep your execution tracking separate from reviewer-owned approval. Reuse
  valid evidence, but re-check or re-review when a change invalidates it.
- Report remaining material gaps. Don't silently approve, fabricate a review, or
  tick the reviewer's checkboxes yourself.

## Dead code hygiene

After a refactor, check for orphaned code:

1. Verify no remaining callers, including dynamic dispatch and public entry
   points.
2. In an authorized implementation task, remove what the task made obsolete.
3. Ask before deleting unrelated user code; a review-only task reports findings
   without editing.

## Dependency discipline

Before adding a dependency: does the existing stack already solve it (often it
does), how large is it, is it maintained, does it have known vulnerabilities,
what is its license? Prefer the standard library and existing utilities.

---

> Source: obra/superpowers (MIT), absorbing the former
> `requesting-code-review` skill. Adapted for coding-kit: host-aware review
> dispatch and coherent change boundaries.