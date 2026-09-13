# coding-kit roadmap refinement: portable knowledge and procedures — 2026-09-12

## Decision and scope

Develop coding-kit as portable, evidence-backed project knowledge plus targeted engineering procedures, not a replacement for Hermes memory. The product hypothesis is that a decision learned in one harness can improve a later task in another; this remains unproven.

This is a planning deliverable. No runtime configuration, installed skill, provider, deployment or model evaluation is changed or authorized here. Retain the safety and release gates in the [existing roadmap](2026-09-06-development-roadmap.md). This refinement changes research priorities, not installed defaults.

## Scope correction — 2026-09-13

The user's server Hermes is one observed environment, not the product boundary. The research target is the chain **available knowledge/procedure -> discovery -> correct application -> independently checked outcome**, across harnesses. Skill-load counts measure access, not benefit. Safe installation is a separate necessary adapter property, not evidence of better decisions.

The adapter self-review supplied a second failure class: procedures were loaded and tests passed, yet the reported guarantees were false. Recorded isolated probes found foreign-file deletion on restore, CRLF byte loss, and committed changes after recovery-anchor write failure despite a rollback message. This is evidence of application/verification failure in this development session, not evidence of a general Hermes recall problem or of kit causation. The adapter remains unaccepted until repaired and rechecked.

Keep two bounded work tracks; neither requires migration of the live server:

- **Product evidence:** prepare host-independent cases and explicit outcome checks using existing `eval/memory_cases.json`, `eval/memory_experiment.py`, task/rigor scenarios and result formats. Use synthetic projects and isolated storage, not production transcripts as fixtures. Do not add a benchmark framework, memory provider or another mandatory startup rule.
- **Adapter safety:** repair the known ownership, byte restoration, transaction-finalization, legacy-discovery and preview/apply defects before any use of the candidate adapter. Verify in disposable profiles on recorded Hermes revisions; working server/OMP installations stay unchanged. Adapter readiness gates runs that actually use it, not case design or independent kit-only preparation.

**Local execution checkpoint:** [follow-on evidence](../../research/2026-09-13-hermes-h1-evidence.md#follow-on-local-research-and-adapter-repair) records the repaired adapter (23 regression checks; separate old/new filesystem probe 0/6 → 6/6), stateless lexical-retrieval comparison (0/16 → 16/16), preserved control decisions with extra retrieval cost, and no check-selection gain from the targeted procedure. This does not close native-Hermes integration, actual cross-harness transfer or model-executed procedure comparisons. The only shared procedure update clarifies the existing `dev-wiki` search contract; no installed harness was redeployed.

### Questions and checks

| Question | Controlled comparison | Evidence required |
|---|---|---|
| Was the right knowledge available and found? | Native harness baseline versus the same baseline plus accessible kit knowledge; identical-inline information diagnoses retrieval separately | Actual available stores/index, tool-returned source identity, and the resulting action; no credit for an unopened file merely existing |
| Did a procedure change execution? | Same task, model, tools and knowledge; current full kit versus a declared thin core plus targeted procedures | Consumer-visible result and forbidden side effects; keep memory constant and report all injected instructions |
| Did verification cover the claim? | Known-good and deliberately faulty disposable artifacts with the same claimed guarantee | Independent checks distinguish the artifacts; the candidate's own green tests/report cannot be the judge |
| Does useful knowledge survive a harness change? | Session A in one clean harness, B in another; transfer only declared project knowledge/procedures | B retrieves the right source, checks authority/freshness and acts correctly without source-session transcript access |

### Next evidence package (preparation, not a claimed model result)

Retain the four existing memory cases: useful hidden decision, stale decision, conflicting authority, and repository-sufficient control. They currently grade a selected action, not executed filesystem behavior, and their `memory` arm is the kit store rather than native Hermes. Do not relabel them as a completed native-baseline experiment.

Prepare a separate procedural/verification case around a synthetic managed-file updater. The task contract requires preservation of unrelated files, exact preimage restoration, and truthful rollback reporting. Generalize the failure mechanism rather than embedding server paths or the Hermes answer. Its external judge must observe:

- a foreign sentinel before installation and after update/restore;
- exact bytes for LF, CRLF and binary supporting data;
- unchanged original state after a handled failure during final recovery-state persistence;
- the actual remaining discoverable procedures after legacy migration, not just disappearance of an old directory name;
- agreement between preview's owned changes and apply's actual write/delete set.

Keep outcome expectations and the judge outside candidate access. Validate the judge against a known-good artifact and one faulty artifact per guarantee before any model trial. Reuse the existing task/rigor machinery where its isolation contract fits; deterministic validation establishes judge sensitivity, not model benefit. Keep at least one unseen variant for later evaluation so a fix tailored to this adapter cannot pass as general improvement.

For every model attempt record case/version, harness revision, model/settings, available and injected knowledge, loaded procedure identity, tool evidence, checked outcome, duration and available usage fields. Hold model/settings constant within comparisons; repeat clean-session attempts before attributing a difference to the kit. A missing or ambiguous trace stays indeterminate. First locate the failing link, then propose only the change that addresses it.

**Order:** prepare cases and verify judges; repair adapter safety independently; run separately authorized, confined model comparisons only on ready paths; test transfer between clean OMP/Hermes profiles. No live-server rollout is a research prerequisite. R1–R5 below retain their scenario-specific detail under this corrected dependency order. No general superiority, prompt-reduction benefit or automated-memory need has been established.

## Evidence baseline

Read the installed server checkout at `/home/user1/.hermes/hermes-agent` (pyproject version 0.21.2), its on-disk configuration and selected skill metadata. This is a host-specific snapshot, not a claim about every Hermes version or a restarted gateway.

- Native `MEMORY.md` / `USER.md` are bounded declarative notes injected into the prompt. Skills are separately stored procedural memory. `session_search` retrieves real SQLite transcript messages using FTS5 without an LLM call. Compression summaries are another context mechanism, not a substitute for the complete transcript.
- Native memory writes persist before the current prompt snapshot changes. A disposable-profile Python probe observed persistence, a frozen existing snapshot, a new store reading the update, and `invalidate_system_prompt()` refreshing the same store. Exit 0. No production notes were modified. Source inspection additionally connects that invalidation to compression commits; a complete interactive compression was not exercised.
- `memory.provider` is empty on disk. Optional external-provider code exists, but no active external backend is established by this inspection. A running process retaining old configuration was not checked.
- Coding-kit skills are installed in `~/.hermes/skills/coding-kit/`. Its Wiki/findings database lives separately in `~/.memory`. `SOUL.md` explicitly instructs searches through `search_all.py`; therefore the kit is NOT unknown to Hermes. What is absent is an evidenced automatic bridge from native recall to that database.
- Hermes guidance routes task procedures into skills and past conversations through `session_search`; the kit routes reusable conclusions into findings/Wiki. This is overlapping routing responsibility, not evidence that either memory system is unused.
- `agent/skill_utils.py:extract_skill_description` truncates prompt-index descriptions to 60 characters. The installed kit has much longer trigger descriptions. Loss of trigger detail is established; an effect on model selection is not yet measured.
- `tools/skills_tool.py` refuses ambiguous bare-name loads and offers categorized paths. Current inspected snapshot entries for several formerly duplicated names point once to coding-kit. Do not reintroduce the historical duplicate cleanup as unfinished work.
- `tools/skill_usage.py` identifies bundled skills by name from `.bundled_manifest`, not by source path. Some kit names remain in that manifest. This creates an ownership risk under built-in pruning; it does not prove a kit skill was actually archived. Pinning and candidate state still matter.
- Existing `eval/memory_experiment.py` prepares isolated coding-kit findings databases and repository-only / memory / inline arms. Here “native memory” means the kit engine, NOT Hermes MEMORY.md. Offline persistence and retrieval do not establish model utility.

## Ownership contract to validate

| Knowledge | Authoritative home | Access from Hermes |
|---|---|---|
| Stable user facts and universal preferences | Hermes native notes | Native memory tools and prompt injection |
| Exact prior conversation or execution trace | Hermes session history | `session_search`; inspect original messages when summaries are insufficient |
| Current project state | Repository, configuration and observed runtime | Read the owning source before acting |
| Durable project decision, rejected approach, verified pitfall | Project knowledge/findings with source and date | Existing kit CLI initially; no second copy of the fact |
| Reusable executable procedure | One owned skill package | Native skill discovery/load; references may point to supporting evidence |

A skill may reference a decision but should not maintain another independently editable copy. A historical note cannot override newer authoritative evidence or current user instructions. Missing, failed and empty searches must remain distinguishable.

## R1 — Explain missed recall before changing retrieval

**Targets:** existing `scripts/tools/usage_audit.py`, selected real session traces, Hermes prompt/index/config evidence. Inspect audit coverage before extending it; use a bounded manual table if its counters cannot answer this question.

**Work:** inspect a small, explicitly selected set of completed tasks with a known prior fact that could affect the outcome. Record the fact's actual location, whether it was present in the prompt, which searches ran, which source was retrieved and whether the final action used it. Separate correct work without retrieval, useful retrieval, missed relevant knowledge, stale-information errors and indeterminate traces. Exclude this investigation's own skill reads.

**Acceptance:** each claimed miss has a concrete expected fact and an observable affected decision. Absence of a kit CLI call is not automatically a memory failure. Publish selection limits; no general failure percentage from a convenience sample.

**Decision:** missing knowledge requires a save/routing fix; unavailable discovery requires an adapter fix; a wrong query requires retrieval work; ignored correct evidence requires behavior work. Do not implement all four by default.

## R2 — Make the existing Hermes adapter coherent

**Targets:** `adapters/UNIVERSAL.md`, `scripts/tools/deploy.py`, the actual source of generated SOUL/skill-index inputs discovered from that script, and the existing deployment/skill checks. Hermes source is evidence, not an implicit edit target.

**Work:** establish one owner for installed kit skills; preserve categorized loading; select a supported ownership mechanism that prevents background curation from treating kit copies as bundled solely by name. Assess `skills.external_dirs` against existing installation/update conventions: it prevents curator writes but is not filesystem write protection and does not eliminate all name collisions. Do not rename the whole catalogue to hide provenance errors.

Render a candidate index through the actual Hermes description path. Front-load meaningful triggers inside its 60-character window rather than copying a full OMP description and assuming it survives. Keep complete procedures on demand. Route native history versus project findings explicitly and without requiring every memory system on every turn.

**Acceptance:** in a disposable Hermes profile, intended skills load by exact identity; the rendered index preserves intended distinguishing triggers; real curator candidate inspection respects ownership; update/restart preserves intended availability; a seeded findings record is reachable through the documented route. Then measure selection behavior separately in R4. File existence alone is not activation.

**Dependencies:** R1 identifies relevant failure cases. Existing CK-01 deployment recovery boundary remains mandatory. No live-home change in this phase.

## R3 — Test incremental memory value over native Hermes

**Targets:** `eval/memory_experiment.py`, existing case fixtures/result format and CK-03 isolation machinery; retain existing preparation code where its contract fits.

**Design:** use clean sessions and identical tasks. Native-Hermes control includes its ordinary notes, skills and session-search capabilities; do not cripple that control and call the result added kit value. Compare it with the same native baseline plus accessible kit project knowledge. An identical-inline-information control separates retrieval failures from inability to use the fact. Retain repository-only as a diagnostic control, not the sole competing product.

Session A generates the evidence; session B acts without shared conversation context. Native history remains available only as the declared recall channel. Record exactly which stores each arm receives. Include one useful hidden decision, a superseded decision, conflicting sources and a case where the repository already suffices. Judge task actions independently; retrieval claims need tool-trace evidence. Missing runs stay missing.

**Acceptance:** reproducible preparation without cross-arm leakage; externally judged task outcomes, retrieved source/version, stale-information behavior, duration and available usage fields. Never score correct behavior solely by matching citation wording. Small pilots identify mechanisms, not universal superiority.

**Dependencies:** CK-03 must confine the real model executor AND verifier, credentials and network access. The current offline proof is insufficient for a live model run. Paid calls require a separately authorized bounded experiment.

## R4 — Make portability the differentiating experiment

**Targets:** the same memory fixture, existing OMP/Hermes adapters and CK-05 prompt-cost accounting. No new benchmark framework.

**Work:** first test A in Hermes -> B in OMP, then the reverse if the first probe is informative. Transfer only the explicitly owned project knowledge and required procedure, not transcripts or a hidden answer. Test the narrow claim that useful decisions survive a harness change. Separately compare full kit versus thin core plus targeted procedures on the same workload; do not change memory and methodology simultaneously.

**Acceptance:** receiving harness discovers the relevant fact, checks freshness and takes the correct action without importing source-harness conversation history. Record overhead and failures. A quality regression rejects the thinner candidate; inconclusive results keep current defaults. No quota for skill loads and no catalogue-growth target.

**Dependencies:** R3 reproducible setup and safe discovery/retrieval in each disposable harness actually used; CK-03 for model runs. R2 acceptance is required when using the new Hermes adapter, not for preparing portable cases. H4 live migration is never a dependency. Portability and prompt-cost results remain separate claims.

## R5 — Automate only the demonstrated missing step

If R1/R3 show that the existing search CLI works but is predictably undiscovered, first try a narrow explicit routing/tool surface. Consider a Hermes memory-provider adapter only if that cannot meet the observed need. Do not synchronize all stores or build an additional vector database by default.

A provider occupies Hermes's single external-provider slot, must bound lookup latency and namespace access, and cannot assume background-review writes pass through it. An automatic recall result must retain source, freshness and trust boundaries. These are acceptance requirements if a provider is selected, not authorization to build one now.

Release gates remain CK-02/06/07: reconcile installed/source versions, run fresh-user save/search/restart/restore on supported environments, and resolve file-level redistribution rights. Publish measured support and limits; avoid promising general “self-improvement” from storage tests.

## First package status and next useful work

R1/H1a has not established a decision-level recall miss in its selected server-session sample; that neither proves universal adequacy nor justifies a memory redesign. R2/H0–H3 produced discovery evidence and an adapter whose acceptance was subsequently refuted by isolated safety probes. Retain those results at their actual scope. Follow the scope-correction evidence package above; repair the adapter before using it, without making live installation the next product milestone. The bounded adapter work remains in [First Hermes adapter package](2026-09-12-hermes-adapter-first-package.md).

## Sources and verification boundary

- [Existing roadmap and CK status](2026-09-06-development-roadmap.md).
- [Kit adapter](../../../adapters/UNIVERSAL.md) and [memory experiment](../../../eval/memory_experiment.py).
- Inspected server: `agent/prompt_builder.py`, `agent/system_prompt.py:678-696`, `agent/conversation_compression.py:2797-2830`, `tools/memory_tool_store.py`, `tools/session_search_tool.py`, `agent/skill_utils.py:741-758`, `tools/skills_tool.py:473-485`, `tools/skill_usage.py:130-133,213-218,251-266`, `agent/curator.py`, `agent/memory_provider.py`, `agent/memory_manager.py`, and installed `~/.hermes/SOUL.md`.
- Dynamic evidence: disposable-profile native-memory persistence/snapshot/invalidation probe exited 0. No interactive gateway lifecycle, model-selection trial or memory-utility experiment was run in this planning task.
