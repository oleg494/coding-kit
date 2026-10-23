# Contributing

Short version: issues and PRs are welcome. Keep the kit thin.

## Ground rules

1. **Install the test dependency first**: `python -m pip install pytest`
   (the only one; no requirements file by design — stdlib kit).
2. **Run the gates before proposing a change**
   ```bash
   python scripts/doctor.py                     # all checks
   python -m pytest tests -q                    # unit suite must be green
   python scripts/tools/check_file_sizes.py --ci # file-size gate (hard limits)
   ```
3. **Skills are Hermes-compatible**: `SKILL.md` + YAML frontmatter
   (`name`, `description` ≤1024 chars), body <500 lines, progressive disclosure.
4. **No new runtime**: no MCP servers, no hooks, no daemons. The kit is
   prompts + skills + stdlib scripts; enforcement belongs to the harness.
5. **Claims need evidence**: cite applicable observed checks for the current
   state and scope (OPS.md §3); reuse evidence until it is invalidated.
6. **Memory stays personal**: nothing under `~/.memory`, no machine-specific
   paths in tracked files (`~/` forms only in kit docs).
7. **English core**; user-facing triggers may stay bilingual where they are
   part of a skill's contract.
8. **Contract review**: for high-materiality changes (workflows, installation,
   dependencies, test infrastructure or agent instructions), inspect the
   affected behavior contract. Update relevant documentation when behavior
   changes; otherwise explain why it remains accurate. Do not touch an
   unrelated document merely to satisfy a filename gate.
   `python scripts/tools/contract_drift.py '["<paths>"]'` identifies review
   candidates via `materiality()` / `needs_contract_review()`. It is advisory:
   a README in the diff proves neither coverage nor correctness, and valid
   CLI invocations do not block on file names.

## Pull requests

- Keep one coherent outcome reviewable; split independently verifiable work,
  not arbitrary line counts.
- Preserve tests for plausible consumer-visible failures. Add a permanent
  regression for an uncertain boundary or recurring defect; isolated smoke
  evidence is sufficient for wiring and ordinary documentation changes.
- New eval scenario? Follow `eval/scenarios/*.md` frontmatter convention
  (`name`, `skill`, `trap`, `expect`) and validate with
  `python eval/runner.py`.
