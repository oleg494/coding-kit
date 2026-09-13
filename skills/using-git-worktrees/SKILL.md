---
name: using-git-worktrees
description: Use when starting feature work that needs isolation from current workspace or before executing implementation plans - ensures an isolated workspace exists via native tools or git worktree fallback
license: MIT
metadata:
  version: "4.6.0"
---

# Using Git Worktrees

## Overview

Use isolation when the task or concurrent writers require it. For a bounded
local change in a usable checkout, work in place unless the user requested
otherwise. Do not manufacture a workspace decision before implementation.

**Core principle:** Preserve existing work. Reuse existing isolation; prefer
native tools when creating it, then fall back to git.

## Step 0: Detect Existing Isolation

**Before creating anything, check if you are already in an isolated workspace.**

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
```

**Submodule guard:** `GIT_DIR != GIT_COMMON` is also true inside git submodules. Before concluding "already in a worktree," verify you are not in a submodule:

```bash
# If this returns a path, you're in a submodule, not a worktree — treat as normal repo
git rev-parse --show-superproject-working-tree 2>/dev/null
```

**If `GIT_DIR != GIT_COMMON` (and not a submodule):** You are already in a linked worktree. Skip to Step 2 (Project Setup). Do NOT create another worktree.

Report with branch state:
- On a branch: "Already in isolated workspace at `<path>` on branch `<name>`."
- Detached HEAD: preserve the externally managed workspace; name a branch only if authorized integration requires one.

**If `GIT_DIR == GIT_COMMON` (or in a submodule):** You are in a normal repo checkout.

Honor the user's declared workspace preference. With no isolation need, work
in place and continue to Step 2. If isolation is required, use the platform's
existing task-isolation mechanism or a task-scoped worktree; ask only when
an unresolved workspace choice would move, discard or interfere with user work.

## Step 1: Create Isolated Workspace

**You have two mechanisms. Try them in this order.**

### 1a. Native Worktree Tools (preferred)

Isolation is needed or requested (Step 0). Use a native facility such as `EnterWorktree`, `WorktreeCreate`, `/worktree` or `--worktree` if available, then continue to Step 2.

Native tools handle directory placement, branch creation, and cleanup automatically. Using `git worktree add` when you have a native tool creates phantom state your harness can't see or manage.

Only proceed to Step 1b if you have no native worktree tool available.

### 1b. Git Worktree Fallback

**Only use this if Step 1a does not apply** — you have no native worktree tool available. Create a worktree manually using git.

#### Directory Selection

Follow this priority order. Explicit user preference always beats observed filesystem state.

1. **Check your instructions for a declared worktree directory preference.** If the user has already specified one, use it without asking.

2. **Check for an existing project-local worktree directory:**
   ```bash
   ls -d .worktrees 2>/dev/null     # Preferred (hidden)
   ls -d worktrees 2>/dev/null      # Alternative
   ```
   If found, use it. If both exist, `.worktrees` wins.

3. **If there is no other guidance available**, default to `.worktrees/` at the project root.

#### Safety Verification (project-local directories only)

**MUST verify directory is ignored before creating worktree:**

```bash
git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

**If NOT ignored:** Add the chosen directory to the local exclude file, or update `.gitignore` when shared ignore policy belongs to the task. Recheck that exact path. Neither operation authorizes a commit.

**Why critical:** Prevents accidentally committing worktree contents to repository.

#### Create the Worktree

```bash
# Determine path based on chosen location
path="$LOCATION/$BRANCH_NAME"

git worktree add "$path" -b "$BRANCH_NAME"
cd "$path"
```

**Sandbox fallback:** If `git worktree add` fails with a permission error (sandbox denial), tell the user the sandbox blocked worktree creation and you're working in the current directory instead. Then run setup and baseline tests in place.

## Step 2: Project Setup

Inspect the documented project setup and available environment. Reuse installed
dependencies; install only missing requirements needed for this task, using
the project's lockfile and package manager. A manifest's presence alone is not
a reason to install, build or contact the network.

## Step 3: Verify Clean Baseline

Run the relevant baseline check when no valid evidence exists for this state.
Broaden only for shared impact, integration requirements or observed failures.

**If checks fail:** Preserve the checkout and identify the cause. Repair
task-related failures within scope and continue reachable work. Report unrelated
or environment failures separately; ask only for a concrete missing prerequisite
or authority, not merely because a baseline is red.

**If checks pass:** Continue the authorized implementation immediately. Report
workspace details only when they affect the user's work; do not stop at a
"ready to implement" handoff.

## Quick Reference

| Situation | Action |
|-----------|--------|
| Already in linked worktree | Skip creation (Step 0) |
| In a submodule | Treat as normal repo (Step 0 guard) |
| Native worktree tool available | Use it (Step 1a) |
| No native tool | Git worktree fallback (Step 1b) |
| `.worktrees/` exists | Use it (verify ignored) |
| `worktrees/` exists | Use it (verify ignored) |
| Both exist | Use `.worktrees/` |
| Neither exists | Check instruction file, then default `.worktrees/` |
| Directory not ignored | Add task-scoped ignore; recheck; no automatic commit |
| Permission error on create | Sandbox fallback, work in place |
| Tests fail during baseline | Diagnose; repair in scope; report unrelated failures |
| Dependencies already available | Reuse; skip installation |

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "I'm obviously not in a worktree — no need to check" | Run Step 0. Harness-created isolation and submodules both fool eyeballing; the detection commands settle it. |
| "`git worktree add` is quicker than hunting for a native tool" | A native tool (e.g. `EnterWorktree`) owns placement, branching, and cleanup. Bypassing it is the #1 mistake — it creates phantom state your harness can't see or manage. |
| "The worktree directory is surely ignored already" | Run `git check-ignore`. An unignored worktree directory commits the whole tree into the repo. |
| "Any directory name works" | Explicit instructions beat an existing project-local directory, which beats the `.worktrees/` default. |
| "Any baseline failure requires user reapproval" | Investigate the failure; only missing authority or a concrete unavailable prerequisite blocks the affected action. |

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: cross-references made local.