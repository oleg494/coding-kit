# Coding Agent OS — Skill Runtime

> **v6.0.0** | Host integration notes, not another operating contract.

## Startup

Point the host's instruction file at the clone's absolute `OPS.md` path and
load it once. `AGENTS.md` is a short repository router; do not embed its body
plus OPS plus skill bodies. If the host already loaded the current contract, a
second pointer must not cause another read.

`profile.yml` declares the 27 kit-owned skills. Its `always_on` list is empty:
the core method is in OPS, and skill bodies load on demand. Expose the short
descriptions; each one names its trigger and the neighbor skill to use
instead. Host mandatory loading rules take precedence.

## Host boundaries

Use the host's native search, symbol tools, delegation and approval APIs.
Do not copy another platform's tool names, shell syntax or agent-type
arguments literally. Installed third-party skills are not kit-owned;
deployment preserves them. Approval mode, sandboxing, model roles, network
routing and context compaction are host configuration, not effects of this
kit.

A read-only request is a scope rule, not a technical sandbox. Use the host's
read-only mode where available; an auto-approved tool is not permission.

## Memory

No automatic warmup, global findings feed or recursive integrity scan at
startup. Retrieval and saving follow OPS §5. Explicit availability check:
`python memory/scripts/memory-warmup.py` from the clone, or the installed
script under `~/.memory/scripts/` (`--full` for diagnostics). `MEMORY_ROOT`
selects the store; no mode silently migrates it.

## Constrained context

OPS §§1–3 are the irreducible core: authority, stop and read-only boundaries,
complete outcomes, applicable evidence and honest limitations. When context
is tight, drop optional procedure before these.
