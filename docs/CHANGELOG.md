# Changelog — Coding Agent OS
- **v4.6.0 (2026-09-13)** — Hermes integration stack, offline confinement, deploy preview:
  - **conditional design references (2026-09-10):**
    - Extended `design-system` with gap-driven reference selection, evidence-to-decision translation, external-content trust boundaries, and explicit unexecuted-verification reporting. `dashboard-design` delegates shared visual research without a duplicate catalog or decorative-removal quota.
    - Added one four-source guide with public-text inspection scope and access caveats, five trigger cases, and seven trap-suite scenarios. Synced the repository skill mirrors only; machine-wide installations are unchanged.
    - Evidence: `python -m pytest tests/test_evals_colocation.py tests/test_skill_lifecycle.py -q` — 16 passed. Text-only model probes exposed imagined reference observations, excessive token layering, and ambiguous verification claims; instructions were corrected. Six of seven judged responses passed before the final repair; the repaired evidence-reporting case and nearby local-fix case passed replay. Responses/verdicts are in local `eval/results/design-reference-probe.json`. The local-fix response still suggested optional unused-local-variable cleanup, so scope adherence is not guaranteed. No rendered UI comparison or improvement in visual quality is claimed.
  - **deploy preview, integrity restamp, asset pin, recovery drill (2026-09-11):**
    - **CK-01/1 preview**: `python scripts/tools/deploy.py --dry-run` now prints the complete full-deploy plan — per-skill add/upd/del actions per sync target, manifest create/update, router regeneration, CLAUDE.md bump — computed by the same plan functions the apply path uses (`execute_skills(..., dry=True)`, `regen_routers(dry=True)`, `bump_claude_md(dry=True)`; `--canonical --dry-run` unchanged). No transaction is opened, no directory created, no snapshot taken, no secret content printed.
    - Evidence (preview): `python -m pytest tests/test_deploy_cli.py tests/test_deploy_rollback.py tests/test_deploy_ownership.py tests/test_skills_sync.py -q` — 59 passed, 1 skipped, 5 subtests. The equivalence case seeds a drifted owned skill, a stale manifest entry, an old CLAUDE.md and an unrelated user file, then asserts the preview's planned path set equals the exact set a real deploy creates/changes/deletes in an identical fixture. Subprocess cases run `--dry-run`/`--help`/unknown-arg with `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `MEMORY_ROOT` redirected and assert the temp home and the repository stay byte-identical; a third case performs a real full deploy into a disposable repository copy and asserts byte-identical skill mirrors, regenerated routers, manifest contents and an untouched original repository. Machine-wide run of the preview exited 0 with md5-identical managed files before/after; no machine-wide deploy was executed.
    - **File-size gate**: the preview pushed `scripts/tools/deploy.py` to 1020 lines (hard limit 1000, `check_file_sizes.py --ci` exit 1). The link/junction-aware I/O primitives moved to `scripts/tools/_deploy_fs.py` (same path-based loading fallback as `_deploy_tx.py`), leaving deploy.py at 903 lines — the gate passes again and the primitives now have a single home.
    - **Integrity restamp**: the committed tree had drifted from `integrity-manifest.json` since 5c189e2 — `skills/design-system/SKILL.md`, `skills/dashboard-design/SKILL.md` and seven added `eval/scenarios/design-*.md` were unrecorded, so `integrity_gate()` failed with exit 3 and refused every rollout. `integrity_manifest.py --update` restores a consistent record — `integrity OK: 163 control-plane files verified` after this session's additions — and the manifest is restamped whenever control-plane files change.
    - **Stale asset-count pin**: `EXPECTED_SCENARIO_COUNT` 31 → 38 (the seven design scenarios); `test_scenario_count_is_21` renamed to `test_scenario_count_is_38`. The release-contract suite was red on the committed tree before this change.
    - **CK-06 recovery drill — `--restore-drill` failed on a clean home**: the findings probe ran `findings.py` with `MEMORY_ROOT` stripped, so `log.py` resolved `_compat.chulan_root()` from `~/.memory`; a `MEMORY_ROOT` user (or any clean/CI home without `~/.memory`) got a `RuntimeError` at import, `doctor_rc=1`, `search_hits=0` and drill exit 1 on a healthy restore. The probe now runs against a throwaway marker-carrying root (`ROOT_MARKERS`), with the database under test still pinned by `MEMORY_ROOT_RESEARCH_DB`. Regression `tests/test_backup_memory.py::BackupDrillTest::test_drill_findings_probe_needs_no_ambient_memory_root` fails before the change (`{'ok': False, 'doctor_rc': 1, 'search_hits': 0}` with the import traceback) and passes after; `python -m pytest tests/test_backup_memory.py tests/test_install.py tests/test_doctor.py -q` — 51 passed.
    - **CK-06 drill executed (Windows, isolated root)**: documented install → save → search → re-run installer (upgrade; only SQLite sidecars and the rebuilt `wiki.db` changed) → save survives → `--list` → `--restore-drill` exit 0 with `integrity_ok: true`, `findings.ok: true`, `doctor_rc: 0`, `search_hits: 1`. README now documents the backup/`--list`/`--restore-drill`/`--restore` commands (previously only OPS.md mentioned backups). A Linux environment was not exercised in this session.
    - **CK-03 confinement backend (first increment)**: `eval/rigor/container.py` adds a Docker-backed OS boundary — read-only root filesystem, `--cap-drop=ALL`, `no-new-privileges`, no network, only the task directory mounted writable, no host environment forwarded, and a timeout that kills the whole container tree. `escape_probes()` runs a deterministic model-free battery inside that boundary (host-path reads including `/mnt/<drive>` and traversal, sentinel writes including `/etc` and through a symlink created in the writable mount, a child-process write, a network connect, the Docker socket, and SHA-256 comparison of host environment values) and the **host** decides pass/fail; no probe output is taken on trust. `require_confined_executor()` gates every live rigor run: dry runs are unaffected, live runs are refused with a precise reason because the executor command would run on the host.
    - Evidence (CK-03): `python -m pytest tests/test_rigor_container.py tests/test_rigor_runner.py tests/test_rigor_gate.py -q` — 29 passed, with the battery and the timeout probe executed against Docker 29.7.2 / `python:3.12-alpine`: all nine checks true (`host_mount_writable`, secret never read, outside writes blocked, no host sentinel, symlink/subprocess/network/Docker-socket blocked, host env absent), and `timeout_kills_descendants` → `timed_out` with the container gone. Docker Desktop was started locally for this verification (Linux containers). **Not yet gated:** the other live runner, `eval/runner.py --executor` (exercised by `tests/test_ablate.py` with fake executors) — next CK-03 increment; the confinement gate in `rigor/runner.py` blocks only that runner's live path today.
  - **native-memory experiment preparation (2026-09-12):** `eval/memory_experiment.py prepare --notes` now seeds isolated real findings databases using the native CLI, exports runnable search commands and environment paths, and preserves repository-only versus identical-inline controls. CLI smoke retrieved the expected source in all four independently prepared memory arms; an independent fresh-root drill observed no cross-case results. `python -m pytest tests/test_memory_experiment.py -q -p no:cacheprovider` — 6 passed. No model calls or memory-utility claims; answer retrieval fields remain explicitly self-reported, and container mounts require rebasing exported absolute memory paths.
  - **offline confined executor and verifier (2026-09-12):** `eval/rigor/runner.py` accepts explicit Docker executors; candidate verification runs with the trusted task directory mounted read-only and only the candidate directory writable. Independent verification: `python -m pytest tests/test_rigor_container.py tests/test_rigor_runner.py tests/test_rigor_gate.py -q -p no:cacheprovider` — 38 passed. `python -m eval.rigor.runner --offline-task 006-import-boundary` produced PASS; the `escape-verifier` executor produced FAIL (`clean_pass=False`, `verifier_rc=1`, `escaped=[]`). The offline CLI currently returns exit 0 for a scored FAIL: consumers must inspect the result, not only the process exit code. This proves the exercised model-free path, not live-model readiness. Open prerequisites: a model CLI image with verifier dependencies, an explicit credential channel, and endpoint-restricted networking (`@net` currently enables unrestricted Docker bridge networking). The separate `eval/runner.py` live path remains outside this milestone.
    - Second escape-battery execution on 2026-09-13: 10/10 (host-judged).
  - **Hermes adapter, first package (H0–H3) (2026-09-13):**
    - New `scripts/tools/hermes_adapter.py` (preview/apply/restore) + `adapters/hermes.md`: Hermes-only integration through three owned surfaces — generated projection `<home>/kit-skills/coding-kit/<skill>`, a `skills.external_dirs` entry, and a delimited routing block inside `SOUL.md`. `UNIVERSAL.md`'s Hermes section now points here (the rsync-into-`~/.hermes/skills/` recipe is retired by contract); `profile.yml` registers the adapter.
    - H0/H1 evidence (disposable server profile, hermes-agent v0.21.2 @ `476a45f4f336`, no model calls, mtime-guarded live roots): external root gives full catalogue visibility (37/37 in `skills_list` AND the rendered prompt index, category `coding-kit`); local same-name copies claim the name while `coding-kit/<name>` still loads the kit body; `archive_skill` really archives local bundled-named copies (live hazard: 3 kit names collide with `prune_builtins: true`) but refuses external skills via two guards; missing external roots are silently skipped. H1a found no decision-level recall miss in the sampled sessions (517 scanned, 75 with any memory surface); the reproduced failure is native MEMORY.md capacity saturation (95–99% of 2,200 chars, one write rejected). Evidence: `docs/research/2026-09-13-hermes-h1-evidence.md`.
    - Regression evidence: `python -m pytest tests/test_hermes_adapter.py -q` — 16 passed (preview read-only, owned-surfaces-only apply, idempotence, update/retire-own, foreign preservation, legacy `--retire-legacy` gate, collision warnings, exact-state restore, mid-apply rollback, missing-kit conflict). Release/deploy contract intact after manifest restamp: `python -m pytest tests/test_hermes_adapter.py tests/test_deploy_cli.py tests/test_release_contract.py -q` — 42 passed, 5 subtests; `integrity_manifest.py --update` — 169 files hashed; `check_file_sizes.py` — hard 0, gate green. Live Hermes migration (H4) remains a separately authorized task; no gateway config changed.
    - H3 integrated drill (server, disposable profile, real adapter CLI + native v0.21.2 render): 17/17 — preview read-only; apply → `skills_list` 37/37 category `coding-kit` + prompt index + `skill_view coding-kit/debug-incident-protocol` full body; seeded finding reachable via isolated `MEMORY_ROOT` findings route; fresh-process restart persists discovery; idempotent re-apply byte-identical; kit-v2 update retires only the removed own skill while a foreign `hand-made` copy survives; `restore` returns owned surfaces to exact pre-integration bytes. Full-suite evidence: `python -m pytest tests -q` (see run log); package scope `95 passed, 1 skipped, 5 subtests` over adapter+deploy+sync+release contracts; `integrity_manifest.py --update` — 169 files; `check_file_sizes.py --ci` green.
    - Defect fixed during H3: the rollback anchor (`.kit-hermes-restore.json`) was rewritten by every apply, so `restore` rolled back only to the latest update instead of the pre-integration state. Now the anchor is written once at first integration and preserved across updates (regression: `test_restore_anchors_to_first_integration`).
  - **Hermes recovery correction and lexical-search evidence (2026-09-13):** earlier broad H3 recovery acceptance below was refuted by exact-byte probes. `hermes_adapter.py` + `_hermes_recovery.py` now preserve individual owned preimages (CRLF, binary assets, empty directories and prior absence), keep foreign siblings, include recovery records in the handled-failure transaction, and remove migrated legacy skills from recursive discovery. Preview retires only previously-owned names. Local adapter regression: 23 passed; separate saved-before/current CLI probe: 0/6 → 6/6. No post-repair native-Hermes integration or live migration is claimed. See [research evidence](research/2026-09-13-hermes-h1-evidence.md#follow-on-local-research-and-adapter-repair).
    - `dev-wiki` and its repository mirror now explain lexical matching, short queries, opening complete notes and checking empty results without imposing retrieval on repository-sufficient tasks. Stateless synthetic comparisons: search contract 0/16 → 16/16; stale/conflicting/repository controls 6/6 in both arms with 8 additional retrieval requests; procedure check-selection 3/3 in both arms. These measure stated decisions, not executed coding quality or cross-harness transfer. No new memory provider or automatic recall.
    - Post-repair native-Hermes probe (disposable profile): 9/9 — catalogue 37/37, curator archive refused for projection skills, repeat apply idempotent, restore byte-exact and removes the projection.
  - **Executed code-synthesis comparisons** (research, no product change): stateless synthesis under thin core / targeted procedure / full-kit-inline prompts, generated code confined in Docker, independent behavioral verifiers with faulty-control sensitivity. Both tasks passed 2/2 in every condition — no kit condition demonstrated a measurable benefit over the thin core; n=2 repeats per cell is directional only, and the targeted condition exists only in the procedure scenario. Retained as reusable harness under `eval/results/autonomous-knowledge-20260913/`; harder discriminating variants are the named next step. See [research evidence](research/2026-09-13-hermes-h1-evidence.md#executed-code-synthesis-comparisons-2026-09-13-second-package).
  - Release hygiene: VERSION/profile.yml/skill metadata restamped 4.5.1 → 4.6.0 (minor: new backward-compatible tooling; no contract break); `EXPECTED_VERSION` updated; OPS banner carries the new surface (trap-suite count corrected 31 → 38). Integrity-manifest scope fix: `in_scope` now excludes `eval/results/` — it had pinned 36 mutable validation artifacts contrary to its own docstring (205 → 170 files), so the next validation run would have failed doctor integrity and blocked every deploy (exit 3); red-first regression added.
  - Post-release hygiene (master after the tag): `NoPersonalPathTest` extended to scan tracked `eval/results/**` text artifacts — red-first, it caught the committed evidence JSONs leaking `C:\Users\<user>\AppData\Local\Temp` throwaway directories. Five JSONs scrubbed to `<TEMP>`/`<HERMES_HOME>` placeholders (JSON validity preserved); throwaway temp-dir names only, no secrets. The tagged tree `06444b2` still carries the raw paths; `master` is the fixed reference.

> Full release history. Moved out of OPS.md in v3.4.4 (64% of OPS was history
> re-read by the model every session; OPS keeps only the living contract).

> **Claim discipline:** every "fixed"/"verified" claim below must cite evidence for its actual scope: regression, smoke run, rendered observation, or applicable doctor check. Reuse evidence only for the unchanged checked state. Sub-agent verdicts and static policy checks do not establish product improvement.

- **v4.5.1 (2026-09-10)** — policy contradiction calibration:
  - Reconciled core authorization, phase handoffs, review ownership, evidence reuse, and minimalism: complete authorized local work without repeated phase approval; preserve read-only scope, stop/revocation, and explicit authority for outward, destructive, spending, and memory actions.
  - Removed fixed-count research/retry rituals, mandatory extra workspaces and documents, and missing reviewer-template dependencies. Independent review findings block only changes that depend on unresolved information; reviewer signoff remains reviewer-owned.
  - Removed tests that pinned policy wording rather than behavior. Retained executable verdict/count coverage and Agent Skills frontmatter validation; aligned the authorized-work and converge-audit scenario briefs with the completion contract.
  - Evidence: baseline/candidate text probes both selected the expected action in 12/12 choice cases. In one repeated free-response design-handoff case, baseline requested approval in 3/3 trials and candidate continued in 3/3; other corrected contradictions often already resolved correctly under baseline authority precedence. These probes measure stated next action, not end-to-end coding quality or a general win rate.
  - Calibration verification: `python -m pytest tests -q` — 740 passed, 2 skipped, 87 subtests passed. Durable prompts, responses, source snapshots and verification provenance are retained in the maintainer's local evidence archive (`coding-kit-evidence-2026-09-05/policy-calibration-2026-09-09/`); that archive is not distributed with the release. Repository skill mirrors ship the corrected policies; existing machine-wide harness installations require a separate deployment.

- **v4.5.0 (2026-09-08)** — opt-in autonomous work selection, portable skill + optional foreground supervisor:
  - **`autonomous-work` skill**: a broad authorization to choose and continue useful work ("do useful work", "keep going without asking", "работай сам") loads `skills/autonomous-work/SKILL.md`; ordinary bounded requests keep their existing scope. It is task opt-in — not an always-on skill and not a `MODE:` override, so `STRICT_AUDIT`/read-only constraints are unchanged (`scripts/doctor.py:check_override` still accepts only the two existing modes).
  - **Core loop**: select the highest-value evidence-backed in-scope objective → smallest correct change → verify by observation → record durable evidence → continue; no busywork inflation, no invented scope, no unobserved success claim.
  - **Durable state & handoff**: mission, scope, completed-with-evidence, current objective, blockers, next action are recorded in files so a later session resumes without re-deriving them.
  - **Stop & revocation**: user stop word, explicit revoke, or a `STOP` file wins immediately — before the next spawn and during a live run.
  - **Boundaries**: autonomy never implies outward (push/deploy/publish/send), destructive, spending/credential, or memory-write authority; those still require explicit authorization per `AGENTS.md`.
  - **Optional supervisor CLI** (`scripts/tools/autonomous.py`): foreground stdlib supervisor, `--workspace --mission --executor --verify [--state-dir] [--max-iterations] [--timeout]`. Commands resolve to argv, never a POSIX shell (Windows `.cmd`/`.bat` need `cmd`). State defaults to `<workspace>/.autonomous` (`state.json`, `logs/`, atomic writes, resumable) and is written before **every** executor launch, including iteration 1 of a fresh run (schema version `1`), so a crash at or before the spawn still leaves resumable state; `checkpoint.json` is a model proposal removed before each spawn, with its absolute path supplied on executor stdin (`Checkpoint: <path>`) and via `AUTONOMOUS_CHECKPOINT`. Checkpoints are untrusted claims, never commands: a `continue` checkpoint's `evidence` strings are shape-checked only (list of strings) and are never independently verified in the loop; independent `--verify` runs only against a `complete` claim. Exit `0` only on independently verified completion; `1` failed/exhausted/blocked/stalled/invalid saved state; `130` user stop. The stall detector compares normalized checkpoint JSON (`status`+`summary`+`next_action`+`evidence`): three identical consecutive `continue` **reports** stop as stalled — it detects repeated reports, not absence of progress, so reworded text evades it while `--max-iterations` bounds the invocation. Iteration exhaustion preserves resumable state and is not completion; resume rejects workspace/mission/executor/verify mismatch while `--max-iterations`/`--timeout` may be raised, and unreadable/malformed/unsupported saved state (including version ≠ `1`) is rejected with exit `1` and a one-line stderr diagnostic before any spawn, leaving the existing `state.json` byte-identical rather than silently reinitializing it. No daemon, installed hook, new dependency, or implicit auto-approval; a filesystem workspace is not a security sandbox.
  - **Routing & counts**: `AGENTS.md` §4 routes broad autonomous authorization to the skill; `profile.yml` `skills.domain` declares it (37 skills = 5 always-on + 32 domain); co-located trigger queries grow to 92 across 13 skills (6 for `autonomous-work`; the 80-query central fallback is unchanged); `OPS.md`, `SKILL_RUNTIME.md`, and `README.md` document the opt-in and its boundaries. Design and acceptance criteria: `docs/research/2026-09-08-autonomous-mode.md`.
  - **Verified supervisor coverage**: `tests/test_autonomous.py` exercises continuation after false completion, resume after iteration limit, pre-spawn state durability on fresh and resumed runs, malformed/missing checkpoint rejection, rejection of malformed/unsupported saved state without overwriting it (19-case parametrized), executor failure, configuration mismatch, stop before launch and during execution, and stalled termination on identical repeated `continue` reports. The stall regression proves repeated identical reports stop the run; it does not prove detection of no-progress work whose reports were reworded, which only `--max-iterations` bounds. The blocked-stdin STOP regression failed before the fix and passed afterward; the parent now polls cancellation while a daemon writer owns stdin. Five `eval/scenarios/autonomous-*.md` files cover portable behavior expectations; runner dry-run validates their structure, not model compliance. A real DeepSeek Flash run continued across two executor processes and passed an independent verifier for both range defects; details in the design evidence section. A second real DeepSeek Flash run tested autonomous selection: given a workspace whose backlog mixed a customer-reported CSV export corruption with a cosmetic rename and a speculative plugin framework, the model chose the CSV defect, fixed it with stdlib `csv.writer`, left `backlog.txt`/`contacts.json` byte-unchanged, and exited `0` in one iteration after an independently rerun external verifier passed (`PASS: CSV round-trip preserves commas, quotes, newlines, empty fields`). This is one trial under one mission, not a reliability rate; it ran on the pre-fix runner while the state owner was still editing `scripts/tools/autonomous.py`.
- **v4.4.0 (2026-09-08)** — memory organization, dynamic project taxonomy, qualitative importance & warmup lifecycle:
  - **Generic Dynamic Project Registry**: `findings.py` replaces hardcoded user project names with dynamic project discovery from `db/*.db` + optional `projects.json` + generic slug validation (`^[a-z0-9][a-z0-9_-]{0,63}$`); only reserved constant fallbacks in code are `{"portable", "unknown"}` (`tests/test_memory_organization.py::MemoryOrganizationTest::test_add_finding_with_project_and_importance`).
  - **Considered Importance & Mutation Audit**: `findings.py add` and `findings.py edit` validate importance against `high`, `normal`, `low`, `unreviewed`; edit input rejects arbitrary strings; all add/edit mutations automatically record an audit trail in `finding_classifications` (`tests/test_memory_organization.py::MemoryOrganizationTest::test_edit_validates_importance_and_updates_audit`).
  - **Atomic Batch Classification**: `findings.py classify <file.json> [--dry-run] [--force]` provides an atomic batch tool that validates slugs/levels, preserves user-curated records, and rolls back on any record error (`tests/test_memory_organization.py::MemoryOrganizationTest::test_batch_classify_atomic_rollback_on_error`, `test_batch_classify_idempotent_preserves_user_curated`).
  - **Legacy RO Schema Evolution**: `search_findings` and `findings_db.connect_read` handle legacy databases gracefully in read-only mode by projecting defaults (`'unknown' AS project`, `'unreviewed' AS importance`, `NULL AS superseded_by`) when columns or tables are absent without crashing (`tests/test_memory_organization.py::MemoryOrganizationTest::test_legacy_ro_projection_defaults`).
  - **Search & Warmup Usability & Lifecycle Guard**: `search_all.py` supports `--project <slug>` and `--importance <level>` flags (`tests/test_memory_organization.py::MemoryOrganizationTest::test_search_all_project_and_importance_filtering`); `memory-warmup.py` enriches findings stats with project distributions, surfaces high-priority architectural invariants and decisions per project with explicit `[unverified]` status badges (`tests/test_memory_organization.py::MemoryOrganizationTest::test_high_priority_feed_labels_unverified_status`), and prioritizes unanchored findings in `unsure_feed` by qualitative importance over low-importance checkpoints with legacy schema fallback and supersession exclusion (`tests/test_memory_organization.py::MemoryOrganizationTest::test_unsure_feed_prioritizes_high_importance_over_low_checkpoints`, `test_unsure_feed_excludes_superseded_unanchored_findings`, `test_unsure_feed_legacy_schema_fallback`).
  - **Classification Audit Lifecycle**: `findings.py del` atomically purges associated `finding_classifications` rows upon finding deletion (`tests/test_memory_organization.py::MemoryOrganizationTest::test_cmd_del_cleans_up_finding_classifications_preserving_others`).
  - **Deploy master junction support & foreign link rejection**: in `sync_skills()` and `verify()`, supported master junctions (`dest.resolve() == SKILLS.resolve()`) are recognized and safely skipped with zero writes (preserving documented `~/.zcode/skills` single-source junction installs per README and `adapters/zcode.md`); foreign destination links and link ancestors (`has_link_ancestor`) strictly fail closed (`tests/test_deploy_ownership.py::TestDeployWriteBoundariesRegression::test_sync_skills_rejects_destination_ancestor_link_and_avoids_mutation`).
  - **All-deploy abort**: `main()` orchestrates stage preflights; a preflight failure in skills, routers, or CLAUDE.md aborts before filesystem mutations (`tests/test_deploy_ownership.py::TestDeployWriteBoundariesRegression::test_skills_preflight_failure_aborts_whole_deploy_before_router_or_claude_mutations`).
  - **Stale skill removal link preflight**: manifest-listed stale removal candidates (`mani.get("skills", [])`) are scanned in Phase 1 preflight (`scan_skill_links`), aborting before mutations if nested links/escapes exist (`TestDeployWriteBoundariesRegression::test_sync_skills_stale_removal_nested_link_refuses_preflight_before_writes`).
  - **Non-regular file preflight**: `CLAUDE.md`, router targets, and router `.kit-bak` paths verify `not path.is_file()` during preflight.
  - **Master skill source preflight & canonical protection**: master skill directory links rejected in Phase 1; canonical sync enforces safe boundary writes; `SkillsReport` clean-cutover dataclass without dict shims.
  - **Bounded rollback of caught I/O failures**: bounded rollback restores prior bytes and absent states after caught I/O or verification failure using pre-mutation snapshots (`tests/test_deploy_rollback.py::TestDeployRollbackRegression`); failed rollbacks preserve a dedicated recovery directory; crashes or concurrent external interference remain unhandled.
  - **Policy residue alignment**: `AGENTS.md` single-sourced action authorization separates local commits, task-scoped temp fixtures, and external actions (repo documentation cannot establish external authority); `skills/yagni` frontmatter description aligned with OPS/body present-value and change-isolation boundaries (removing unconditional single-consumer dogma). Details in `docs/research/2026-09-07-third-round-remediation.md`.
  - **Standing user authorization policy alignment**: aligned `skills/fable-method`, `skills/fable-judge`, and reference flowcharts/failure-modes with `AGENTS.md:29-38` to recognize explicit standing user authorization (`AUTH: standing authorization`) alongside direct in-conversation quotes (`AUTH: user said`); enforced anti-spoofing boundaries (documentation, memory findings, or self-authored lines cannot grant authority) and preserved instruction hierarchy (`scripts/doctor.py`).
- **v4.3.1 (2026-09-07)** — second-round external audit remediation (audit of v4.3.0 delivered in chat; residual defects after the v4.3.0 pass):
  - **Deploy write boundary (P1)**: `scan_skill_links()` preflight-scans existing target skill dirs for symlinks/junctions/escapes; nested links now refuse the destination with zero writes. Integrated into adoption (`dirs_byte_identical`), `sync_skills` preflight, `sync_one_skill` write path and `verify()` (`tests/test_deploy_ownership.py::TestResidualDefects`). *Footnote: At tag release time, preflight covered skill destinations only; canonical `.agents/skills` and destination ancestor links remained unshielded until the third-round remediation.*
  - **Global preflight (P2)**: `sync_skills()` is two-phase — all skill destinations validated (manifest, ownership, links) before ANY mutation; any conflict → zero writes to skills, all failures reported together (`TestResidualDefects::test_global_preflight_all_destinations_fail_before_any_write`). *Footnote: In v4.3.1, this preflight was restricted to skill destinations; router and CLAUDE.md stages still continued afterwards in main() until the third-round all-deploy abort fix.*
  - **Canonical preview parity (P2)**: `.kit-manifest.json` create/update is now part of the computed plan; `--dry-run` advertises exactly what execution applies (`TestResidualDefects::test_canonical_manifest_change_advertised_in_dry_run_and_executed`, `test_canonical_identical_manifest_dry_run_no_changes`).
  - **Canonical verdict arithmetic (LR-03 completion)**: `verdict_from_counts(critical, warning, unverified=0)` — unverified>0 caps at VERIFIED WITH CAVEATS; matches skills/fable-judge examples, which tests extract and compare (`tests/test_review_protocol.py`).
  - **JSON search lifecycle (LR-05 completion)**: `search_all.py --json` findings hits now carry `superseded_by`/`verified` additively; pinned db/path/snippet keys unchanged (`tests/test_search_all.py`).
  - **Residual contradiction alignment (LR-01/02/04/07/09 completion)**: fable-method Step 2 rule 6 and Step 4.8 aligned with the single commit/intent policy; verification-before-completion Gate Function honors checked-state evidence reuse; OPS §4 YAGNI rule 1 matches skills/yagni; README n=9 takeaway made descriptive (no general reliability claim). LR-07 footnote: the OPS §1 identity-pillar YAGNI wording still carried the consumer-count dogma at tag time; aligned to §4 rule 1 in follow-up commit 7bc9268 (post-tag, on master).
- **v4.3.0 (2026-09-07)**:
  - **Deploy & install hardening (CR-01..05)**:
    - Remediated 5 deployment and installation defects identified in `docs/research/2026-09-07-independent-code-review.md`.
    - Kit ownership established before any writes in `deploy.py`: skill directories require target manifest listing, non-existence, or byte-identical match to master for safe adoption; unowned differing skill directories refuse with conflict status without mutations; routers require kit markers to modify and create `.kit-bak` backups before replacement (`tests/test_deploy_ownership.py::TestCR01Ownership`).
    - Manifest validation before mutation: complete manifest schema, single-component names, traversal, absolute path, and junction/symlink checks fail closed before sync writes (`tests/test_deploy_ownership.py::TestCR02ManifestValidation`).
    - Preflight missing harness configs: missing `~/.claude/CLAUDE.md` is skipped as harness-not-present without crashing `bump_claude_md()` or `verify()` (`tests/test_deploy_ownership.py::TestCR03Preflight`).
    - Single computed deployment plan: `canonical_mode` computes a unified add/upd/del/rm-dir plan shared between `--dry-run` preview and execution (`tests/test_deploy_ownership.py::TestCR04SinglePlan`).
    - Installer final-path verification: `install.py` runs index builds and search smoke against the final `<root>/db-tools` path; conflicting real directories are preserved and signaled with an INCOMPLETE status (`tests/test_install.py::InstallTest::test_real_dir_is_preserved`, `test_successful_install_validates_final_entry_point`).
  - **Policy coherence (LR-01..10)**:
    - Remediated 10 logic and policy boundaries identified in `docs/research/2026-09-07-independent-logic-review.md`.
    - Single-sourced commit and authorization policy in `AGENTS.md` and `OPS.md`, cross-referenced in phase skills (`brainstorming` AUTHORIZATION-GATE, `git-workflow-and-versioning` Commit Policy).
    - `fable-method` intent gate distinguishing code defects from test/specification disagreements.
    - `fable-judge` per-claim verdict states where unverifiable load-bearing claims cap verdicts at VERIFIED WITH CAVEATS.
    - `verification-before-completion` evidence discipline explicitly keyed to verified system state.
    - `search_all.py` search hits display superseded/verified lifecycle badges and metadata (`tests/test_search_all.py::FindingsLifecycleMetadataTest`). The recall routes in `AGENTS.md`, `OPS.md` §5 and `dev-wiki` now require resolving lifecycle validity (superseded → replacing finding; unverified → confirm) before answering.
    - Explicit side-effect boundaries for memory operations across `AGENTS.md`, `OPS.md`, and `dev-wiki`.
    - `yagni` and `architecture-simplicity` reframed as present-value engineering heuristics.
    - `engineering-persona` allows calibrated uncertainty where evidence is incomplete.
    - `SKILL_RUNTIME.md` irreducible core retains authorization, stop conditions, and exceptions.
    - `README.md` evaluation claims clearly partition health/activation/adherence metrics from task success/cost without causal overreach.
    - `skill-authoring` candidate state introduced with concrete promotion and retirement criteria.
  - **Sources**: `docs/research/2026-09-07-independent-code-review.md` and `docs/research/2026-09-07-independent-logic-review.md`.

- **v4.2.0 (2026-09-06)**:
  - **Instruction precedence & authorization gate**: clarified hierarchy
    (host system/developer > user instructions > kit skills) in AGENTS.md and
    OPS.md; replaced brainstorming hard gate with authorization gate to allow
    proceeding on authorized reversible local work without false halts.
  - **Verification scope calibration**: calibrated testing discipline to run
    checks appropriate to the scope of change without redundant whole-suite
    ceremony on untouched components or claiming unrun suites.
  - **Deploy CLI safety boundary**: added argparse CLI interface to
    `scripts/tools/deploy.py` so `--help` and invalid flags exit safely without
    triggering unintentional deployment sequences.
  - **Runner & tooling resilience**: restored stdlib fallback in `lint_wiki.py`
    and `scripts/doctor.py` for environments lacking PyYAML; handled Windows
    cross-drive execution in findings tests; fixed backup CLI exit code on
    skipped databases; byte-level integrity manifest hashing.
  - **Trap-suite & eval expansion**: expanded trap-suite from 24 to 26
    scenarios (`authorized-work-proceeds`, `calibrated-testing`).
  - **Licensing & attribution**: preserved `license: Proprietary` on
    `skills/windows-encoding-fixes` with explicit README disclosure without
    unsubstantiated claims of an all-MIT bundle.

- **Post-v4.1.0 deploy CLI boundary fix (2026-09-06)**:
  - `scripts/tools/deploy.py` now parses CLI flags via argparse; `--help`
    no longer executes a full rollout (previously `main()` ran the deploy
    path on any invocation, regenerating host routers and bumping
    `~/.claude/CLAUDE.md`). `def main()` signature and `bump_claude_md()`
    behavior preserved. Regressions: `tests/test_deploy_cli.py`
    (`test_help_flag_exits_zero_and_causes_zero_mutations`,
    `test_unknown_argument_exits_2_and_causes_zero_mutations`,
    `test_standalone_dry_run_rejected_before_any_deploy_step`,
    `test_no_args_still_runs_full_deploy_sequence`);
    `tests/test_release_contract.py::test_bump_claude_md_rewrites_version_line`
    unchanged and green. Incident record:
    `docs/research/2026-09-06-deploy-help-incident.md`. Skill-source
    inventory produced alongside:
    `docs/research/2026-09-06-priority-skill-sources.md` (+ `-inventory`
    companion).
- **Post-v4.1.0 instruction-precedence & verification-scope calibration (2026-09-06)**:
  - Instruction hierarchy added to AGENTS.md and OPS.md (host
    system/developer above user, user above kit skills) plus a
    skill-stall diagnosis reflex: a pause must name the exact SKILL.md and
    quote the line. Brainstorming HARD-GATE replaced by an
    AUTHORIZATION-GATE — proceed on authorized reversible local work; stop
    only for irreversible/external/destructive actions not already
    authorized, money/auth/privacy/data-safety paths, outcome-changing
    ambiguity, or a plan-first request; prior explicit authorization is not
    re-asked and host restrictions stay the host's gate.
  - Verification scope calibrated across superpowers, SKILL_RUNTIME,
    test-driven-development, dispatching-parallel-agents,
    verification-before-completion, testing-discipline: checks appropriate
    to the change by default, broadened when scope warrants (shared code
    touched, or a failure the targeted check exposed); re-running an
    unchanged check with no new changes is ceremony, claiming an unrun
    suite is a lie.
  - Retired prose pins deleted (BrainstormingClarifyGateTest; the
    "5 targeted questions"/"before any plan exists" needles); trap suite
    24 -> 26 with two behavior scenarios (authorized-work-proceeds,
    calibrated-testing); brainstorming dot graph deleted (prose is the
    single process description). Evidence: tests/test_sdd_gates.py
    (revised needles + counts), tests/test_release_contract.py
    EXPECTED_SCENARIO_COUNT=26, tests/test_ops_diet.py (OPS <=150 lines),
    focused suites 105 passed / 25 subtests (incl. test_deploy_cli,
    test_skills_sync), doctor integrity 143 files OK,
    eval/runner.py dry-run ALL GREEN 26 scenarios, trigger-eval 86 queries
    OK. Design: docs/superpowers/specs/2026-09-06-instruction-precedence-calibration-design.md.
- **Post-v4.1.0 onboarding corrections + R1 (2026-09-05)**:
  - Fresh memory root is warmup-clean: `install.py` now seeds
    `Wiki/index.md` and `Wiki/log.md` (absent-only; never overwrites user
    data). Regressions: `test_fresh_install_seeds_wiki_cycle_files`,
    `test_seeded_root_is_warmup_clean`,
    `test_rerun_preserves_existing_wiki_cycle_files` (2 red pre-fix via
    `git stash` of install.py, green post-fix). Verified: doctor 14/14
    GREEN, full suite 673 passed / 1 skipped.
  - Public docs corrected to runner-derived counts (24 scenarios, 6 tasks
    incl. 2 canaries, 36 skills; trigger-eval 86 co-located across 12
    skills via `--queries auto`, 80-query central fallback across 10
    skills); Gemini-CLI retirement claim removed (repo verified active);
    install split into memory-bootstrap vs agent-integration phases with a
    runnable save/search demo; root-MIT vs `windows-encoding-fixes`
    `license: Proprietary` conflict disclosed as unresolved (no rights
    adjudication, no deletion workaround). Evidence:
    `docs/research/2026-09-05-public-onboarding-check.md`.
- **Post-v4.1.0 reliability checks (2026-09-05)**:
  - Backup CLI exits 1 when a database is skipped rather than reporting
    success for a degraded snapshot. JSON diagnostics and snapshot evidence
    remain available. Regression:
    `test_backup_cli_fails_when_database_is_skipped`.
  - Integrity hashes preserve invalid UTF-8 bytes instead of merging them
    through replacement decoding; CRLF/CR/LF equivalence remains intact.
    Regressions: `test_invalid_utf8_byte_changes_are_reported` and
    `test_newline_styles_remain_equivalent`.
- **Post-v4.1.0 rigor measurement corrections (2026-09-05)**:
  - Count uncached + cache-read + cache-creation input in stream usage;
    prefer reported final totals, then model totals, then assistant totals.
    Empty final usage no longer hides usable fallback data; explicit zero
    remains authoritative. Regressions: `tests/test_rigor_runner.py`.
  - Compare median per-task effort ratios, not a ratio of medians. The
    replacement regression changes the verdict under the old formula:
    `test_effort_ratios_pairs_per_task_medians_not_ratio_of_medians`.
  - Persist `input_token_accounting=total_input_v1`; exclude token ratios
    unless both arms carry this marker, with an explicit finding. Other
    effort metrics remain available. Regression:
    `test_legacy_input_tokens_cannot_satisfy_fast_savings`.
  - Historical results remain unchanged; old cache-unaware totals cannot
    establish total-input savings. Input volume is not billed cost/quota.
- **Post-v4.1.0 hardening (skills licensing & memory warmup)**:
  - **Skills supply chain license compliance**: standardized `license: MIT`
    frontmatter across 34 skills (all 36 skills licensed now: 35 MIT, 1
    Proprietary). Doctor check `supply chain` is now `OK: 36 skills, all licensed`
    (0 warnings). Verified on the real 36-skill tree by `scripts/doctor.py`;
    checker behavior is covered by `tests/test_security_map.py`. Deployed
    canonical copies synced to `.agents/skills`, `~/.agents/skills`, and
    `~/.claude/skills`.
  - **Memory warmup unsure contradiction hardening**: added filter to exclude
    superseded contradiction links (`NOT EXISTS s.kind='supersedes'`) so past
    resolved regressions don't surface in warmup. Regression test:
    `test_superseded_contradiction_is_excluded_from_unsure_feed` in
    `tests/test_v29.py` (20 passed).
  - **Memory findings hygiene**: anchored findings #233, #234, #236 with
    sources and verify commands; resolved contradiction links around #60 in
    `research.db` (findings #237 recorded and verified).
- **v4.1.0 (memory findings remediation)**: research.db из write-only памяти
  стал retrievable. Retrieval: `findings.py search` ранжирует bm25(10.0,1.0)
  вместо id DESC, честный «found/showing», highlight, prefix-retry,
  fallback для dot-запросов (`5.3` больше не крашит FTS5); `search_all.py`
  (маршрут AGENTS.md §4) теперь union'ит findings-стор и мерджит глобально по
  bm25 — до этого research.db был структурно невидим (нет files_fts);
  warmup печатает «в чём память НЕ уверена» (открытые contradicts + unanchored
  за 7 дней + pull-шаблон) вместо сырого фида последних топиков. Trust:
  `add --supersedes` + бейджи (скалярный подзапрос, не LEFT JOIN — второй
  supersedes не размножает строку), tag-нормализация на записи + свип 40
  comma-строк prod, dedup-хинт «edit id=N», auto-source только URL-формы,
  verify_cmd исполняется как shell-строка (quote-guard на записи), doctor-
  команда self-heal (FTS rank=1 integrity-check). DR: restore-контракт —
  pre-snapshot деградирует на CORRUPT и отказывает на LOCKED (busy ≠ corrupt:
  `_is_corruption`), sidecars удаляются после замены, backup API ограничен
  preflight-пробой (CPython backup() крутит BUSY вечно), degraded-снапшоты
  (`.degraded` вместо `.complete`) не градуируются в restore-point (restore
  rc 3 без --include-degraded, drill fail-fast, --list тегирует, отдельный
  prune cap=3). Регресс-тесты: test_ftsquery.py, test_search_all.py (25),
  test_v29.py (unsure-feed + шаблон), test_findings_lifecycle.py (supersedes
  fanout, URL-only, deployed-parity), test_findings_migration.py (trigger
  self-heal, log DDL-guard, ro-contract), test_backup_memory.py (23: locked/
  corrupt/degraded/retention), canaries P2/P3 переписаны в after-state.
  642 passed, doctor 14 GREEN, manifest 126.
- **v4.0.3 (dead-harness cutover)**: Gemini CLI install plane removed —
  Google retired the CLI on 2026-06-18 (individual accounts stopped
  being served; official discussion google-gemini/gemini-cli#28017);
  Antigravity is the successor and keeps its own deploy target. Removed:
  gemini harness target in scripts/tools/deploy.py, adapters/gemini.md,
  profile.yml adapters entry, README/UNIVERSAL install stanzas. Kept:
  `normalize_gemini` + fixture (tests/test_transcript_normalize.py) —
  historical chat-JSON archives remain readable; usage_audit skips the
  absent store. Also fixed a latent POSIX-branch bug in
  tests/test_install.py rollback test: `mock.patch.object(Path,
  "symlink_to", ...)` lacked `autospec=True`, so the side-effect never
  received `self`, raised TypeError instead of OSError and the
  rollback branch was silently untested off-Windows (verified green:
  test_install.py 17 passed; the bug was latent on Windows where the
  nt/PowerShell branch runs instead). Regression tests:
  test_release_contract.py (version 4.0.3, 36 skills),
  test_integrity_manifest.py (adapter pin removed, 127 files).

- **v4.0.2 (audit remediation)**: closes the verified v3.5.0–v4.0.1
  release-wave audit. Honest-oracle fixes: newly added regression tests no
  longer count as verifier weakening (trade-off: addition-only hacks such
  as appending `+assert True` are not diff-detectable — the verify.py AST
  oracles remain that guard), and both divide canaries now require
  `test_divide_by_zero`; MAST frontmatter is persisted as `mast_mode` on
  every scenario row. Trust/DR fixes: SQLite sidecars are never copied,
  successful backups carry `.complete`, restore-drill fails on corrupt DBs,
  incomplete backups do not satisfy freshness, and completed backups retain
  the newest ten; the integrity manifest now pins eval scenarios/tasks/
  trigger queries/baselines. Standards/privacy fixes: frontmatter
  descriptions require a scalar string, canonical-skill drift detects extra
  dirs/files, committed result paths are scrubbed, SQLite sidecars are
  ignored, and memory search closes read-only handles on exceptions using
  Windows-safe URIs. Interchange/devflow fixes: Hermes tool call/result halves
  normalize to one record, GenAI token-total is documented as a kit
  extension, contract drift uses root CONTRIBUTING.md, dead review/
  materiality code was removed, and the OPS relocation proof now pins real
  content. Regression tests: test_clean_pass.py, test_canaries.py,
  test_mast_labels.py, test_backup_memory.py, test_doctor.py,
  test_integrity_manifest.py, test_result_hygiene.py, test_search_all.py,
  test_transcript_normalize.py, test_contract_drift.py,
  test_review_protocol.py, test_ops_diet.py, test_otel_names.py. Verified:
  pytest = 546 passed, 1 skipped, 73 subtests; doctor 14 checks GREEN;
  file-size gate hard 0; deploy ALL OK. Release contract: version 4.0.2,
  36 skills. Historical annotated tags v3.5.0 through v4.0.0 published.
- **Post-v4.0.0 docs update**: README gains a "Measured cost (external
  benchmark)" section from the 2026-09-01 DeepSWE A/B (findings #199):
  pass rate 6/9 vs 6/9 (no effect), +21% steps / +41% prompt tokens on
  identical outcomes, task-dependent flips (igel 24/24-vs-6/24 win, opa
  2/5-vs-5/5 loss), n=9 trend-not-verdict caveat. Verification: section
  rendered in README lines 74–93; `check_file_sizes.py --ci` green
  (README 115 lines, docs soft limit 300). Claim source is an external
  benchmark run, not a kit test — no regression test applies; retained
  artifacts are under `~/Desktop/deepswe-ab/keep/`.
- **v4.0.0 (wave6 interchange)**: MAJOR — observability interchange layer
  from the 2026-09-01 roadmap. (1) GenAI telemetry aliases: registry-
  aligned names where available plus explicit kit extensions (notably
  `gen_ai.usage.tokens_total`; old keys kept one release). results_io emits
  aliases alongside legacy keys with identical values; task rows carry
  gen_ai.prompt.name from TASK.md frontmatter;
  load_reported_usage accepts input/output token split; trend prefers new
  keys. (2) ATIF v1.7 export layer:
  eval/atif_export.py to_atif() — one Trajectory per run (agent
  coding-kit, steps, tool_calls linked via source_call_id, per-step
  token/cost metrics, llm_call_count), structural validator vs Harbor
  RFC tables, CLI --from/--out; smoke export of real run
  tasks-20260829-083643 (10 steps, validator clean); token_ids/logprobs
  skipped. (3) Multi-harness transcript normalization:
  eval/transcript_normalize.py — trajectory-v1 records (meta/user/system/
  assistant/tool, tool results linked by tool_call_id) with readers for
  OMP JSONL, Claude Code JSONL, Gemini chats, Hermes state.db;
  usage_audit.py rewritten to consume ONLY normalized records;
  sanitized fixtures per harness under tests/fixtures/transcripts/.
  Live run 2026-09-01 since 2026-08-01: 850 sessions audited (omp 145,
  claude 678, hermes 27; gemini store present, 0 sessions in window) —
  189 real sessions, 5.42 memory calls/session. Regression tests:
  test_otel_names.py (8), test_atif_export.py (7),
  test_transcript_normalize.py (8); corpus restamped 4.0.0. Verified:
  pytest = 513 passed, 1 skipped, 57 subtests; doctor 14 checks GREEN.
  Release contract: version 4.0.0, 36 skills.
- **v3.9.0 (wave5 devflow-gates)**: SDD + review discipline from the
  2026-09-01 roadmap. (1) spec-kit gates in the superpowers cycle:
  clarify-before-plan (<=5 targeted questions folded into the spec
  before any plan exists), checklist sovereignty (implementer never
  toggles reviewer-owned - [ ] markers; counts unchecked, asks),
  converge pass (strictly append-only anti-false-done audit; its only
  write is ADDING missed work; severity-graded findings) — in
  skills/superpowers + OPS.md §3 + skills/brainstorming; trap scenario
  24 converge-audit.md (mast FM-3.1). (2) Cloudflare review protocol:
  "What NOT to Flag" preamble (no theoretical risks, no
  defense-in-depth when primary suffices, no issues in unchanged code,
  no "consider library X"), 3-value severity with machine-checkable
  counts line, verdict_from_counts(critical, warning) canonical
  implementation in scripts/tools/review_protocol.py (critical>0 ->
  REFUTED; warning<=2 -> VERIFIED; else VERIFIED WITH CAVEATS) —
  fable-judge's rubric example lines are extracted by tests and must
  behave identically (doc = executable spec); break-glass keyword
  (срочно-пропустить) skips the gate only with a logged note. (3)
  AGENTS.md materiality gate: scripts/tools/contract_drift.py
  (materiality high/medium/low; needs_contract_update = high-tier
  change without a contract doc in the same diff; CLI exit 1 on
  flagged drift), fable-judge "contract drift?" step, CONTRIBUTING.md
  rule 7. 5 skills restamped 3.9.0 (lifecycle pin: 3.9.0 touched /
  3.8.0 rest). Regression tests: test_sdd_gates.py (13),
  test_review_protocol.py (13 + 4 doctests), test_contract_drift.py
  (17 + 23 subtests); scenario count 23->24. Verified: pytest = 490
  passed, 1 skipped, 57 subtests; doctor 14 checks GREEN; deploy ALL
  OK; integrity 92 files; contract_drift CLI smoke (VERSION diff ->
  exit 1). Release contract: version 3.9.0, 36 skills.
- **v3.8.0 (wave4 context-hygiene)**: context layering per the
  2026-09-01 roadmap. (1) OPS/AGENTS diet: 3 inline rule blocks relocated
  verbatim to JIT skill homes (destructive-commands -> git-workflow-
  and-versioning, TDD spec/name gate -> testing-discipline, memory-trust
  ASI06 -> security-and-hardening); OPS.md 155->145 lines; relocation-only
  proven by red-first no-content-lost tests; adapters/UNIVERSAL.md
  fragment->harness mapping; AGENTS.md JIT rule-skill index; 6 trigger
  queries added to co-located evals.json (central stays 80; merged 86).
  (2) Compaction-continuity scenario 23: owner correction mid-run
  ("нет, используй postgres, не sqlite") + compact-before-delivery; oracle
  = correction survives AND verbatim quote in report (9-section summary
  discipline); mast: FM-1.4 (context loss); runner dry-run 23/23 GREEN.
  (3) Wiki hygiene: lint_wiki type frontmatter in {user, feedback,
  project, reference} (legacy WARN), index.md hard cap 200 lines (ERROR
  demanding consolidation, tail never silently dropped), freshness WARN
  >180d, modified ISO-8601 stamping (stamp_modified writer helper,
  build.py stamps indexed copy only — disk never rewritten). Real-Wiki
  lint read-only: exit 0. Regression tests: test_ops_diet.py (11),
  test_compaction_scenario.py (9), test_wiki_hygiene.py (11); scenario
  count 22->23. Verified: pytest = 447 passed, 1 skipped, 34 subtests;
  doctor 14 checks GREEN; deploy ALL OK (home+repo canonical copies
  synced, 36 skills restamped 3.8.0). Ablation token delta: live run
  attempted (claude -p executor) — executor phase failed (subprocess
  exit 1 + Windows temp-dir lock), no comparable baseline produced;
  recorded as NOT measured, not skipped silently. Release contract:
  version 3.8.0, 36 skills.
- **v3.7.0 (wave3 standards-conformance)**: agentskills.io alignment
  from the 2026-09-01 roadmap. (1) Full Agent Skills spec conformance in
  doctor (`check_frontmatter_spec`): name 1-64 chars ^[a-z0-9]+(-[a-z0-9]+)*$
  hard-FAIL on charset/length, description <=1024 hard-FAIL, name!=dir and
  compatibility>500 WARN; metadata/allowed-tools type checks. All 36
  skills passed pre-check without fixes. (2) evals/evals.json
  co-location: 80 trigger queries migrated into 10 per-skill
  skills/<slug>/evals/evals.json files (ids stable <slug>-<n>),
  load_queries() prefers per-skill files with central-file fallback
  (eval/trigger_queries.json kept), --queries auto mode. (3) Canonical
  .agents/skills/ target: deploy.py --canonical (junction via mklink /J,
  copy fallback, --dry-run), doctor `check_skills_sync` byte-compares
  repo+home deployed copies (WARN when none deployed), profile.yml
  adapters[].canonical flags; live deploy executed. (4) Skill lifecycle:
  metadata.version "3.7.0" stamped on all 36 SKILL.md; doctor WARN on
  missing version; usage_audit.py --retirement-report --since D
  (proposal-only). Real run 2026-09-01: 803 sessions audited, 0/36
  zero-use skills — no retirement proposals. doctor docstring check-list
  refreshed (14 checks). Regression tests: test_skill_spec_conformance.py
  (13), test_evals_colocation.py (9), test_skills_sync.py (10),
  test_skill_lifecycle.py (8). Verified: pytest = 416 passed, 1 skipped,
  34 subtests; doctor 14 checks GREEN. Release contract: version 3.7.0,
  36 skills.
- **v3.6.0 (wave2 honest-oracle)**: verifier-integrity axis from the
  2026-09-01 roadmap. (1) ImpossibleBench canaries: eval/tasks/005-canary-
  oneoff + 006-canary-conflicting — mutated oracles (flipped expected
  value; contradictory duplicate assertion) whose correct score is 0;
  any pass is recorded as hacked (`canary: true` TASK.md frontmatter,
  canary/hacked fields on attempts); canaries EXCLUDED from pass-rate
  baselines and trend scores; trend gains "## Canary integrity" section.
  Live check: honest executor FAILs both canaries, runner exit-clean.
  (2) Clean-pass accounting: shortcut_patterns() flags the 4
  ImpossibleBench strategies (test-file modification, comparison
  operator overload, call-count state, exact-assert special-casing) over
  a difflib sandbox-vs-pristine diff; every attempt records `shortcuts`;
  trend renders resolved/hacked/clean columns (Qwen Verification
  Horizon). (3) MAST taxonomy: docs/mast-taxonomy.md (14 modes,
  arXiv:2503.13657v3 Appendix A ids), MAST_MODES dict, optional
  mast_mode on result rows, trend "## MAST failure modes" histogram with
  unknown-id WARNING; 5 scenarios backfilled (false-done FM-3.1,
  silent-failure FM-3.2, weakened-test FM-3.3, contract-drift FM-1.1,
  silent-cross-write FM-2.6). Regression tests: test_canaries.py (12),
  test_clean_pass.py (11), test_mast_labels.py (9); task count 4->6.
  Verified: pytest = 376 passed, 1 skipped, 34 subtests; doctor 12
  checks GREEN; trap dry-run 22/22 GREEN. Release contract: version
  3.6.0, 36 skills.
- **v3.5.0 (wave1 trust-surface)**: security triad + memory DR from the
  2026-09-01 SOTA roadmap. (1) OWASP ASI01-10 + AST10 map
  (docs/SECURITY-MAP.md, 20 rows, every row names a kit control) +
  doctor `check_skill_supply_chain` WARN row (34/36 skills lack
  `license:` — hygiene seed). (2) CBSE integrity manifest:
  scripts/tools/integrity_manifest.py SHA-256 over 87 control-plane
  files (OPS/AGENTS/profile/adapters/scripts/eval/db-tools/skills);
  doctor `check_integrity` FAIL row; deploy.py refuses on drift
  (exit 3); `--update` regenerates. (3) ASI06 memory defenses: OPS.md
  "Memory trust" section (web/subagent content is DATA, lethal-trifecta
  screen), lint_wiki `check_origin` (missing origin WARN,
  origin:web without source_url = error), trap scenario 22
  `memory-poisoning.md` (DATA-not-INSTRUCTIONS oracle). (4) Backup/DR:
  scripts/tools/backup_memory.py — SQLite online-backup API (never raw
  copy of live WAL db), `--restore-drill` restores to temp root and
  verifies `PRAGMA integrity_check` + search probe inside its lifetime;
  doctor `check_backup_freshness` WARN (14d). Regression tests:
  test_security_map.py (5), test_integrity_manifest.py (13),
  test_memory_provenance.py (8), test_backup_memory.py (5), release
  contract updated (22 scenarios, 3.5.0). Verified: pytest = 344
  passed, 1 skipped, 34 subtests; doctor 12 checks GREEN; ruff on
  touched files clean (baseline unchanged). Release contract: version
  3.5.0, 36 skills.
- **v3.4.7 (CLI machine mode)**: closes the CLI-vs-MCP decision
  (findings #166) — the two measured pain points (shell quoting on
  `add --text`, prose output agents parse by eye) fixed inside the CLI,
  no second runtime. `findings.py add --stdin` reads the conclusion from
  stdin: zero shell quoting, CRLF normalized to LF, mutual exclusion with
  `--text` (exit 2), empty input rejected (exit 2). `findings.py search
  --json` and `search_all.py --json` emit a JSON list (id/created/topic/
  tags/source/snippet and db/path/snippet respectively); empty result is
  `[]` with exit 0; human output unchanged. Regression tests:
  `tests/test_findings_cli_machine.py` (4 tests, red-first: quoting-
  survival text with mixed quotes/backticks/$VAR verified verbatim in the
  DB, JSON contract fields, empty-result `[]`, CRLF normalization via
  byte-mode pipes; harness passes stdin as bytes — text=True doubles
  CRLF on Windows). skills_search already had --json (v3.4.4). Verified:
  `python -m pytest tests/ -q` = 313 passed, 1 skipped, 34 subtests;
  ruff on touched files = baseline 8 (0 new). Release contract: version
  3.4.7, 36 skills.
- **v3.4.6 (zero-use skill re-audit)**: the 2-3-week re-review of the 9
  zero-read skills flagged by the 2026-08-29 audit (findings #113/#114),
  executed 2026-08-31 against real-session telemetry since v3.4.5
  (usage_audit + a skill://-read scan of both transcript stores; audit's own
  subagent transcripts excluded). Evidence-based kills/merges, 42 -> 36
  skills: `agent-ux` (0 uses ever), `executing-plans` +
  `subagent-driven-development` (0 real uses; 12 apparent hits were the
  audit's own C1/C2 subagents; dispatching-parallel-agents covers the
  parallel path), `learn` (0 real invocations — every "/learn" hit was
  substring noise from `skills/learn` paths; flow folded into skill-authoring
  §6 "Turning a session into a skill", RU triggers preserved),
  `dashboard-ui-review` + `data-visualization` (0 uses; both merged into
  `dashboard-design`, which kept its single real use — the Otklik realty
  dashboard session 2026-08-29). `design-system` kept (1 real use, same
  session). screenpipe-api was already gone (v3.4.3). Manifest/OPS/credits/
  cross-references updated; trigger_queries.json learn -> skill-authoring (8
  queries). Regression tests: `DashboardSkillsPresentTest` +
  `LearnFoldedIntoSkillAuthoringTest` (killed slugs absent, merged flow +
  RU trigger present), `ManifestContractTest` count 36,
  `tests/test_trigger_eval_prelude.py` slug swap learn -> ponytail.
  Verified: `python -m pytest tests/ -q` = 309 passed, 1 skipped, 34
  subtests; `python scripts/doctor.py` = All systems GREEN (9 checks).
- **v3.4.5 (eval truth-fixes)**: three root causes found by the first live
  v3.4.4 matrix run, closed with regression tests. (1) `eval/trigger_eval.py`
  `<skills listing>` placeholder was NEVER replaced — the measured listing
  never entered the prompt, so runs measured the executor's ambient global
  skills; `prompt_for` now interpolates a real listing read live from
  skills/ frontmatter (`listing_entries()`,
  `tests/test_trigger_eval_prelude.py` red-first: placeholder must be gone,
  >=10 entries, named slugs present). (2) Judge verdict parser rejected
  `PASS.` (sentence period) — live judge wrote "PASS. The candidate..." and
  grounded-decision recorded FAIL; `_JUDGE_PASS_RE` now accepts sentence
  punctuation `,` `;` `.` after the token
  (`tests/test_json_output.py::test_judge_passed_strict_parser`, 3 new rows).
  (3) Task 003 brief under-specified the regression contract the verifier
  enforces (boundary calls both below and above the range); TASK.md now
  states it. Skills: `debugging-and-error-recovery` merged into
  `systematic-debugging` (duplicate root-cause debugging skills; models
  systematically chose systematic-debugging; unique Test/Build Failure
  Triage trees grafted across) — 43 -> 42 skills; `learn` description
  reworded (skill-authoring intercepted "make a skill from X"; live probe
  now answers SKILLS LOADED: learn). Post-fix live matrix
  (dashscope-glm-5.2-fast-preview, 80 queries): 8/10 skills at/above
  threshold, learn 0.25 -> 1.00, false-fire ~0; superpowers 0.25 remains
  (always-on skill, behavior-oracle measured, description triggers are
  method-phrases that overlap other skills — accepted). Release contract:
  version 3.4.5, 42 skills. Verified: full pytest suite (308 passed),
  doctor 9/9, file-size gate hard 0.


- **v3.4.4 (audit-driven optimization)**: OPS.md diet — the 22-entry
  CHANGELOG section (64% of the file by tokens, 4230 of 6593 approx tokens,
  re-read by the model every session) moved verbatim to `docs/CHANGELOG.md`;
  §5 CROSS-CHAT MEMORY trimmed 540->~150 tokens to the commands the
  2026-08-29 real-usage audit observed in use; §6 skill table (774 tokens,
  duplicating profile.yml and each SKILL.md frontmatter) collapsed to an
  always-on line + pointer. OPS.md: 439 -> 142 lines. New
  `scripts/tools/usage_audit.py` (+ `tests/test_usage_audit.py`, 8 tests):
  segregates kit-internal vs real sessions across Claude Code and omp
  transcript stores, counts memory-engine calls, skill reads, OPS-in-context
  markers — closes the two audit confounds (selftests-as-usage,
  pre-install baselines) that the 2026-08-29 audit caught. Eval: task
  `004-regression-test-first` (both prior task-smoke failures were missing
  regression tests; red-test-first is now a verified success criterion,
  `tests/test_task_runner.py::test_task_runner_discovers_tasks`); traps
  19-21 (refuse-disclaimer, no-are-you-sure, full-delivery) give OPS §2's
  nine compliance locks their first measured scenarios — previously zero
  coverage (`tests/test_release_contract.py:AssetCountsContractTest`,
  scenarios 18 -> 21, tasks 3 -> 4). `eval/trigger_eval.py` prelude
  strengthened: the 2026-08-24 baseline showed the executor ignoring the
  skills listing (8/10 skills at 0.00 trigger rate, including skills whose
  descriptions already carry Russian trigger tokens) — the prelude now
  mandates choosing from the listing and shows the exact output format
  (`tests/test_trigger_eval_prelude.py`). `docs/audit-methodology.md`: the
  era/segregation confound checklist behind this release. Version 3.4.4
  across VERSION, profile.yml, OPS.md, SKILL_RUNTIME.md, and
  tests/test_release_contract.py. Verified: full pytest suite (306 passed,
  1 skipped), doctor 9/9 GREEN, file-size gate hard 0, `eval/runner.py`
  dry-run ALL GREEN (21 scenarios), `eval/task_runner.py --dry-run` 4 tasks,
  `usage_audit.py` real run OK (48 real sessions since 08-26).

- **v3.4.3 (dashboard & UX design suite, installer resilience & contract alignment)**:
  adds 5 dedicated dashboard & UX design skills (`skills/agent-ux`,
  `skills/dashboard-design`, `skills/dashboard-ui-review`,
  `skills/data-visualization`, `skills/design-system`) covering AI copilot/automation
  collaboration loops, marketplace/back-office dashboard information hierarchy,
  browser/Playwright UI review, honest metric visualizations, and compact design
  tokens; registered in profile.yml domain list (public skill count 38 -> 43).
  Installer (`scripts/install.py`) hardened with strict absolute-path validation
  for `MEMORY_ROOT` (S-L1, `tests/test_install.py:InstallMemoryRootValidationTest`),
  PowerShell preflight check and automated rollback on junction/symlink creation
  failure (S-M1, `tests/test_install.py:LinkEngineHardeningTest`), early detection
  and rejection of unsupported isolated/embedded Python environments (S-M2,
  `tests/test_install.py:PythonEnvironmentCheckTest`), and engine schema version
  aligned to 2.9 (S-L4, `scripts/doctor.py:check_engine_sync`, `tests/test_doctor.py`).
  Eval harness hardened with bounded prefix and untrusted candidate delimiters in
  trap-suite judge prompts (E-2, `eval/runner.py:judge_one`, `tests/test_json_output.py`),
  explicit top-level `mode` discriminator (`"dry-run"` vs `"live"`) in task runner
  and safe legacy zero-result filtering in trend reporting (E-3, `eval/task_runner.py`,
  `eval/trend.py`, `tests/test_task_runner.py`, `tests/test_trend.py`). Asset counts
  explicitly asserted by release contract: 43 skills, 18 trap scenarios, 80 trigger queries,
  3 task smokes, 9 doctor checks (E-1, `tests/test_release_contract.py:AssetCountsContractTest`,
  `tests/test_release_contract.py:NewDashboardSkillsPresentTest`).
  Stale instruction paths (`scripts/task-brief`, `eval/workflow.js`, `skills/fable-method/eval/`)
  cleared from `fable-judge` and SDD skills (A-R1/A-R2, `tests/test_release_contract.py:StaleDocReferencesTest`).
  Ponytail skill MIT license added (`skills/ponytail/LICENSE`), supported versions table
  in `SECURITY.md` updated with `3.4.x`, and OPS.md §6 table formatting repaired.
  Version 3.4.3 across VERSION, profile.yml, OPS.md, SKILL_RUNTIME.md, and test_release_contract.py.
  Verified: full pytest suite, doctor, and file-size gate green.

- **v3.4.2 (persona → behavioral rules + context-monitor removal)**:
  identity/persona declarations replaced with behavioral rules per 2026
  persona-prompting research (expert personas add no accuracy for code tasks
  and hurt clarity). OPS §1 and AGENTS §1 drop the persona role
  declarations, keep the Three pillars, language rule, and stop-word, and
  open with the one-line method: plan → TDD → implement → verify → report;
  evidence over claims. The AGENTS self-check and the OPS drift-killer
  self-check now ask "do I follow the method / check memory / back every
  claim with fresh evidence?" instead of a persona identity check.
  engineering-persona SKILL.md description clarified as response-format
  rules (not a persona). Adapter Verify sections (UNIVERSAL, gemini,
  antigravity, zcode) and the eval/trigger_eval.py prelude converted from
  "who are you" identity checks to behavioral checks (show the method, search
  memory through db-tools).
  `scripts/context-monitor.py` and `tests/test_context_monitor.py` are
  removed (YAGNI — no consumer; the context-reflex was unclaimed dead
  weight, and keeping an unused script is exactly the accidental scope the
  release removes). doctor drops the reflex-command check it guarded and is
  now 9 checks; the OPS CONTEXT MONITOR section and the AGENTS reflex block
  are stripped, README/SKILL_RUNTIME/adapters no longer command it. Version 3.4.2
  across VERSION and profile.yml; OPS.md and SKILL_RUNTIME.md headers
  v3.4.2; skill count stays 38. Release-contract test
  `tests/test_release_contract.py` extended to assert no identity-declaration
  phrase in the public release text, the 3.4.2 version, and the
  context-monitor script/test absent plus no ACTIVE doc reference. Sources:
  Wharton GAIL "Playing Pretend: Expert Personas Don't Improve Factual
  Accuracy" (2025-12-07, Basil et al., SSRN 5879722,
  gail.wharton.upenn.edu/research-and-insights/playing-pretend-expert-
  personas/); PRISM arXiv 2603.18507 (2026-03, expert personas improve
  alignment/safety but damage knowledge retrieval); arXiv 2605.29420
  (2026-05, roles raise expertise depth, reduce clarity; baseline wins in
  tech/science/finance/legal); arXiv 2311.10054 (EMNLP 2024 Findings,
  personas in system prompts do not improve factual performance). Verified:
  full pytest suite, doctor, and the file-size gate green.

- **v3.4.1 (ponytail skill)**: `skills/ponytail/SKILL.md` — lazy senior-dev
  mode adapted from DietrichGebert/ponytail (MIT, credits note preserved) into
  coding-kit Hermes conventions; registered in the profile.yml domain list.
  Public skill counts 37 -> 38 across README/OPS/UNIVERSAL. Version 3.4.1
  across VERSION and profile.yml; OPS.md and SKILL_RUNTIME.md headers v3.4.1.
  Release-contract test `tests/test_release_contract.py` extended to assert
  ponytail presence and a 38-skill manifest in sync. Verified: full pytest
  suite, doctor, and the file-size gate green.

- **v3.4.0 (focused release — behavior oracle & accidental-scope removal)**:
  only the valid behavior-oracle feature from the reverted mixed commit
  e7449f6 is kept: `eval/behavior_oracles.py` plus `signal_fired()` /
  `has_oracle` and per-row/per-attempt `mode=oracle|name` in
  `eval/trigger_eval.py` (`tests/test_trigger_eval.py`, BehaviorOracleTest).
  The accidental screenpipe scope (`skills/screenpipe-api`,
  `skills/screenpipe-cli`, profile.yml declarations — never had consumers)
  and the four stale pre-oracle live result JSONs from e7449f6 (one leaked
  the personal path) are excluded from this release. Version 3.4.0 across
  VERSION and profile.yml; OPS.md and SKILL_RUNTIME.md headers v3.4.
  Release-contract regression test `tests/test_release_contract.py` asserts
  the release invariants (version, skill manifest 37 in sync, screenpipe
  absent, no personal path in the public release text, stale results absent).
  Verified: full pytest suite, doctor, and the file-size gate green.
- **v3.3.1 (pre-publication hardening)**: `scripts/kitctl.py` removed — the
  thin lifecycle dispatcher had zero runtime consumers: agent skills,
  harness triggers, and CI call the underlying scripts directly
  (`python scripts/doctor.py`, `python -m pytest tests`,
  `python scripts/tools/check_file_sizes.py --ci`). The
  install.py CLI-guard tests moved to `tests/test_install.py`
  (`InstallCliGuardTest`), the trend ascii-stdout unicode regression
  test to `tests/test_trend.py`; `tests/test_kitctl.py` deleted with
  the dispatcher. README daily loop and CONTRIBUTING gates now name
  the scripts directly. Verified: full pytest suite, doctor, and the
  file-size gate green after the cut.
  Git history sanitized pre-publication: personal machine paths and
  internal docs purged from every revision (both pickaxe forms return
  zero commits; originals kept in a local pre-sanitize bundle).


- **v3.3.0 (eval telemetry & experimental inlined-prompt ablation)**:
  `eval/telemetry.py` — `summarize_durations` folds finite, non-negative
  per-attempt `duration_s` into `duration_s_total`/`duration_s_mean`
  (skipping negatives, NaN/Inf, and booleans), and `load_reported_usage`
  ingests a user-supplied `--usage-json` `{tokens_total, cost_usd}` object
  only when strictly numeric and finite — measured wall-clock only, never
  fabricated tokens/cost (`tests/test_telemetry.py`). All three runners
  persist the duration aggregates, and attach `reported_usage` on live runs
  only — dry-run never ingests it
  (`tests/test_json_output.py`, `tests/test_task_runner.py`,
  `tests/test_trigger_eval.py`). `eval/prompt_assembly.py` — controlled
  inlined-prompt assembly (`skill_manifest`, `assemble_prompt`) plus
  `runner.py --inline-skills/--disable-skill` wiring; the executor runs from
  a neutral per-call temp `cwd` while `executor_env()` retains HOME/auth and
  drops secrets (`tests/test_prompt_assembly.py`,
  `tests/test_prompt_inline.py`, `tests/test_json_output.py`,
  `tests/test_task_runner.py`). `eval/ablate.py` — experimental per-skill
  inlined-prompt contribution (pass-rate with/without the inlined body),
  persisted as `kind="ablate"` and dispatched via `kitctl ablate`
  (`tests/test_ablate.py`, `tests/test_results_io.py`,
  `tests/test_kitctl.py`); rendered raw by `trend.py` under an explicit
  experimental caveat (`tests/test_trend.py`). Ablation is descriptive, not
  causal: ambient global skills are NOT controlled, small samples may be
  non-conclusive, and a treatment removes a skill from that experiment's
  inlined prompt only — it never deletes the skill or claims deletion evidence.

- **v3.2.0 (evidence-first evals & reliable trend loop)**: `eval/results_io.py` —
  schema_version 1 append-only store with atomic `os.link` temp-writes, unique UTC
  microsecond+uuid4 `run_id`, separate `model` and sanitized `executor_spec`, kind
  validation (`trap`, `tasks`, `trigger`), concurrent write safety, and resilient loading
  (`tests/test_results_io.py`). `eval/task_runner.py` — task smoke canary on 3 real
  coding tasks using binary `verify.py` oracles (no LLM judge), pristine fixture sandbox
  isolation per attempt, default `--tries 2`, shared 6-class failure taxonomy, and trace
  tail capture (`tests/test_task_runner.py`). `eval/runner.py` & `eval/trigger_eval.py` —
  truthful per-attempt duration, error, and verdict recording, decoupled `--model` metadata,
  and cleanup regression tests (`tests/test_json_output.py`). `eval/trend.py` — reliable
  history reporting grouped by `(kind, model)`, pass-rate calculation, warn-only baseline
  deltas (exit 0), and structured Failure Evidence Packets without unsupervised source
  edits (`tests/test_trend.py`). `scripts/kitctl.py` — `tasks` (dry-run default), `trend`,
  and pytest-based `tests` dispatch (`tests/test_kitctl.py`). CI & gates: `.github/workflows/evals.yml`
  dry-only validation on Ubuntu and Windows matrix (`permissions: contents: read`),
  no live push races; eliminated plan baseline grandfather loophole in `scripts/file_size_baseline.json`;
  memory extraction equivalence tests for `file_scanner.py`, `findings_db.py`, `findings_links.py`.
- **v3.0.0 (publication-ready)**: `scripts/kitctl.py` — one command for
  the lifecycle (install/doctor/gate/eval/triggers/tests/warmup/
  checkpoint/context; thin dispatcher, tests/test_kitctl.py).
  install.py CLI guard: '--help' prints usage instead of running the
  installer, unknown argv refused (tests/test_kitctl.py; the audit's
  '--help ran the install' hazard). README: kitctl daily loop,
  trigger-eval row. Version 3.0.0 across VERSION/profile/OPS.
- **v2.9.0 (memory quality)**: single FTS sanitizer — db-tools/
  ftsquery.py; the three drifting copies (search.py / findings.py /
  memory-warmup.py) import it now (tests/test_v29.py; quoted
  phrase-prefix semantics live-verified). Findings gain verify-commands:
  `add --verify-cmd` + `findings.py verify <id>` re-runs it (VERIFIED +
  verified_at / FAILED exit 1) — memory that proves itself fresh.
  build.py: full rebuild is atomic (temp db + rename — a crash mid-build
  leaves the previous index intact), refuses a project named 'research'
  defaulting into the findings store, wiki-branch root compare is
  case-insensitive. memory-warmup honors MEMORY_ROOT (OPS §5 contract).
- **v2.8.0 (self-verifying kit)**: doctor learns the two classes the
  2026-08-22 audit sailed past — `check_reflex_commands` (a documented
  reflex command must print status and exit non-zero on trouble; catches
  the v2.7.3 silent no-op context-monitor) and `check_encoding_discipline`
  (no bare text=True in engine/scripts/eval — the cp1251 mojibake class;
  the one live instance, context-monitor dump_checkpoint, fixed)
  (tests/test_doctor.py; doctor is now 10 checks). Trap-suite 15 -> 18:
  dead-flag, contract-drift, silent-cross-write — the three degradation
  classes the audit itself demonstrated (eval/scenarios/, dry-run
  validated). CI: trigger-queries validation step in the gates workflow.
- **v2.7.4 (contract-truth release — closes all 4 MAJOR of audit 2026-08-22)**:
  `search.py --refresh` refuses a (-r, -b) pair that does not match
  build.py's own mapping; `--force-refresh` overrides
  (tests/test_search_refresh.py — wiki.db and project indexes can no
  longer silently cross-destroy; the v2.6 bug class, reopened by the
  audit as reachable via --refresh). `context-monitor.py --check` always
  prints a status line; exit codes 0/1/2 = ok/warn/critical
  (tests/test_context_monitor.py — the OPS §7 reflex used to be a silent
  no-op). githist.py: git output decoded via _compat.run (no permanent
  cp1251 mojibake in research.db on Windows), real 40-hex commit
  boundary, empty commits kept (tests/test_githist.py — the misdocumented
  v2.6 claim is now true). `trigger_eval --timeout` reaches the executor
  (tests/test_trigger_eval.py). sanitize_query comment now matches
  behavior (quoted phrase-prefix verified live). ZCode adapter
  (adapters/zcode.md, profile.yml, README, UNIVERSAL).

- **v2.7.3 (trap-suite live matrix)**: first full live run of all 15
  scenarios via `claude --model dashscope-glm-5.2-fast-preview -p`
  (default resale provider was 502ing). 13/15 first try; breaking-migration =
  fast-model elision (stable 2/2 on retry); grounded-decision `expect`
  over-specified "web search" and is now the skill's real contract
  (primary sources + honest tool-gap disclosure). Result: 15/15 PASS,
  matrix in eval/results-2026-08-21-trap15-glm52.md.
- **v2.7.2 (trap-suite 2.0, part 1)**: 5 new scenarios (silent-test-skip,
  type-erasure, infinite-retry-masking, breaking-migration, mock-pollution)
  — real agent-degradation classes from review round 2. Content calibrated
  against a live model: 5/5 PASS with session-model sanity run; live
  claude -p suite blocked by external provider 502 (not the kit).
- **v2.7.1 (review round)**: doctor.py YAML-validates skill frontmatter
  (regex fallback without pyyaml); debug-incident-protocol frontmatter
  quoted (PyYAML/Hermes crash); docs 36->37 skills, headers v2.6/v2.5->v2.7.
- **v2.7.0 (skill autopilot)**: trigger-eval (description trigger-rate
  measurement, 80 baseline queries) + skills_search (no-model catalog);
  ROUTING rule zero uses skills_search.
- **v2.6 (review round 2)**: 12 engine defects closed with live
  repros — `build.py -r X` without `-o` no longer destroys wiki.db;
  text->binary flip drops the stale FTS row; BOM-tolerant skip.local;
  skip.local never indexed; warmup `created` column + sanitized MATCH;
  `search.py -p` slash-normalized; githist 40-hex commit boundary;
  extract_findings bootstraps schema + word-boundary markers; engine
  regression tests (tests/test_build.py).
- **v2.5 (review-driven hardening)**: all v2.4-review findings closed —
  Camoufox dead-refs cut (R1), install link follows the last installer (R2),
  unit tests for install/root resolver (R3), CI windows+ubuntu matrix (R4),
  neutral skip defaults + per-machine `skip.local` (R5), smoke by exit-code
  (N1), `.override.md`/`skip.local` gitignored (N2), 8-16K runtime mode (N3),
  engine fully English (N5). Engine: binaries never indexed (ext list + NUL
  sniff — a 50MB .exe bloated agent.db to 372MB and froze search), FTS
  optimize after deletions.
- **v2.4 (hardening)**: destructive-command guardrail (OPS §2.9), override modes
  (`.override.md`: EXPLORATORY_PROTOTYPE / STRICT_AUDIT), findings `--file/--symbol`
  linkage surfaced in `repomap.py file`, `scripts/doctor.py` self-diagnostic,
  trap-suite +2 (hallucinated-import, premature-abstraction) — 10 scenarios.
- **v2.3 (shareable kit)**: memory engine vendored into the kit (`memory/db-tools`,
  one physical copy via junction), `scripts/install.py` one-command bootstrap,
  README + MIT LICENSE + .gitattributes, user-path remnants purged —
  one clone gives a friend a fully working kit.
- **v2.2**: portable memory paths (`~/.memory` + `MEMORY_ROOT`), context-monitor `--dump-checkpoint`, trap-suite +3 scenarios (silent-failure, money-safety, shell-injection) — 8/8 PASS.
- **v2.1**: English core (AGENTS/OPS/BOOT/SKILL_RUNTIME/profile, all skills).
- **v2.0**: obra/superpowers phase skills imported (MIT), AGENTS.md soul, trap-suite evals.
