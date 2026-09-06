# Open-source product direction — evidence, alternatives, decision (2026-09-05)

Status: research deliverable. Owner: product-evidence worker. Nothing here is
deployed or committed. Companion onboarding check:
`docs/research/2026-09-05-public-onboarding-check.md`.

Method: primary sources fetched and read today (obra/superpowers,
prime-radiant-inc/superpowers-evals, github/spec-kit, agentskills.io
specification, langchain deepagents memory docs, arXiv:2602.11988,
google-gemini/gemini-cli); kit-internal evidence re-run today (fresh-root
onboarding experiment, usage audit over 889 session transcripts, live gate
JSON re-read, static-size measurement). No paid live models were used for
this document. Critique incorporates feedback from an independent model
review (agent://product-independent-review); it remains automated and
author-internal judgment, not external-user evidence or field trials.
Source pages read were READMEs/docs unless noted; no comparative
implementation audit of competitors was performed, so their capabilities
are cited only as documented.

## 1. The honest evidence base

What the kit has actually measured about itself (re-verified today from
artifacts, not from memory):

1. **DeepSWE A/B (README claim)**: 6/9 pass both arms; kit +21% steps,
   +41% prompt tokens on identical outcomes (5 mutually-solved tasks,
   99.5M vs 70.4M). One task flipped to a kit win (24/24 vs 6/24), one to
   a kit loss (2/5 vs 5/5). n=9, one model, one benchmark; historical
   run, counts as reported in README (raw artifacts not re-derived here).
2. **Adaptive-rigor live gate (2026-09-03, `eval/results/gate-2026-09-03-live.json`)**:
   REJECT. Conditions 2-5 failed: route accuracy dropped on deepseek
   (0.900 vs 0.967), clean-pass fraction dropped on glm (0.857 vs 0.929),
   FAST effort *increased* on deepseek (steps 1.33, tools 1.50), and
   STANDARD/HIGH effort ratios ran 1.05-1.41 on steps and 1.09-1.35 on
   tool calls across models (deepseek STANDARD steps 1.25, tools 1.27;
   deepseek HIGH steps 1.41, tools 1.35; glm STANDARD steps 1.05, tools
   1.09; glm HIGH steps 1.09, tools 1.14). The three-tier policy made
   things worse on the models tried. Caveat: the archived token ratios in
   that snapshot (e.g. HIGH input_tokens 1.47) were computed by the
   original cache-unaware counter and an aggregation formula later
   replaced; the file is preserved as historical output, and its token
   columns cannot be re-aggregated under the fixed accounting —
   steps/tools/route/clean-pass rows remain verified, while token ratios do
   not support fresh exact aggregation.
3. **Code health**: 645-673 tests pass across recent runs; that is code
   health, not utility proof. The suite verifies contracts (memory cycle
   behavior, verifier integrity, manifest pinning) but no test measures
   end-to-end utility on real work (e.g. cross-session recall improving a
   real task outcome, false-done reduction in production); the kit's
   behavioral claims rest on the eval harness, not on the unit suite.
4. **Real-usage audit (today; instrument = `scripts/tools/usage_audit.py`
   over OMP + Claude session transcripts, all sessions since 2026-08-20,
   kit-internal sessions separated by project-marker match; definitions:
   memory call = transcript text matching broad regex
   `memory-warmup|search_all\.py|findings\.py|build\.py|repomap|skills_search|doctor\.py|check_file_sizes`;
   skill read = `skill://<name>` reference; OPS marker = OPS text marker)**.
   Anonymized aggregates over 207 real sessions with >=1 human turn:
   80/207 (39%) had >=1 regex hit for the broad memory pattern; 46/207
   (22%) had >=1 skill:// read; 60/207 (29%) had >=1 OPS marker. Of 33
   long sessions (>=10 turns), 25 had >=1 broad memory pattern hit.
   **Measurement caveats**: these counts are neither a strict lower nor
   upper bound. The memory pattern includes generic script names like
   `build.py`, `doctor.py`, and `check_file_sizes`, which occur in
   arbitrary non-kit projects and produce false-positive matches;
   conversely, `skill://` captures only OMP-style references and omits
   direct file-path reads or native harness loadings. These are rough
   pattern-frequency counts from one machine, one user, over 16 days, not
   proof of tool adoption, causal utility, or skill neglect.
5. **Static size (today)**: AGENTS+OPS+SKILL_RUNTIME = 13,809 bytes
   (~3.4k tokens at ~4 chars/token — a rough estimate of always-loaded
   text, not a measured resident-token count and not by itself a causal
   explanation of the DeepSWE +41%, which the README attributes to
   methodology iterations); 36 skill descriptions total ~10.6k chars
   (~2.7k tokens by the same estimate) resident in Agent-Skills-style
   harnesses. arXiv:2602.11988 measured >20% average inference-cost
   increase from context files — same direction, different setup.
6. **Onboarding (today, fresh temp MEMORY_ROOT)**: pre-fix, install →
   doctor (14/14) → add/search all green but warmup reported
   "Wiki/index.md missing, Wiki/log.md missing" on every fresh root;
   post-fix (R1 below) the same journey ends `Integrity: OK`. Exact
   commands, env (host HOME visible; only MEMORY_ROOT isolated), and
   exit codes: companion onboarding check.

## 2. Independent critique (my judgment)

**Case FOR the kit having a real product:**

- The only measured behavioral win is process discipline rescuing a flailing
  attempt (24/24 vs 6/24, single task). That is consistent with the
  superpowers thesis: methodology pays on hard multi-part tasks.
  obra/superpowers (MIT, ~282k stars, commits through 2026-08, maintained
  by Prime Radiant with a paid eval lab) demonstrates substantial
  *adoption* of this thesis; adoption is not proof of utility, and I did
  not audit their outcomes.
- The memory layer is the kit's most distinctive artifact: a stdlib SQLite
  FTS5 cross-chat store with provenance, supersession, secrets lint,
  restore drills. langchain deepagents ships a comparable *concept*
  (markdown memories + AGENTS.md) per their docs; I read their
  documentation, not their implementation, so comparative feature
  completeness is unverified. The 2026-09-02 remediation plan shows 12
  confirmed defects found and P1-P6 fixed under adversarial review —
  honest engineering, rare in my experience of prompt kits (anecdote).
- The eval harness has properties I value: deterministic verifiers, canary
  tasks, trap suite, isolation probes, cache-aware token accounting (as of
  today), and a predeclared acceptance gate that actually rejected its own
  candidate. I have not audited competitor eval suites, so no comparative
  superiority claim is made.

**Case AGAINST:**
- 36 skills with ~10.6k chars of descriptions are a standing resident cost
  in Agent-Skills-style harnesses. In the audited 207 real sessions, 61%
  had no broad memory regex match and 78% had no skill:// read (subject to
  the measurement caveats in §1.4). The retirement analysis found no
  completely unused skill, but frequency across sessions varies widely.
- The universal-compatibility claim is untested per-harness (see onboarding
  check). The kit works where the author runs it; everywhere else is
  inference.
- The kit's measured value proposition ("reliability on hard tasks at a
  token premium" — one benchmark, one model, n=9) sits in the same niche
  obra/superpowers occupies with per-harness plugin installers and a
  commercial eval operation. A second general methodology kit faces a
  well-resourced incumbent; that is a market observation, not a measured
  outcome comparison.

**Working hypothesis** (my synthesis, not a proven differentiation): the
kit's least-replicated assets are (a) the memory engine with integrity
tooling and (b) the eval harness with a gate that rejects its own
candidates. Whether mainstream alternatives actually lack equivalents is
unverified — I read superpowers/Quorum READMEs and deepagents docs, not
their codebases. The memory layer's user utility remains an unvalidated
hypothesis (the kit possesses no cross-session recall benchmark, and the
eval corpus consists solely of single-turn fresh-sandbox oracles).

## 3. Alternatives compared (>=4, primary sources)

| Option | Evidence | Fit | Verdict |
|---|---|---|---|
| **A. Status quo + polish**: keep selling the full 36-skill OS, fix onboarding, add more gates/doctor checks | README A/B: neutral pass rate, +41% tokens; usage audit: 61% of real sessions with zero broad memory regex matches | Keeps paying a measured cost for unproven breadth | Rejected as primary direction |
| **B. Evidence-gated default-off**: ship methodology JIT-only, always-loaded surface reduced to AGENTS.md router (~1k tokens est.), each skill/section must justify itself via existing ablation harness before inclusion in default profile | arXiv:2602.11988: context files didn't generally help and cost >20% (their setting); kit A/B same direction (n=9, one model); usage audit: 78% zero skill:// reads (subject to §1.4 caveat); adaptive-rigor gate shows the machinery to test reductions exists and works | Directly attacks the one measured defect (cost) without abandoning the win case (discipline on hard tasks) | **Recommended** |
| **C. Memory engine as the product**: position SQLite FTS5 store + db-tools as the headline; skills become optional example pack | Usage audit: 25/33 long sessions hit the memory regex (subject to false-positive caveat); deepagents docs indicate mainstream interest in agent memory; comparative feature audit not performed; task-outcome utility of memory remains unmeasured | Positions a distinctive component, but its user value remains an unvalidated hypothesis | **Recommended (merge with B as hypothesis to test)** |
| **D. Fork/absorb into obra/superpowers**: contribute memory engine upstream, retire the standalone kit | superpowers is MIT, multi-harness, actively maintained, commercial backing and eval lab | Loses independent identity; engine (Windows-first, stdlib, personal-DR focus) doesn't match their TS-centric infra; contribution path uncertain | Rejected; keep upstream attribution (already present) |
| **E. Eval-harness-as-product**: publish the trap/rigor harness as a general behavioral-eval framework | Quorum exists tied to superpowers; kit harness already has schema-v1 store, gates, ATIF export | The harness's value is proving *this* kit's claims; as a generic framework it competes with established tooling with more manpower | Rejected as product; kept as internal instrument |

Rejected explicitly: building a new eval platform (constraint), more
doctor checks as "product" (director note: self-maintenance is not user
outcome), broadening platform integrations (not a priority this cycle).

## 4. Product direction (hypothesis)

**Proposed hypothesis: coding-kit's public product = cross-session agent
memory engine + a default-thin, opt-in-rigor methodology layer.**

1. **Memory first (unvalidated hypothesis).** The proposed headline:
   knowledge survives across sessions and tools, with secrets lint,
   provenance, and backups that restore. While the tooling is tested
   locally, its value in improving real task outcomes remains an
   unvalidated hypothesis — the existing eval corpus contains zero
   cross-session evaluation tasks, and builder transcript patterns do
   not constitute external market demand.
2. **Methodology default-thin (hypothesis to test).** Always-loaded
   surface: AGENTS.md router + OPS identity block only. Skills stay
   available but are not inlined anywhere by default; any always-on bundle
   must pass the existing rigor gate with cache-aware accounting (a
   future candidate must beat baseline numbers on the same corpus/models
   to be comparable — the rejected adaptive-rigor run set that bar).
3. **Claims ledger.** Every public claim maps to a runnable command or is
   deleted. (Started today in README/onboarding fixes.)

## 5. Falsifiable experiment (predeclared)

**Question**: does the default-thin profile (B) preserve user-observable
outcomes while reducing cost, versus the current full profile and against
two distinct baselines? (Note: this evaluates *methodology overhead*, not
memory utility; memory evaluation requires a separate multi-session
recall benchmark.)

- **Arms** (same executor, same models, >=2 models incl. one non-preview),
  kept separate in analysis and never conflated:
  (1) **bare executor** — same harness mandatory base prompt and tools with
  optional methodology plugins and skills disabled;
  (2) **upstream baseline** — named pinned methodology distribution enabled
  (e.g. stock obra/superpowers plugin). Explicit constraint: if the harness
  lacks a separable optional upstream methodology, arms 1 and 2 coincide
  and must not be sold as distinct;
  (3) **current full kit**;
  (4) **thin profile**.
  Arms 1 and 2 answer different questions: 1 is "does any methodology help",
  2 is "does the kit add over what the user already has". Each arm's ambient
  state must be recorded per run.
- **Harness limitations acknowledged**: `eval/rigor/runner.py` currently
  restricts `--arm` to `['baseline', 'candidate']` and injects policies
  from git refs via `--add-dir` (mounting `AGENTS.md`, `OPS.md`,
  `SKILL_RUNTIME.md`). It has no CLI or plumbing to run unbundled bare
  executions (disabling kit policy injection only; the mandatory harness
  system prompt is never removed) or stock upstream harness defaults.
  Running all four arms requires extending `runner.py` and `gate.py`;
  sequencing pairwise runs alone does not implement these missing modes.
- **Isolation limits, stated**: neutral temp cwd prevents repo-local
  instruction discovery only; ambient global skills and HOME env are
  uncontrolled. A canary-clean run is evidence against gross instruction
  leakage, NOT proof of no contamination: ambient skills can overlap kit
  skills without tripping canaries, which biases the bare arm toward the
  full-kit arm. If ambient overlap is detected, the bare/no-kit comparison
  is reported as inconclusive for that harness rather than adjusted.
  Not an OS sandbox; per-run HOME pinning (Quorum's pattern) is the
  stronger isolation if the experiment needs it.
- **Oracles**: real-task verify.py oracles (deterministic, no LLM judge
  for pass/fail) + named legacy traps with a *distinct* judge model;
  canary tasks must stay impossible.
- **Cost**: `input_token_accounting=total_input_v1` on every arm
  (cache-aware, fixed today); wall-clock duration_s; never equate tokens
  with dollars — report provider-reported cost only when present.
- **Sample size honesty**: 6 tasks/24 traps detect trends only. No fixed
  task count guarantees statistical significance — report per-task
  outcomes and effect direction with explicit n; widen the corpus if
  decisions would rest on small deltas.
- **Kill criteria (predeclared)**: if the thin profile (a) loses any
  legacy-trap clean-pass vs full kit on both models, or (b) shows no
  complete effort ratio <= 0.9 vs full kit, then "default-thin" is refuted
  and the kit keeps the full profile with the cost premium documented.
  Conversely if the upstream baseline (arm 2) matches the full kit on all
  oracles at lower cost across both models, the always-loaded methodology
  layer is the thing to demote — with the caveat that ambient overlap
  (above) can mask kit contribution, so that conclusion requires a
  recorded-clean ambient state.

## 6. Prioritized releases (each with observable acceptance)
**R1 (selected, implemented today).** Seed `Wiki/index.md` and
`Wiki/log.md` (only the two files warmup's integrity contract actually
consumes; no README seed — no evidenced consumer) in `install.py`,
absent-only, so a fresh install produces a warmup-clean memory root.
Evidence: today's fresh-root run — install green, then warmup immediately
reported "Integrity: 2 issue(s): Wiki/index.md missing, Wiki/log.md
missing". Acceptance (all met): fresh-root install → real warmup CLI in a
separate process prints `Integrity: OK` rc=0; 2 new missing-file/warmup
tests in `tests/test_install.py` failed pre-fix (verified red via `git stash`
of install.py) while the preservation test passes post-fix; full suite
673 passed / 1 skipped / 85 subtests; doctor 14/14 GREEN; manifest
refreshed.

**R2. README/onboarding truth pass** (done today, see companion check):
memory bootstrap vs agent integration split, runnable first save/search
demo, 36 not 42 skills, Gemini retirement claim removed (repo actively
ships weekly releases — verified today), root-MIT vs skill-Proprietary
license-label conflict disclosed as unresolved (no rights adjudication,
no author-identity conclusion, no deletion workaround; deletion would
break profile/manifest/contract wiring), DeepSWE section labeled
historical with artifacts outside the repo and no bundled reproduction
command, Python requirements stated from CI evidence (3.12 tested; no
floor claimed), contributor pytest prerequisite.

**R3. Description diet.** Reduce the ~2.7k-token always-resident description
surface. Per the agentskills.io specification, each description must concisely
state *what the skill does* and *when to use it* (trigger conditions).
Descriptions should cut conversational filler and background exposition while
preserving both clauses. Acceptance: total description characters <= 6,000
(~1.5k tokens estimated); trigger query pass rate does not regress against
the baseline (evaluating against the 80-query central fallback suite or the
86-query co-located suite across 12 skills accessible via `--queries auto`).

**R4. Thin-profile + baseline methodology evaluation.** Extend
`eval/rigor/runner.py` and `eval/rigor/gate.py` to support unbundled/bare
and upstream harness runs alongside candidate bundles. Execute the 4-arm
comparison evaluating methodology overhead (bare vs upstream vs full kit vs
thin profile). Acceptance: gate JSON produced with `total_input_v1` markers,
per-run ambient-state records, and verified pairwise ratio tables; README
"Measured cost" section updated with the result whatever it shows.

**R5 (dropped).** An `install.py --memory-only` flag was considered and
rejected: today's installer already gives a working memory root with zero
agent integration (Phase 1). Memory-only adoption is documentation
(README Phase 1), not a code path.

## 7. Uncertainty register

- Usage audit is broad pattern counts from one machine, one user, 16 days.
  Subject to both false-positive script matches and omitted native loadings.
- The 24/24-vs-6/24 rescue is one task; could be noise.
- DeepSWE subset is 9-10 tasks on one model via one gateway.
- I did not run obra/superpowers' Quorum against coding-kit (would need
  live CLIs + keys); comparative workflow-compliance numbers are absent by
  design, and prior failed scouts are not represented as reviews.
- Gemini CLI "active" is verified as of today (weekly release cadence,
  106k stars, Apache-2.0); future retirement is possible but claiming it
  already happened is factually wrong today.
- The memory engine's value proposition for real task completion is
  untested: no task in the eval suite evaluates cross-session memory
  recall or database retrieval during problem solving.
