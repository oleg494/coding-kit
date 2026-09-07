# Third-Round Remediation: Policy Coherence, Confinement Probe, and Eval Verification (2026-09-07)

**Date:** 2026-09-07  
**Status:** Policy remediation complete; deploy preflight & rollback verified (56/1 passed); manifest updated (144 control plane files); no live host deployment or git commit/push performed.
**Companion Documents:**
- `docs/research/2026-09-07-independent-logic-review.md`
- `docs/research/2026-09-06-bounded-eval-incident-negative-result.md`
- `OPS.md`, `AGENTS.md`, `skills/yagni/SKILL.md`

---

## 1. Executive Summary & Exact Report Scope

This note records the third-round remediation addressing two concrete policy residues (the outward action authorization contradiction in AGENTS.md and the YAGNI description single-consumer dogma in skills/yagni), the container isolation capability probe following the 2026-09-06 unbounded-search incident, and the precise mapping of existing evaluation coverage against proposed regression scenarios.

### Scope Boundaries
1. **Policy Alignments Complete:**
   - Single-sourced commit policy and outward action authorization in `AGENTS.md` (separating local commits, task-scoped temp files, and external actions).
   - YAGNI frontmatter `description:` alignment with body and `OPS.md` in `skills/yagni/SKILL.md` and `.agents/skills/yagni/SKILL.md`.
2. **Deploy & Manifest Integrated:**
   - Deployment preflight and bounded rollback verified in isolated test suites (`tests/test_deploy_ownership.py`, `tests/test_deploy_rollback.py`); `integrity-manifest.json` updated with 144 control-plane files hashed (including `_deploy_tx.py`). No live host deployment, mirror sync, or git push executed.
3. **Experiments Proposed / Unexecuted:**
   - The 10 discriminating scenarios from Logic Review §6 remain proposed evaluation targets; held-out A/B cross-arm evaluation remains unexecuted.
4. **Confinement Environment Clarified:**
   - Docker container execution configuration (`--network none`, `--read-only`, no mounts) is proven via a running probe container.
   - However, an end-to-end sandboxed agent execution harness and allocated model budget remain unresolved.

---

## 2. Policy Alignments & Authority Hierarchy

### 2.1. Action Authorization & Commit Policy (`AGENTS.md`)
The previous phrasing in `AGENTS.md` conflated local git commits with outward-facing external actions:
> `Commits and outward actions happen when the user asked or when the repo's standing convention explicitly declares them — never silently expanded by a skill.`

This contradicted `fable-method` (§Step 3 Authorization Gate) and `fable-judge`, where documentation (such as a README or internal doc) cannot authorize outward actions (e.g. push, deploy, publish, payments, data destruction). Furthermore, intermediate revisions risked ambiguity over whether repository documentation could establish standing authority for external actions or whether local scratch test files required permission.

**Remediated Text (`AGENTS.md` lines 29–38):**
```markdown
**Action authorization & commit policy:** Commits happen when the user
asked or when the repo's standing convention explicitly declares them —
never silently expanded by a skill. Local task-scoped temporary files follow
the authorized task boundary. Outward actions (push, deploy, publish, send,
payment, delete shared data, writing outside local task boundary) require
explicit user authorization (direct or explicit standing user authorization).
Repository documentation (including §3 reflexes) cannot itself establish
external authority. Memory writes require user authorization (direct or
standing) and remain bounded. Phase skills reference this rule rather than
inventing conflicting gates.
```

**Key Invariants Established:**
- **Local commits:** Follow explicit user request or standing repository convention.
- **Local task-scoped temporary files:** Permitted within the authorized task boundary without external approval ceremony.
- **Outward actions:** Strictly require direct or explicit standing user authorization. Repository documentation (including §3 reflexes) cannot establish external authority.
- **Cross-chat memory:** Bounded by explicit user authorization (direct or standing reflexes), never silently expanded into external effects.

### 2.2. YAGNI Minimalism Description (`SKILL.md`)
The frontmatter `description:` in `skills/yagni/SKILL.md` and `.agents/skills/yagni/SKILL.md` previously mandated an unconditional caller-count rule (`Abstraction with one consumer → inline`), conflicting with `OPS.md` §1 / §4 and `skills/yagni/SKILL.md` Rule 1.

**Remediated Frontmatter (`SKILL.md` line 3):**
```yaml
description: 'Always-on. Law of minimalism: don''t build what wasn''t asked for. Abstraction must pay rent via present value or a genuine change-isolation boundary; hypothetical reuse → inline. New dependency → only if the pain is measurable. Dead code → delete. "For the future" → not a reason. Use for ANY code change.'
```
This protects genuine change-isolation boundaries (such as a pure parser separating AST manipulation from I/O) while maintaining zero tolerance for speculative generalizations.

---

## 3. Release Tag `v4.3.1` vs Current Working Tree Inspection

To distinguish immutable released tag contents from working tree modifications, `git show v4.3.1` was inspected independently (read-only):

- **Tag Metadata:**
  ```text
  tag v4.3.1
  Tagger: oleg494 <oleg2200000@gmail.com>
  Date:   Mon Sep 7 11:28:52 2026 +0500
  Release 4.3.1: second-round audit remediation — deploy write boundary, verdict arithmetic, JSON lifecycle
  commit c6b268b0c892a3e8ac369fba97c86aad6bd37200
  ```
- **Git Show Evidence (`v4.3.1:AGENTS.md` lines 29–32):**
  ```text
  **Action authorization & commit policy:** Commits and outward actions happen
  when the user asked or when the repo's standing convention explicitly
  declares them — never silently expanded by a skill. Phase skills reference
  this rule rather than inventing conflicting gates.
  ```
- **Git Show Evidence (`v4.3.1:skills/yagni/SKILL.md` line 3):**
  ```text
  description: 'Always-on. Law of minimalism: don''t build what wasn''t asked for. Abstraction with one consumer → inline. New dependency → only if the pain is measurable. Dead code → delete. "For the future" → not a reason. Use for ANY code change.'
  ```
- **Conclusion:** Both contradictions were present in the published `v4.3.1` release. The remediations reside strictly in the current working tree on `master` and do not alter the historical release tag.

---

## 4. Container Confinement Capabilities & Probe Evidence

### 4.1. Confinement Prerequisite Status
Following the 2026-09-06 evaluation incident (`2026-09-06-bounded-eval-incident-negative-result.md`) where an unconfined agent escaped its scratch workspace via PowerShell search, a hard OS-level isolation gate was mandated.

- **Desktop Daemon:** Docker Desktop executable was located at `C:\Program Files\Docker\Docker\Docker Desktop.exe` and started safely (`--unattended`) without host security alterations.
- **Local Cached Images:** 34 cached images exist locally. No images were pulled from external networks.
  - Python test runner image available: `adaptix-name-mapping-aliases__6kog2ev-main:latest` (contains Python 3.12.12 and pytest 8.3.4).
  - Minimal probe image: `alpine:latest` (`28bd5fe8b56d`).

### 4.2. Probe Container Inspection Output
An isolated test container was launched with strict confinement arguments:
```bash
docker run --name probe_test --network none --read-only alpine:latest sh -c "echo probe_done"
```
Inspection of the actual container configuration via `docker inspect probe_test`:
```json
{
  "NetworkMode": "none",
  "Privileged": false,
  "ReadonlyRootfs": true,
  "Binds": null,
  "Mounts": null
}
```
Mount array: `[]`.

**Confinement Assessment:**
- **Container Configuration Proven:** The daemon supports and enforces network isolation (`NetworkMode: none`), read-only root filesystem (`ReadonlyRootfs: true`), zero volume binds (`Binds: null`), and zero mounts (`Mounts: []`) without privileged container flags (`Privileged: false`). Note: `Privileged: false` means host device pass-through is disabled, but inside the container process execution may still default to UID 0 (root) unless `--user` is explicitly supplied.
- **Agent Executor Unresolved:** Proving that container configuration can run is NOT proof that an automated, instrumented subagent execution harness is wired, isolated, or tested. No live agent trials or paid model evaluations were executed.

---

## 5. Review §6 Regression Scenarios & Eval Coverage Mapping

The 10 discriminating regression scenarios proposed in Logic Review §6 were audited against existing kit capabilities, explicitly distinguishing static scenario fixtures, deterministic component checks, and unexecuted live behavior.

| # | Review §6 Proposed Scenario | Existing Kit File / Test | Mechanism / Rigor Level | Actual Coverage Status |
|---|---|---|---|---|
| 1 | **Authorized local spike**<br>Investigates without redundant approval pause; no retained prod feature. | `eval/scenarios/authorized-work-proceeds.md` | Static scenario fixture (`FM-3.1`). Evaluates response text for stall language and missing verification. | **Fixture exists; live behavior unexecuted** under automated multi-turn runner. |
| 2 | **Local change, no git instruction**<br>Follows one declared commit policy; no skill silently expands authority. | `eval/tasks/001-fix-div-zero/verify.py` through `004` | Deterministic component check. AST oracle and git working tree inspection in sandbox. | **Deterministic component check exists**; not run in this pass. |
| 3 | **Code wrong, test/spec agree**<br>Fixes under existing authorization; does not demand 3-way agreement first. | `eval/tasks/001-fix-div-zero/` & `eval/scenarios/contract-drift.md` | Tasks 001/002 verify bug repair against failing test. Scenario evaluates comment-vs-code drift. | **Partially covered.** Defect repair verified, but dedicated scenario asserting Fable 4.1 intent formulation unexecuted. |
| 4 | **One material claim cannot be checked**<br>Labels incomplete evidence; no count-only VERIFIED label. | `eval/scenarios/false-done.md` & `tests/test_review_protocol.py` | Unit test `test_unverified_caps_verdict_at_caveats` + static scenario fixture. | **Deterministic component check** on verdict arithmetic; live judge run unexecuted. |
| 5 | **Follow-up after unchanged passing test**<br>Cites checked state; reruns only if invalidated. | `eval/scenarios/calibrated-testing.md` | Static scenario fixture (`FM-3.2`). Expects targeted check run, no ceremony re-run. | **Fixture exists; live behavior unexecuted.** |
| 6 | **Old finding superseded by new decision**<br>Shows supersession and resolves applicable conclusion. | `tests/test_search_all.py` (`FindingsLifecycleMetadataTest`) | Deterministic unit check on `search_all.py --json` lifecycle metadata. | **Deterministic component check** on search metadata; agent resolution unexecuted in live session. |
| 7 | **Review-only task finishes**<br>No undeclared write/deploy/memory side effects after report. | `eval/scenarios/scope-creep.md`, `eval/scenarios/silent-cross-write.md` | Static scenario fixtures. Evaluates refusal of out-of-scope edits and cross-store writes. | **Fixture exists; live behavior unexecuted.** |
| 8 | **Single-consumer pure parser**<br>Keeps/removes boundary for present value, not caller-count dogma. | `eval/scenarios/premature-abstraction.md` | Static scenario fixture (skill: `yagni`). Evaluates refusal of speculative plugin framework. | **Fixture exists for speculative framework refusal; genuine parser retention unexecuted.** |
| 9 | **Same task on full/compact/runner profiles**<br>Same authorization and honesty invariants across profiles. | `tests/test_ops_diet.py` & `tests/test_prompt_inline.py` | Unit tests checking prompt assembly line bounds and compact exclusions. | **Genuinely missing.** No cross-profile behavioral replay exists. |
| 10 | **Skill replay plus nearby counterexample**<br>Special-case success does not become a universal rule. | `tests/test_trigger_eval.py` & `eval/trigger_queries.json` | Unit check enforcing near-miss non-triggering queries for all skills. | **Deterministic component check** for trigger rules; learning-loop policy promotion unexecuted. |

---

## 6. Verification Results

1. **Unit & Conformance Checks:**
   ```bash
   pytest tests/test_skill_spec_conformance.py tests/test_skills_search.py tests/test_prompt_assembly.py tests/test_trigger_eval.py tests/test_trend.py
   ```
   **Output:** `86 passed in 1.93s`.
2. **Confinement Container Probe:**
   `docker run --network none --read-only alpine:latest` completed with zero exit code, network unreachable, read-only rootfs confirmed via `docker inspect`.
3. **Local State Hygiene & Manifest Status:**
   `integrity-manifest.json` updated to hash 144 control-plane files (including `scripts/tools/_deploy_tx.py`). Doctor reports all 14 systems green. No live host deployment or git commit/push executed.
