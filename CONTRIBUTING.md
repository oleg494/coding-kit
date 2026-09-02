# Contributing

Short version: issues and PRs are welcome. Keep the kit thin.

## Ground rules

1. **Run the gates before proposing a change**
   ```bash
   python scripts/doctor.py                     # all checks
   python -m pytest tests -q                    # unit suite must be green
   python scripts/tools/check_file_sizes.py --ci # file-size gate (hard limits)
   ```
2. **Skills are Hermes-compatible**: `SKILL.md` + YAML frontmatter
   (`name`, `description` ≤1024 chars), body <500 lines, progressive disclosure.
3. **No new runtime**: no MCP servers, no hooks, no daemons. The kit is
   prompts + skills + stdlib scripts; enforcement belongs to the harness.
4. **Claims need evidence**: every "fixed/verified" statement cites the test or
   doctor check that re-verifies it (OPS.md §Claim discipline).
5. **Memory stays personal**: nothing under `~/.memory`, no machine-specific
   paths in tracked files (`~/` forms only in kit docs).
6. **English core**; user-facing triggers may stay bilingual where they are
   part of a skill's contract.
7. **Contract materiality**: high-materiality changes — workflows
   (`.github/workflows/*`), `scripts/install.py`, pyproject/dep
   definitions, test-framework files, `VERSION`/`profile.yml`/`OPS.md`/
   `AGENTS.md`/`adapters/*` — must update the contract they describe
   (`AGENTS.md`, `OPS.md`, this file, `README.md`,
   `docs/SECURITY-MAP.md`, `docs/CHANGELOG.md`) in the same change.
   Check: `python scripts/tools/contract_drift.py '["<paths>"]'`
   (`materiality()` / `needs_contract_update()`); fable-judge's
   "contract drift?" step enforces it at review time.

## Pull requests

- One logical change per PR; ~300 lines is a comfortable ceiling.
- Add or extend a test in `tests/` for behavior changes.
- New eval scenario? Follow `eval/scenarios/*.md` frontmatter convention
  (`name`, `skill`, `trap`, `expect`) and validate with
  `python eval/runner.py`.
