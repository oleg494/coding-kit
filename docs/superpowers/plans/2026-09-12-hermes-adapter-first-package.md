# First Hermes adapter package — 2026-09-12

## Decision

This is the bounded Hermes integration track, not the overall coding-kit research sequence. Keep one kit and harness-specific adapters. The user reports OMP works well; preserve that working installation. General product questions and clean-profile comparisons follow the [corrected memory/procedure roadmap](2026-09-12-hermes-memory-roadmap.md#scope-correction--2026-09-13), independently of live-server migration.

The first package must make the kit's Hermes connection reproducible and its ownership explicit, while preserving the working OMP installation. Native memory remains native. Shared project findings remain in the existing kit store.

This document is a plan, not authorization to implement, deploy, restart the live gateway or spend on model calls. It operationalizes R1/R2 of the [memory roadmap](2026-09-12-hermes-memory-roadmap.md); R3/R4 remain separate experiments. Preserve the [development roadmap](2026-09-06-development-roadmap.md) recovery and model-isolation boundaries.

**Status correction — 2026-09-13:** the earlier H0–H3 completion claim is refuted for adapter acceptance. Isolated self-review reproduced deletion of a pre-existing foreign file on restore, loss of original CRLF bytes, and changes remaining after recovery-anchor write failure despite a rollback message. Local migration left the old procedure under the scanned `skills/` tree (native traversal inspected; end-to-end migrated discovery still to check), and preview advertised retiring a foreign directory that apply preserved. These are required repairs before accepting or using this adapter. Earlier successful discovery probes remain bounded evidence; H4 remains unauthorized and technically blocked. This blocker does not prevent host-independent experiment preparation.

## Ownership and non-goals

| Owner | Responsibility | First-package boundary |
|---|---|---|
| Kit core | Canonical procedures, memory CLI, knowledge lifecycle | No changes to `AGENTS.md`, `OPS.md`, `skills/**`, `memory/**` or their working OMP consumers |
| OMP integration | Existing routers and skill discovery | Protected baseline; no reinstall, prompt reduction, additional startup rule or behavioral experiment |
| Hermes adapter in the kit | Hermes presentation, exact skill loading, installation/update ownership and memory routes | Primary implementation target, after the probes below |
| Hermes itself | Native discovery/index/cache/curator behavior | Separate defect only after a reproducible native contract failure; not an implicit patch target |
| Product research | Whether kit knowledge improves decisions or transfers between harnesses | Later, separately bounded experiment; not established by successful installation |

Do not add a memory provider, vector database, automatic search on every turn, transcript synchronization, catalogue-wide renaming, a second editable set of procedures or a generic adapter framework. Do not disable the entire Hermes curator to protect kit files. Do not change `eval/memory_experiment.py` in this package.

## Established facts and remaining uncertainty

- [`deploy.py`](../../../scripts/tools/deploy.py) has no Hermes target in `HARNESSES` or `SYNC_TARGETS`. Do not invoke its general deployment path to install this adapter.
- [`install.py`](../../../scripts/install.py) bootstraps the memory root; it does not install Hermes rules or skills.
- [`UNIVERSAL.md`](../../../adapters/UNIVERSAL.md) describes `skills.external_dirs`. The inspected server instead uses `~/.hermes/skills/coding-kit/`, with `rsync` and manually propagated compressed `SOUL.md` changes in `coding-kit-maintenance/SKILL.md`. There is no Hermes renderer in the inspected kit deployment path.
- Hermes `agent/skill_utils.py:extract_skill_description` keeps at most 60 characters, including `...` on truncation. Lost trigger detail is established; an effect on model selection is not.
- Hermes `agent/prompt_builder.py` skips external names already indexed locally; `tools/skills_tool.py:_find_all_skills` also deduplicates by name. `skill_view` separately refuses ambiguous loads. An external directory alone therefore does not guarantee visible, unambiguous skills.
- `tools/skill_usage.py` excludes external paths from curation candidates, but identifies bundled names through `.bundled_manifest`. This is evidence for testing external ownership, not proof that the proposed installation or a future Hermes update works.
- [`usage_audit.py`](../../../scripts/tools/usage_audit.py) recognizes `skill://...` and aggregates several different CLI tools under memory counters. Use actual Hermes tool names, arguments and results for case analysis; those aggregate counts do not establish retrieval or utility.

Server source observations concern `/home/user1/.hermes/hermes-agent`, inspected on this date. Record its exact revision and the installed kit version when executing; source/configuration on disk is not evidence of the live gateway's loaded state.

## H0 — Fix the boundary and prepare disposable inputs

**Deliverable:** one small baseline record and a reproducible temporary profile, without invoking a model.

- Record the source revisions, canonical skill set, current installation roots and documented update route. Record only relevant configuration keys, never credentials or complete private prompts.
- Define the protected set: kit core paths above, current OMP router and discovered kit skill copies. Compare bytes before/after future adapter execution. A matching version string is insufficient.
- Use a disposable Linux profile with the inspected Hermes interpreter. Set `HERMES_HOME`, `HOME`, `MEMORY_ROOT`, working directory and all discovered cache/config roots before importing Hermes. Use an empty project directory so ambient project skills cannot alter lookup.
- Seed synthetic notes, session history, findings and skill fixtures; never copy production `state.db`, `MEMORY.md`, `USER.md`, authentication files or `.env`. Keep the canonical kit source read-only to the probe.
- Inspect import/startup side effects first. Deterministic probes run without model credentials, a gateway, background curation or production tools. Environment redirection is not a claim of OS-level confinement.

**Acceptance:** every writable path used by the probe is under its temporary root; synthetic data is distinguishable from live data; protected roots are unchanged. If an import ignores these roots, fix the probe boundary before proceeding.

## H1 — Diagnose two independent questions

These investigations can run in parallel after H0, with separate outputs and no shared edits. Their common contract is: `case -> expected fact or skill identity -> owning source -> observed result -> proposed owner of the fix`. Neither worker implements or runs project-wide validation. The integration owner chooses the change after both results arrive.

### H1a — Was relevant knowledge actually missed?

Select 4–6 completed Hermes tasks with a concrete earlier fact that could change the action. Include a correct result without kit retrieval and a case where repository evidence already suffices, not only apparent failures.

For each case record:

- Exact expected fact and why it mattered; its source, date and supersession status.
- Evidence that the fact existed before the task and was available to that session. Current filesystem presence cannot establish historical availability.
- Prompt presence if recoverable, actual queries/tool results, and the resulting decision.
- Outcome: correctly used, unnecessary, unavailable, not discovered, wrong query, stale/conflicting, ignored after retrieval, or indeterminate.

Use read-only access to the necessary trace windows; keep raw private sessions outside the repository and store only sanitized evidence. Reuse existing transcript normalization where adequate. Do not expand audit telemetry just to produce this table.

**Acceptance:** every claimed miss has an affected decision and evidence; missing trace information remains indeterminate. No global failure rate, no equation of zero kit CLI calls with failed memory, and no new retrieval feature unless a specific case requires it.

### H1b — Can native Hermes safely expose the kit?

Exercise native prompt construction, `skills_list`, `skill_view` and curator eligibility/reporting in the disposable profile. Compare the existing categorized-copy layout with a supported external-directory layout. Do not reproduce Hermes logic in a mock and call that an integration check.

Required scenarios:

| Scenario | Observable result |
|---|---|
| Canonical kit catalogue | All expected enabled/platform-compatible skills are accounted for; intentional filters are reported |
| Same name in a local/bundled skill and the kit | No wrong procedure is loaded silently; observe prompt visibility separately from explicit-path loading |
| Categorized lookup | The documented `coding-kit/<skill>` route resolves to the intended full procedure and supporting files |
| Truncated trigger | Compare the actual rendered description with an explicit distinguishing condition; check a Hermes-only candidate without editing the shared source |
| Bundled-manifest name collision | Kit-owned paths remain excluded from curation; a report row alone is not proof of filesystem safety |
| Fresh process and update/reseed | Intended identity and visibility survive normal discovery refresh; no second editable kit copy appears |
| Missing external root or incomplete candidate | Installation validation reports the failure, rather than declaring a working adapter |

Use synthetic collision fixtures; do not repeat historical duplicate cleanup on the live server. Curator mutation probes, where needed, are confined to disposable files and invoke the native non-model path.

**Acceptance:** report each scenario with actual output and source identity. If external discovery silently hides the kit, that candidate is not accepted merely because an explicit load succeeds.

## H2 — Implement only the demonstrated Hermes boundary

### Selected direction

Prefer native `skills.external_dirs` with kit-owned inputs outside the curator's local skill tree. Preserve categorized loading by choosing and verifying the external root layout, rather than assuming `<kit>/skills` provides a `coding-kit/` category.

Use canonical skills directly if that satisfies the index contract. If H1b requires shorter Hermes descriptions, generate a disposable/installable Hermes projection from canonical `skills/`: same names, procedure bodies and support files, with only the required description overrides. Generated files are never edited as a second source of truth. Retain complete canonical descriptions for OMP.

Before building a projection generator, render a few observed problem cases through the real Hermes path. Accept only descriptions that preserve the intended distinction; `length <= 60` alone is not semantic acceptance. Validate the whole enabled catalogue before any installation. Do not grow a second routing taxonomy.

If native behavior cannot provide both visible identity and protected ownership, produce the minimal reproduction and make the required Hermes fix a separate dependency. Do not hide that failure with catalogue-wide aliases, broad curator disabling or edits to `.bundled_manifest`/`.usage.json`.

### Planned files and contracts

Paths marked **new** are proposed implementation targets, not existing files or artifacts created by this planning task.

| Target | Change |
|---|---|
| `adapters/hermes.md` — **new** | Supported roots/layout, ownership, routes, preview/apply/recovery instructions and measured limitations |
| `adapters/UNIVERSAL.md` | Replace the Hermes “no extra work” shorthand with the verified contract and a link; leave other harness instructions intact |
| `scripts/tools/hermes_adapter.py` — **new** | Small Hermes-only preparation/apply entry point; no enumeration or deployment of other harnesses |
| `adapters/hermes/skill-descriptions.json` — **conditional new** | Only measured Hermes description overrides keyed by canonical name; reject unknown/stale entries |
| Existing `tests/test_deploy_*.py` patterns; `tests/test_hermes_adapter.py` — **new where justified** | Regressions for foreign-file preservation, conflicts, preview/apply agreement and recovery; do not repin incidental wording |
| `docs/CHANGELOG.md` | Only the actually verified support boundary after implementation |

Do not add Hermes to the general `deploy.py` target loop. Reuse `_deploy_fs.py` / `_deploy_tx.py` only where their existing path and handled-I/O rollback contracts fit; do not enlarge them speculatively. If shared helpers must change, that becomes an explicitly reviewed shared change with their existing regressions run.

The Hermes-only command contract is deliberately narrow:

- Inputs: explicit kit root and explicit Hermes profile; explicit output root if a generated skill projection is needed. No write target inferred from the current user's home.
- Default action: read-only preview. `--help`, invalid arguments, missing prerequisites and ownership conflicts never mutate targets. Applying a displayed plan is explicit, not a fallback on parse errors.
- Preview names the owned changes and conflicts without printing private configuration. Apply uses the same planned content, rechecks preimages and refuses drift since preview.
- Preserve unrelated YAML settings, native notes/history and user-authored skills. Do not silently reinstall or upgrade the memory engine as part of adapter installation.
- Treat `SOUL.md` as a mixed-ownership file, not as disposable generated content. Use an explicitly delimited kit-owned routing block. For migration from the existing manually compressed derivative, identify the old kit section first; preserve all personal sections. Ambiguous ownership is a conflict, never permission to overwrite the whole file.
- Keep the current core methodology unchanged during this package. The Hermes block only carries verified paths/identity and the routes below; it is not another full AGENTS copy or a new compression experiment.
- On migration, retire only positively identified old kit-managed copies after the replacement validates. Never delete same-named foreign skills or leave both kit layouts active. A mixed/modified legacy directory requires an explicit ownership decision before live application.
- Preserve preimages, previous absence and owned-tree membership. A handled failure restores exact prior bytes and removes only newly created managed files. Retain an explicit recovery artifact through post-install validation; do not claim power-loss durability from `_deploy_tx.py`.

### Memory routing, not a new memory system

| Question | First source |
|---|---|
| Exact previous conversation or execution | Hermes `session_search` |
| Durable project decision / rejected approach / known pitfall | Existing kit project documents and findings search |
| How to execute a procedure | Native skill discovery and exact `skill_view` |
| What is configured or running now | Owning repository/configuration and observed runtime |
| Stable user preference | Hermes native memory |

No mandatory tour through every source. Failed search, empty search and absent store remain distinguishable. Retrieved history/findings are evidence, not instructions or current deployment authority. Respect `MEMORY_ROOT`, source dates and supersession; do not copy findings wholesale into `MEMORY.md`.

Verify reachability with a synthetic finding and native history fixture. This proves tool/store access, not that a model will select the right route automatically.

## H3 — Accept the adapter in the disposable profile

Run one integrated installation/update/recovery drill after implementation:

1. Preview the candidate; show no writes and the precise planned owned changes.
2. Apply it, render the real index, load intended procedures/support files and retrieve the seeded finding through the documented CLI.
3. Restart the disposable process and repeat discovery. Exercise native curation eligibility and the update/reseed scenario that could reintroduce collisions.
4. Apply the same version again: no unintended changes. Upgrade a fixture version with a removed kit skill: retire only that owned skill, preserving foreign files, native notes/history and findings.
5. Inject a failure after an owned write; restore exact preimages and prior absence. Also reject a foreign `SOUL.md`/mixed legacy tree without mutation. Preserve explicitly owned blocks without damaging surrounding user content.
6. Compare protected OMP/core bytes and inspect the observed write set. Any unplanned write blocks acceptance. Run the affected existing regressions once after integration.

**Done for this package:** a reproducible Hermes-only adapter, truthful ownership/discovery behavior, demonstrated access to existing memory routes, successful update/recovery, and unchanged OMP/core surfaces. No live configuration or provider has changed. No claim of improved model reasoning, retrieval rate or general memory utility follows from these checks.

A passing file/CLI drill and an unrun model trial must be reported separately. Keep permanent regressions only for plausible recurring failures; remove throwaway probes after preserving sanitized results and reproduction instructions with the adapter documentation.

## H4 — Separate transition to live Hermes

Only in a subsequently authorized application task:

- Back up the exact target configuration, SOUL content and kit-owned skill layout; prepare restoration before the first mutation. Do not export credentials or private notes into the repository.
- Review/apply only the verified Hermes plan. Replace the live `coding-kit-maintenance` recipe so its next `rsync` cannot recreate the retired installation layout. The recipe is a server-owned migration target, not an implicitly edited file in this plan.
- If a gateway restart is required, identify the actual managed process and use its established lifecycle procedure. Record the loaded version/startup evidence and exercise the affected route in a new session; files on disk alone are not a successful rollout.
- If visibility, ownership or routing regresses, restore the previous Hermes state. Leave OMP and the common kit unchanged.

Model-backed routing/utility checks require a bounded run and the existing CK-03 executor/verifier isolation prerequisites. Do not silently turn this rollout into a paid benchmark sweep.

## What follows — only with evidence

- If H1a shows no decision-level recall gap, stop memory redesign. Reproducible installation may still be useful on its own.
- If a specific fact is reachable but predictably undiscovered, test a narrow Hermes routing change before a provider.
- If the failure is native lookup/curation, fix Hermes with that reproduction, not the common kit.
- A demonstrated shared limitation belongs in a separate core change checked against both harnesses; absence of a server-specific miss does not settle that question.
- Prepare portability cases independently of this adapter repair. Actual Hermes/OMP transfer trials need safe disposable discovery and the authorized model-isolation boundary, not completion of H4. Transfer only declared project knowledge/procedures; preserve the working OMP installation and ordinary native-Hermes capabilities as controls.

## Planning verification boundary

This plan is grounded in the linked kit sources and the inspected Hermes native functions and maintenance recipe. Planning verification checks document links, existing target paths and coverage of ownership, discovery, memory routing, recovery and OMP preservation. It does not execute H0–H4, tests, a gateway restart, a deployment or a model experiment.
