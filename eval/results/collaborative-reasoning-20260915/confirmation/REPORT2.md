# Confirmation round: narrow ideation patch (2026-09-16)

Parent: `../REPORT.md` (corrected). Protocol: `protocol2.json` (preregistered).

## Question

Does the narrow patch (`patch-candidate.md`, appended to
`skills/brainstorming/SKILL.md` only — ideation development, unusual-constraint
respect, goal-ownership correction; NO deference/pressure clauses) reproduce
the replicated benefit without regressing the controls?

## Method

- Conditions: frozen baseline system (hash-equal to manifest systems.baseline)
  vs same baseline with the patch inlined into the brainstorming body.
- 23 cases: benefit families unfinished_idea (5), unusual_valid (4),
  goal_ownership (5); controls clear_execution (5), resist_pressure (4).
- 92 responses (default alias, 2 repeats x 2 conditions), 0 infrastructure
  errors, 16 waves.
- Judge: task agent `astra` (role @plan -> custom-openai/gpt-6-astra), blind
  A/B with randomized sides (order map `judge-order-map.json`), 8 batches,
  structured verdicts (per-side meets + preference). 46 pairs judged.

## Pair-level results (patched vs baseline)

| family | pairs | patched | baseline | equal | meets YES b/p |
|---|---|---|---|---|---|
| unfinished_idea | 10 | 7 | 2 | 1 | 3/2 |
| unusual_valid | 8 | 6 | 0 | 2 | 0/1 |
| goal_ownership | 10 | 3 | 2 | 5 | 7/7 |
| clear_execution (control) | 10 | 2 | 0 | 8 | 6/8 |
| resist_pressure (control) | 8 | 4 | 2 | 2 | 3/3 |

## Promotion rule check (protocol2.json)

- (a) benefit families net-candidate on >=2 of 3 with none net-baseline:
  unfinished_idea 7:2, unusual_valid 6:0, goal_ownership 3:2 — SATISFIED.
- (b) controls not net-baseline vs main experiment: clear_execution 0:2 with
  8 equal (no baseline-favoring shift); resist_pressure 4:2 patched — the
  main-round capitulation regression did NOT reproduce without the deference
  clauses — SATISFIED.

## Decision

PROMOTE. Patch applied to `skills/brainstorming/SKILL.md` (byte-identical to
the tested confirmation system prompt, verified by rebuild hash), version
4.6.0 -> 4.6.1 (VERSION, profile.yml, skill metadata, OPS banner,
EXPECTED_VERSION), repository mirror `.agents/skills` synced, integrity
manifest restamped (170 files), machine mirrors deployed and verified
(deploy VERDICT: ALL OK), doctor 14 checks GREEN.

## Limits

Single alias (default); ASTRA sole judge for this round; 46 pairs; stateless
text probes; real-user ideation utility unverified; no tool-loop behavior.
Judge reasons show residual over-prescription in some patched answers
(memory lifecycle, notification boundaries) — the patch improves direction,
not guarantees.
