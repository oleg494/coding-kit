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
- Report observed model/tool limitations when they affect verification; do not conceal failures or attribute unmeasured behavior to a provider.

## Verifying a change

Run checks matching the affected contract. `python -m pytest tests -q` is the
repository-wide check when shared policy/runtime changes warrant it; focused
checks suffice for isolated changes. `scripts/doctor.py` diagnoses installation
health, not model behavior or every feature's correctness.

For an installation/bootstrap task on a disposable runner, install prerequisites,
run `scripts/install.py`, then doctor. Do not bootstrap or mutate a real user
memory root merely to verify an unrelated edit. Report environmental failures
separately from failures caused by the change.

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
- Local implementation does not authorize a commit, push or pull request; follow AGENTS.md. If publication is authorized, use a branch/PR rather than pushing to `master`.
- Report exact commands, checked state and coverage. Reuse still-valid evidence; never claim broader coverage than was exercised.
