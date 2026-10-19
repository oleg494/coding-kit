# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 4.4.x | yes |
| 4.3.x | yes |
| 4.x   | yes |
| 3.4.x | yes |
| 3.3.x | yes |
| < 3.3 | no |

## Reporting a vulnerability

Use GitHub's private vulnerability reporting
(**Security → Report a vulnerability** on this repository). Please do not open
a public issue for anything exploitable.

Include: affected paths/scripts, reproduction steps, and the environment
(OS, Python version, harness).

## Scope notes

- The kit runs **your** code through your agent harness; prompt-injection
  resistance is a methodology goal (see `eval/scenarios/`), not a sandbox.
- `scripts/install.py` writes only under `MEMORY_ROOT` (default `~/.memory`)
  and links the engine from the clone — review it before running, like any
  bootstrap script.
- **Enforced boundary (since 4.10.1):** before the first write, install.py
  runs a link/reparse-aware preflight over every installer-managed
  destination — the root layout, every intermediate ancestor (Wiki, db,
  scripts), Wiki seed files, VERSION, `scripts/` copies, and every
  existing `db/*.db` entry the engine writes or opens read-write
  (wiki.db, research.db) — and over MEMORY_ROOT itself. If any of them
  is a symlink/junction whose target resolves outside MEMORY_ROOT, is a
  dangling link pointing outside, or cannot be resolved at all — or
  MEMORY_ROOT is itself a link to a different location — the install
  fails closed with an explicit error and nothing is created or
  modified. Remaining limitations: the engine link `<root>/db-tools -> <kit>/memory/db-tools`
  is by design the one external link (created by the installer itself, never
  written through); content already *inside* a link that stays within the
  root is trusted; the check is pre-mutation only, so a link swapped in
  after the check but before a write (TOCTOU) is not caught — bootstrap
  is not a crash-atomic transaction; and scripts executed after install
  (`memory-warmup.py`, `db-tools/*`) rely on the same root convention,
  not on this preflight.
