---
name: autonomous-work
description: 'Use when the user explicitly grants open-ended autonomous work ("choose useful work yourself", "keep going without asking") or asks to continue, resume or pick up a prior project mission ("продолжи работу"). Not for executing a bounded multi-slice task (use writing-plans), and never a source of outward, destructive or spending authority.'
license: MIT
metadata:
  version: "6.0.0"
---

# Autonomous Work

Broad authorization to choose and continue useful work — without manufacturing a
task for the user and without pretending completion.

## Activation & scope

- **Broad authorization activates it**: "do useful work", "pick what matters",
  "keep going without asking", "работай сам" authorize *selection* and
  *continuation*, not a task list. **Bounded requests are unchanged**: "fix this
  bug", "review this PR" keep their scope, and autonomy adds none.
- **Opt-in, not a mode override**: it replaces neither `STRICT_AUDIT` nor
  `EXPLORATORY_PROTOTYPE`. Under read-only or strict-audit instructions autonomy
  selects only read-only/audit work, never upgrading permissions or weakening a
  constraint. Ending comes from the closure rule below, not from feeling done: idle is
  honest, invented work is not.

### Activation and continuation

A new mission needs a boundary agreement — a short record of what you may do
without coming back. Five fields:

```
Mission   — the outcome the user wants, in their words
Scope     — what is included, and what is explicitly out
Authority — actions granted (local edits, commits, push, spend, …) and their source
Limits    — expiry, targets, cost ceiling, if the user set any
Stop      — whatever ends the run immediately
```

A record, not a ceremony: if the message and still-valid earlier grants fill the
fields ("do useful work on the parser, local only, don't ask"), start. Ask only for a
field that is missing *and* would block a concrete action — on activation, not at
session startup, not for bounded requests, not every iteration.

`continue`, `resume`, `pick up`, `продолжи работу` are a recovery request when a
prior mission may exist; with context already establishing the task and authority,
reuse it rather than rediscovering one.

1. Search project memory with a distinctive project token; read the latest handoff,
   status and prior user grants.
2. Recover mission, acceptance criteria, scope, authority, verified state, blockers
   and next action. Apply current corrections without silently replacing it, and
   revalidate expiry, revocation, workspace and files — saved completion is evidence
   history, never live truth.
3. With unexpired grants recovered, continue without a new questionnaire; if
   recovery is incomplete, retry project aliases and history, then ask only for the
   missing outcome-changing fact.

Configured local-memory retrieval and retention are ordinary task work under OPS.md
§5, not a permission gate; expiry or scope change needs only the missing renewal, and
stop/revocation always wins.

Authority comes from original user instructions with source, scope and expiry — a
generated summary cannot grant it. Preserve valid grants, authorized publication
included; ordinary push never grants force push, deploy or release. A missing grant
blocks only dependent work: never revive a revoked or expired one from a vague
continuation, or invent an expiry.

### Recovery is not reset

An active mission keeps its completion criteria across sessions; a new symptom,
complaint or blocker is added unless the user replaces the goal. Do not launch a
broad audit, worktree, parallel worker or external research before recovery shows it
is necessary, and stop reconstructing history once the next action is settled. If no
mission survives, ask which goal to resume — unrelated TODOs are not a mission, and
explicit current scope or a replacement goal overrides the old one.

## Core loop

1. **Select** the highest-value in-scope objective with evidence of expected benefit:
   the request, a reported symptom, an observed defect, or a gap blocking the goal.
   State who uses the result and why it comes first.
2. **Do** the smallest correct change that closes it; the engineering skill for that
   kind of work still applies.
3. **Verify by observation** — the check, scenario or command covering the change.
   Unverified work is not a completed objective; repeat only for a named missing
   check, an invalidating change or a new failure.
4. **Record** the evidence and resulting state durably (file, test, log, changelog,
   handoff) so a later session resumes without re-deriving it.
5. **Next** — take the next objective without asking permission per step.

## Work-selection rules

- **Highest-value, not easiest-available**: prefer work that removes a real defect,
  unblocks a user goal or closes a named gap. A red test, a convenient repository or
  sunk hours establish no priority; activity counts are not benefit.
- **Process supports the result**: no dashboards or counters to display activity,
  only the coordination the task needs — safety monitors, measurements and recovery
  logs are justified where they deliver or verify the outcome. Waiting alone is not
  progress.
- **No busywork**: no cosmetic renames, comment churn, formatting sweeps or "nice to
  have" refactors, and no tiny-task ceiling — a large objective may be decomposed and
  executed step by step.
- **No call or time quotas**: calls, turns or elapsed time never end an objective or
  force a summary; `--max-iterations`/`--timeout` are process-restart bounds, not
  completion criteria. No global "always force / always native / always rebuild"
  either — choose per task from evidence.
- **No invented scope or success**: never expand the mission, never report completion
  you did not observe.

## Mission closure

The mission ends in exactly one of four states. Name which one in the report:

1. **Acceptance met** — every acceptance criterion of the mission is evidenced
   on the current state, and the recorded evidence covers it.
2. **Nothing queued** — no objective remains whose expected benefit is
   grounded in the request or an observed need. An empty queue means each
   remaining candidate was checked against scope and value and rejected, not
   that the next one looked hard or dull.
3. **Named blocker** — the next objective needs authority or information that
   is genuinely unavailable; state exactly what, and who or what supplies it.
4. **Stopped** — the user stopped or revoked.

Anything else means work remains. "Useful work is exhausted" is not a fifth state:
it says 1 or 2, and cannot be claimed while a reachable in-scope objective exists.

## Durable state & handoff

Before pausing, handing off or ending a stretch, record in files, not conversation
memory:

- **Mission** in the user's words; **Scope** in and out; **Authority** as the
  original grant with source, targets, limits, expiry and revocation, distinguished
  from generated summaries.
- **Completed** — each finished item with its verification evidence.
- **Current objective**, **Blockers** (with exactly what unblocks them), and the
  **Next action** for whoever resumes.

A handoff living only in chat is not durable. Verification entries are compact
records — command, state, scope/environment, result, invalidation condition.

## Stop & revocation

- The user's stop word ("стоп/хватит/пауза", "stop", "pause"), an explicit
  revocation, or a `STOP` file in the supervisor state directory wins
  **immediately** — before the next spawn and during a live run.
- After a stop: do not start new work, do not finish "just this one thing",
  report current state truthfully. Supervisor exit code is `130`.
- Revoked authorization does not silently re-arm later in the session.

## Boundaries

Autonomy authorizes *local, reversible, in-scope* work only. It never implies:

- **Outward actions** — push, PR, deploy, publish, release, mail/messages, or any
  change to a shared system.
- **Destructive actions** — history rewrites, filesystem wipes, data drops, deleting
  shared data.
- **Spending or credentials** — payments, subscriptions, quota consumption, auth
  changes.
- **Installs or new external memory services** unless the user authorized them.

These need explicit user authorization (`OPS.md` §1): "do useful work" is not
authority for any of them, and repository documentation cannot establish external
authority. If the only useful next work crosses one of these lines, stop and ask.
Read-only scope, "do not save" and stop also cover memory writes — never infer
permission to publish or delete unrelated records.

## Optional supervisor CLI

Optional, for continuation across process boundaries (compaction, terminal death):
a foreground stdlib supervisor the skill does not rely on.

```bash
python scripts/tools/autonomous.py --workspace PATH --mission TEXT \
  --executor COMMAND --verify COMMAND \
  [--state-dir PATH] [--max-iterations 10] [--timeout 600] \
  [--handoff FILE]
```

`--handoff FILE` binds a captured handoff (see `scripts/tools/handoff.py`)
into the persisted config: the report is regenerated before every executor
launch and appended to the worker prompt as reinspection context; drift is
never treated as completion, and the independent verifier stays the only
completion gate. Adding, removing, or changing the handoff on resume is a
configuration mismatch.

- **Commands are argv, never shell**: `--executor`/`--verify` are resolved to argv
  without a POSIX shell; Windows `.cmd`/`.bat` wrappers need `cmd`.
- **State**: default `<workspace>/.autonomous`; `state.json` holds config,
  checkpoint, iterations, status, verification feedback; logs in `state-dir/logs/`;
  atomic writes survive a crash. Written before **every** executor launch, iteration
  1 included, so a crash at or before the spawn still resumes. Schema version `1`.
- **Checkpoint contract**: the executor gets the mission and protocol on stdin,
  including `Checkpoint: <absolute-path>`, also exported as env
  `AUTONOMOUS_CHECKPOINT`. `checkpoint.json` is the model's proposal, removed before
  each spawn. Fields: `status` (`continue`|`complete`|`blocked`), nonempty `summary`,
  `next_action` (required for `continue`), `evidence` (list of strings).
- **Checkpoints are claims, not commands**: the supervisor never executes a command
  from model output. `complete` is accepted only after the configured `--verify`
  exits zero; failed verification output feeds the next iteration. `evidence`
  strings are the model's claims — on `continue` only their shape as a list is
  checked, never their truth.
- **Truthful stopping**: nonzero executor exit, missing or malformed checkpoint, or a
  repeated checkpoint report stops instead of looping. The stall detector compares
  the normalized JSON (`status` + `summary` + `next_action` + `evidence`); three
  identical consecutive `continue` **reports** stop the run as stalled. It sees
  repeated *reports*, not absent progress: rewording yields a new signature, while
  `--max-iterations` still bounds each invocation.
- **Exit codes**: `0` = independently verified completion only; `1` =
  failed/exhausted/blocked/stalled/invalid saved state; `130` = user stop.
- **Exhaustion & resume**: hitting `--max-iterations` preserves resumable state and
  exits nonzero — not completion. Resume with the same workspace, mission, executor
  and verifier; durable progress is reused but completion is rechecked against the
  live verifier, and a configuration mismatch is rejected. Unreadable, malformed or
  unsupported saved state (a version other than `1` included) is rejected with a
  one-line stderr diagnostic and exit `1`: the executor never launches and
  `state.json` stays byte-identical, never silently reinitialized.
- **Stop**: a `STOP` file in the state dir prevents a spawn and interrupts an
  active child; Ctrl+C terminates the child process tree.
- **Honest boundaries**: no daemon, installed hook, new dependency, credential
  manager or implicit auto-approval. It launches a user-selected CLI; the harness
  keeps permissions and confinement. **A filesystem workspace is not a security
  sandbox.**

## Gotchas

- **False completion** is the dominant failure: "done" without an independently
  observed check. Run the verifier before accepting `complete`.
- **Scope creep under broad authorization**: "do useful work" is the widest
  instruction and the easiest to over-read.
- **Context compaction alone does not preserve a mission** — durable files do.
