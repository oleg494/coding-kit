# Public onboarding check — evidence (2026-09-05)

Experiment environment (exact): temp root created via `mktemp -d`; env for
every kit command: `MEMORY_ROOT=<TMP>` (Windows absolute path). `HOME`/
`USERPROFILE`/`HOMEDRIVE`+`HOMEPATH` were **not** redirected — the host home
remained visible; the experiment isolates the memory *store* only, not the
host. Personal memory was never touched because every engine CLI honors
`MEMORY_ROOT` (findings_db resolver; verified below by add/search hitting
the temp db). Kit checkout: `coding-kit` at 5377c16 + uncommitted local
changes (this pass). No commits, no global deploy, no model calls.

## Experiment A — PRE-FIX (original install.py)

Reconstructed from the documented run, not a fresh re-execution. The shell
exported `MEMORY_ROOT` once for every command below (shown explicitly so
the block is reproducible without touching personal memory):

```
$ export MEMORY_ROOT=<TMP>            # Windows absolute temp path; set once
$ python scripts/install.py
  ... linked <TMP>/db-tools -> <kit>/memory/db-tools
  search smoke: OK                                  rc=0

$ python scripts/doctor.py
  == All systems GREEN (14 checks) ==               rc=0

$ python "$MEMORY_ROOT/db-tools/findings.py" add "onboarding-demo" --text "..."
  [✓] added: onboarding-demo (id=1)                 rc=0
$ python "$MEMORY_ROOT/db-tools/findings.py" search "onboarding-demo"
  found: 1, showing: 1                              rc=0
$ python "$MEMORY_ROOT/db-tools/search_all.py" "onboarding-demo"
  [research] finding#1 onboarding-demo ...          rc=0

$ python scripts/install.py   (re-run)
  db-tools already linked to this kit ... search smoke: OK    rc=0

$ python "$MEMORY_ROOT/db-tools/findings.py" add ... --text "password hunter2x ..."
  [!] possible secret ... REFUSED                   rc=2

$ python "$MEMORY_ROOT/scripts/memory-warmup.py"
  Wiki: 0 entries ... findings: 1 ... pull hint printed
  Integrity: 2 issue(s)
    ! Wiki/index.md missing
    ! Wiki/log.md missing                           rc=0 (nag, not failure)
```

Defect: install green, but the dev-wiki cycle files the warmup integrity
contract requires are absent on every fresh root.

## Experiment B — POST-FIX (R1: install.py seeds index/log, absent-only)

```
$ export MEMORY_ROOT=<TMP2>                         # explicit for the whole shell
$ python scripts/install.py
  seeded Wiki/index.md
  seeded Wiki/log.md
  search smoke: OK                                  rc=0

$ python "$MEMORY_ROOT/db-tools/findings.py" add "r1-verification" --text "..." --source docs/research/2026-09-05-public-onboarding-check.md
  [✓] added: r1-verification (id=1)                 rc=0

$ python "$MEMORY_ROOT/db-tools/findings.py" search "r1-verification"
  found: 1, showing: 1
  [1] ... [r1-verification]                         rc=0   (separate process)

$ python "$MEMORY_ROOT/scripts/memory-warmup.py"
  Wiki: 2 entries (2 this week)
    findings: 1
  Recent: Wiki\index.md, Wiki\log.md
  Unsure: pull: search_all.py "<your topic>"
  Integrity: OK                                     rc=0

# preservation: user content survives a re-run
$ echo "custom" >> "$MEMORY_ROOT/Wiki/index.md" && python scripts/install.py
  db-tools already linked ... search smoke: OK      rc=0
$ grep -c custom "$MEMORY_ROOT/Wiki/index.md"       -> 1   (not overwritten)
```

Regression tests (tests/test_install.py), exact results:
- PRE-FIX (install.py stashed, tests applied): the 2 new missing-file /
  warmup tests `test_fresh_install_seeds_wiki_cycle_files` and
  `test_seeded_root_is_warmup_clean` **FAILED** — output contained
  `Integrity: 2 issue(s) / ! Wiki/index.md missing / ! Wiki/log.md missing`.
- POST-FIX: `python -m pytest tests/test_install.py -q` →
  **20 passed, 0 failed, exit 0** (17 pre-existing at HEAD + 3 new;
  `test_rerun_preserves_existing_wiki_cycle_files` is one of the 3 new
  tests and asserts preservation of user-modified index/log across re-run).
- Full suite post-fix + manifest refresh:
  `python -m pytest tests -q` → **673 passed, 1 skipped, 85 subtests, exit 0**;
  `python scripts/doctor.py` → **14/14 GREEN, exit 0**.

## Onboarding findings (both experiments)

1. **Bootstrap vs integration are different phases; doctor covers only
   self-consistency.** `install.py` creates a working *memory root*. It
   performs zero agent integration (no `~/.claude`, `~/.agents`, `~/.zcode`
   writes). Doctor green = repo control-plane consistent + memory root
   healthy — NOT proof any harness loaded the kit. `check_skills_sync`
   compares only copies that exist; a machine with no integrations is green
   by design (correct for CI). File presence/consistency ≠ model
   activation; the kit has no activation check that avoids launching a
   harness, and none is claimed.
2. Warmup nag on fresh installs (fixed today as R1 — see direction doc).
3. `42 skills` in `adapters/UNIVERSAL.md` was stale; actual 36 (skill dirs,
   SKILL.md files, `profile.yml`, doctor, release-contract
  `EXPECTED_SKILL_COUNT=36` all agree). Corrected; no new test added (the
   existing pin already guards it).
4. **Gemini retirement claim removed.** Verified today:
   `google-gemini/gemini-cli` is active — weekly stable/preview/nightly
   releases, 106k stars, Apache-2.0, live official docs. Removed the
   "retired 2026-06-18" assertions from README, adapters/UNIVERSAL.md,
   profile.yml comment. The historical-archive reader
   (`transcript_normalize.py --source gemini`) is kept (real, tested).
5. **Licensing disclosure.** Root LICENSE = MIT; 35 of 36 skills declare
   `license: MIT` in frontmatter; `skills/windows-encoding-fixes` declares
   `license: Proprietary`. The root MIT grant conflicts with that
   frontmatter label and the conflict is unresolved. No rights
   adjudication is made in either direction and no author-identity or
   provenance conclusion is drawn here — a frontmatter label is not proof
   of a grant or of an exclusion. README discloses the open mismatch only;
   no relicensing performed and no deletion workaround offered (the skill
   is wired into profile.yml, the release-contract pin, the integrity
   manifest, and the trigger corpora).
6. **Python requirement stated from evidence.** CI (both workflows) tests
   **3.12 only** on windows-latest and ubuntu-latest. No version floor is
   claimed in the public docs: an earlier draft's "3.9+ (removesuffix)"
   guess was not evidence-based. Actual code uses `str.removesuffix`
   (3.9+), `Path.write_text(newline=...)` (3.10+), and PEP 604 `X | None`
   annotations (3.10+), so 3.8 is not supported regardless of the
   `_is_link` docstring's "the kit supports 3.8+" line — that docstring is
   a package-floor claim, not an API-version note, and it is stale. It was
   left untouched (runtime code comment; docs-only pass).
7. **Counts re-derived from the runners**: 24 scenarios (`eval/runner.py`
   dry-run + release contract pins 24), 6 tasks incl. 2 impossible canaries
   (`task_runner --dry-run` output), trigger-eval: 86 co-located queries
   across 12 skills via `--queries auto` with the 80-query central
   `trigger_queries.json` (10 skills) as fallback (`trigger_eval.py`
   validation output for both modes). README corrected from 23/21/4
   mismatches to these.

## Files changed in this pass

- `README.md` — two-phase install (memory bootstrap vs agent integration),
  runnable save/search demo on the default `~/.memory` root, requirements
  section (3.12 tested, no floor claim), corrected counts (36 skills / 24
  scenarios / 6 tasks; 86 co-located/12-skill auto corpus vs 80-query/
  10-skill central fallback), Gemini claim removed, license conflict
  disclosed unresolved (no deletion workaround, no rights adjudication),
  doctor-green ≠ activation wording, rigor A/B bullet.
- `CONTRIBUTING.md` — pytest prerequisite explicit (rule 1).
- `adapters/UNIVERSAL.md` — 36 not 42; retirement comment replaced with
  archive-reader note; verify section distinguishes file-consistency from
  activation.
- `profile.yml` — stale Gemini-retirement comment removed.
- `scripts/install.py` — R1 fix: `_WIKI_SEEDS` (index.md, log.md only;
  no README seed — no evidenced consumer in the kit's cycle), written
  absent-only.
- `tests/test_install.py` — 3 regression tests (seed presence, observable
  warmup `Integrity: OK` via real CLI in a separate process with isolated
  `MEMORY_ROOT`, preservation of user-modified index/log across re-run).
- `integrity-manifest.json` — refreshed (`--update`) after control-file
  edits; doctor integrity GREEN.

## Limits of this evidence

- Memory-store isolation via `MEMORY_ROOT` only; host home/env visible
  throughout (stated above). Not a sandbox.
- Warmup `Integrity: OK` and add/search round-trips prove the memory
  cycle's file/db contracts on a fresh root. They do not prove any agent
  harness activates the kit (no harness was launched).
- Test counts cite this machine's run today (Python 3.11.16 local, CI 3.12).

## Final verification snapshot (2026-09-05, end of pass)

- `python -m pytest tests -q` → **673 passed, 1 skipped, 85 subtests, exit 0**
  (includes the 3 new R1 regressions; pre-fix red proven via `git stash` of
  `scripts/install.py`: `test_fresh_install_seeds_wiki_cycle_files` and
  `test_seeded_root_is_warmup_clean` both FAILED with
  `! Wiki/index.md missing` / `! Wiki/log.md missing`).
- `python scripts/doctor.py` → **14/14 GREEN, exit 0** after
  `integrity_manifest.py --update` (141 files hashed; covers the edited
  control files `adapters/UNIVERSAL.md`, `profile.yml`, `scripts/install.py`).
- Preservation re-verified end-to-end: fresh root → install → append custom
  line to `Wiki/index.md` → re-install → custom line present (grep rc=0),
  warmup `Integrity: OK`.
- Post-correction focused re-run (after this doc's trigger-count/license
  corrections and the CHANGELOG entry): `test_release_contract +
  test_contract_drift + test_ops_diet + test_install` → **73 passed,
  23 subtests, exit 0**; doctor **14/14 GREEN, exit 0**; file-size gate
  green, exit 0. Raw logs (outside the repo, on the session Desktop):
  `<Desktop>/coding-kit-evidence-2026-09-05/contract-tests.log` and
  `<Desktop>/coding-kit-evidence-2026-09-05/doctor.log` (contain both the
  pre- and post-correction runs).
- CHANGELOG entry added under "Post-v4.1.0 onboarding corrections + R1
  (2026-09-05)" citing the three regression tests; latest-entry prefix
  satisfies `test_latest_changelog_entry_matches_current_version`.
- Session lesson recorded to memory: findings.py id=313 with this doc set
  as source.

## Remaining caveats (truthful)

- No model/harness was launched anywhere in this pass: nothing here proves
  agent activation of the kit in any environment. Doctor skills-sync is
  file-consistency only (by design; CI depends on that).
- Local Python was 3.11.16 (CI runs 3.12); the 3 new tests run the real
  warmup CLI as a subprocess and inherit that interpreter.
- The `install.py` `_is_link` docstring's "the kit supports 3.8+" is a
  stale package-floor claim contradicted by actual 3.10+ API usage
  (finding 6); left untouched — runtime code comment, docs-only pass.
- Two previously-deployed worker scouts died at OMP startup
  (getWorkPoolYieldItems) with zero tool calls; they are not represented
  as reviews anywhere in these documents.
- Unrelated pre-existing local modifications (eval/rigor, backup_memory,
  integrity tools, their tests, CHANGELOG) were present before this pass
  and are not mine; I did not touch or revert them.
