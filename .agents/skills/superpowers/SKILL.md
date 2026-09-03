---
name: superpowers
description: 'Always-on. The main development method: Plan → TDD → Implement → Verify → Report. Use for ANY non-trivial task. Do not write code without a plan and a test. Complex tasks (>3 files) → split into atomic tasks. Bug fix → Prove-It Pattern (reproduce with a test before the fix).'
license: MIT
metadata:
  version: "4.1.0"
---

# Superpowers — main development method

Always-on skill. Every non-trivial task goes through 5 phases.

## The Cycle

```
PLAN ──→ TDD ──→ IMPLEMENT ──→ VERIFY ──→ REPORT
  │        │         │            │          │
  ▼        ▼         ▼            ▼          ▼
Spec    Red test  Green code   Evidence    Outcome
first   first     minimal      observed    first
```

## Phase skills (obra accretion)

Kit v2: each phase has a granular skill helper. A phase is not replaced, but deepened:

- PLAN → `brainstorming` (design questions, spec), `writing-plans` (execution plan)
- IMPLEMENT → `dispatching-parallel-agents` (parallel slices), per-plan implementation with checkpoints
- VERIFY → `verification-before-completion` (fresh output), `requesting-code-review`, `fable-judge` (adversarial)
- Debug → `systematic-debugging`
- Git → `using-git-worktrees`, `finishing-a-development-branch`

## Phase 1: PLAN

**Formulate what "done" means — concrete, observable.**

- What should be true when the task is done?
- Which files do you touch? Which do you NOT touch?
- What assumptions do you make?
- Complex task (>3 files / >5 changes) → split into atomic tasks.

**Scope discipline:** touch only what the task requires. Not "I'll clean up along the way".

## Phase 2: TDD

**Red test → green code → refactoring.**

- No code without a failing test.
- Test = spec. Test name = rule: `test_payment_idempotent`, `test_referral_no_self`.
- A test verifies behavior, not implementation.

### Prove-It Pattern (bug fix)

```
Bug report → test reproducing the bug → test FAILS → fix → test GREEN
```

## Phase 3: IMPLEMENT

**Minimal change that makes the test green.**

- YAGNI: don't add anything beyond what the test requires.
- Style — as in the surrounding code. Don't refactor someone else's code without asking.
- DRY: duplicated in 3+ places? → shared source.

## Phase 4: VERIFY

**Evidence, not inference.**

- [ ] Test green? → observed.
- [ ] All existing tests green? → ran.
- [ ] Build not broken? → checked.
- [ ] Linter clean? → ran.
- [ ] Bug fix → TWINS: searched for the same pattern in the codebase.

### SDD contract gates (v3.9.0)

Three contract rules — not advice. Violating one invalidates the phase.

1. **Clarify before plan.** Spec ambiguous? Ask ≤5 targeted questions
   and fold every answer back into the spec — BEFORE any plan exists.
   A plan built on an unclarified spec is waste.
2. **Checklist sovereignty.** Reviewer-owned `- [ ]` markers in a plan
   or task list: the implementer NEVER toggles one. Counts unchecked,
   reports the number, asks the owner.
3. **Converge pass.** Before REPORT: a strictly append-only
   anti-false-done audit. Its ONLY write is ADDING missed work to the
   task list; findings are severity-graded (critical/warning/
   suggestion). Re-checking a box, editing done work, or declaring
   "converged, nothing to add" without the audit is a false done.

## Phase 5: REPORT

**Result first line.**

- What was done.
- Which files were touched.
- What was verified.
- What's next (if any).

## When NOT to use

- One-line fix, typo — verify is enough.
- Pure documentation — plan + verify.

## Gotchas

- Most common mistake: skipping TDD. "I'll just write the code, then the test". No. Test FIRST.
- Second: scope creep. "I'll also clean up the neighboring file". No. Separate task.
- Third: "seems to work". No. Observed that it works.