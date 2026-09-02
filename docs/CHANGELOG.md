# Changelog — Coding Agent OS

> Full release history. Moved out of OPS.md in v3.4.4 (64% of OPS was history
> re-read by the model every session; OPS keeps only the living contract).

> **Claim discipline (v2.7.4):** every "fixed"/"verified" claim below must cite the regression test (tests/test_*.py) or doctor check that re-verifies it. A claim without a check is not a claim — the v2.6 "githist 40-hex boundary" entry had neither code nor test (audit 2026-08-22). Sub-agent/cross-model verdicts are testimony: re-run fresh before reporting.
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
