---
name: test-driven-development
description: Use when designing new behavior whose expected failure must be specified first, fixing a reported failure, or when regression coverage for a change is uncertain; ordinary edits with adequate coverage do not need it
license: MIT
metadata:
  version: "5.0.0"
---

# Test-Driven Development

## Overview

Define acceptance and a behavior check before implementation. For bug fixes, reproduce the failure where reproduction is needed for diagnosis or regression defense; a user-supplied failure report is ground truth for the symptom, and prior failure evidence remains valid for an unchanged state. Show the reproduction (or the valid prior evidence) passes after the fix. Existing contract tests, isolated smoke probes and actual rendered UI checks can provide appropriate evidence; a permanent test must defend a plausible failure. State explicitly when reproduction is unavailable rather than claiming an unrun one.

## The TDD Cycle

```
    RED                GREEN              REFACTOR
 Write a test    Write minimal code    Clean up the
 that fails  ──→  to make it pass  ──→  implementation  ──→  (repeat)
      │                  │                    │
      ▼                  ▼                    ▼
   Test FAILS        Test PASSES        Tests still PASS
```

### Step 1: RED — Establish Failing Evidence
For a bug or new missing behavior, observe the check fail for the intended reason before the fix — freshly, or by reusing prior failure evidence valid for the unchanged state. Reuse follows OPS.md §3: a recorded failure still covers the same state, command and environment, and a new session or phase alone does not invalidate it. A passing check can establish existing behavior, but cannot establish that it reproduced the reported bug; a user-supplied failure report is ground truth for the symptom. Do not manufacture failures in unrelated behavior.

### Step 2: GREEN — Make It Pass
Write the smallest correct implementation of the full request, not just the subset exercised by the current test. Don't over-engineer or drop acceptance criteria.

### GREEN is Two Claims: Targeted and Suite
A green run of the check you wrote (targeted green) is not the same claim as the project's checks passing on your final state (suite green). Both are evidence, at different scopes:

- **Targeted green** (always): the behavior check for this task passes after the change.
- **Suite green** (scaled to risk, per OPS §3): applicable existing checks pass on the final state. Run the affected suite(s) — not only your file — when the change touches shared code, public contracts or an exposed failure, or when a named concern requests it; a self-contained change with a scoped probe may not need the full project suite. Reuse valid prior evidence instead of rerunning when state, command and environment are unchanged.
- **Reporting failures**: name every failure you observed, including preexisting ones you did not cause. A red check watched scrolling past and left unmentioned is a report falsified by omission. Distinguish "caused by this change" from "present before" when you know, and say when you don't.

### Step 3: REFACTOR — Clean Up
With checks green, remove task-related duplication or complexity only when it improves the implementation. Recheck affected behavior after changes; do not refactor unrelated code for ceremony.

## The Prove-It Pattern (Bug Fixes)

```
Bug report → test that reproduces bug → test FAILS → fix → test PASSES → checks appropriate to the change
```

## The Test Pyramid

```
          ╱╲
        ╱  ╲         E2E Tests
        ╱    ╲        Full user flows
       ╱──────╲
      ╱        ╲      Integration Tests
     ╱          ╲     Component interactions, API boundaries
    ╱────────────╲
  ╱              ╲   Unit Tests
  ╱                ╲  Pure logic, isolated, milliseconds
 ╱──────────────────╲
```

## Writing Good Tests

### Test State, Not Interactions
Assert on the outcome of an operation, not on which methods were called internally.

### DAMP Over DRY in Tests
In tests, DAMP (Descriptive And Meaningful Phrases) is better than DRY. Each test should tell a complete story.

### Prefer Real Implementations Over Mocks
Preference: Real implementation > Fake > Stub > Mock. Use mocks only when real is too slow, non-deterministic, or has side effects you can't control.

### Use Arrange-Act-Assert
```typescript
// Arrange: Set up the test scenario
// Act: Perform the action being tested
// Assert: Verify the outcome
```

### One Assertion Per Concept
Each test verifies one behavior. Use multiple assertions when they jointly
establish that behavior; split unrelated concepts, not necessary evidence.

### Name Tests Descriptively
```typescript
it('sets status to completed and records timestamp', ...);
it('throws NotFoundError for non-existent task', ...);
it('is idempotent — completing already-completed task is a no-op', ...);
```

## Verification
- [ ] Bug/new-behavior reproduction failed for the intended reason before the fix (fresh run, or prior failure evidence valid for the unchanged state; unavailable reproduction is stated, not faked)
- [ ] The same behavior check passes after implementation
- [ ] Targeted green distinguished from suite green: applicable existing checks pass on the final state, scaled to risk (broaden for shared code, public contracts or exposed failures); valid prior evidence reused, not rerun
- [ ] Every observed failure reported by name, including preexisting ones; cause attribution stated as known or unknown
- [ ] Kept tests defend observable contracts rather than wording or internal wiring
- [ ] Every requested capability is implemented and verified