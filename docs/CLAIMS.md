# Claims ledger

Every public claim the kit makes is tracked here with either a runnable
verification command, an in-repo evidence artifact, or an explicit
`unverified` marker. This file is release documentation, not a live monitor:
`verified` means the command is runnable and the last recorded green run is
cited; it does not mean the command was re-run while you read this.

## Status semantics

- `verified` — the row carries a runnable command AND an evidence artifact
  (the release record or covering tests). Rerun the command to reproduce.
- `evidence-only` — an artifact documents the claim, but the repo ships no
  runnable reproduction for it.
- `unverified` — the repo carries no reproduction and no in-repo artifact.
  `unverified (historical)` marks observations about past states that the
  current release does not claim to reproduce.

Freshness: verified rows cite the last tagged release's recorded evidence
([CHANGELOG](CHANGELOG.md)). Between tags the working tree may drift
intentionally; every gate is re-run and re-recorded at tag time (see
[Release acceptance gates](#release-acceptance-gates)).

## Claims

| ID | Claim | Verification command | Evidence | Status |
|---|---|---|---|---|
| C-01 | Full test suite passes on Windows/Python 3.12 (846 passed, 20 skipped, 488 subtests at v4.10.0) | `python -m pytest tests -q` | [CHANGELOG](CHANGELOG.md) v4.10.0 verification record | verified |
| C-02 | CI kit gates run on both Windows and Ubuntu with Python 3.12 and read-only permissions | `python -m pytest tests/test_ci_workflow.py -q` | [.github/workflows/test.yml](../.github/workflows/test.yml) | verified |
| C-03 | Doctor: 14/14 repository and memory checks green at v4.10.0 | `python scripts/doctor.py` | [CHANGELOG](CHANGELOG.md) v4.10.0 verification record | verified |
| C-04 | Integrity manifest: zero control-plane drift (182 files pinned at v4.10.0) | `python scripts/tools/integrity_manifest.py` | [integrity-manifest.json](../integrity-manifest.json) | verified |
| C-05 | File-size gate green (0 hard violations at v4.10.0) | `python scripts/tools/check_file_sizes.py --ci` | [CHANGELOG](CHANGELOG.md) v4.10.0 verification record | verified |
| C-06 | Trap-suite dry-run validates scenario inputs (DRY_RUN rows, exit 0) | `python eval/runner.py --inline-skills` | [CHANGELOG](CHANGELOG.md) v4.10.0 input-validation record | verified |
| C-07 | Task-runner dry-run validates task inputs (DRY_RUN rows, exit 0) | `python eval/task_runner.py --dry-run` | [CHANGELOG](CHANGELOG.md) v4.10.0 input-validation record | verified |
| C-08 | Trigger-eval input validation covers colocated cases plus the 80-query fallback corpus | `python eval/trigger_eval.py --queries auto` | [eval/trigger_queries.json](../eval/trigger_queries.json) | verified |
| C-09 | Full deploy to all local harnesses; repeat deployment changes no bytes | `python scripts/tools/deploy.py --dry-run` (must report no pending changes after a deploy) | [CHANGELOG](CHANGELOG.md) v4.10.0 verification record | verified |
| C-10 | Canonical mirror `.agents/skills/` is byte-identical to repo masters | `python scripts/tools/deploy.py --canonical --dry-run` (must report no changes) | [tests/test_canonical_deploy.py](../tests/test_canonical_deploy.py) | verified |
| C-11 | All 37 profile-declared skills exist on disk; manifest equals disk | `python scripts/doctor.py` (manifest check) | [profile.yml](../profile.yml) | verified |
| C-12 | Installer bootstraps the memory store and passes the search smoke check | `python scripts/install.py` (look for `search smoke: OK`) | [tests/test_install.py](../tests/test_install.py) | verified |
| C-13 | `memory-warmup.py` honors `MEMORY_ROOT` and is not auto-run by generated routers | `python -m pytest tests/test_v29.py tests/test_deploy_cli.py -q` | [tests/test_v29.py](../tests/test_v29.py) | verified |
| C-14 | Backup/restore drill: DEGRADED snapshots refused; drill exits 0 only after `PRAGMA integrity_check` and search verification pass | `python -m pytest tests/test_backup_memory.py -q` | [tests/test_backup_memory.py](../tests/test_backup_memory.py) | verified |
| C-15 | Handoff resume exit codes 0/1/2; stale evidence marked, embedded commands never executed | `python -m pytest tests/test_handoff.py -q` | [tests/test_handoff.py](../tests/test_handoff.py) | verified |
| C-16 | Deploy rolls back earlier skills/routers on mid-deploy failure and keeps a recovery directory if rollback itself fails | `python -m pytest tests/test_deploy_rollback.py -q` | [tests/test_deploy_rollback.py](../tests/test_deploy_rollback.py) | verified |
| C-17 | Trend compares only matching `comparison_id`s; baseline files are never rewritten; dry/zero/malformed runs seed nothing | `python -m pytest tests/test_trend.py tests/test_trend_baselines.py -q` | [tests/test_trend.py](../tests/test_trend.py) | verified |
| C-18 | Rigor A/B acceptance gate can reject a candidate policy change | `python -m pytest tests/test_rigor_gate.py -q` | [tests/test_rigor_gate.py](../tests/test_rigor_gate.py) | verified |
| C-19 | Prompt confinement: bare host commands refused; `docker:` executors with declared read-only mounts only | `python -m pytest tests/test_prompt_confinement.py -q` | [tests/test_prompt_confinement.py](../tests/test_prompt_confinement.py) | verified |
| C-20 | Hermes adapter generates the owned-skill projection into `SOUL.md` | `python -m pytest tests/test_hermes_adapter.py -q` | [tests/test_hermes_adapter.py](../tests/test_hermes_adapter.py) | verified |
| C-21 | Autonomous supervisor records resumable state, gates completion on the independent verifier, and honors a `STOP` file | `python -m pytest tests/test_autonomous.py -q` | [tests/test_autonomous.py](../tests/test_autonomous.py) | verified |
| C-22 | Telemetry measures duration; token totals are user-reported, not measured cost | `python -m pytest tests/test_telemetry.py -q` | [tests/test_telemetry.py](../tests/test_telemetry.py) | verified |
| C-23 | Historical DeepSWE A/B observations (6/9 solved in both arms, +21% steps, +41% prompt tokens) | — | — | unverified (historical) |
| C-24 | v4.5.1 policy-calibration observations (stated-next-action evidence) | — | External release notes only: <https://github.com/oleg494/coding-kit/releases/tag/v4.5.1> | evidence-only |
| C-25 | The kit makes no demonstrated universal coding-quality or token-efficiency improvement claim | — | [README](../README.md) "Evidence and limitations" | evidence-only |

Notes on the unverified rows:

- C-23: raw artifacts are retained outside this repository and the repo
  ships no reproduction script; the numbers describe a small historical
  sample (36-skill manifest), not the current release. They are recorded
  for transparency, not offered as evidence.
- C-24/C-25: these rows document deliberate abstinence or externally hosted
  records; no in-repo runnable check exists by design.

## Release acceptance gates

All of the following must be green on the exact tree being tagged, and the
results recorded in [CHANGELOG](CHANGELOG.md) before the version tag is
created. CI must also be green on both OS legs for the tag commit.

1. **Full suite**: `python -m pytest tests -q` — zero failures; skips must
   be limited to documented environment prerequisites (Docker/task images,
   Windows symlink/8.3 aliases, platform-specific prerequisites).
2. **Doctor**: `python scripts/doctor.py` — every check green (14/14 at
   v4.10.0; the count may grow with new checks, never shrink silently).
3. **Integrity**: `python scripts/tools/integrity_manifest.py` — zero
   files drifted/added/removed versus `integrity-manifest.json`; the pinned
   file count is recorded in the changelog.
4. **Size gate**: `python scripts/tools/check_file_sizes.py --ci` — zero
   hard violations and zero baseline-grown entries.
5. **Dry-run validations** (input validity only, no live model claims):
   `python eval/runner.py --inline-skills`,
   `python eval/task_runner.py --dry-run`,
   `python eval/trigger_eval.py --queries auto` — each exits 0; DRY_RUN
   rows record `passed: 0` by design.
6. **Deployed mirror sync**: run `python scripts/tools/deploy.py`, then
   `python scripts/tools/deploy.py --dry-run` must report no pending
   changes; `python scripts/tools/deploy.py --canonical --dry-run` must
   report no changes (canonical mirror byte-identical).
7. **CI kit gates**: the tag commit's GitHub Actions runs are green on
   both `windows-latest` and `ubuntu-latest`.

## Rollback

Rollback triggers: any gate above that cannot be made green on the tagged
tree, unexplained integrity drift discovered after tagging, or a deployed
harness misbehaving because of the release.

- **Git tag revert.** Revert with `git revert <offending commit>` (do not
  rewrite published history or force-move tags). Re-run gates 1–6 on the
  reverted tree, redeploy with `python scripts/tools/deploy.py`, and
  confirm the harness dry-run reports no pending changes. A revert
  commit moves forward; tags are never silently re-pointed.
- **Integrity baseline regeneration.** Regenerate only after the drift
  diff has been reviewed file-by-file and every changed control-plane
  file is an intended change: run
  `python scripts/tools/integrity_manifest.py --update`, commit
  `integrity-manifest.json`, and require `python scripts/doctor.py` green
  again. Regenerating without review is forbidden — the manifest exists
  to detect control-plane compromise, and an unreviewed update launders
  exactly that.
- **Memory root untouched.** Releases, deploys and rollbacks operate only
  on the repository and deployed skill copies. `~/.memory/` (`MEMORY_ROOT`)
  is never written by any release or rollback procedure; it lives outside
  the repository and is not rebuilt from it. If an authorized memory
  migration is ever part of a change, take a backup first with
  `python scripts/tools/backup_memory.py` and prove it with
  `--restore-drill` before proceeding.
