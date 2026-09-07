# Independent code review — deployment boundaries and verification (2026-09-07)

**Date:** 2026-09-07  
**Reviewer:** Notion AI, independent review pass requested by the maintainer  
**Status:** static review; findings open, not remediated  
**Baseline:** local `coding-kit/`, `VERSION` = `4.2.0`; commit and GitHub parity not established  
**Scope:** installation, deployment, cross-database search, selected regression tests and CI configuration

This note records the review delivered in chat. It is not a fresh test run.
The repository instructions were inspected as review material, not installed
or adopted as the reviewer's operating instructions.

## 1. Executive judgment

The project has a useful engineering foundation, but its deployment path
still assumes too much about the maintainer's existing machine. The primary
risk is not code style: it is the boundary between kit-owned files and user
state, followed by checks that can establish the wrong kind of success.

Do not rewrite the whole project on this evidence. First harden ownership,
preflight, change previews and final-path verification before treating the
rollout as safe for unfamiliar home directories.

## 2. Method and limits

Read directly through the maintainer's local MCP connection:

- `scripts/install.py` and `scripts/tools/deploy.py`;
- `memory/db-tools/search_all.py` and the opening/schema portion of `build.py`;
- `tests/test_install.py` (selected sections), `tests/test_deploy_cli.py`,
  and `tests/test_skills_sync.py` (selected sections);
- `.github/workflows/test.yml` and `.github/workflows/claude.yml`;
- introductory project documentation and `VERSION`.

No project scripts, tests, deployments, live evaluations or external service
calls were executed. No source/configuration fixes were made. No claim is
made that CI currently passes, that the entire repository was reviewed, or
that the local tree equals GitHub. Line references describe the inspected
snapshot and may move after edits.

Severity: **P1** = address before broad rollout because user data can be
lost; **P2** = reliability or verification defect that should be fixed next.
All scenarios below are inferred from visible control flow, not dynamically
reproduced in this pass. They are not claims that damage has occurred.

## 3. Findings

### CR-01 — P1: existing user files can be adopted and overwritten without ownership checks

**Evidence:** `scripts/tools/deploy.py`, `sync_one_skill()` (line 116),
`sync_skills()` (line 137), `regen_routers()` (line 178).

`sync_skills()` synchronizes every master skill before reading the target's
ownership manifest. For an existing skill directory, `sync_one_skill()`
replaces differing files and deletes files absent from the master.
Separately, `regen_routers()` regenerates existing router files, preserving
only the specially marked CODEGRAPH block.

**Failure scenarios:**

1. A user has a locally authored skill whose name also appears in the kit.
   A first deploy replaces its content and removes its local-only files,
   despite the previous manifest not establishing kit ownership.
2. A target such as `~/AGENTS.md` contains unrelated user instructions.
   Regeneration replaces them unless they happen to be inside the one
   preserved CODEGRAPH block.

**Impact:** an ordinary rollout can destroy configuration the kit did not
create. A subsequent byte comparison against the master will pass precisely
because the user's previous state has been replaced.

**Counterpoint:** authoritative synchronization of an explicitly kit-owned
copy is reasonable. The defect is assuming ownership from path/name alone,
not synchronization itself. Local-only skill directories with distinct names
are preserved; that does not protect name collisions.

**Remediation:** establish ownership before any writes; treat unknown
existing targets as conflicts. Use managed blocks for shared rule files,
backups before replacement, and an explicit adoption policy.

**Regression evidence to add:** a same-name, unowned local skill and a
pre-existing router with custom text survive a refused deployment unchanged.
Separately verify that explicitly owned targets can be updated.

### CR-02 — P1: manifest entries reach recursive deletion without path validation

**Evidence:** `scripts/tools/deploy.py`, `sync_skills()`, removal loop over
`mani.get("skills", [])`.

An entry is joined directly to the destination and passed to
`shutil.rmtree(dest / name)`. The inspected path does not validate a manifest
schema, a single-component skill name, or containment under the destination.

**Precondition:** the target `.kit-manifest.json` is malformed, manually
edited or substituted. A traversal or absolute-path entry may direct cleanup
outside the intended skills directory, subject to filesystem permissions.
This is not an established remote vulnerability or privilege escalation:
the problematic input is local state.

**Impact:** a bookkeeping file controls a destructive filesystem operation
without a checked boundary.

**Remediation:** validate the complete manifest before mutation; accept only
valid single-component skill names; check resolved containment; explicitly
handle symlinks/junctions. Invalid state must fail closed before sync begins.

**Regression evidence to add:** reject traversal, absolute paths, wrong JSON
shapes and link-based boundary escapes using disposable temporary fixtures;
verify that an outside sentinel remains intact.

### CR-03 — P2: full deployment can fail after mutation on a clean machine

**Evidence:** `scripts/tools/deploy.py`, `bump_claude_md()` (line 210),
`main()` (line 326); `tests/test_deploy_cli.py`,
`test_no_args_still_runs_full_deploy_sequence`.

`bump_claude_md()` reads `~/.claude/CLAUDE.md` without checking whether it
exists. `main()` calls it after skills synchronization and router
regeneration. Missing Claude configuration therefore causes a
`FileNotFoundError` after other targets have already changed.

**Failure scenario:** deploy into a fresh home, or into a user's environment
that has a different agent but no Claude rules file.

**Impact:** a failed command leaves a partially deployed environment. An
unrelated agent's configuration becomes an implicit prerequisite.

**Test gap:** the no-argument sequence test replaces all deployment steps
with recorders. It verifies orchestration order, not successful deployment
into a genuinely empty home.

**Remediation:** preflight all required inputs before mutation. Create the
missing configuration intentionally or skip unselected harnesses; make
partial failure and rollback behavior explicit.

**Regression evidence to add:** run the real full deployment path in a fully
isolated temporary home, with no Claude configuration, and verify either
successful selected-target installation or refusal with zero mutations.

### CR-04 — P2: canonical dry-run omits deletions performed by the real run

**Evidence:** `scripts/tools/deploy.py`, `canonical_mode()` (line 266) and
`sync_one_skill()`.

The dry-run branch reports additions and changed master files. The real
branch also deletes extra files within a skill and removes skill directories
absent from the master. Those actions do not share one computed change plan.

**Failure scenario:** the canonical copy contains an obsolete skill while
all current master files match. The preview can report `no changes`, but
execution removes the obsolete directory.

**Impact:** the preview cannot reliably communicate destructive effects.
This is a preview/execution mismatch, not a claim that dry-run itself writes.

**Remediation:** compute one add/update/delete plan. Dry-run renders it;
execution applies the same plan. Include manifest-only changes when relevant.

**Regression evidence to add:** stale files and stale skill directories
appear in the preview; applying the plan produces exactly the advertised
changes and nothing else.

### CR-05 — P2: installer validates the clone's engine rather than the user's final entry point

**Evidence:** `scripts/install.py`, `link_engine()` and the build/smoke
sequence near the end of `main()`; `tests/test_install.py`,
`test_real_dir_is_preserved`.

If `<MEMORY_ROOT>/db-tools` is an ordinary directory, the installer preserves
it and returns from the linking step. Build and smoke checks nevertheless
execute scripts from `ENGINE` in the current clone, not from the preserved
user-facing `db-tools` path.

**Failure scenario:** the existing directory contains only a personal file
or an incomplete/older engine. The clone's search works, so installation can
report `search smoke: OK`, while the documented command through
`~/.memory/db-tools/...` is unavailable or invokes a different engine.

**Test gap:** `test_real_dir_is_preserved` creates a directory containing
`precious.txt` and expects install success. It protects data preservation,
but does not prove the installed command path is usable.

**Remediation:** distinguish "existing data preserved" from "usable engine
installed". Validate the exact final entry point and report an unresolved
real-directory conflict as incomplete installation, not success.

**Regression evidence to add:** successful installation must support the
documented CLI via the final path; a conflicting real directory is preserved
and produces an explicit incomplete-install result.

## 4. Strengths observed

- Regression tests exercise meaningful behavior: Wiki preservation across
  reinstalls, smoke failures and no-mutation CLI help paths.
- Engine-link replacement attempts to restore the previous link on failure.
- Windows paths are passed through environment variables to PowerShell,
  rather than interpolated into command text.
- Cross-database search uses read-only SQLite connections and parameterized
  search values.
- CI is configured for Windows and Ubuntu. Configuration was read; run
  results were not inspected or reproduced in this pass.

## 5. Architectural interpretation

The recurring gap is between a guarantee's wording and the oracle used to
check it. Call order is not successful deployment. Equality to the master is
not preservation of user state. A working script in a clone is not a working
installed entry point.

The absolute anti-warning/anti-confirmation language in `AGENTS.md` also
deserves a separate behavioral review. The kit does contain instruction
precedence and destructive-action confirmation provisions; the concern is
how competing rules interact, not a claim that no safeguards exist.

## 6. Recommended sequence — not executed

1. Define ownership and path boundaries; reject conflicts before writes.
2. Use a single computed deployment plan for preview and execution.
3. Add backup/rollback behavior and explicit target selection.
4. Verify final installed entry points in fresh and unfamiliar environments.
5. Add behavioral regression tests for CR-01 through CR-05.

No source fix, test pass, commit, deployment or incident resolution is
claimed by this document. A companion logic analysis is a separate review,
not additional evidence that these code scenarios were reproduced.
