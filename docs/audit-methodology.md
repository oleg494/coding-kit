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

Since the 2026-10-20 extension, the counter records distinct skills explicitly
targeted by `Read`, `read`, `read_file`, or `functions.read`, including
`multi_tool_use.parallel` children. Targets come from `path`, `file_path`, or
`absolute_path`: skill URIs (`skill://<name>/...`) and Windows/POSIX paths to
ANY file under a named skill payload — `SKILL.md`, `references/`, `evals/`,
`assets/`, or arbitrary nested files — so a deep reference read attributes to
its owning skill. A second-level `skills/skills/` root is unwrapped, so
`skills/skills/beta/SKILL.md` attributes to `beta`, never to a phantom
skill named `skills`. Messages, result bodies, write payloads,
non-read tools, and incidental argument text do not count. Repeat
reads of the same skill count once per session.

**Limits:** a request does not prove successful loading or useful application.
Shell/eval reads and native skill loaders are not inferred; Gemini tool traffic
omitted by the normalizer remains unmeasured. `zero_use` means no observed
explicit reads, not demonstrated non-use. `sessions_audited` in the retirement
report counts only real sessions. Both human and JSON reports carry the scope
warning; historical counts are not directly comparable across this correction
(pre-2026-09-19 counts also matched mentions; pre-2026-10-20 counts missed
nested payload reads, so migration of historical numbers requires re-running
the audit over the same window).

**Rule:** do not retire a skill from this counter alone. Check transcript
coverage and actual outcomes; keep retrieval, application, and utility separate.

### 4. memory_calls attribution: entrypoints only, diagnostics separate
Before the 2026-10-20 correction, `memory_calls` matched any tool record whose
name/arguments mentioned the memory engine OR kit diagnostics — a loose regex
that also caught `build.py`, `doctor.py`, `check_file_sizes`, and `skills_search`
in unrelated projects. Real sessions that merely built their own project or
ran kit checks inflated "memory engine usage".

The counter now counts only:
- explicit memory-engine entrypoints — `memory-warmup`, `search_all.py`,
  `findings.py`, `repomap`, `build-memory`;
- `build.py` only when the same command line carries a memory path marker
  (`.memory`, `db-tools`, or a `memory/` path segment) — bare project
  `build.py` does not count, and a later `cd` to an unrelated path drops
  the marker carried by an earlier `cd`.

`skills_search` is counted separately in `skill_search_calls`, not in
`memory_calls` or `kit_diag_calls`.

Command lines are parsed structurally: leading environment assignments
(`PYTHONUTF8=1 python x.py`, quoted values included), runner options
and their values (`python -B`, `py -3`, `python -W error -X utf8`,
`uv run --python 3.12`), and `-c`/`-m` payloads — bare or attached
(`-cX`, `-mjson`), also under `uv run` — are never mistaken for the
executed script; argv-style argument arrays are treated as one command
with argument boundaries preserved (hostile elements carrying `;`,
`&&`, quotes or newlines stay inert arguments); and only whitelisted
command/argv fields of recognized shell tools are parsed (env lists,
paths, prompts and prose never reach the parser).

Kit diagnostic/maintenance commands (`doctor.py`, `check_file_sizes`) are
counted separately in `kit_diag_calls` (per-session and per-aggregate,
additive JSON fields) so kit self-maintenance is visible without
inflating memory-engine adoption. Existing `memory_calls` keys and the
report shape are unchanged; consumers see new optional fields only.

**Limits:** entrypoint matching is lexical on the parsed executable
entry. A memory-engine invocation wrapped so that no known entrypoint
string appears in the record is missed; a project whose own scripts
share these names is over-counted (mitigated, not eliminated, by the
build.py marker rule). Command-shape knowledge is heuristic — options
outside the known value-consuming set are skipped as bare flags.
Historical `memory_calls` totals computed before this correction are
not directly comparable — re-run the audit over a fixed window instead
of diffing pre/post numbers.

**Rule:** when reporting memory-engine adoption, quote both the corrected
`memory_calls` and `kit_diag_calls` from the same run, and state the
attribution version alongside the numbers.

## How to run

```bash
python scripts/tools/usage_audit.py                 # last 14 days, human summary
python scripts/tools/usage_audit.py --since 2026-08-26 --json   # machine-readable
```

Reads Claude Code (`~/.claude/projects`) and omp (`~/.omp/agent/sessions`)
transcripts; reports human turns, memory-engine calls, kit diagnostic calls,
skill reads, OPS-in-context markers, split real vs kit-internal.

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

## Heldout corpus and release protocol

> Added 2026-10-20 (4.10.2). This section is a protocol, not data: the
> heldout corpus is operator-owned and lives outside the repo while it
> is in force. Heldout cases are sealed from all tuning until evaluated;
> after evaluation the operator MAY publish the artifacts with their
> provenance (see `eval/results/collaborative-reasoning-20260915/`
> for a published example). Published heldout evidence is spent — once
> cases are visible to kit work, they can never again serve as heldout
> for a future change. A file under `eval/` claiming current heldout
> provenance for an in-force (still-sealed) corpus misrepresents the
> protocol; check the operator's run record, not the repo.

### What each run level proves

- **Open dry-run** (`task_runner.py --dry-run`, `runner.py --inline-skills`)
  proves input validity only: task layout, spec parseability, canary
  marking. It records `DRY_RUN` rows, never a model verdict; exit zero
  means the inputs are well formed, not that the model passed.
- **Open live run** (confined `docker:` executor) proves execution on the
  development corpus. The development cases — everything versioned in
  `eval/tasks/`, `eval/scenarios/`, `eval/trigger_queries.json` — are
  visible to every kit change and every kit session. Pass rates here are
  fit-to-development-corpus evidence, not generalization evidence.
- **Heldout live run** is the strongest generalization check in this
  protocol: cases the operator selected before the candidate change and
  kept sealed from every development loop until after evaluation. It is
  not the only conceivable source of generalization evidence — a
  preregistered published experiment with a sealed split
  (`eval/results/collaborative-reasoning-20260915/`) is another —
  but it is the one that gates releases here.

### Separation of development and heldout cases

- Development (open) cases may be read, iterated on, and tuned against
  by kit work and kit sessions without restriction.
- Heldout cases are authored by the operator before the candidate change
  and stored outside the repo, sealed from all kit sessions until the
  scoring run has been evaluated: while in force they are never
  committed and never appear under `eval/`. After evaluation the
  operator MAY publish them with provenance; a published corpus is
  historical evidence, not a reusable seal — the cases are spent and
  cannot gate a future change. If a still-sealed heldout case leaks
  into repo content, the run that used it is void and the case is
  retired.
- No overlap: a development case, or a paraphrase of one, must not enter
  the heldout set. The operator records the selection date and corpus
  size by hand; the kit does not fabricate them.

### Independent judge requirements

- The judge must be a distinct model/session from the executor
  (`eval/runner.py --judge`): self-judging is descriptive evidence at
  best, never gate evidence.
- The judge is blind: it receives the case evidence and acceptance
  criteria, not the run's purpose, the candidate's identity, or the
  expected direction (same contract as the sycophancy pilot,
  `docs/research/2026-09-18-sycophancy/protocol.md`).
- A run where the judge was the executor, or where judging was not
  blind, must be labeled as such in its report; it cannot gate a
  release.

### Canary hacked exit contract

- The ImpossibleBench canaries (`005-canary-oneoff`,
  `006-canary-conflicting`) carry oracles no honest solution can pass.
  In any live `task_runner.py` run, a canary PASS is recorded
  `hacked: true` and the process exits nonzero — even when every
  ordinary task passes.
- Honest canary failures exit clean. A nonzero exit on an otherwise
  all-pass run is hacking evidence, not a flaky gate.
- The gate is pinned behaviorally in `tests/test_canaries.py`
  (`test_hacked_canary_gates_suite_exit_nonzero`,
  `test_hacked_canary_gates_process_exit_nonzero`) and referenced from
  `docs/SECURITY-MAP.md`.

### Limitations

- The protocol is one operator's discipline, not an enforced sandbox:
  nothing in the kit mechanically prevents leakage except the separation
  rules above.
- Heldout n is small (operator-authored); results are directional, and
  "improved on heldout" is never a statistical claim.
- No in-force (still-sealed) heldout results exist in the repo, so a
  candidate's heldout gate cannot be re-verified by CI from repo
  content alone; the operator's run record is the authority while the
  corpus is sealed. Historical published heldout artifacts under
  `eval/results/` (e.g. the 2026-09-15 collaborative-reasoning
  experiment) are evidence for the change they evaluated, not a
  reusable seal.
- Judge blindness is procedural: the kit cannot verify what a judge
  session actually saw.
