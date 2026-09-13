# coding-kit

**Reusable workflows and cross-session memory for coding agents.**

Give your agent a shared development method, searchable project knowledge,
and tools to evaluate its behavior. The kit combines 37 skills, plain-text
instructions, and a Python standard-library memory engine. It is not an
agent runtime, a sandbox, or a guarantee of better answers.

[![Kit gates](https://github.com/oleg494/coding-kit/actions/workflows/test.yml/badge.svg)](https://github.com/oleg494/coding-kit/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/oleg494/coding-kit)](https://github.com/oleg494/coding-kit/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Get started](#get-started) · [Daily use](#daily-use) · [Evidence and limitations](#evidence-and-limitations) · [Contributing](CONTRIBUTING.md)

## What you can use it for

- **Carry decisions across sessions.** Save findings in your private memory
  store and search them from a fresh agent session instead of reconstructing
  project history from chat.
- **Give coding work a repeatable method.** Skills cover planning,
  reproducing bugs, implementation, review, and verification. YAGNI means
  avoiding functionality and abstractions the task does not need.
- **Evaluate behavior rather than trust promises.** Run policy scenarios,
  skill-routing checks, and small coding tasks with deterministic verifiers.
  These answer different questions; none alone proves overall coding quality.

Developed and tested with **Claude Code and Oh My Pi (OMP)**. Other agents
that read instruction files and `SKILL.md` skills can be configured manually;
this project does not claim to have tested their behavior. Instructions are
in English; the kit asks the agent to answer in your language.

## Get started

Installation has two separate steps: **create the memory store**, then
**connect your agent**. The first step does not install agent instructions.

### 1. Create your memory store

Requirements: Git and **Python 3.12**. CI runs on Windows and Ubuntu with
Python 3.12; other Python versions are untested. Runtime scripts use the
standard library. Only contributors running the test suite need `pytest`.

Run these commands in PowerShell or Bash:

```text
git clone https://github.com/oleg494/coding-kit.git coding-kit
cd coding-kit
python scripts/install.py
```

The installer creates your user-level `~/.memory/` directory, including
fixtures and indexes, and links its engine to this clone. Keep the clone in
place. Re-running the installer is supported. Look for `search smoke: OK`.
It does not configure your agent's rules or skills.

<details>
<summary>Use a different memory location</summary>

Set `MEMORY_ROOT` before installation and in sessions that use the kit.

PowerShell:

```powershell
$env:MEMORY_ROOT = "$HOME/coding-memory"
python scripts/install.py
```

Bash:

```bash
export MEMORY_ROOT="$HOME/coding-memory"
python scripts/install.py
```

Examples below call the engine from the clone, so they do not depend on
shell expansion of `~` in script arguments.

</details>

### 2. Connect your agent

Merge a pointer to this clone's [AGENTS.md](AGENTS.md) and
[OPS.md](OPS.md) into your agent's rules file. Use an absolute path to the
clone so the files remain reachable from other projects. Preserve your
existing instructions; do not replace them wholesale.

Copy or link the contents of [skills/](skills/) into the agent's skill
directory, preserving unrelated skills. These are user-level changes and
can affect every project opened with that agent.

| Agent | Rules file | Skills |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `~/.claude/skills/` |
| Oh My Pi (OMP) | `~/.omp/agent/AGENTS.md` | Auto-discovers `~/.claude/skills/` |
| Antigravity | `~/AGENTS.md` | `~/.agents/skills/` |
| ZCode | `~/.zcode/AGENTS.md` | `~/.zcode/skills/` |
| Hermes | `SOUL.md` | Point `config.yaml` → `skills.external_dirs` at the clone's `skills/` |

The OMP paths above match the kit's [deployment targets](scripts/tools/deploy.py).
See the [Antigravity](adapters/antigravity.md) and [ZCode](adapters/zcode.md)
guides for their environment-specific setup.

### 3. Verify the connection

From the clone, enter the tools directory, save a note, and retrieve it:

```text
cd memory/db-tools
python findings.py add "first-note" --text "hello" --project coding-kit
python findings.py search "first-note" --project coding-kit
cd ../..
```

Then start a **fresh agent session** and ask:

> Search my coding-kit memory for "first-note" using the memory tools.
> Show the command you ran and the stored finding.

The agent should invoke `findings.py search` or `search_all.py` against your
memory store and retrieve the note, not merely repeat this example. If it
does not, check that the rules and skill paths are loaded by your agent.

`python scripts/doctor.py` checks repository and memory consistency.
A green result is **not** proof that an agent loaded or followed the kit.

## Daily use

Run the memory tools from the clone, or use their absolute paths elsewhere:

```text
python memory/db-tools/search_all.py "deployment decision"
python memory/db-tools/search_all.py "deployment decision" --project coding-kit
python memory/db-tools/search_all.py "deployment decision" --importance high
python memory/db-tools/findings.py projects
```

Ask the agent to save a decision when it is worth carrying into another
session. Memory writes need authorization; a read-only review should not
silently modify your knowledge base.

Your knowledge lives in `~/.memory/` (or `MEMORY_ROOT`), **outside the kit
repository**. The clone contains methodology and tooling, not your personal
project history. Do not commit your memory store or assume it is a sandbox
for untrusted data. See the [security policy](SECURITY.md).

<details>
<summary>Back up and verify recovery</summary>

The store is the one asset this repository cannot rebuild (`db/*.db` are
gitignored by design). Back it up, then prove the snapshot is usable:

```text
python scripts/tools/backup_memory.py
python scripts/tools/backup_memory.py --list
python scripts/tools/backup_memory.py --restore-drill <backup directory>
```

Backups land in `<memory root>/backups/<timestamp>/`. A snapshot whose
database was skipped is tagged `DEGRADED` and refused as a restore point.
`--restore-drill` restores into a temporary root, runs `PRAGMA
integrity_check` on every restored database, verifies the findings store and
searches a token taken from the restored rows; it prints JSON and exits 0
only when that verification passes. `--restore <dir>` performs a live restore
(pre-restore snapshot first; asks unless `--yes`).

</details>

<details>
<summary>Organize findings by project and importance</summary>

Projects are discovered from the memory root's `db/*.db` files and optional
`projects.json`. Project slugs use `[a-z0-9][a-z0-9_-]{0,63}`.
Use `portable` for reusable cross-project knowledge and `unknown` for
unclassified notes.

Importance levels:

- `high`: critical boundaries, invariants, and durable release contracts.
- `normal`: actionable findings, runbooks, and feature setups.
- `low`: temporary checkpoints and scratch notes.
- `unreviewed`: findings not yet qualitatively reviewed.

Use `findings.py edit --help` to update a finding using its returned ID;
IDs are not guaranteed to start at 1. For batch classification,
`findings.py classify mapping.json --dry-run` validates a mapping before
mutation. Classification is transactional and preserves user-curated records
unless `--force` is supplied. See [findings.py](memory/db-tools/findings.py).

</details>

## Evidence and limitations

**The kit is not a demonstrated universal coding-quality improvement.**
It adds instructions and can add work. Whether that helps depends on the
model, task, and integration.

A historical external [DeepSWE](https://deepswe.datacurve.ai/) A/B run
compared the same agent with and without the kit using `deepseek-v4-pro`,
pier + mini-swe-agent in Docker, and a 10-task seed-0 subset:

| Observation | Reported result |
|---|---|
| Solved tasks in the reported nine-task comparison | **6/9 in both arms** |
| Steps across five mutually solved tasks | **+21% with the kit** |
| Prompt tokens across those five tasks | **+41%**: 99.5M vs 70.4M |
| Task-level differences | One kit win and one kit loss |

This was a small historical sample using a 36-skill manifest, not a benchmark
of the current release. Raw artifacts are retained outside this repository;
the repo does not ship a reproduction script for these numbers. The results
are descriptive, not a causal explanation or a general reliability claim.
Prompt-token counts are not a measured monetary bill.

The [4.5.1 release notes](https://github.com/oleg494/coding-kit/releases/tag/v4.5.1)
separately document policy-calibration observations and their limits. They
are stated-next-action evidence, not an end-to-end coding-quality win rate.

### Run the kit's checks

```text
python -m pip install pytest
python scripts/doctor.py
python -m pytest tests -q
python scripts/tools/check_file_sizes.py --ci
```

CI runs the [kit gates](.github/workflows/test.yml) on Windows and Ubuntu.
Structural validation can run without a model or paid API calls:

```text
python eval/runner.py --inline-skills
python eval/task_runner.py --dry-run
python eval/trigger_eval.py --queries eval/trigger_queries.json
```

These commands validate evaluation inputs; they do **not** measure a live
model's behavior.

<details>
<summary>Evaluation tools and what they measure</summary>

| Tool | Purpose and boundary |
|---|---|
| [Trap-suite](eval/runner.py) | 31 adversarial policy scenarios. The judge defaults to the executor; use a distinct judge to reduce self-judging bias. Policy adherence is not task superiority. |
| [Task smoke](eval/task_runner.py) | Six coding tasks, including two impossible canaries, with deterministic `verify.py` oracles. A smoke check, not a statistical benchmark. |
| [Trigger evals](eval/trigger_eval.py) | Skill activation routing: 92 co-located queries across 13 skills with `--queries auto`; an 80-query central corpus provides fallback coverage. |
| [Results store](eval/results_io.py) and [trend](eval/trend.py) | Structured results, explicit live/dry-run modes, failure categories, and comparisons of recorded runs. |
| [Telemetry](eval/telemetry.py) | Measures duration. Optional usage totals are user-reported, not independently measured token cost. |
| [Ablation](eval/ablate.py) | Compares prompts with and without an inlined skill. Ambient skills remain uncontrolled; results are descriptive, not causal. |
| [Rigor A/B](eval/rigor/) | Policy experiments with isolation probes and an acceptance gate that can reject a candidate. |

Live evaluations require an executor and may incur provider charges.
A neutral temporary working directory reduces repo-local instruction
loading; global skills, credentials, and general filesystem access remain
available. This is **not security isolation**.

</details>

## Autonomous work (opt-in)

Requests such as “do useful work” or “keep going without asking” activate
[autonomous-work](skills/autonomous-work/SKILL.md): evidence-backed work
selection, verified progress, and immediate stop/revocation. Ordinary
bounded requests do not become autonomous missions. Outward, destructive,
spending, and memory-writing actions still need authorization.

An optional foreground Python [supervisor](scripts/tools/autonomous.py)
supports continuation across process boundaries:

```text
python scripts/tools/autonomous.py --help
```

It accepts an executor and independent verifier, records resumable state,
and reports completion only after verification succeeds. A `STOP` file
prevents further spawning and interrupts a live child. Read the
[supervisor contract](docs/research/2026-09-08-autonomous-mode.md) before
configuring commands; a workspace is not a security sandbox.

## Inside the repository

| Component | Entry point |
|---|---|
| Agent instructions and routing | [AGENTS.md](AGENTS.md) |
| Operating contract | [OPS.md](OPS.md) |
| Context-size modes | [SKILL_RUNTIME.md](SKILL_RUNTIME.md) |
| Paths and skill manifest | [profile.yml](profile.yml) |
| Workflow and domain skills | [skills/](skills/) |
| Memory engine | [memory/db-tools/](memory/db-tools/) |
| Evaluation tools | [eval/](eval/) |
| Changes and contribution guide | [Changelog](docs/CHANGELOG.md) · [Contributing](CONTRIBUTING.md) |

Windows-first development; CI also runs on Ubuntu. The memory engine link
is a junction on Windows and a symlink elsewhere.

## Credits and license

[MIT](LICENSE). Phase-workflow skills are derived from
[obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent,
reworked and extended for coding-kit; see the
[superpowers license](skills/superpowers/LICENSE).
The `ponytail` skill is adapted from
[DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail);
see its [license](skills/ponytail/LICENSE).
