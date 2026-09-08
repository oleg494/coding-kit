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
  Do not point agents at untrusted repositories and expect isolation.
- `scripts/install.py` writes only under `MEMORY_ROOT` (default `~/.memory`)
  and links the engine from the clone — review it before running, like any
  bootstrap script.
