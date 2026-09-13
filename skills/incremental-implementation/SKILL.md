---
name: incremental-implementation
description: Delivers changes incrementally. Use when implementing any feature or change that touches more than one file. Use when you're about to write a large amount of code at once, or when a task feels too big to land in one step.
license: MIT
metadata:
  version: "4.6.0"
---

# Incremental Implementation

## Overview

Build in thin vertical slices — implement one piece, test it, verify it, then expand. Each increment should leave the system in a working, testable state.

## The Increment Cycle

```
Define check → Implement → Verify → Next slice → Integrated verification
```

For each slice:
1. **Implement** the smallest complete piece of functionality
2. **Test** — exercise the slice's affected behavior, reusing suitable checks
3. **Verify** — confirm its observable result and relevant compatibility
4. **Move to the next slice** without asking to continue already authorized work

An increment is an execution boundary, not permission to ship a partial
request. Commits follow AGENTS.md; no automatic commit per slice.

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
Slice 1b: Implement frontend against the agreed contract
Slice 2: Integrate real backend and frontend, verify end-to-end
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
Keep intermediate states locally recoverable. Check affected paths as they
become executable; run integration checks once shared mutations settle.

### Rule 3: No Incomplete Delivery
Use a feature flag only for an actual rollout requirement, not to disguise
unfinished requested behavior. Temporary mocks are not completed integration.

### Rule 4: Safe Defaults
New code should default to safe, conservative behavior.

### Rule 5: Rollback-Friendly
Each increment should be independently revertable.

## Increment Checklist
- [ ] The change does one thing and does it completely
- [ ] Relevant behavior and compatibility checks pass
- [ ] Applicable build/type/lint checks pass for the affected surface
- [ ] All requested slices are integrated before final delivery

## Red Flags
- A large unverified uncertainty accumulating across changes
- Multiple unrelated changes mixed in one increment
- "Let me just quickly add this too" scope expansion
- Partial functionality reported complete because one slice passed
- Commit, review or task boundaries treated as permission to stop