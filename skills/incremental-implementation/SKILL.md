---
name: incremental-implementation
description: Delivers changes incrementally. Use when implementing any feature or change that touches more than one file. Use when you're about to write a large amount of code at once, or when a task feels too big to land in one step.
metadata:
  version: "3.7.0"
---

# Incremental Implementation

## Overview

Build in thin vertical slices — implement one piece, test it, verify it, then expand. Each increment should leave the system in a working, testable state.

## The Increment Cycle

```
Implement ──→ Test ──→ Verify ──→ Commit ──→ Next slice
```

For each slice:
1. **Implement** the smallest complete piece of functionality
2. **Test** — run the test suite (or write a test if none exists)
3. **Verify** — confirm the slice works (tests pass, build succeeds)
4. **Commit** — save progress with descriptive message
5. **Move to the next slice**

## Slicing Strategies

### Vertical Slices (Preferred)
Build one complete path through the stack:
```
Slice 1: Create (DB + API + basic UI) → user can create
Slice 2: List (query + API + UI) → user can see
Slice 3: Edit (update + API + UI) → user can modify
Slice 4: Delete → full CRUD complete
```

### Contract-First Slicing
```
Slice 0: Define API contract (types, interfaces)
Slice 1a: Implement backend against contract
Slice 1b: Implement frontend against mock data
Slice 2: Integrate and test end-to-end
```

### Risk-First Slicing
Tackle the riskiest piece first. If it fails, you discover it before investing in everything else.

## Implementation Rules

### Rule 0: Simplicity First
Before writing code, ask: "What is the simplest thing that could work?"

### Rule 0.5: Scope Discipline
Touch only what the task requires. Do NOT:
- "Clean up" adjacent code
- Refactor imports in files you're not modifying
- Add features not in the spec because they "seem useful"
- Modernize syntax in files you're only reading

If you notice something worth improving outside scope, note it — don't fix it.

### Rule 1: One Thing at a Time
Each increment changes one logical thing. Don't mix concerns.

### Rule 2: Keep It Compilable
After each increment, project must build and existing tests must pass.

### Rule 3: Feature Flags for Incomplete Features
```typescript
const ENABLE_FEATURE = process.env.FEATURE_X === 'true';
if (ENABLE_FEATURE) { /* new code */ }
```

### Rule 4: Safe Defaults
New code should default to safe, conservative behavior.

### Rule 5: Rollback-Friendly
Each increment should be independently revertable.

## Increment Checklist
- [ ] The change does one thing and does it completely
- [ ] All existing tests still pass
- [ ] The build succeeds
- [ ] Type checking passes
- [ ] Linting passes
- [ ] The new functionality works as expected
- [ ] The change is committed with a descriptive message

## Red Flags
- More than 100 lines of code written without running tests
- Multiple unrelated changes in a single increment
- "Let me just quickly add this too" scope expansion
- Build or tests broken between increments
- Large uncommitted changes accumulating