# Real-Usage Audit Methodology

> Born from the 2026-08-29 audit: conclusions drawn from session transcripts were
> about to kill healthy subsystems because two confounds went unnoticed. This note
> is the checklist so the next audit doesn't repeat them.

## Confounds

### 1. Kit-internal sessions masquerade as "usage"
The kit works on itself: releases, self-tests, eval harness runs (`kit-eval-*`,
`KODEKITTEST`, `CLAUDETESTS`, sessions with cwd inside `coding-kit`, or first human
turn mentioning «код кит»/kit). In the audited window this was 69/82 Claude Code
sessions and 5/45 omp sessions. Any "skill X is unused" or "memory engine unused"
count that doesn't segregate these is measuring the kit testing itself.

**Rule:** segregate first (kit-internal vs real), then compute adoption numbers.
`scripts/tools/usage_audit.py` does this automatically.

### 2. Installation eras invalidate baselines
"0 uses in two weeks" was true — and meaningless: the machine-wide kit install
happened 2026-08-26. Before that, OPS.md entered real-session context in 1 of 11
sessions (and only because the assistant read it itself). Usage numbers from
before an install/change date say nothing about the installed product.

**Rule:** establish the era boundary (install date, config change) first; judge
the kit only on sessions after it. A subsystem with zero uses needs ≥2 weeks of
post-install data before any kill/merge decision — era-2's "never-read" skills
(agent-ux, dashboard-*, design-system, learn, executing-plans,
subagent-driven-development) get a re-audit, not a deletion.

### 3. Mentions are not read requests, and reads are not utility
Before the 2026-09-19 correction, `skill_reads` matched `skill://...` anywhere
in a normalized record. User/assistant prose and tool results could inflate
usage, while actual reads through `skills/<name>/SKILL.md` paths were missed.

The counter now records distinct skills explicitly targeted by `Read`, `read`,
`read_file`, or `functions.read`, including `multi_tool_use.parallel` children.
Targets come from `path`, `file_path`, or `absolute_path`: skill URIs and
Windows/POSIX `skills/<name>/SKILL.md` paths, including read selectors.
Messages, result bodies, write payloads, and incidental argument text do not
count. Repeat reads of the same skill count once per session.

**Limits:** a request does not prove successful loading or useful application.
Shell/eval reads and native skill loaders are not inferred; Gemini tool traffic
omitted by the normalizer remains unmeasured. `zero_use` means no observed
explicit reads, not demonstrated non-use. `sessions_audited` in the retirement
report counts only real sessions. Both human and JSON reports carry the scope
warning; historical counts are not directly comparable across this correction.

**Rule:** do not retire a skill from this counter alone. Check transcript
coverage and actual outcomes; keep retrieval, application, and utility separate.

## How to run

```bash
python scripts/tools/usage_audit.py                 # last 14 days, human summary
python scripts/tools/usage_audit.py --since 2026-08-26 --json   # machine-readable
```

Reads Claude Code (`~/.claude/projects`) and omp (`~/.omp/agent/sessions`)
transcripts; reports human turns, memory-engine calls, skill reads, OPS-in-context
markers, split real vs kit-internal.

## What the 2026-08-29 audit established

- Memory engine (db-tools) is the kit's most-used subsystem post-install
  (93 calls across 20/40 real omp sessions, 36 findings written).
- The trigger layer is broken at the mechanism level: the eval executor ignores
  the skills listing (8/10 skills 0.00 trigger rate even where Russian trigger
  tokens exist in descriptions). Fixing vocabulary does not fix this.
- OPS.md was 64% changelog by tokens; it is a per-session context payload.
  History now lives in `docs/CHANGELOG.md`.
- Adoption conclusions require adversarial verification: 4 of 12 proposed
  changes were refuted on re-examination (kill dashboard skills — too young;
  Russian rewording — mechanism not vocabulary; drift-killer kill — kept for its
  cheap meta-check; plan-gate hardening — pain was kit-selftest, not real user).
