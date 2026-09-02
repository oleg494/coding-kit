---
name: test-driven-development
description: Drives development with tests. Use when implementing any logic, fixing any bug, or changing any behavior. Use when you need to prove that code works, when a bug report arrives, or when you're about to modify existing functionality.
metadata:
  version: "4.0.3"
---

# Test-Driven Development

## Overview

Write a failing test before writing the code that makes it pass. For bug fixes, reproduce the bug with a test before attempting a fix. Tests are proof — "seems right" is not done.

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
Write the test first. It must fail. A test that passes immediately proves nothing.

### Step 2: GREEN — Make It Pass
Write the minimum code to make the test pass. Don't over-engineer.

### Step 3: REFACTOR — Clean Up
With tests green, improve the code without changing behavior. Extract shared logic, improve naming, remove duplication. Run tests after every refactor step.

## The Prove-It Pattern (Bug Fixes)

```
Bug report → test that reproduces bug → test FAILS → fix → test PASSES → full suite
```

## The Test Pyramid

```
          ╱╲
         ╱  ╲         E2E Tests (~5%)
        ╱    ╲        Full user flows
       ╱──────╲
      ╱        ╲      Integration Tests (~15%)
     ╱          ╲     Component interactions, API boundaries
    ╱────────────╲
   ╱              ╲   Unit Tests (~80%)
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
- [ ] Test was RED before code was written
- [ ] Test is GREEN after minimal implementation
- [ ] Full test suite still passes
- [ ] Test names read like a specification