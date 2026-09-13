---
name: test-driven-development
description: Drives development with tests. Use when implementing any logic, fixing any bug, or changing any behavior. Use when you need to prove that code works, when a bug report arrives, or when you're about to modify existing functionality.
license: MIT
metadata:
  version: "4.6.0"
---

# Test-Driven Development

## Overview

Define acceptance and a behavior check before implementation. For bug fixes, reproduce the bug before changing its source, then show the reproduction passes. Existing contract tests, isolated smoke probes and actual rendered UI checks can provide appropriate evidence; a permanent test must defend a plausible failure.

## The TDD Cycle

```
    RED                GREEN              REFACTOR
 Write a test    Write minimal code    Clean up the
 that fails  ──→  to make it pass  ──→  implementation  ──→  (repeat)
      │                  │                    │
      ▼                  ▼                    ▼
   Test FAILS        Test PASSES        Tests still PASS
```

### Step 1: RED — Write a Failing Test
For a bug or new missing behavior, observe the check fail for the intended reason before the fix. A passing check can establish existing behavior, but cannot establish that it reproduced the reported bug. Do not manufacture failures in unrelated behavior.

### Step 2: GREEN — Make It Pass
Write the smallest correct implementation of the full request, not just the subset exercised by the current test. Don't over-engineer or drop acceptance criteria.

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
Each test verifies one behavior. Don't bundle multiple assertions into one test.

### Name Tests Descriptively
```typescript
it('sets status to completed and records timestamp', ...);
it('throws NotFoundError for non-existent task', ...);
it('is idempotent — completing already-completed task is a no-op', ...);
```

## Verification
- [ ] Bug/new-behavior reproduction failed for the intended reason before the fix
- [ ] The same behavior check passes after implementation
- [ ] Applicable existing checks pass on the final state; broaden for shared code or exposed failures
- [ ] Kept tests defend observable contracts rather than wording or internal wiring
- [ ] Every requested capability is implemented and verified