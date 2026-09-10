---
name: finishing-a-development-branch
description: Use when implementation is complete, all tests pass, and you need to decide how to integrate the work
license: MIT
metadata:
  version: "4.5.1"
---

# Finishing a Development Branch

## Overview

**Core principle:** Verify the deliverable, then perform only the integration
the user authorized. A verified local task can remain local, without an
integration menu, commit, push or cleanup of the user's workspace.

## Step 1: Verify Tests

Use `verification-before-completion`: evidence must cover the final source and
the requested acceptance criteria. Run applicable checks when no valid evidence
exists; broaden for shared changes, integration policy or observed failures.
Repair task-caused failures within scope. Report unrelated/environment failures
separately; do not discard work or stop reachable repairs because a suite is red.

If no integration was requested, report the verified local result and leave the
branch/workspace intact. The remaining steps apply only to authorized integration.

## Step 2: Detect Environment

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
# Capture now, while still inside the workspace — Step 5 changes directory
# before cleanup (Step 6) needs this value
WORKTREE_PATH=$(git rev-parse --show-toplevel)
```

This determines available integration and cleanup operations:

| State | Integration | Cleanup |
|-------|-------------|---------|
| Normal repo | Authorized merge or publication | No worktree to remove |
| Named-branch worktree | Authorized merge or publication | Provenance-based (Step 6) |
| Detached HEAD | Preserve unless a target branch/publication is authorized | Externally managed — leave in place |

## Step 3: Determine Base Branch

Use the plan, upstream and repository history to establish the intended base
and target. Ask only when available evidence cannot resolve a materially
different destination. Do not infer authority to merge from knowing the base.

## Step 4: Resolve integration authority

Execute the user's specified integration without asking them to choose it
again. If they explicitly asked you to choose how to integrate but the choice
is material and unresolved, present the relevant tradeoffs: local merge,
publication/PR, or keeping the branch. No fixed option count or exact wording.

Discarding work is never a suggested finish step. It requires explicit
authorization naming the work and destructive effect under AGENTS.md.

## Step 5: Execute Choice

### Option 1: Merge Locally

```bash
# Get main repo root for CWD safety
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"

# Merge first — verify success before removing anything
git checkout <base-branch>
# Synchronize remote state only if required and authorized; never pull blindly.
git merge <feature-branch>

# Verify tests on merged result
<test command>
```

If the merged result fails, retain the branch/worktree and investigate.
Repair authorized in-scope failures and reverify; do not publish a failed result
or silently reset the user's work.

Once the merged result is green: clean up the worktree (Step 6), then
delete the branch:

```bash
git branch -d <feature-branch>
```

### Option 2: Push and Create PR

```bash
git push -u origin <feature-branch>
# From a detached HEAD, name the new branch on the remote:
# git push origin HEAD:refs/heads/<new-branch>
```

Then create the pull/merge request against <base-branch> with the forge's
tooling — its CLI if one is available, or the creation URL most forges
print when you push — following the repo's PR template and conventions if
present, and report the URL to your human partner.

Keep the worktree — your human partner iterates on PR feedback there.

### Option 3: Keep As-Is

Report: "Keeping branch <name>. Worktree preserved at <path>."

### If your human partner asks to discard the work

Identify the exact branch, commits, workspace and any uncommitted/untracked
files at risk. Obtain missing destructive authority for that exact effect;
if it was already explicitly granted, do not demand a magic confirmation word.
An ambiguous "clean up" does not authorize discarding work.

After authorization for the identified deletion:

```bash
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"
```

Then clean up the worktree (Step 6) and force-delete the branch:

```bash
git branch -D <feature-branch>
```

## Step 6: Cleanup Workspace

**Runs for Option 1 and confirmed discards.** Options 2 and 3 always
preserve the worktree. Both callers have already changed directory to the
main repo root — worktree removal must run from outside the worktree —
and use the `GIT_DIR`/`GIT_COMMON`/`WORKTREE_PATH` values captured in
Step 2, from before that directory change.

**If `GIT_DIR == GIT_COMMON`:** Normal repo, no worktree to clean up. Done.

**If session provenance records that this task created the worktree and the
authorized integration includes its cleanup:** remove that exact workspace.
A `.worktrees/` directory name alone does not establish ownership:

```bash
git worktree remove "$WORKTREE_PATH"
git worktree prune  # Self-healing: clean up any stale registrations
```

**If removal is refused** (`contains modified or untracked files`): the
worktree holds files that exist nowhere else — uncommitted plans, notes,
or scratch work. Never `--force` on your own initiative. Show your human
partner what is at stake and ask:

```bash
git -C "$WORKTREE_PATH" status --porcelain -uall
```

```
Worktree removal refused — these files were never committed:

<file list>

1. Commit them to <branch> before cleanup
2. Move them into <main repo root>
3. Delete them (unrecoverable)

Which?
```

Carry out the choice, then remove the worktree.

**Otherwise:** The host environment owns this workspace — leave it in
place. If your platform provides a workspace-exit tool, use it.

## Quick Reference

| Option | Merge | Push | Keep Worktree | Cleanup Branch |
|--------|-------|------|---------------|----------------|
| 1. Merge locally | yes | - | - | yes |
| 2. Create PR | - | yes | yes | - |
| 3. Keep as-is | - | - | yes | - |
| Discard (explicit request only) | - | - | - | yes (force) |

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Tests passed earlier" | Reuse only evidence covering the exact final state, with no invalidating change or unresolved failure. |
| "They obviously want it merged" | Local implementation is not integration authority. Preserve it unless integration was requested. |
| "They already asked for a PR, but the skill says ask again" | Execute the authorized PR workflow; do not reopen a settled choice. |
| "The PR is up, so the worktree is clutter" | Preserve the feedback workspace unless its cleanup was authorized. |
| "This worktree looks stale" | Name/path is not proof of ownership. Do not remove unrelated workspaces. |
| "Removal refused — force is just cleanup" | Identify the unique files and obtain explicit deletion authority; never force silently. |
| "The merged-result failure is probably flaky" | Investigate, repair in scope and verify before publication. |
| "The base is obviously main" | Establish the intended destination from evidence or ask if irreducibly ambiguous. |
| "The push was rejected — force-push will fix it" | A rejected push means the remote moved. Investigate; force-push only on your human partner's explicit request. |

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: cross-references made local.