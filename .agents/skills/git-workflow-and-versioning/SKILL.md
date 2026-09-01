---
name: git-workflow-and-versioning
description: Structures git workflow practices. Use when making any code change. Use when committing, branching, resolving conflicts, or when you need to organize work across multiple parallel streams. Use when cutting a release, choosing a semantic version bump, tagging, or writing a changelog.
metadata:
  version: "3.7.0"
---

# Git Workflow and Versioning

## Overview

Git is your safety net. Treat commits as save points, branches as sandboxes, and history as documentation.

## Core Principles

### Trunk-Based Development (Recommended)
Keep `main` always deployable. Work in short-lived feature branches (1-3 days).

```
main ──●──●──●──●──●──●──●──●──●──  (always deployable)
        ╲      ╱  ╲    ╱
         ●──●─╱    ●──╱    ← short-lived feature branches
```

### 1. Commit Early, Commit Often
Each successful increment gets its own commit. Don't accumulate large uncommitted changes.

### 2. Atomic Commits
Each commit does one logical thing:
```
# Good: Each commit is self-contained
a1b2c3d Add task creation endpoint with validation
d4e5f6g Add task creation form component
h7i8j9k Connect form to API and add loading state

# Bad: Everything mixed together
x1y2z3a Add task feature, fix sidebar, update deps, refactor utils
```

### 3. Descriptive Messages
```
feat: add email validation to registration endpoint

Prevents invalid email formats from reaching the database.
Uses Zod schema validation at the route handler level.
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

### 4. Keep Concerns Separate
Don't combine formatting changes with behavior changes. Don't combine refactors with features. Each type of change should be a separate commit.

### 5. Size Your Changes
```
~100 lines  → Easy to review, easy to revert
~300 lines  → Acceptable for a single logical change
~1000 lines → Split into smaller changes
```

## Branching Strategy

```
main
  ├── feature/task-creation    ← One feature per branch
  ├── feature/user-settings    ← Parallel work
  └── fix/duplicate-tasks      ← Bug fixes
```

- Branch from `main`
- Keep branches short-lived (merge within 1-3 days)
- Delete branches after merge
- Prefer feature flags over long-lived branches

## The Save Point Pattern

```
Agent starts work
    ├── Makes a change
    │   ├── Test passes? → Commit → Continue
    │   └── Test fails? → Revert to last commit → Investigate
    └── Feature complete → All commits form a clean history
```

## Change Summaries

After any modification, provide a structured summary:
```
CHANGES MADE:
- src/routes/tasks.ts: Added validation middleware

THINGS I DIDN'T TOUCH (intentionally):
- src/routes/auth.ts: Has similar gap but out of scope

POTENTIAL CONCERNS:
- The Zod schema is strict — rejects extra fields. Confirm desired.
```

## Pre-Commit Hygiene

```bash
git diff --staged                    # Check what you're committing
git diff --staged | grep -i "password\|secret\|api_key"  # No secrets
npm test                             # Tests pass
npm run lint                         # Lint clean
npx tsc --noEmit                     # Type check
```

## Semantic Versioning

```
MAJOR.MINOR.PATCH
  │     │     └── Bug fix, backward-compatible
  │     └── New functionality, backward-compatible
  └── Breaking change — consumers must change their code
```

Tag releases: `git tag -a v1.4.0 -m "Release 1.4.0"`