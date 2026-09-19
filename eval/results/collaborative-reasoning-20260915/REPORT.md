# Collaborative Reasoning Addendum — Comparative Experiment Report (corrected)

Experiment dir: `eval/results/collaborative-reasoning-20260915/`.
Dates: 2026-09-15 → 2026-09-16. Frozen protocol: `protocol.json`.
This revision supersedes the first report's numbers; the method and the
verdict direction are unchanged. Corrections are listed first.

## Corrections applied in this revision

1. **Duplicate judgments removed.** Retried judge calls that later succeeded
   had left two valid rows for the same `case|model|repeat|order` key; the
   first report summed both. `analysis-corrected.json` keeps the first valid
   row per key (11 duplicates removed; 351 unique valid rows).
2. **Order sensitivity recomputed on decoded preference.** The first report
   compared raw A/B letters across the two side orders, which flips whenever
   the judge consistently likes the same *response* (the letter moves with the
   side). Corrected comparison is on the decoded preference
   (baseline/candidate/equal): 131 of 175 twice-judged pairs are order-stable
   (75%), per-response acceptance is stable in 158/175 (baseline) and 165/175
   (candidate) pairs. The earlier "123 of 176 flipped" figure was an artifact
   and is withdrawn.
3. **Pair-level verdicts replace per-call sums.** Each `case × model × repeat`
   pair gets one verdict = majority of its order judgments; ties are recorded
   as `split` and excluded from win/loss counts. All tables below are
   pair-level.
4. **Ambiguous acceptance noted.** `hold-exec-daily-sql` did not state whether
   "distinct sensors per day" counts all rows or only `ok` rows; both readings
   are defensible, so its NO verdicts against the candidate are treated as
   acceptance ambiguity, not as a behavioral regression.

## Question

Does a short "collaborative reasoning" addendum to the current coding-kit
rules (OPS.md + reasoning-engine, brainstorming, receiving-code-review,
debug-incident-protocol, engineering-persona, yagni) measurably change model
behavior in user-collaboration dialogues?

## Method (as preregistered, deviations recorded)

- 44 unique Russian dialogue cases, 10 families: 24 development (12 main +
  12 independent subagent), 20 heldout (sealed independent subagent).
- Each case × 2 aliases (`default`, `smol`) × 2 repeats × 2 conditions
  (baseline ≈32K-char frozen system; candidate = baseline + addendum) =
  352 responses via stateless `completion()`.
- Blind paired judge (alias `slow`), strict line format, each pair judged
  twice with counterbalanced sides.
- Deviations: schema judge rejected by provider (thinking mode) → line format;
  3 pairs scored from truncated windows or a single valid order after
  repeated judge timeouts (marked in judgment files); 351/352 responses after
  infra retries.

## Corrected results (pair-level)

| Split | pairs | baseline wins | candidate wins | equal | split (tie) |
|---|---|---|---|---|---|
| development | 96 | 27 | 31 | 14 | 24 |
| heldout | 80 | 33 | 23 | 4 | 20 |

Family-level pair verdicts (B/C/E/S per split):

| family | dev | heldout | reading |
|---|---|---|---|
| unfinished_idea | 2/9/0/1 | 1/7/0/0 | **consistent candidate win** |
| unusual_valid | 0/5/0/3 | 2/4/0/2 | **consistent candidate win** |
| goal_ownership | 4/3/0/5 | 2/5/0/1 | mixed, heldout favors candidate |
| informed_tradeoff | 1/2/5/4 | 3/1/0/4 | noise |
| symptom_trust | 1/3/0/4 | 3/0/0/5 | mixed, heldout favors baseline |
| grounded_correction | 4/3/0/1 | 3/2/2/1 | noise |
| clear_execution | 0/0/9/3 | 4/2/2/0 | dev equal, heldout favors baseline |
| update_from_evidence | 5/2/0/1 | 4/1/0/3 | **consistent baseline win** |
| symptom_cause | 4/2/0/2 | 6/0/0/2 | **consistent baseline win** |
| resist_pressure | 6/2/0/0 | 5/1/0/2 | **consistent baseline win** |

Manual audit of the consistent deltas (answer texts read, not only verdicts):

- `resist_pressure`: candidate answers capitulate to repeated insistence
  without new evidence ("решение твоё, исполняю"), violating the case's own
  acceptance; the addendum's "respect an informed choice" clause is read by
  the model as satisfied by repetition. Real regression.
- `symptom_cause`: candidate over-hedges well-attributed evidence (challenges
  trace semantics that the supplied data already settles); partly acceptance
  strictness, partly genuine loss of decisiveness.
- `update_from_evidence`: quality near-equal; judges prefer baseline's tighter
  evidence-to-action linkage. Small but consistent.
- `unfinished_idea` / `unusual_valid`: candidate supplies 2-4 concrete
  interpretations with examples kept as proposals, and honors explicit
  unusual constraints instead of pushing standard advice. Real, replicated
  benefit — the ability the original user question asked about.
- `clear_execution`: candidate adds explanatory notes (e.g. Unicode caveat)
  that read as scope expansion on strict-format requests; dev equal, heldout
  against.

Response length: 2965 (baseline) vs 2867 (candidate) chars average — no
systematic padding.

## Verdict against preregistered promotion criteria

**Full addendum NOT promoted.** Heldout pair-level preference favors baseline
33:23, and three families show consistent material regressions
(resist_pressure, symptom_cause, update_from_evidence).

**Targeted subset confirmed as the only replicated benefit:** ideation support
(unfinished_idea, unusual_valid; goal_ownership weaker/mixed). Per protocol,
the subset requires its own confirmation experiment before any rule change.
That confirmation is now running with a narrowed patch (ideation behavior
only, no deference/pressure clauses) and an independent ASTRA judge; see
`confirmation/` subdir and finding #443.

## Scope limits

Stateless text probes; aliases do not prove distinct backends; single judge
model per round (slow for main, ASTRA for confirmation); real-user ideation
utility unverified; no tool-loop behavior measured.

Artifacts: protocol.json, manifest.json, baseline-system.txt,
candidate-system.txt, collaborative-development.json, factual-development.json,
sealed-heldout.json, responses-*.json, responses-all.json,
judgments-development.json, judgments-heldout.json, analysis.json (superseded),
analysis-corrected.json (authoritative), REPORT.md (this file).
