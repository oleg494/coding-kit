# Changelog — Coding Agent OS

- **v4.10.3 (2026-10-20) — product proof plumbing (local release):**
  - Claims ledger docs/CLAIMS.md (25 rows): every public claim carries a
    runnable verification command plus evidence, an evidence-only record,
    or an explicit unverified marker; the historical DeepSWE A/B stays
    `unverified (historical)`. Release acceptance gates and rollback
    criteria (reviewed-only integrity regeneration, git revert without
    history rewrite, memory root untouched) live in the same file.
    README links the ledger; tests/test_release_contract.py pins its
    structure (ClaimsLedgerTest, 7 tests / 50 subtests).
  - Cross-session memory evaluation (eval/memory_experiment.py): grading
    now supports `grade --verify-retrieval PREPARED` — the memory arm's
    retrieval claims are cross-checked against the real isolated memory
    store output instead of self-report alone. `retrieval_verified` is
    True only when the claimed decision id appears in actual tool
    output; absent/unusable stores yield null, never fabricated
    failures. This verifies retrieval plumbing deterministically; it
    makes no model-behavior claim. 11 tests in
    tests/test_memory_experiment.py.
  - Arm-profile experiment plumbing (eval/prompt_assembly.py):
    `assemble_arm_profile(profile, skills_root)` builds the predeclared
    methodology arms — bare (no kit policy bytes), thin (AGENTS.md +
    OPS.md only), full (current bundle: three policy files + owned
    skills manifest) — returning the file inventory and policy byte
    count for each. Reuses existing manifest helpers; no new runtime,
    no subprocess, no model call. On the current kit: bare 0 B,
    thin 9,914 B, full 25,355 B / 40 files. 9 inventory-based tests in
    tests/test_arm_profiles.py.
  - Usage-audit attribution hardening (v4.2.1): command-entry
    attribution now splits command lines only at unquoted separators
    (quote-aware scanner), recurses into `bash -c "<script>"` inner
    scripts, and resolves `uv run <script>` / `uv run python <script>`
    to the actually executed script. memory_calls counts only
    recognized shell-tool executions, never reads/echo/prose;
    skills_search moved to its own counter; kit diagnostics report
    separately. Regressions cover quoted inner scripts, cd-marker
    preservation through recursion, and uv-run resolution.
  - Task-runner canary exit gate: a live run whose canary is classified
    hacked exits nonzero even when every ordinary task passes; honest
    canary failures still exit clean. Pinned at suite and process
    level (tests/test_canaries.py).
  - Canonical deploy parity: `deploy.py --canonical` now runs the same
    integrity gate as full deploy (exit 3 on drift), refuses a
    differing unowned same-name skill (manifest-claimed or
    byte-identical adoption remains allowed), fails closed on a
    malformed destination ownership manifest, preflights source links,
    and verifies the canonical result inside the transaction before
    commit. Coverage moved to tests/test_canonical_deploy.py; deploy.py
    and its test files back under the 1000-line hard gate.
  - Integrity manifest v2 scope: every regular file under a
    profile-owned skill directory is pinned (SKILL.md, references/,
    evals/, assets/ — binary payload byte-exact, declared text formats
    newline-normalized); foreign skill directories and `.agents`
    mirrors stay out. No cross-call slug cache: inventory is resolved
    once per traversal from disk (same-size profile rewrites with
    restored mtime are detected).
  - Installer boundary preflight: link/reparse-aware check over all
    managed destinations (layout ancestors, Wiki seeds, VERSION,
    scripts, every db/*.db entry) runs before any mutation and fails
    closed on escapes, dangling links, loops, and unresolvable
    reparse points. `db-tools` remains the one intentional external
    engine link. TOCTOU between check and write is documented as
    accepted; bootstrap is not a sandbox (SECURITY.md updated).
  - search_all.py error contract: malformed FTS queries (including the
    brace column-filter shape `{component}`) exit 2 with an actionable
    diagnostic instead of "not found in any database"; corrupt or
    unopenable known stores exit 3 with partial results clearly marked
    PARTIAL; a run with no usable stores at all is an error, never an
    empty-search claim. Valid empty searches keep exit 1. JSON
    findings hits now carry `source` and the exact `verified_at` stamp
    (or null) alongside the compatible `verified` flag.
  - Trap-suite release-grade gate: `--release-grade` requires a live
    run, a digest-distinct judge command, and nonempty distinct
    declared executor/judge model ids (`--judge-model`); command/argv
    differences alone are never treated as model independence.
    Exploratory self-judged runs remain possible and are persisted
    with explicit provenance (judge_status, declared ids,
    independence_basis). judge_provenance is threaded through the CLI
    and result JSON.
  - Trend baseline guards: update_baselines seeds only complete
    measured populations — trap rows with executor/judge-phase
    attempts, trigger rows with infra errors, and tasks rows whose
    attempts show no real verifier signal (infra error_class, no
    oracle `FAIL:` trace, no PASS) are all unmeasured and seed
    nothing; a measured FAIL still seeds its 0.5. Legacy numeric
    trap/trigger baselines render an explicit "ignored legacy
    baselines" note instead of silently dropping. tests/test_trend.py
    stays under the size gate; baseline tests live in
    tests/test_trend_baselines.py.
  - Heldout corpus and release protocol documented
    (docs/audit-methodology.md): what open dry-runs prove (input
    validity) versus live heldout runs (generalization check);
    development/heldout separation rules; independent-judge
    requirements; canary exit contract. Published heldout artifacts
    (eval/results/collaborative-reasoning-20260915/) are sealed-then-
    published evidence, spent for future gating, not fabricated.
  - UI readiness guidance: design-system and dashboard-design replace
    the Playwright-discouraged `networkidle` heuristic with observable
    readiness — bounded condition waits on route/data markers, target
    content visibility or loading-state disappearance, plus console/
    network error checks. Deployed mirrors updated.
  - Verification (Windows/Python 3.12, isolated HOME, fresh memory
    bootstrap): full suite `python -m pytest tests -q -p
    no:cacheprovider` — 945 passed, 22 skipped (Docker runtime and
    task-image prerequisites unavailable locally; Windows symlink
    privilege skips), 548 subtests passed. doctor 14/14 GREEN
    (integrity 213 files; 37 skills in sync across all harnesses);
    file-size gate hard 0. Dry-run validations: 48 scenarios, 6 tasks,
    144 trigger queries — input validity only. Full deploy VERDICT
    ALL OK; repeat deploy byte-unchanged; canonical dry-run reports
    no changes. Direct probe: `search_all.py "{component}"` exits 2
    with the malformed-query diagnostic. No behavioral model
    comparison or quality/token-efficiency claim is made; CI legs for
    the tag commit remain to be observed on push (not performed in
    this local release).

- **v4.10.2 (addendum) — claims ledger release contract:**