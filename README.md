# coding-kit — Coding Agent OS

A portable agent-brain kit: methodology (superpowers), minimalism (YAGNI), cross-chat memory (SQLite FTS5), adversarial evals (trap-suite). 36 Hermes-compatible skills, English instructions, one command bootstrap.

Works in environments that read an agent rules file and SKILL.md skills. Developed and tested on Claude Code / OMP (see adapters for others; per-harness behavior beyond those is untested by this project).

## What's inside

| Layer | File | Role |
|---|---|---|
| Soul | `AGENTS.md` | identity, red lines, routing (read first) |
| Contract | `OPS.md` | phases, memory hierarchy, gates, changelog |
| Runtime | `SKILL_RUNTIME.md` | context-size modes |
| Manifest | `profile.yml` | single source of truth: paths, skills |
| Skills | `skills/` | 36: always-on core + obra phase skills + domain + dashboard/UX |
| Memory engine | `memory/db-tools/` | build, search_all, findings, repomap (FTS5) |
| Evals | `eval/` | trap-suite (26 scenarios), task smoke (6 oracle-verified tasks incl. 2 canaries), trigger-eval (86 co-located queries across 12 skills; 80-query central fallback), ablation, rigor A/B, schema-v1 store + trend + telemetry |
| Adapters | `adapters/` | per-environment setup guides |

## Requirements

- Python **3.12** — the only version tested (CI: windows-latest and
  ubuntu-latest). Other versions are untested; reports of working setups
  are welcome.
- For the test suite: `pytest` (`python -m pip install pytest` — the only
  test dependency; the kit itself is stdlib-only).

## Install — two phases

**Phase 1 — memory bootstrap** (one command, touches nothing global):

```bash
git clone https://github.com/oleg494/coding-kit.git coding-kit
cd coding-kit
python scripts/install.py
```

`install.py` creates `~/.memory/` (your private knowledge base — fixtures,
engine link, indexes), idempotent, safe to re-run. Custom location:
`MEMORY_ROOT=/x/y python scripts/install.py`. After it prints
`search smoke: OK` the memory store works standalone — prove it:

```bash
python ~/.memory/db-tools/findings.py add "first-note" \
  --text "hello from coding-kit" --source README.md   # → [✓] added (id=1)
python ~/.memory/db-tools/findings.py search "first-note"  # → found: 1
```

**Phase 2 — agent integration** (per-harness; `install.py` does NOT do
this step). Pick your agent from `adapters/`:

- **Claude Code / OMP**: rules → `~/.claude/CLAUDE.md`; skills → `~/.claude/skills/`
- **Antigravity**: rules → `~/AGENTS.md`; skills → `~/.agents/skills/`
- **ZCode (Z.ai)**: rules → `~/.zcode/AGENTS.md`; skills → `~/.zcode/skills/` (junction recommended)
- **Hermes**: soul → `SOUL.md`; `config.yaml` → `skills.external_dirs`

Verify integration by behavior, not file checks: ask the agent to show its
method (plan → TDD → implement → verify → report) and to search memory for
your first-note — it must route through
`python ~/.memory/db-tools/search_all.py "X"`, not answer from
conversation. `python scripts/doctor.py` green means the repo and memory
root are self-consistent; it does not prove your harness loaded anything.

## Daily loop

```bash
python ~/.memory/db-tools/search_all.py "X"    # before "what do we know about X"
```

Gates and checks (the kit's own lifecycle, run directly):
- `python scripts/doctor.py` — 14 self-diagnostic health checks.
- `python -m pytest tests -q` — unit test suite (needs `pytest` installed).
- `python scripts/tools/check_file_sizes.py --ci` — file-size gate (hard limits).
- `python memory/scripts/memory-warmup.py` — cross-chat memory warmup.


## Evals & Trend Loop

The kit includes an evidence-first evaluation harness:
- **Trap-suite (`eval/runner.py`)**: 26 adversarial scenarios testing adherence to superpowers, YAGNI, and security invariants. Candidate answers are bounded and delimited as untrusted evidence. Omitted `--judge` defaults to the executor (self-judging carries inherent bias; recommend configuring a distinct `--judge` for gating).
- **Task Smoke (`eval/task_runner.py`)**: 6 real coding tasks (incl. 2 impossible canaries) verified by deterministic `verify.py` test oracles (no LLM judge for pass/fail). Each attempt runs in an isolated sandbox cloned fresh from `eval/tasks/repo-fixture` (default `--tries 2`). This serves as a smoke canary, not a statistical benchmark.
- **Trigger Evals (`eval/trigger_eval.py`)**: `--queries auto` validates 86 co-located queries across 12 skills (per-skill `evals/evals.json`), with `eval/trigger_queries.json` (80 queries, 10 skills) as the central fallback for skills lacking a co-located file — testing skill activation routing.
- **Schema-v1 Results Store (`eval/results_io.py`)**: atomic append-only JSON storage under `eval/results/` with microsecond UTC timestamps, UUID `run_id`, separate `model` metadata, explicit `mode` (`"dry-run"` vs `"live"`), and standardized failure taxonomies.
- **Trend Reporting (`eval/trend.py`)**: summarizes newest runs by `(kind, model)`, filters dry-runs and zero-result artifacts via explicit mode discriminators, reports baseline deltas, and produces structured Failure Evidence Packets with bounded trace tails for debugging.
- **Telemetry (`eval/telemetry.py`)**: every result doc folds per-attempt wall-clock `duration_s` into `duration_s_total`/`duration_s_mean` across all three runners (trap/tasks/trigger). Optional `--usage-json` `{tokens_total, cost_usd}` records user-reported provider totals — the harness measures wall-clock only and never fabricates cost.
- **Ablation (`eval/ablate.py`)**: experimental per-skill inlined-prompt contribution (pass-rate with vs. without the inlined skill body). Descriptive, not causal — ambient CLI skills are uncontrolled and small samples may be non-conclusive; it never deletes a skill. Requires a live `--executor`.
- **Rigor A/B (`eval/rigor/`)**: controlled policy experiments with route/microtask/trap corpora, isolation + canary probes, and an acceptance gate that can reject its own candidate (it did — see docs/research/2026-09-03).
- **Isolation**: executor subprocesses run from a neutral per-call temp `cwd`, which prevents automatic discovery of repo-local instruction/config files via the inherited `cwd`; ambient global skills and general filesystem access remain uncontrolled. HOME/auth environment is retained.

Quick validation (no model, no live output):

```bash
python eval/ablate.py --help                          # ablation flags/contract
python eval/runner.py --inline-skills                 # dry-run: validate scenarios + skills manifest (no executor prompts sent)
python eval/task_runner.py --dry-run                  # validate task layout
python eval/trigger_eval.py --queries eval/trigger_queries.json   # validate queries
```

## Measured cost (historical external benchmark)

Historical external A/B run (2026-09) on [DeepSWE](https://deepswe.datacurve.ai)
(pier + mini-swe-agent in Docker, model `deepseek-v4-pro`, 10-task seed-0
subset, 1 concurrent trial): the same agent with the kit (OPS.md + AGENTS.md +
36-skill manifest inlined, ~5.4k tokens) vs. without it. Raw artifacts are
retained outside this repository and are not bundled with the kit; this repo
ships no reproduction script or composite-analysis command for these numbers —
they are reported as run, not re-derivable from the repo.

- **Pass rate: no difference** — 6/9 both arms. The kit did not make a strong
  model solve more tasks.
- **Token cost is real**: +21% steps, +41% prompt tokens on identical outcomes
  (99.5M vs 70.4M across 5 mutually-solved tasks). Cache absorbs the kit's
  static ~5.4k-token overhead; the extra spend is the methodology's own
  iterations (plan → TDD → verify).
- **Task-dependent flips**: kit won one task outright (24/24 vs 6/24 — process
  discipline rescued a flailing attempt) and lost one small fiddly task
  (2/5 vs 5/5 — ceremony overhead). n=9: trend, not a verdict.

Honest takeaway: on a strong model and well-specified tasks the kit is not a
uniform win — it buys reliability on hard multi-part tasks at a measurable
token premium. Budget accordingly.

## Where your data lives

The kit repo contains only methodology and engine. Your knowledge (Wiki posts, findings, indexes) lives in `~/.memory/` — personal, never committed, gitignored in every place it can appear.

## Platform note

Developed and tested Windows-first (CI also runs ubuntu-latest). The engine link
is a junction on Windows, a symlink elsewhere — `install.py` picks automatically.

## Credits & licensing

Phase-workflow skills (`brainstorming`, `writing-plans`, `using-git-worktrees`,
`requesting-code-review`, `receiving-code-review`, `verification-before-completion`,
`systematic-debugging`, `dispatching-parallel-agents`, `finishing-a-development-branch`)
are derived from
[obra/superpowers](https://github.com/obra/superpowers) (MIT) © Jesse Vincent,
reworked and extended for coding-kit. See `skills/superpowers/LICENSE`.
`ponytail` is adapted from [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)
(MIT; see `skills/ponytail/LICENSE`).

## License

The repository root is MIT (see LICENSE). One conflict is unresolved:
`skills/windows-encoding-fixes` declares `license: Proprietary` in its
frontmatter, which is inconsistent with the root MIT grant. This README
makes no rights determination in either direction and draws no
author-identity or provenance conclusion — a frontmatter label is not
proof of a grant or of an exclusion. The mismatch stays open until the
owner resolves it; the skill is wired into `profile.yml`, the
release-contract pin, `integrity-manifest.json`, and the trigger corpora,
so it is not a drop-in deletion.

MIT — see LICENSE.