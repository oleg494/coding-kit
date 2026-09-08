# coding-kit — Coding Agent OS

A portable agent-brain kit: methodology (superpowers), minimalism (YAGNI), cross-chat memory (SQLite FTS5), adversarial evals (trap-suite). 37 Hermes-compatible skills, English instructions, one command bootstrap.

Works in environments that read an agent rules file and SKILL.md skills. Developed and tested on Claude Code / OMP (see adapters for others; per-harness behavior beyond those is untested by this project).

## What's inside

| Layer | File | Role |
|---|---|---|
| Soul | `AGENTS.md` | identity, red lines, routing (read first) |
| Contract | `OPS.md` | phases, memory hierarchy, gates, changelog |
| Runtime | `SKILL_RUNTIME.md` | context-size modes |
| Manifest | `profile.yml` | single source of truth: paths, skills |
| Skills | `skills/` | 37: always-on core + obra phase skills + domain + dashboard/UX |
| Memory engine | `memory/db-tools/` | build, search_all, findings, repomap (FTS5) |
| Evals | `eval/` | trap-suite (31 scenarios), task smoke (6 oracle-verified tasks incl. 2 canaries), trigger-eval (92 co-located queries across 13 skills; 80-query central fallback), ablation, rigor A/B, schema-v1 store + trend + telemetry |
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
  --text "hello from coding-kit" --project coding-kit --importance normal \
  --source README.md   # → [✓] added (id=1)
python ~/.memory/db-tools/findings.py search "first-note" --project coding-kit  # → found: 1
python ~/.memory/db-tools/findings.py projects   # overview grouped by project and importance
python ~/.memory/db-tools/findings.py edit 1 --project coding-kit --importance high
python ~/.memory/db-tools/findings.py classify mapping.json --dry-run  # validate batch mapping
```

### Project Taxonomy & Importance Levels

- **Projects:** dynamically discovered from `~/.memory/db/*.db` plus optional `projects.json`. Slug format: `[a-z0-9][a-z0-9_-]{0,63}`.
  - `portable`: reusable engineering patterns, tools, and cross-project knowledge.
  - `unknown`: unclassified personal notes, coursework, or items not tied to a specific project.
- **Importance levels:**
  - `high`: critical security boundaries, invariants, data-loss prevention, durable release contracts.
  - `normal`: standard actionable engineering findings, reproducible runbooks, feature setups.
  - `low`: transient checkpoints, scratch notes, personal experiments, milestone logs.
  - `unreviewed`: default state prior to qualitative review.
- **Batch Classification (`classify`):**
  Accepts JSON list or object with `{"records": [...]}`:
  `[{"id": 1, "candidate_project": "coding-kit", "candidate_importance": "low", "project_rationale": "...", "importance_rationale": "..."}]`
  Atomic transaction (rolls back on any error) and idempotent: user-curated records (`cli_edit`) are preserved unless `--force` is given.

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
python ~/.memory/db-tools/search_all.py "X"                     # before "what do we know about X"
python ~/.memory/db-tools/search_all.py "X" --project <slug>   # scoped to project
python ~/.memory/db-tools/search_all.py "X" --importance high   # prioritized recall
```

Gates and checks (the kit's own lifecycle, run directly):
- `python scripts/doctor.py` — 14 self-diagnostic health checks.
- `python -m pytest tests -q` — unit test suite (needs `pytest` installed).
- `python scripts/tools/check_file_sizes.py --ci` — file-size gate (hard limits).
- `python memory/scripts/memory-warmup.py` — cross-chat memory warmup.


## Autonomous work (opt-in)

Broad authorization to choose and continue useful work ("do useful work",
"keep going without asking", "работай сам") loads skill `autonomous-work`.
It is task opt-in: ordinary bounded requests keep their existing scope, and
there is no `MODE:` override — `STRICT_AUDIT` and read-only tasks stay
read-only. Outward, destructive, spending, and memory-writing actions still
require explicit authorization.

The skill covers work selection from evidence, verify-by-observation loops,
durable mission/progress/handoff state, and immediate stop/revocation. For
continuation across process boundaries (context compaction, terminal death)
an optional foreground stdlib supervisor ships with the kit:

```bash
python scripts/tools/autonomous.py --workspace PATH --mission TEXT \
  --executor COMMAND --verify COMMAND \
  [--state-dir PATH] [--max-iterations 10] [--timeout 600]
```

`--executor`/`--verify` are argv, never a POSIX shell (Windows `.cmd`/`.bat`
need `cmd`). State defaults to `<workspace>/.autonomous` (`state.json` +
`logs/`, atomic writes, resumable). The executor writes a checkpoint proposal
(`checkpoint.json`, removed before each spawn; its absolute path is passed on
stdin as `Checkpoint: <path>` and via `AUTONOMOUS_CHECKPOINT`). Checkpoints
are untrusted claims, never commands: `complete` is accepted only after the
independent `--verify` exits zero. Exit codes: `0` verified completion only,
`1` failed/exhausted/blocked/stalled, `130` user stop; a `STOP` file in the
state dir prevents a spawn and interrupts a live child. A filesystem
workspace is not a security sandbox. Design and acceptance criteria:
`docs/research/2026-09-08-autonomous-mode.md`.

## Evals & Trend Loop

The kit includes evaluation harnesses targeting distinct questions (health checks, trigger activation routing, and behavioral adherence are evaluated separately from task success or cost claims):
- **Trap-suite (`eval/runner.py`)**: 31 adversarial scenarios testing policy adherence to superpowers, YAGNI, and security invariants. Candidate answers are bounded and delimited as untrusted evidence. Omitted `--judge` defaults to the executor (self-judging carries inherent bias; recommend configuring a distinct `--judge` for gating). Adherence to rules does not prove task-level superiority.
- **Task Smoke (`eval/task_runner.py`)**: 6 real coding tasks (incl. 2 impossible canaries) verified by deterministic `verify.py` test oracles (no LLM judge for pass/fail). Each attempt runs in an isolated sandbox cloned fresh from `eval/tasks/repo-fixture` (default `--tries 2`). This serves as a smoke canary, not a statistical benchmark.
- **Trigger Evals (`eval/trigger_eval.py`)**: `--queries auto` validates 92 co-located queries across 13 skills (per-skill `evals/evals.json`), with `eval/trigger_queries.json` (80 queries, 10 skills) as the central fallback for skills lacking a co-located file — testing skill activation routing.
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

- **Pass rate: no difference** — 6/9 both arms. In this test, the kit did not increase solved-task counts for a strong model.
- **Token cost is real**: +21% steps, +41% prompt tokens on identical outcomes
  (99.5M vs 70.4M across 5 mutually-solved tasks). Cache absorbs the kit's
  static ~5.4k-token overhead; the extra spend is the methodology's own
  iterations (plan → TDD → verify). No causal claim of overall cost reduction can be made.
- **Task-dependent flips**: kit won one task outright (24/24 vs 6/24 — process
  discipline rescued a flailing attempt) and lost one small fiddly task
  (2/5 vs 5/5 — ceremony overhead). n=9: descriptive observation, not a general verdict.

Honest takeaway: on a strong model and well-specified tasks the kit is not a
uniform win — the sample showed process discipline rescuing one hard task
and ceremony costing one small task, at a measurable token premium; no general
reliability claim follows from n=9. Negative results and confounded replays are recorded as negative evidence, not optimization wins. Budget accordingly.

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