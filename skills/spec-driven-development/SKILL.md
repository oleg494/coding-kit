---
name: spec-driven-development
description: Creates specs before coding. Use when starting a new project, feature, or significant change and no specification exists yet. Use when requirements are unclear, ambiguous, or only exist as a vague idea. Use when a single requirement spans several independently testable capabilities.
metadata:
  version: "4.0.3"
---

# Spec-Driven Development

## Overview

Write a structured specification before writing any code. The spec is the shared source of truth — it defines what we're building, why, and how we'll know it's done.

## When to Use

- Starting a new project or feature
- Requirements are ambiguous or incomplete
- The change touches multiple files or modules
- You're about to make an architectural decision
- The task would take more than 30 minutes to implement

**When NOT to use:** Single-line fixes, typo corrections, or changes where requirements are unambiguous.

## The Gated Workflow

```
SPECIFY ──→ PLAN ──→ TASKS ──→ IMPLEMENT
   │          │        │          │
   ▼          ▼        ▼          ▼
 Human      Human    Human      Human
 reviews    reviews  reviews    reviews
```

### Phase 0: Scope Check (multi-capability only)

If a single requirement bundles several independently testable capabilities → propose a capability map first:

```markdown
# Capability Map: [Initiative Name]
| Module id | Responsibility | Depends on |
|---|---|---|
| identity | Accounts, sessions, SSO | — |
| billing | Plans, invoices, payments | identity |
| notifications | Email and webhook fan-out | identity |
```

Build order: identity → billing, notifications.

### Phase 1: Specify

**Surface assumptions immediately:**
```
ASSUMPTIONS I'M MAKING:
1. This is a web application (not native mobile)
2. Authentication uses session-based cookies (not JWT)
3. The database is PostgreSQL
→ Correct me now or I'll proceed with these.
```

**Spec template (6 core areas):**

```markdown
# Spec: [Project/Feature Name]

## Objective
[What we're building and why. User stories or acceptance criteria.]

## Tech Stack
[Framework, language, key dependencies with versions]

## Commands
[Build, test, lint, dev — full commands]

## Project Structure
[Directory layout with descriptions]

## Code Style
[Example snippet + key conventions]

## Testing Strategy
[Framework, test locations, coverage requirements, test levels]

## Boundaries
- Always: [Run tests before commits, follow naming conventions, validate inputs]
- Ask first: [DB schema changes, adding dependencies, changing CI config]
- Never: [Commit secrets, edit vendor directories, remove failing tests]

## Success Criteria
[How we'll know this is done — specific, testable conditions]

## Open Questions
[Anything unresolved that needs human input]
```

**Reframe instructions as success criteria:**
```
REQUIREMENT: "Make the dashboard faster"
REFRAMED:
- Dashboard LCP < 2.5s on 4G connection
- Initial data load completes in < 500ms
- No layout shift during load (CLS < 0.1)
```

### Phase 2: Plan

Generate a technical implementation plan:
1. Identify major components and dependencies
2. Determine implementation order
3. Note risks and mitigation strategies
4. Define verification checkpoints between phases

### Phase 3: Tasks

Break plan into discrete tasks:
- Each task completable in single focused session
- Each task has explicit acceptance criteria
- Tasks ordered by dependency
- No task should touch more than ~5 files

```markdown
- [ ] Task: [Description]
  - Acceptance: [What must be true when done]
  - Verify: [How to confirm]
  - Files: [Which files touched]
```

### Phase 4: Implement

Execute tasks one at a time, following test-driven-development and incremental-implementation.

## Keeping the Spec Alive

- Update when decisions change
- Update when scope changes
- Commit the spec in version control
- Reference the spec in PRs

## Red Flags
- Starting to write code without any written requirements
- Implementing features not mentioned in any spec or task list
- Making architectural decisions without documenting them
- Skipping the spec because "it's obvious what to build"

## Verification
- [ ] Spec covers all six core areas
- [ ] Human reviewed and approved
- [ ] Success criteria are specific and testable
- [ ] Boundaries (Always/Ask First/Never) defined
- [ ] Spec saved to file in repository