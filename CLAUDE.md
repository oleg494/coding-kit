# Claude Code

@AGENTS.md

AGENTS.md points to OPS.md, the full contract. This file only adapts it to a
run on a GitHub-hosted runner, where the machine-local parts cannot apply.

## Runner context

You run from `.github/workflows/claude.yml` on `ubuntu-latest`, triggered by an
`@claude` mention in an issue or pull request comment.

- The memory store (`~/.memory`, its search and findings tools, the warmup
  script) does not exist on the runner. Skip memory search and saving (OPS §5)
  and say so in one line instead of failing the step.
- There is no `.override.md` here, so the default contract applies.
- Report model or tool limitations that affect verification; do not attribute
  unmeasured behavior to a provider.

## Verifying a change

Run checks matching the affected contract. `python -m pytest tests -q` is the
repository-wide check when shared policy or runtime changes warrant it;
focused checks suffice for isolated changes. `scripts/doctor.py` diagnoses
installation health, not model behavior.

For an installation task on a disposable runner, install prerequisites, run
`scripts/install.py`, then the doctor. Do not bootstrap or mutate a real user
memory root to verify an unrelated edit. Report environmental failures
separately from failures caused by the change.

Repository gates to respect before proposing a push:

- **File size.** Code soft 500 / hard 1000 lines, docs soft 300 / hard 500.
  Split rather than grow; never edit `scripts/tools/file_size_baseline.json`
  to make the check pass.
- **Integrity manifest.** `integrity-manifest.json` hash-pins the control
  plane. After changing a file in its scope, regenerate it with
  `python scripts/tools/integrity_manifest.py --update` for your own change
  only, never to hide someone else's drift.
- **Encoding.** Every `subprocess.*` call with `text=True` also passes
  `encoding="utf-8"`; an AST-based gate fails the build otherwise.

## Conventions

- English for code, comments and commit messages.
- Conventional commits matching the log: `fix(policy): ...`, `docs: ...`,
  `test: ...`.
- Commits, pushes and pull requests follow OPS §1. When publication is
  authorized, use a branch and PR rather than pushing to `master`.
- Report exact commands, checked state and coverage; never claim broader
  coverage than was exercised.
