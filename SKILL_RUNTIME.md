# Coding Agent OS — Skill Runtime

> **v4.8.0** | Host integration notes, not another operating contract.

## Startup

Point the host's instruction file at the clone's absolute `OPS.md` path and
load it once. `AGENTS.md` is a short repository router; do not embed its body
plus OPS plus every method skill. If the host already loaded the current
contract, a second pointer must not cause another read.

`profile.yml` declares the 37 kit-owned skills. Its `always_on` list is empty:
the core principles are in OPS, while full skill bodies load on demand.
Expose short descriptions; read the primary skill for an explicit invocation
or an unresolved domain question. Cross-references do not trigger more loads.
Host mandatory loading rules take precedence and may limit these savings.

## Host boundaries

Use native search, symbol tools, task/delegation and approval APIs. Do not copy
another platform's tool names, shell syntax or agent-type arguments literally.
Installed third-party skills are not kit-owned; deployment must preserve them.
Host approval mode, sandboxing, model roles, network routing and context
compaction are host configuration, not effects of this instruction file.

A read-only request is a scope rule, not a technical sandbox. Choose the host's
read-only mode where available; do not infer permission from an auto-approved
tool. Local implementation checks and external effects follow OPS §1.

## Memory

No automatic warmup, global findings feed, recursive integrity scan or save
ritual. Retrieve memory when prior decisions matter, using project/topic scope.
Explicit availability check: `python memory/scripts/memory-warmup.py` from the
clone, or the installed script under `~/.memory/scripts/`. Full diagnostics:
add `--full`. `MEMORY_ROOT` selects the store; no mode may silently migrate it.

## Completion and constrained context

OPS §§1–3 remain the irreducible core: authority, stop/read-only boundaries,
complete requested outcomes, applicable evidence and honest limitations.
When context is constrained, omit optional procedures before these safeguards.
Recover a continued mission from history/memory, including its grants and
verification provenance; do not reset it to a new task.

A bounded task ends after the verified deliverable and report. An explicitly
autonomous mission continues within its grant; it cannot override a stop,
read-only instruction or missing external authority. See `autonomous-work`
only when mission recovery or autonomous execution is the open question.
