# Hermes H1 evidence: missed-recall table + native discovery matrix — 2026-09-13

Execution of H0/H1 from [First Hermes adapter package](../superpowers/plans/2026-09-12-hermes-adapter-first-package.md).
Disposable profile: `/tmp/hermes-h0` on the server (hermes-agent @ `476a45f4f336`, v0.21.2, live gateway untouched, verified by mtime guard).
Probes: `h0_import_probe.py`, `h1b_probe.py` (17/17 checks), `h1a_scan.py`, `h1a_case*.py` — kept in `/tmp/hermes-h0/probes/` until H3 completes.

## H1a — missed-recall evidence table (read-only, state.db)

Selection: sessions named by first human turn; 517 sessions with human turns scanned, 75 (14.5%) touched any memory surface (memory tool, session_search, kit CLI). No global failure rate claimed — this is a purposeful sample.

| # | Session(s) | Expected fact | Its source & availability | Recall surface used | Decision affected | Outcome class |
|---|---|---|---|---|---|---|
| 1 | 2026-08-16 `aace2910` (zip kit update) | maintenance pitfalls (`cp -a` vs state.db, SOUL bump, `--delete`) | skill `coding-kit-maintenance` — **did not exist yet** (created 2026-09-08, mtime verified) | none possible | update quality | **knowledge-absent** (not a recall failure); the session's own lessons were later distilled into the skill |
| 2 | 2026-08-23 `466b6487` (MP v1.8.1 deploy) | deploy procedure, dashboard paths | `multiproxy-operations` + `references/deploy-new-version` (skill_view, msg 96985–96989) | skills + live config | deploy steps | **positive control**: staging→backup→deploy→verify all followed; memory + findings.py written at end (id=2xx) |
| 3 | 2026-08-23 `f0fd86a9` (provider prep) | whitelist/alias rules for akml/egor | own session discovered from live config; memory write at end (95%) | terminal reads of live state | whitelist edits | **correct without retrieval** (repo/config was the authority; nothing pre-recorded to miss) |
| 4 | 2026-09-08 `3eb563db` (kit update + deepseek2 provider) | kit update pitfalls; MP2 provider layout (keys/ symlink, whitelists) | skill loaded 5× (120933…121064); MP2 layout in native MEMORY.md | skill_view + memory tool | provider add | **save-side failure**: native memory at 95–99% of 2,200 chars; one write REJECTED ("would put memory at 2,204/2,200"); later replace failed ("No entry matched"); agent had to compress by hand. No decision-level recall miss observed |
| 5 | 2026-09-08 same, bare-name model claims | earlier recorded fact about bare-name double-claims? | none found in findings/Wiki before the session | fresh discovery (log warning 121843) | alias config | **no earlier fact existed** → fresh discovery, correctly reported |

**Verdict (per plan R1 decision rules):** no decision-level recall miss demonstrated in the sample. The one real, reproduced failure is **native memory capacity saturation** — a Hermes-side save constraint, not a kit retrieval gap. Consequence: stop memory redesign; the adapter needs no retrieval feature. Durable-fact offload path (native MEMORY.md → findings.py) already exists and was used; the adapter documentation should recommend it explicitly at the capacity limit.

## H1b — native discovery/ownership matrix (disposable profile, no model)

Layouts: A = external root `<ext>/coding-kit/<skill>` via `skills.external_dirs`; B = local copy `<home>/skills/coding-kit/<skill>` (live-server layout).

| Scenario | Layout | Observed result |
|---|---|---|
| Catalogue visibility | A | `skills_list` 37/37, category `coding-kit`; rendered prompt index 37/37 under `coding-kit:` — full visibility, no leak to other categories |
| Trigger truncation | A | canonical descriptions 150–231 chars render as first 57 chars + `...` (`extract_skill_description`, limit 60). No selection harm demonstrated (H1a); documented as measured limitation |
| Same name local + external | A+local copy | local copy **claims the name** in the prompt (kit entry vanishes from `coding-kit` category); `skills_list` shows 1 entry; bare-name `skill_view` REFUSES ("Ambiguous skill name"); categorized `coding-kit/<name>` loads the full kit body (3,646 chars, verified content) |
| Bundled-manifest collision, external | A | `is_curation_eligible` returns **True** (name-based flag) but `archive_skill` REFUSES via two independent external guards — external skills are write-protected in practice; flag ≠ write access |
| Bundled-manifest collision, local copy | B | `is_curation_eligible` True, appears in `list_agent_created_skill_names()`, and **`archive_skill` really archives it** — live hazard confirmed. On the live server 3 kit names are bundled (`requesting-code-review`, `systematic-debugging`, `test-driven-development`) with `curator.prune_builtins: true` and interval 168h |
| Missing external root | A | silently skipped (`get_external_skills_dirs` → []); adapter must validate existence itself |
| Env boundary | — | `HERMES_HOME` redirect honored end-to-end (config, skills, snapshot); import + prompt build + curator probes wrote nothing outside the probe root (gateway-volatile files excluded) |

## Consequences for H2

1. External-root layout is the correct primary: full visibility, protected ownership, category route `coding-kit/<skill>` works.
2. No description projection generator: truncation is real but harmless at decision level in the sample (YAGNI; revisit only with a demonstrated selection failure).
3. Adapter MUST: validate external root exists; refuse/flag name collisions against local skills and `.bundled_manifest`; handle legacy local `skills/coding-kit/` copy retirement as an explicit migration step; keep `SOUL.md` edits inside delimited kit markers; default to preview.
4. Native MEMORY.md capacity (2,200 chars) is an ops constraint: document the findings.py offload route in `adapters/hermes.md`.

## Follow-on local research and adapter repair

Sanitized prompts, responses, source snapshot and measured JSON are retained locally under `eval/results/knowledge-procedure-20260913/` (not a distributed release artifact). `metadata.json` records the scope: stateless `completion()` decisions, no native Hermes/OMP session and no model-executed code. The backend behind alias `default`, temperature and usage were not exposed; the parent model identity is not substituted for them. The user's model switch also prevents comparing earlier development with this repair as a same-model experiment.

| Comparison | Observed outcome | Boundary |
|---|---|---|
| Balanced hidden decisions, 8 variants × 2 repeats | repository-only, discoverable search and explicit search each 0/16 correct, 16/16 abstentions; identical-inline facts 16/16 correct | Models did not guess an unavailable policy; search access alone was insufficient |
| Same balanced cases, two-request search protocol | capability alone 0/16; lexical-query/full-note procedure 16/16 | Real isolated findings CLI behind a simulated request loop; not native tool selection |
| Stale, conflicting and repository-sufficient controls, 2 repeats | both protocols 6/6 correct; procedure added 8 retrieval requests versus 0 | Retrieval has overhead when the repository already settles the action |
| Check selection, compact core versus targeted updater procedure, 3 repeats | both selected all five required checks in 3/3 attempts | Supplied choices expose the right checks; no execution-quality gain established |

CLI smoke independently returned the Cedar decision for `Cedar` and `Cedar OR Birch`, but no hit for `Cedar outage what should we do`. The existing `dev-wiki` search procedure now explains lexical AND matching, short initial queries, full-note reads, and retrying a simpler query before claiming absence. It explicitly avoids mandatory retrieval when current authoritative evidence suffices. No provider, automatic recall, prompt reduction or skill-load quota was introduced. Only the repository skill mirror is synchronized; live harness installations are not deployed.

### Filesystem verification, not model-performance evidence

The original adapter passed its own tests while violating required guarantees. Strengthened byte-level regressions first observed 7 failures and 13 passes; after repair and additional update/restore boundaries, the adapter suite passed 23 checks. A separate CLI/file probe (`recovery_probe.py`) against the saved original adapter failed all six cases: foreign sibling preservation, CRLF restore, binary assets, failure during recovery-record persistence, recursive legacy discovery, and truthful preview. The same probe against the repaired adapter passed all six. Raw logs: `recovery-before.json` and `recovery-after.json`.

Recovery now captures individual owned skill subtrees as exact byte images, includes recovery metadata in the handled-I/O transaction, preserves unrelated siblings, and records legacy bytes outside the scanned tree. Custom external roots must remain inside the selected profile; restoration retains first-touch preimages across updates. Generated subtree contents are owned, not an editable user surface. Concurrent writes and power-loss durability are not claimed. Old recovery formats are rejected rather than guessed or silently converted.

Two requested independent agents (review and probe authoring) failed with provider 502 before delivering results. The separate probe was authored and executed by Main; this is independent of the adapter's test implementation, not independent-agent signoff. Native Hermes integration was not rerun after the repair. Live migration remains separate and unperformed.

Integrated local verification: `python -m pytest tests/test_hermes_adapter.py tests/test_deploy_cli.py tests/test_deploy_rollback.py tests/test_deploy_ownership.py tests/test_skills_sync.py tests/test_release_contract.py tests/test_memory_experiment.py tests/test_evals_colocation.py tests/test_skill_lifecycle.py -q` → **123 passed, 1 skipped, 5 subtests passed**. `integrity_manifest.py` → **171 files verified**; `check_file_sizes.py --ci` → **hard 0, soft 36, gate green**. These are the exercised contracts, not a full-suite claim. Probe source is retained as non-installed research evidence; disposable databases are removed after result capture.

**Decision:** the demonstrated product change is a clearer existing search contract, not a new memory system. The procedural selection pilot was inconclusive; retain current method defaults. Actual cross-harness transfer and executed full-kit versus thin-core comparisons remain unmeasured.

## Executed code-synthesis comparisons — 2026-09-13 (second package)

Artifacts: `eval/results/autonomous-knowledge-20260913/` (`metadata.json`, `confinement.json`, `native-adapter-result.json`, `model-comparison.json`, `validation/`). Scope: stateless `completion()` code synthesis; generated code executed only inside no-network read-only-root Docker; independent verifier mounted read-only. Not a native agent session; no tool loop during synthesis.

| Component | Observed result |
|---|---|
| Docker escape battery | 10/10 checks: secret never read, all outside writes/symlink/subprocess escapes blocked, network blocked, no docker socket, host env absent |
| Native adapter probe (real Hermes `skills_tool`/`prompt_builder`/`skill_usage`, disposable profile) | 9/9: preview mutates nothing; 37/37 catalogue + rendered prompt; categorized load full body; curator archive refused for projection; repeat apply idempotent; restore byte-exact and removes projection |
| Scenario validation (confined) | memory scenario: reference 10/10, stub fails all 10, four controls fail exactly their documented fail-sets, mutating control fails only `no_input_mutation`. procedure scenario: reference 11/11, three faulty controls fail exactly the targeted checks |
| Code synthesis, procedure task (3 conditions × 2 repeats) | neutral 2/2 pass, thin core + targeted verification procedure 2/2 pass, full kit inline 2/2 pass — all 11 checks each; the targeted condition exists only in this scenario |
| Code synthesis, routing task (2 conditions × 2 repeats) | neutral 2/2 pass, full kit inline 2/2 pass — all 10 checks each; targeted cell N/A by design — no targeted artifact exists in `memory-execution-fresh/` |

Measurement defect found and corrected mid-run: the collection script reused tuple keys across the two scenario groups, overwriting four procedure results with routing solutions (surfaced as `AttributeError: no attribute 'preview'`); handles were re-waited and the four runs re-verified from the correct texts. The targeted/neutral procedure difference in code length (13.6K/13.2K vs 16.0K/14.2K neutral, 9.3K/9.5K full kit) is observational, not a quality metric.

Limitations before any ablation reading: n=2 repeats per cell — pass counts are directional, not statistical. The targeted condition exists only in the procedure scenario, so targeted-vs-neutral and targeted-vs-full-kit statements are procedure-scenario-only; the routing scenario supports only neutral-vs-full-kit.

Interpretation at actual scope: with this backend both tasks were solvable from the neutral prompt alone, so **no kit condition demonstrated a measurable benefit over the thin core** — consistent with the earlier "tests pass, procedure adds nothing" finding, now with executed code rather than check selection. The tasks are solvable; a discriminating comparison needs a task whose failure mode the neutral condition actually exhibits (deliberately harder oracle variants remain unrun). No claim about native on-demand skill loading, retrieval efficacy, or cross-harness transfer is supported.

**Decision (second package):** no kit change follows from these results. The scenario pair, confined verifier battery, and control fail-sets are retained as reusable harness; harder discriminating variants are the named next step, not a catalogue or prompt change.
