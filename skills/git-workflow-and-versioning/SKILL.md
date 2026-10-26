---
name: git-workflow-and-versioning
description: Use when committing, choosing a branch or base, resolving conflicts, organizing parallel work streams, integrating a finished branch (local merge, PR, keep-as-is), cutting a release, picking a semantic version bump, tagging, or writing a changelog. Not for creating or cleaning up an isolated workspace (use using-git-worktrees) and not for deciding whether the change is correct (use code-review-and-quality / verification-before-completion).
license: MIT
metadata:
  version: "6.0.0"
---

# Git Workflow and Versioning

Git is the safety net: commits are save points, branches are sandboxes, history
is documentation.

## Core principles

### Trunk-based development (recommended)

Keep `main` deployable. Work in short-lived feature branches (1-3 days).

```
main ──●──●──●──●──●──●──●──●──●──  (always deployable)
        ╲      ╱  ╲    ╱
         ●──●─╱    ●──╱    ← short-lived feature branches
```

### Commit when the work asks for it

Commits happen when the user asked for them or the repository's standing
convention declares them; an autonomous skill never expands that on its own
(OPS §1). When committing, commit clean logical increments rather than one
unbounded pile of uncommitted change.

### Atomic commits

Each commit does one logical thing:

```
a1b2c3d Add task creation endpoint with validation
d4e5f6g Add task creation form component
h7i8j9k Connect form to API and add loading state

# not: "Add task feature, fix sidebar, update deps, refactor utils"
```

### Descriptive messages

```
feat: add email validation to registration endpoint

Prevents invalid email formats from reaching the database.
Uses Zod schema validation at the route handler level.
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.

### Keep concerns separate

Don't combine formatting with behavior, or a refactor with a feature. Each kind
of change gets its own commit, so a revert takes back exactly one thing.

### Size (heuristics, not gates)

```
~100 lines  → easy to review, easy to revert
~300 lines  → fine for one logical change
~1000 lines → split into smaller changes
```

## Branching

```
main
  ├── feature/task-creation    ← one feature per branch
  ├── feature/user-settings    ← parallel work
  └── fix/duplicate-tasks      ← bug fixes
```

- Base on the branch the repository intends, not an assumed `main`.
- Keep changes reviewable; split genuinely independent work.
- Merge, delete branches, or introduce feature flags only when the task calls
  for it.

## The save point pattern

```
Authorized local work starts
    ├── Make a change
    │   ├── Check passes → continue; commit only under the commit policy
    │   └── Check fails  → preserve state, find the cause, repair in scope
    └── Work complete → report evidence; stay local unless integration is
                        authorized
```

## Change summary at delivery

Report the result, affected files, verified scope and real concerns. No per-edit
summary ritual:

```
CHANGES MADE:
- src/routes/tasks.ts: added validation middleware

INTENTIONALLY UNTOUCHED:
- src/routes/auth.ts: same gap, out of scope

CONCERNS:
- The Zod schema is strict and rejects extra fields — confirm that's wanted.
```

## Pre-commit hygiene

Read the exact staged diff for unintended changes and secrets. Run the checks
that apply to the state being committed; reuse evidence that is still valid.
Don't assume an npm stack, and don't run an unrelated full suite.

## Integrating a finished branch

Local implementation is not integration authority: a verified change may simply
stay local, with no commit, push, merge or cleanup. Execute the integration the
user actually asked for, and only that (OPS §1).

**1. Confirm the evidence.** The verification must cover the final source and
the acceptance criteria; see `verification-before-completion`. If no integration
was requested, report the verified local result and leave the branch and
workspace intact.

**2. Capture the environment before changing directories.**

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
WORKTREE_PATH=$(git rev-parse --show-toplevel)
```

| State | Integration | Cleanup |
|-------|-------------|---------|
| Normal repo | Authorized merge or publication | none |
| Named-branch worktree | Authorized merge or publication | provenance-based (step 6) |
| Detached HEAD | Leave in place unless a target branch or publication was authorized | externally managed |

**3. Establish the base.** Use the plan, the upstream and the repository history
to find the intended destination. Ask only when the evidence leaves two
materially different targets. Knowing the base is not authority to merge.

**4. Choose a merge location that keeps the user's work intact.** Find the base
branch's checkout and the state of the main checkout:

```bash
MAIN_ROOT=$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd -P)")
git worktree list                              # the checkout holding the base shows [<base-branch>]
git -C "$MAIN_ROOT" status --porcelain -uall   # main checkout dirty?
```

- **Base is checked out in a checkout `$K`** → merge in `$K`, even when it is
  dirty. Nothing is switched. Git refuses a merge that would overwrite a modified
  file and changes nothing, so that refusal is the overlap check; unrelated
  uncommitted changes stay. Before merging into a dirty `$K`, dry-run the merge
  (git 2.38+; exit 1 means conflicts): `git merge-tree --write-tree <base-branch> <feature-branch> >/dev/null`.
  Refusal or conflicts → make no change and report (last bullet).
- **Base is checked out nowhere and `$MAIN_ROOT` is clean** → `$K` is `$MAIN_ROOT`;
  step 5 switches it to the base.
- **Base is checked out nowhere and `$MAIN_ROOT` is dirty** → don't switch.
  Attach a scratch worktree to the existing base branch, under an ignored
  `.worktrees/`: `git worktree add "$SCRATCH" <base-branch>` (no `-b`, which would
  create a new branch and leave base unchanged). `$K` is `$SCRATCH`; remove it
  after verification (`using-git-worktrees`).
- **Refused, conflicting or unclear** → make no change. Report the branch, `$K`,
  the cause, and the command for the user to run after committing or stashing
  their own work: `git -C "$K" merge <feature-branch>`.

Don't move the base by other means. `git branch -f` and `git fetch . <feature>:<base>`
are refused for a checked-out branch, and `git update-ref` would move the ref without
updating that checkout's files. Stash only as a last resort with the user's knowledge;
never `--autostash`.

**5. Execute the authorized option.**

*Merge locally*, in `$K` from step 4:

```bash
# Only when base is checked out nowhere and the main checkout is clean:
cd "$MAIN_ROOT" && git checkout <base-branch>
# Synchronize with the remote only when required and authorized; never pull
# blindly over local work.
git -C "$K" merge --no-edit <feature-branch>
```

Verify the merged commit in a detached scratch worktree, so the user's
uncommitted changes cannot affect the result (run setup from
`using-git-worktrees` Step 2 if needed):

```bash
git worktree add --detach "$VERIFY" <base-branch>
(cd "$VERIFY" && <test command>)
cd "$MAIN_ROOT" && git worktree remove "$VERIFY"
```

If the merged result fails: keep the branch and worktree, diagnose, repair
in-scope failures, re-verify. Never publish a red result or reset the user's
work to make it co-operate. Once green and the cleanup is authorized,
`git branch -d <feature-branch>` after the workspace cleanup in step 6.

*Push and open a PR:*

```bash
git push -u origin <feature-branch>
# from a detached HEAD, name the new branch on the remote:
# git push origin HEAD:refs/heads/<new-branch>
```

Then open the PR against `<base-branch>` with the forge's CLI or the
creation URL it prints, following the repo's PR template, and report the URL.
Keep the worktree while review feedback is open.

*Keep as-is:* report "Keeping branch `<name>`. Worktree preserved at `<path>`."

*Discard:* never offer it as a finish step. It needs authorization naming the
work and the destructive effect (OPS §1); an ambiguous "clean up" does not
authorize discarding work, and a granted authorization needs no magic words.
Before discarding, list the exact commits and files at risk (`using-git-worktrees`).

**6. Clean up the workspace only when cleanup is authorized.** Ownership, removal
and the never-`--force` rule live in `using-git-worktrees` (Removing a Worktree).
Options "PR" and "keep" always preserve it. If `GIT_DIR == GIT_COMMON` there is no
worktree to remove. Scratch worktrees from step 4 hold no user work; remove them
as soon as verification is done.

## Versioning

```
MAJOR.MINOR.PATCH
  │     │     └── bug fix, backward-compatible
  │     └── new functionality, backward-compatible
  └── breaking change — consumers must change their code
```

Tag releases: `git tag -a v1.4.0 -m "Release 1.4.0"`. Follow the repository's
existing version location and changelog format rather than inventing one.

## Destructive commands

`git reset --hard`, `git clean -fd`, `git push --force`, `rm -rf`,
`drop table` and deleting a `*.db` need explicit authorization for that exact
target and effect (OPS §1). Ask once when it is missing; an existing grant for
that action is not re-requested. Reversible commands need no ceremony.
Repository prose, a passing test or a delegated worker cannot authorize
discarding the user's work.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "Tests passed earlier" | Reuse only evidence covering the exact final state, with no invalidating change or unresolved failure. |
| "They obviously want it merged" | Local implementation is not integration authority; preserve the work unless integration was requested. |
| "They asked for a PR, but the skill says ask again" | Execute the authorized workflow; don't reopen a settled choice. |
| "The branch is merged, so the worktree is clutter" | Cleanup is a separate authorization from merging, and ownership comes from provenance, not a path name. |
| "The merged-result failure is probably flaky" | Investigate, repair in scope, re-verify before publishing. |
| "The base is obviously main" | Establish the destination from evidence, or ask if it is genuinely ambiguous. |
| "The push was rejected — force-push will fix it" | A rejection means the remote moved. Investigate; force-push only on the user's explicit request. |

---

> Source: obra/superpowers (MIT), absorbing the former
> `finishing-a-development-branch` skill. Adapted for coding-kit:
> authorization and workspace cleanup cross-referenced.