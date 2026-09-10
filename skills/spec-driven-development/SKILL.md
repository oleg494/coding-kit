---
name: spec-driven-development
description: Creates specs before coding. Use when starting a new project, feature, or significant change and no specification exists yet. Use when requirements are unclear, ambiguous, or only exist as a vague idea. Use when a single requirement spans several independently testable capabilities.
license: MIT
metadata:
  version: "4.5.1"
---

# Spec-Driven Development

## Overview

Capture observable requirements before code. Reuse an existing spec or the user's explicit acceptance criteria; write only the missing design. Authorization follows AGENTS.md, not phase approval.

## When to Use

- Starting a new project or feature
- Requirements are ambiguous or incomplete
- The change touches multiple files or modules
- You're about to make an architectural decision

**When NOT to use:** Single-line fixes, typo corrections, or changes where requirements are unambiguous.

## Workflow

Specify → plan → implement → verify. Review at meaningful uncertainty or
integration boundaries, not as a mandatory human permission step after each
phase. Continue already authorized implementation; plan-only requests end at
the plan. Artifact size follows complexity, not a fixed template quota.

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

**Spec template:**

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
- Always: [Verify affected behavior, follow project conventions, validate trust boundaries]
- Ask first: [Missing irreversible/outward authority or unavailable outcome-changing information]
- Never: [Expose secrets, mutate production data as a test, suppress a real failure]

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
- Split by independent outcomes and explicit shared contracts, not file counts

```markdown
- [ ] Task: [Description]
  - Acceptance: [What must be true when done]
  - Verify: [How to confirm]
  - Files: [Which files touched]
```

### Phase 4: Implement

Execute dependency-ordered tasks with focused checks; parallelize independent ownership when useful. Complete all requested capabilities before reporting implementation complete.

## Keeping the Spec Alive

- Update when decisions change
- Update when scope changes
- Save durable specs when requested or required by the project; otherwise a concise task plan can suffice
- Commits and PRs require authority under AGENTS.md

## Red Flags
- Coding before acceptance or a check is defined
- Adding unrequested features or omitting requested ones as an MVP
- Inventing incompatible defaults when the user must choose the outcome
- Demanding a spec file, human signoff or another menu for already authorized work

## Verification
- [ ] Required behavior, constraints and important risks are explicit
- [ ] Success criteria are observable and mapped to suitable checks
- [ ] Any necessary user decision is resolved; ordinary details use repo conventions
- [ ] The complete authorized implementation continues without phase stalls