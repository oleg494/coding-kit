# Claude Code

@AGENTS.md

The soul above is the full contract. What follows only adapts it to a run on a
GitHub-hosted runner, where the machine-local parts of it cannot apply.

## Runner context

You run from `.github/workflows/claude.yml` on `ubuntu-latest`, triggered by an
`@claude` mention in an issue or pull request comment.

- `~/.memory`, `findings.py`, `build.py`, and the memory-warmup script do **not**
  exist on the runner. Skip every memory step the soul asks for: do not search
  the base, do not record findings. Say so in one line rather than failing the
  step.
- There is no `.override.md` here, so the default contract applies.
- The model behind this session is not an Anthropic model. Behaviour differences
  are yours to work around, not to report.

## Verifying a change

`scripts/doctor.py` is the gate, and it is the whole verification story:

```bash
python -m pip install pytest
python scripts/install.py    # bootstrap memory engine, self-test
python scripts/doctor.py     # 14 checks; must end "All systems GREEN"
python -m pytest tests -q
```

Doctor's `memory+db` and `backup freshness` checks read `~/.memory`, which does
not exist yet on a fresh runner — `scripts/install.py` creates it, so run that
first. If doctor still fails only on backup freshness, that check is WARN-tier
and does not block.

Before pushing anything, respect these repo rules:

- **File-size gate.** Code soft 500 / hard 1000 lines, docs soft 300 / hard 500.
  Split rather than grow; never edit `scripts/tools/file_size_baseline.json` to
  make a check pass.
- **Integrity manifest.** `integrity-manifest.json` hash-pins the control plane.
  If you change a file in its scope, regenerate it with
  `python scripts/tools/integrity_manifest.py --update` — but only for your own
  change, and never to paper over someone else's drift.
- **Encoding discipline.** Never a bare `text=True` on `subprocess.*`; always
  pass `encoding="utf-8"` alongside. The gate is AST-based and will fail you.

## Manners

- The repo's language is English for code, comments, and commit messages.
- Conventional commits, matching the existing log: `fix(policy): ...`,
  `docs: ...`, `test: ...`.
- Work on a branch and open a pull request. Never push to `master` directly.
- Report what you verified with the actual command output. A claim of "done"
  without a fresh run is forbidden here the same as anywhere else.
