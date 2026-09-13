---
name: superpowers
description: 'Always-on development method: plan, check, implement, verify, report. Use for non-trivial tasks. Define observable acceptance before code, reproduce bugs before fixes, and complete the requested outcome without procedural permission gates.'
license: MIT
metadata:
  version: "4.6.0"
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
- Split by independently verifiable outcomes and shared interfaces, not file or step counts.

**Scope discipline:** touch only what the task requires. Not "I'll clean up along the way".

## Phase 2: TDD

**Red test → green code → refactoring.**

- Define an observable check before changing behavior; reproduce a bug before its fix.
- Test names express consumer rules, not implementation details. Keep a permanent regression only where a plausible bug would fail it; a throwaway probe or rendered UI interaction can provide the appropriate proof.
- A test verifies behavior, not implementation.

### Prove-It Pattern (bug fix)

```
Bug report → test reproducing the bug → test FAILS → fix → test GREEN
```

## Phase 3: IMPLEMENT

**Smallest correct implementation of the full request.**

- Do not reduce requested scope to fit the current test or increment.
- Match existing patterns. Repair in-scope gaps; avoid unrelated cleanup.
- Share a source where duplication is genuinely the same knowledge, not merely similar text.

## Phase 4: VERIFY

**Evidence, not inference.**

- [ ] Test green? → observed.
- [ ] Tests appropriate to the change green? → ran; broaden when scope
  warrants (shared code touched, or a failure the targeted check exposed).
  Re-running an unchanged check with no new changes, failures, or
  unresolved concerns is ceremony, not verification.
- [ ] No test that merely mirrors a reversible low-impact change? → skipped it.
- [ ] Build/lint checks applicable to affected paths pass; no unrelated runtime or production-store demand.
- [ ] Bug fix → TWINS: searched for the same pattern in the codebase.

### Completion and ownership

1. **Resolve material ambiguity.** Inspect code, config and requirements;
   decide ordinary implementation details. Ask only for information that
   remains unavailable and changes the outcome. Planning is not an approval gate.
2. **Separate tracking from signoff.** Update your execution checklist from
   evidence. Never toggle a separately owned reviewer approval or claim their
   acceptance. Missing signoff does not prohibit authorized implementation.
3. **Converge by repair.** Before reporting, compare the deliverable against
   every requested requirement. Add missed work, fix in-scope gaps and verify
   them. Record out-of-scope findings without silently expanding the task.
   A review-only request produces findings, not edits. A single small change's
   direct verification can be the audit; no extra review ceremony is required.

Continue through these steps without yielding at a phase boundary. Stop only
for user revocation or a concrete unavailable prerequisite under AGENTS.md.

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