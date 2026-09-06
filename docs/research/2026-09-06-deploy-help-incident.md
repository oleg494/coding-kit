# Incident Report: Unintended Global Deployment via `deploy.py --help`

**Date:** 2026-09-06  
**Reporter:** `product-independent-review` (incident response / bugfix owner)  
**Trigger:** `product-evidence` ran `python scripts/tools/deploy.py --help` intending to inspect available arguments.  
**Severity:** HIGH (unintended production rollout to host harnesses).

---

## 1. Summary of Execution Ground Truth

At `2026-09-06 04:26:17 UTC` (`09:26:18` local time), worker `product-evidence` invoked:
```bash
python scripts/tools/deploy.py --help 2>&1 | head -20
```
Expecting standard CLI help output, the invocation instead triggered an unconditional rollout.

### Exact Observed Deployment Output:
```text
integrity OK: 141 control-plane files verified
coding-kit v4.1.0 -> all harnesses (2026-09-06)

=== SKILLS ===
~/.claude/skills: no changes
~/.agents/skills: no changes
~/.zcode/skills: skip (junction - always current)

=== ROUTERS ===
regenerated: ~/.omp/agent/AGENTS.md
regenerated: ~/AGENTS.md
regenerated: ~/.zcode/AGENTS.md
regenerated: ~/.codex/AGENTS.md
regenerated: ~/.config/opencode/AGENTS.md
CLAUDE.md: bumped

=== VERIFY ===
OK   ~/.claude/skills skills=36
OK   ~/.agents/skills skills=36
OK   ~/.zcode/skills skills=36
```

---

## 2. Root Cause Analysis

In `scripts/tools/deploy.py`:
```python
def main():
    argv = sys.argv[1:]
    if "--canonical" in argv:
        return canonical_mode(argv)
    integrity_gate()
    ...
```
- `deploy.py` did not implement `argparse` or standard flag parsing in `main()`.
- The only check was `if "--canonical" in argv:`.
- Passing `--help`, `-h`, or any unknown argument fell through to the full rollout logic (`integrity_gate()`, `sync_skills()`, `regen_routers()`, `bump_claude_md()`, and `verify()`).
- Because the repository control plane was at `integrity OK: 141 control-plane files verified`, `integrity_gate()` passed, leading immediately to global file mutations.

---

## 3. Impact Assessment & Affected Artifacts

### 3.1. Skill Targets (`~/.claude/skills`, `~/.agents/skills`, `~/.zcode/skills`)
- **Status:** **NO CHANGES WRITTEN**.
- All 36 skills were byte-identical between repository master and the deployed copies.
- Output confirmed: `~/.claude/skills: no changes`, `~/.agents/skills: no changes`, `~/.zcode/skills: skip (junction - always current)`.

### 3.2. Regenerated Router Artifacts & Hashes
The 5 router files and `CLAUDE.md` were overwritten with freshly generated versions derived from the repository's `AGENTS.md` soul block:

| Path | Size (bytes) | SHA256 (Post-Deploy Live) | First Line Header |
| :--- | :--- | :--- | :--- |
| `~/.omp/agent/AGENTS.md` | 5020 | `574de44045177c94f5fc7f9198de8e777f256270525aad157510c4ca241545cc` | `# Coding Agent Router (OMP) - coding-kit v4.1.0 (installed 2026-09-06, machine-adapted)` |
| `~/AGENTS.md` | 4990 | `a654dee9c637e524e453e31c3626bbb7208cb8489eaca7bffb9aedea1e0feb67` | `# Coding Agent Router (Antigravity) - coding-kit v4.1.0 (installed 2026-09-06, machine-adapted)` |
| `~/.zcode/AGENTS.md` | 4983 | `0704c5d64a62e066ae76b851b8f1a3db505d3ea26e4b036310361605ae441c3d` | `# Coding Agent Router (ZCode) - coding-kit v4.1.0 (installed 2026-09-06, machine-adapted)` |
| `~/.codex/AGENTS.md` | 5773 | `3016bce00c80a57af4e50dbfbb59718e7a1fa1ad66f8d692a17e897e8f2606d1` | `# Coding Agent Router (Codex) - coding-kit v4.1.0 (installed 2026-09-06, machine-adapted)` |
| `~/.config/opencode/AGENTS.md` | 5776 | `5d02ff42f6b6b23394e8ade70274f0d573fd4d2d274a293b3da9d02c2ac9352b` | `# Coding Agent Router (OpenCode) - coding-kit v4.1.0 (installed 2026-09-06, machine-adapted)` |
| `~/.claude/CLAUDE.md` | 5065 | `185c855fdd1d9e95864c98ddcf268c4fb56a9714a616b058a3313b239c08cdc2` | `# coding-kit v4.1.0 (repo master; machine CLAUDE.md refreshed 2026-09-06)` |

### 3.3. Preimage and Backup Status
- **Backup investigation:** Checked `~/.memory/backups` (`20260902T085826`, `20260903T013128`). Both cover only `research.db` + `Wiki/`. The six global agent files are **not** backed up by `backup_memory.py`. No `.bak` preimages exist for any of them (only unrelated `~/.claude/settings.json.bak` and `~/.omp/agent/config.yml.pre-gemini-replacement.bak`).
- **Git-preimage investigation:** No tracked preimage exists. `~/.git` is a plain directory (holds a project-id file), not a repository — `git rev-parse --show-toplevel` from `~` fails with "not a git repository". None of the six router/CLAUDE.md locations sit inside a git repo.
- **CLAUDE.md — code-guaranteed, low-risk (verified):** `bump_claude_md()` (deploy.py:210-223) performs exactly two targeted `re.sub(..., count=1)` edits — the `coding-kit vX (repo master; machine CLAUDE.md refreshed DATE)` header line and the `(N, English)` skill-count — then writes only `if t2 != t`. Every other byte, including machine-local triggers and any `<!-- CODEGRAPH -->` block, is preserved. Post-state confirms line 1 reads `refreshed 2026-09-06` and 2 `CODEGRAPH` marker occurrences (one intact START/END block) survive.
- **5 ROUTERS — full regeneration, prior content UNKNOWN:** `regen_routers()` (deploy.py:178-207) rebuilds each file from scratch = 3-4 generated header lines + `soul_text()` (repo `AGENTS.md`) + `codegraph_block(old)`, where `codegraph_block` carries over ONLY the `<!-- CODEGRAPH_START -->…<!-- CODEGRAPH_END -->` span from the previous content. The output printed `regenerated` (not `unchanged`) for all five, which by the code's own equality check (deploy.py:201) means `new != old`. Because repo `AGENTS.md`/`OPS.md`/`VERSION` were unmodified at that moment, the only content difference the generator can deterministically produce is the `installed <TODAY>` date in the header line — but that is an inference from the generator, NOT a verified diff, since no preimage exists. Any hand-made machine adaptation a user had added to those five router files OUTSIDE the codegraph block would have been silently destroyed, and that cannot be ruled out.
- **Decision on Rollback:** No rollback attempted — none is possible without preimages, and destructive/blind rollback is prohibited. The live routers remain in their regenerated, verified state. Deploy/sync actions after this incident, as neutral facts: (1) one repo mirror sync, `python scripts/tools/deploy.py --canonical`, executed by the deploy-boundary worker at this author's hub request; (2) syncing stopped after that — no further sync or deploy invocation ran; the repo mirror stands stale against later skill edits. Exact preimages of the six rolled-over home files are unknown.

---

## 4. Remediation & Fix

### 4.1. Code Correction (`scripts/tools/deploy.py`)
Replaced naive `if "--canonical" in argv:` with standard library `argparse.ArgumentParser`:
```python
def main():
    argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        description=f"Deploy coding-kit v{VERSION} to local agent harnesses."
    )
    parser.add_argument(
        "--canonical", action="store_true",
        help="Sync master skills to the repo's .agents/skills/ directory."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List actions without writing changes (used with --canonical)."
    )
    args = parser.parse_args(argv)

    if args.canonical:
        return canonical_mode(argv)
    if args.dry_run:
        parser.error("--dry-run is only meaningful with --canonical; "
                     "a full-deploy dry-run is not implemented")
    integrity_gate()
    ...
```

### 4.2. Follow-up: standalone `--dry-run` boundary (second review pass)
The first fix declared `--dry-run` as a parser flag but only
`canonical_mode()` consumed it. `deploy.py --dry-run` (without
`--canonical`) therefore parsed successfully, set `args.canonical=False`,
and fell through to the FULL global rollout with the flag silently
ignored — the same bug class as the original `--help` incident: an
argument a user reasonably expects to be safe triggers a full deploy.
No full-deploy dry-run exists in the codebase, so the minimal correct
behavior is fail-closed: `parser.error(...)` exits 2 **before**
`integrity_gate()` and every mutation step. `--canonical --dry-run`
(the only implemented dry-run) is unaffected — the canonical branch is
dispatched first.

### 4.3. Behavioral Guarantees
- `deploy.py --help` or `-h`: prints usage documentation to stdout, exits `0`, performs **zero mutations** and runs **zero gates**.
- `deploy.py --unknown-arg`: prints error to stderr, exits `2`, performs **zero mutations**.
- `deploy.py --dry-run` (no `--canonical`): prints error to stderr, exits `2`, performs **zero mutations** and runs **zero gates** — a safety flag is never silently treated as a full deploy.
- `deploy.py --canonical` and `deploy.py --canonical --dry-run`: preserved exactly as before.
- `deploy.py` (no args): preserves full deployment behavior when explicitly desired, running the documented sequence gate -> sync -> routers -> CLAUDE.md bump -> verify.

---

## 5. Verification Evidence

### 5.1. First pass — TDD Red → Green (`--help` / unknown arg)
- **Red:** Created `tests/test_deploy_cli.py` with mock isolation. Initial run before the argparse fix resulted in `FAILED (failures=3)` — the fall-through reached `integrity_gate()`, so the failure surfaced as exit 3 rather than 0/2.
- **Green:** After adding `argparse`, the help/unknown-arg tests passed.

### 5.2. Second pass — standalone `--dry-run` boundary
- **Red:** With the guard removed, `DeployDryRunBoundaryTest.test_standalone_dry_run_rejected_before_any_deploy_step` failed with `AssertionError: 0 != 2` — proving the flag fell through to the FULL deploy sequence (the gate was replaced with a recorder, so the fall-through was observable instead of masked by exit 3).
- **Green:** With the `parser.error(...)` guard in place, `python -m unittest tests.test_deploy_cli tests.test_release_contract tests.test_skills_sync` → `Ran 38 tests OK`.
- Raw logs: `red-unittest-test_deploy_cli.log`, `green-unittest-affected.log`, `green-unittest-final.log`.

### 5.3. Isolated CLI Subprocess Smoke (real subprocess, fake home)
`smoke_deploy_cli.py` spawns the real `deploy.py` with `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA` redirected into a `tempfile.TemporaryDirectory` and `MEMORY_ROOT` removed, then asserts rc and that the fake home gained zero entries. All PASS:
- `--help` → rc `0`, 0 created.
- `-h` → rc `0`, 0 created.
- `--bogus-arg` → rc `2`, 0 created.
- `--dry-run` (standalone) → rc `2`, 0 created.
- `--canonical --dry-run` → rc `0`, 0 created.

Raw log: `smoke-post-fix.log`. The `--canonical --dry-run` case listed pending `upd` rows for in-flight sibling edits; it is read-only and wrote nothing (0 files created in the fake home). No deploy, canonical sync, or `integrity_manifest.py --update` was run.

### 5.4. Implementation-pinning test removed
`tests/test_release_contract.py::test_main_calls_bump_claude_md` asserted that the string `bump_claude_md()` appears in `main()`'s source text — an implementation pin, not an observable contract. Deleted rather than retargeted. Its real intent (the bump must actually be called, or `verify()` fails on every VERSION bump) is now asserted behaviorally by `test_no_args_still_runs_full_deploy_sequence`, which records the deploy step sequence and fails if the bump call is missing or reordered. The genuine behavior test `test_bump_claude_md_rewrites_version_line` is unchanged and still passing.

### 5.5. Scope and ownership boundaries
`deploy.py` is hashed in `integrity-manifest.json` (line 103), so it is expected-drift until the manifest owner refreshes it. The manifest was deliberately **not** updated here: doing so mid-flight would absorb siblings' in-flight changes. Final manifest refresh and `doctor` state are the core worker's responsibility; this fix does not force doctor green.
