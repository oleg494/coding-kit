---
name: using-git-worktrees
description: Use when work needs an isolated workspace — concurrent writers or parallel agents, an explicit user request for isolation, or changes that would interfere with the current checkout. Covers detection, native worktree tools before the git fallback, setup, clean baseline, ignore handling, and removing task-created worktrees. Not for every planned change (a bounded single-writer task works in place) and not for merge authority or branch-retention decisions (use git-workflow-and-versioning).
license: MIT
metadata:
  version: "6.0.0"
---

# Using Git Worktrees

## Overview

Isolation costs a setup step and a second checkout, so it earns its place.
Create one when:

- **Concurrency** — another agent, process or session writes to the same repo.
- **The user asked** for an isolated or separate workspace.
- **Interference** — the work would disturb the current checkout: a long
  experiment, a migration with generated files, or a change that must stay
  buildable while `main` keeps moving.

Otherwise a bounded single-writer change belongs in the checkout you already
have. Don't manufacture a workspace decision before implementation, and don't
ask the user to choose between isolation mechanisms you can already resolve.

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

**If `GIT_DIR != GIT_COMMON` (and not a submodule):** You are already in a linked worktree. Skip to Step 2 (Project Setup). Do not create another worktree.

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

Verify the directory is ignored before creating the worktree:

```bash
git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

**If NOT ignored:** add the path to the repository's local exclude file — it is
private to this clone and never reaches the user's tracked files:

```bash
printf '.worktrees/\n' >> "$(git rev-parse --git-common-dir)/info/exclude"
```

Edit `.gitignore` only when the ignore rule genuinely belongs to the project
(other people checking out this repo would create the same directory).
Recheck that exact path afterwards. Neither operation authorizes a commit.

**Why:** an unignored worktree directory lets `git add .` sweep the whole tree
into a commit.

#### Create the Worktree

```bash
# Determine path based on chosen location
path="$LOCATION/$BRANCH_NAME"

git worktree add "$path" -b "$BRANCH_NAME"
cd "$path"
```

To attach to an existing branch (a merge location, for example), omit `-b`: `git worktree add "$path" "<branch>"`. Git refuses a branch already checked out in another worktree; `git worktree add --detach "$path" "<branch>"` gives a detached checkout of its commit for verification without moving the branch.

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

## Removing a Worktree

Removal can destroy uncommitted files and strand commits. Remove only a workspace this task created, and only when the authorized integration includes its cleanup.

- **Ownership comes from provenance.** This task created the workspace (Step 1a or 1b) and recorded its path and branch. A `.worktrees/` name, a stale-looking path or a matching branch name does not prove ownership. Host- or user-created workspaces, and detached externally managed ones, are host-owned: leave them in place, and use the platform's workspace-exit tool if it has one.
- **Inventory what would be lost.** Inside the workspace, capture `WT_PATH=$(git rev-parse --show-toplevel)`, then identify the exact files and commits:

  ```bash
  git -C "$WT_PATH" status --porcelain -uall --ignored   # modified, untracked and ignored files
  git -C "$WT_PATH" log --oneline "<base-branch>..HEAD"  # commits not in base
  ```

  Ignored files (build output, a local `.env`) are deleted without warning, so decide them explicitly.
- **Remove from outside the workspace.** `cd` to the main checkout root (`MAIN_ROOT`, as in git-workflow step 4) first, using the path captured before any directory change. Removing the directory you are standing in fails on Windows with `Permission denied`; elsewhere it leaves the shell in a deleted directory.
- **Remove without `--force`:**

  ```bash
  git worktree remove "$WT_PATH"
  git worktree prune
  ```

  Git refuses when the worktree has modified tracked files or untracked files. Ignored files do not block removal.
- **If removal is refused,** show the unique files and ask which: commit them to the branch (needs commit authority), move them into the main repo root, or delete them (unrecoverable; needs explicit authority naming those files). Carry out the choice, then retry the plain removal. Never add `--force` on your own initiative.
- **Branch.** `git branch -d <branch>` after a merge; git refuses unmerged branches. `git branch -D` only under explicit discard authority naming the commits being discarded.

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
| Directory not ignored | Add to `.git/info/exclude` (or `.gitignore` if shared); recheck; no automatic commit |
| Permission error on create | Sandbox fallback, work in place |
| Tests fail during baseline | Diagnose; repair in scope; report unrelated failures |
| Dependencies already available | Reuse; skip installation |
| Removing a task-created worktree | Removing a Worktree: inventory, remove from outside, no `--force` |
| Removal refused | Show the unique files and ask; never `--force` on your own |

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "I'm obviously not in a worktree — no need to check" | Run Step 0. Harness-created isolation and submodules both fool eyeballing; the detection commands settle it. |
| "`git worktree add` is quicker than hunting for a native tool" | A native tool (e.g. `EnterWorktree`) owns placement, branching, and cleanup. Bypassing it is the #1 mistake — it creates phantom state your harness can't see or manage. |
| "The worktree directory is surely ignored already" | Run `git check-ignore`. An unignored worktree directory commits the whole tree into the repo. |
| "The plan mentions worktrees, so I need one" | Isolation is triggered by concurrency, an explicit request, or real interference with the checkout — not by having a plan. A bounded single-writer change works in place. |
| "Any directory name works" | Explicit instructions beat an existing project-local directory, which beats the `.worktrees/` default. |
| "Any baseline failure requires user reapproval" | Investigate the failure; only missing authority or a concrete unavailable prerequisite blocks the affected action. |
| "The branch is merged, so the worktree is clutter" | Cleanup needs its own authorization, and ownership comes from provenance, not a path name. |
| "Removal refused — force is just cleanup" | List the unique files and obtain explicit deletion authority; never force silently. |

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: cross-references made local.