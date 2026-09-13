# coding-kit development roadmap — 2026-09-06

## Decision

Stabilize installation and evaluation safety, then test the product hypothesis: **portable cross-session memory with an optional, evidence-gated methodology layer**. Do not mistake more skills, checks or prompt text for more user value. Do not remove instructions on the strength of the failed September 6 experiment.

This document plans development only. It does not authorize global deployment, paid model runs, licence changes or edits to installed agent instructions. NOW/NEXT/LATER are dependency gates, not release dates. S = bounded correction or drill; M = interacting contracts; L = staged experiment. These are scope estimates, not promised engineer-days.

## Baseline and reconciliation

- `VERSION` and the current changelog identify repository v4.2.0. Installed OMP/router context still identifies v4.1.0; repository version and installed state are different facts.
- Deploy CLI parsing is already fixed: help returns 0; unknown flags and standalone `--dry-run` return 2 before mutation. Only `--canonical --dry-run` currently previews. Do not schedule the original incident fix again.
- Fresh-root index/log seeding and absent-only preservation are already implemented and recorded in the changelog. Extend only a reproduced installation gap.
- The September 6 raw verification log records 105 passing focused tests plus 25 subtests, but doctor **fails skills-sync**. It also reports v4.1.0, so it is not a fresh v4.2.0 release clearance. Historical 14/14 doctor results must not conceal later drift.
- The bounded comparison failed in both arms: Full Kit escaped scratch and modified a live file; Thin Core timed out. This confounded result establishes neither profile's superiority and cannot justify prompt removal.
- Existing eval machinery includes a result store, task oracles, trigger evaluations and rigor gates. Reuse it rather than create another evaluation framework.
- Persistent findings live in `~/.memory/db/research.db`, not an invented `findings.db`. Markdown-derived indexes are rebuildable; research findings require backup.
- The root MIT licence does not erase the `windows-encoding-fixes` Proprietary declaration. Disclosure is already recorded; redistribution rights remain unresolved.

## Alternatives and assumptions

**Keep everything and polish:** lowest short-term change, but does not test whether standing context earns its cost.

**Immediately make all methodology default-off:** potentially cheaper, but quality preservation is unproven. Rejected as an immediate cutover, retained as an experiment candidate.

**Selected:** safety and reproducibility first; evaluate memory utility and prompt cost as separate questions; change defaults only after valid comparative evidence.

Keep core tools stdlib-first, preserve Windows support, and reuse existing adapters. No arbitrary hard cap on skills or 150-character description rule: the locally tested description constraint is 1–1024 characters. New standing instructions need a demonstrated behavior benefit, not an available catalogue slot.

## NOW — safe, reproducible local operation

### CK-01 — Complete deploy preview and recovery [M]

**Targets:** `scripts/tools/deploy.py`, `tests/test_deploy_cli.py`, `tests/test_release_contract.py`, existing deploy documentation.

**Gap:** full-deploy preview is absent and the incident lacked router preimages. Existing safe CLI rejection remains a regression contract until the preview is implemented.

**Work:** implement read-only full-deploy planning using the same generated content as apply; show affected paths and changes without exposing secrets; preserve preimages and the previous absence of files before actual deployment; define restoration after partial failure. Preserve machine-local sections under the documented ownership contract. Do not add a second renderer or a mandatory interactive prompt that breaks explicit automation.

**Acceptance:** preview/help/invalid arguments leave fake home and repository mirrors byte-identical; preview predicts actual fixture changes; interruption after one target write can restore exact preimages and remove only newly created managed files; unrelated home files remain untouched.

**Proof during implementation:** existing CLI tests plus a real subprocess against an isolated copy of the repository and temporary HOME/USERPROFILE/APPDATA/LOCALAPPDATA/MEMORY_ROOT. Redirecting home alone is insufficient for canonical writes into repository mirrors.

**Dependency:** none. First implementation package below is the preview subset.

**Status 2026-09-11 — DONE (preview + recovery proof).** `--dry-run` (no `--canonical`) now prints the full-deploy plan read-only; apply-path plan functions are reused with `dry=True`, so no second renderer exists. Evidence: `tests/test_deploy_cli.py` — preview opens no transaction, mutates nothing, and its planned paths equal the exact file set a real deploy creates/changes/deletes on an identical fixture; a subprocess drill redirects `HOME`/`USERPROFILE`/`APPDATA`/`LOCALAPPDATA`/`MEMORY_ROOT` into a temp root, runs `--dry-run`/`--help`/unknown-arg (home and repository byte-identical) and performs a real full deploy into a disposable repository copy (byte-identical skill mirrors, regenerated routers, untracked original repo). Preimage restoration after a mid-deploy failure stays covered by `tests/test_deploy_rollback.py` (canonical, mid-skills, late-router and verify-false cases). Suite: 59 passed, 1 skipped, 5 subtests across the deploy-related files. The machine-wide deploy itself was not executed; the local preview reported 4 drifted skill files across two sync targets plus five routers and CLAUDE.md pending regeneration.

### CK-02 — Reconcile release and installed state deliberately [S/M]

**Targets:** `VERSION`, `profile.yml`, `integrity-manifest.json`, `scripts/doctor.py`, deploy/sync and release tests.

**Work:** inventory repository, canonical mirror and installed copies separately; freeze an intended release tree; review generated changes; update integrity metadata only for reviewed source; rehearse deployment and rollback in disposable targets. Deploy to real harness homes only in an explicit release task.

**Acceptance:** doctor passes for the frozen release and the staged installed targets; installed versions and skill bytes match intended source; local extensions survive; raw output names the exact version and environment. A green manifest is not proof of installed parity.

**Dependency:** CK-01 recovery boundary. No instruction deployment occurs while preparing this roadmap.

### CK-03 — Establish genuine execution isolation before model evals [L]

**Targets:** `eval/rigor/isolation.py`, `eval/rigor/runner.py`, `tests/test_rigor_runner.py`, existing evaluation instructions.

**Work:** choose an OS-enforced disposable environment compatible with the actual executor, such as a VM or a container without writable host mounts. A temporary cwd, path checks around the runner, environment redirects and a prompt are not a sandbox when child processes can access the host. Windows Home is a constraint, not permission to weaken the boundary. If a supported executor cannot be confined, leave its live eval path blocked.

**Acceptance before any paid/model run:** a deterministic child process cannot read an external fixture secret or write an external sentinel through absolute paths, traversal, links or subprocesses; descendants stop on timeout; host credentials are absent; only reviewed result artifacts leave the environment. Network access is limited to explicitly required endpoints. The runner fails closed when the isolation backend is unavailable.

**Proof:** deterministic non-model escape probes under the exact execution backend, followed by one harmless agent task. Do not use a successful canary string as proof of filesystem isolation.

**Dependency:** independent of CK-01/02. No more live Desktop scratch experiments.

**Status 2026-09-11 — backend and escape battery landed; confined-executor adapter still open.** `eval/rigor/container.py` implements the OS boundary on this machine's Docker (29.7.2, linux containers, image `python:3.12-alpine`): read-only rootfs, `--cap-drop=ALL`, `no-new-privileges`, `--network=none`, `--tmpfs /tmp`, only the task directory mounted writable, no host environment forwarded, timeout kills the container tree. `escape_probes()` performs the acceptance battery and the host, not the container, judges it — measured green on all nine checks (secret outside every mount never read via `/…`, `/mnt/<drive>/…`, `/host/…` or `/work/../…`; sentinel writes blocked on `/`, beside the mount, in `/etc` and behind a symlink; child-process write blocked; network and Docker socket unreachable; host env digests absent). `timeout_kills_descendants()` confirms a run past its deadline leaves no container or child behind. `require_confined_executor()` is wired into `run_rigor_suite`, so a live rigor run now raises `IsolationUnavailable` instead of executing the host CLI unconfined; dry runs are unchanged. Evidence: `python -m pytest tests/test_rigor_container.py tests/test_rigor_runner.py tests/test_rigor_gate.py -q` — 29 passed. **Still open before a model trial:** a confined-executor adapter (an image/VM carrying the actual CLI), the same gate for `eval/runner.py --executor` (its tests drive a fake executor, so gating it needs a test-side decision), a Linux/macOS run of the battery, and no live eval is authorized by this status.

**Status 2026-09-12 — offline confined executor and verifier verified.** The rigor runner now accepts explicit Docker executors and confines candidate verification with read-only trusted inputs. Independent scoped suite: 38 passed. The deterministic `--offline-task 006-import-boundary` produced PASS; its import-time escape variant produced FAIL with `verifier_rc=1` and no escape marker. The scored FAIL still returns CLI exit 0; inspect `clean_pass`. CK-03 remains open for live models: model CLI image and verifier dependencies, credential transport, endpoint-restricted networking (`@net` is unrestricted bridge networking), and the separate `eval/runner.py` path. No model call was made.

## NEXT — establish actual user value

### CK-04 — Cross-session memory outcome benchmark [M]

**Targets:** existing `eval/runner.py`, `eval/results_io.py`, `eval/scenarios/`, memory db-tools and their current tests. Add a two-session scenario format only where the existing single-session contract cannot express it.

**Question:** does persisted project knowledge improve a later task beyond what an ordinary fresh agent can infer from the repository?

**Design:** session A records a necessary project decision in a disposable memory root; session B, with no conversation history, implements or diagnoses a task that depends on it. Compare memory-enabled and memory-disabled arms on identical fixtures. Include changed/stale and conflicting decisions with provenance (source and date), not just exact-string recall. A repository-only control prevents rewarding knowledge already visible in source.

**Acceptance:** publish task outcomes from independent oracles, retrieval evidence, duration and usage for every arm; no cross-case memory leakage; stale information does not override newer authoritative evidence. Failure is a valid result: it blocks the product claim rather than triggering benchmark tailoring.

**Dependency:** CK-03. Run the fixture without a model first. Paid evaluation is a separately authorized experiment with a fixed scope.

**Status 2026-09-12 — native-memory offline preparation exercised.** `eval/memory_experiment.py prepare --notes` now seeds an independent native findings database per memory arm through the real CLI, exports its search command and environment, and retains repository-only and identical-inline controls. A CLI smoke prepared all four cases and retrieved each source from a separate process; an independent disposable-root drill confirmed empty starting databases and no cross-case results. No model ran. This proves persistence, retrieval and source preservation, not task-solving utility, stale-decision handling by a model, or independently observed retrieval during a model trial. Moving an exported arm into a container requires rebasing its explicit absolute memory environment paths to that container's mount location.

### CK-05 — Measure and reduce methodology overhead [M]

**Targets:** existing rigor gate/result pipeline, `eval/trigger_eval.py`, selected existing skill descriptions and owned runtime prompt files.

**Work:** compare pinned Full Kit, a precisely defined thin candidate and separable bare/upstream baselines where supported. Record executor/model/tool permissions, prompt hashes, cache categories, failed runs and independent task outcomes. Change one prompt surface at a time. Preserve host instructions; optimize only kit-owned content.

**Acceptance:** the candidate meets predeclared quality gates and reduces measured cost on the same workload; safety-sensitive failure cases are not hidden by an average pass rate; unavailable token fields remain unknown rather than zero. Description edits also preserve trigger behavior on positive and negative cases. No 95% target invented after observing the run.

**Dependency:** CK-03; can run independently of CK-04, but the findings must remain separate. Existing `total_input_v1`/cache-aware accounting is the baseline to inspect and reuse, not a new format to recreate. Older incompatible reports stay labelled incomparable; do not rewrite raw history.

**Decision gate:** if inconclusive, retain the existing default. If cost decreases but quality degrades, reject that candidate. Only reproducible non-degrading evidence supports a default change.

### CK-06 — Fresh-user adoption and recovery drill [M]

**Targets:** `scripts/install.py`, `tests/test_install.py`, existing README/onboarding documents, `scripts/tools/backup_memory.py`.

**Work:** run documented install → save → search → restart → retrieve on a clean supported Windows and Linux environment; upgrade an existing fixture without changing its Wiki/findings; restore a backup into a separate root and retrieve the saved fact. Validate agent integration separately from memory bootstrap.

**Acceptance:** no live-home writes in development; saved knowledge survives upgrade and restore; failures identify the missing prerequisite; a reader can follow the public commands without author-specific paths or credentials. Historical onboarding fixes are retained, not reimplemented.

**Dependency:** CK-01 for deployment portion; basic memory drill can proceed independently. Measure first-use time rather than promise an unsupported minute target.

**Status 2026-09-11 — drill executed on Windows (isolated root); Linux environment still unexercised.** Ran the documented commands against a temporary `MEMORY_ROOT` + empty `HOME`: `install.py` (exit 0, `search smoke: OK`), `findings.py add`, `search_all.py` retrieval, re-run of `install.py` as the upgrade path (only SQLite sidecars and the rebuilt `wiki.db` changed — the saved finding survived intact), `backup_memory.py` (default destination), `--list`, and `--restore-drill` (exit 0 with `integrity_ok: true`, `findings.ok: true`, `doctor_rc: 0`, `search_hits: 1`), then retrieval from the live root after the drill. The drill exposed a real defect: `--restore-drill` exited 1 on a healthy restore whenever `~/.memory` was absent, because the findings probe stripped `MEMORY_ROOT` and `log.py` resolved `_compat.chulan_root()` from home; fixed by probing against a throwaway marker-carrying root (regression `tests/test_backup_memory.py::BackupDrillTest::test_drill_findings_probe_needs_no_ambient_memory_root`, red before / green after). README now documents the backup and recovery commands. Not done: a Linux run, a first-use time measurement, and the agent-integration half of the drill.

## LATER — release only demonstrated capabilities

### CK-07 — Public release and licence boundary [M]

**Targets:** current README, `docs/SECURITY-MAP.md`, `profile.yml`, distribution/build paths and licence declarations.

**Work:** attach every public quality/cost/memory claim to reproducible evidence; distinguish observed support from untested adapters. Resolve redistribution permission for the proprietary skill with the rights holder or explicitly exclude it from the redistributable profile and validate that profile separately. Do not relabel the skill MIT or claim legal clearance because doctor accepts its frontmatter.

**Acceptance:** published artifact has a clear file-level licence inventory; installation and restore drills pass on that artifact; example data contains no personal memory or credentials; changelog names supported behavior and limitations. Version bump follows the actual contract change, not a preselected v5.0 milestone.

**Dependency:** CK-02/06; CK-04/05 required only for the claims/default changes they govern. A valid negative experiment does not prevent a modest release with honest claims.

## Metrics and stop conditions

| Question | Measure | Decision rule |
|---|---|---|
| Does memory help? | Independent later-task outcome with/without memory, retrieval provenance | Claim benefit only for the measured cases and executor settings. |
| Is methodology worth its cost? | Outcome, elapsed time, uncached/cache-read/cache-write usage | No default reduction based on failed or confounded comparisons. |
| Can users recover? | Saved fact retrieved after isolated restore | Exact recoverability required; backup existence alone is insufficient. |
| Is deployment safe? | Preview/apply agreement and preimage restoration | Any unexpected write blocks release. |
| Is onboarding usable? | First save/search success and observed setup time | Remove observed friction; avoid adding another gate as the product. |

No new orchestration framework, vector database, broad adapter expansion, paid benchmark sweep or catalogue-growth quota. Reconsider external storage only after an observed retrieval/capacity problem that SQLite cannot reasonably solve.

## First executable package

**CK-01/preview [M]:** extend `tests/test_deploy_cli.py` to specify standalone preview against disposable repository/home fixtures; preserve existing help/error guarantees; reuse generated target content for preview; exercise actual subprocess before and after. Run `python -m pytest tests/test_deploy_cli.py tests/test_release_contract.py -q` in the project environment. Never run bare `deploy.py` to inspect its interface. Recovery is the next subset of CK-01, not an unimplemented promise attached to preview completion.

## Sources and evidence boundary

- [Release history](../../CHANGELOG.md): existing deploy, onboarding, instruction hierarchy and licence work.
- [Deploy incident](../../research/2026-09-06-deploy-help-incident.md): exact failure, remediation and isolated smoke evidence.
- [Confounded eval](../../research/2026-09-06-bounded-eval-incident-negative-result.md): failed arms and isolation gate.
- [Raw verification](../../research/2026-09-06-final-verification-raw.txt): historical focused passes and skills-sync failure.
- [Product research](../../research/2026-09-05-open-source-product-direction.md): alternatives and unproven memory/default-thin hypotheses; usage regex statistics have acknowledged limitations.
- [Deploy source](../../../scripts/tools/deploy.py), [isolation source](../../../eval/rigor/isolation.py), [skill conformance tests](../../../tests/test_skill_spec_conformance.py).

This planning session reconciled sources and checked document paths; it did not run application suites, deploy instructions, repair mirrors or execute model evaluations. Earlier raw verification is historical evidence only. This roadmap supersedes completed evolution-wave priorities, not the user's instructions or unresolved release constraints.
