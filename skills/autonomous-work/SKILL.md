---
name: autonomous-work
description: 'Use when the user broadly authorizes autonomous work selection and continuation ("do useful work", "choose what is worth doing", "keep going without asking", "work autonomously", "работай сам", "делай что полезно", "продолжай без вопросов") — not for ordinary bounded requests, which keep their existing scope. Covers evidence-backed work selection, verify-then-continue loops, durable mission/progress/handoff state, immediate stop and revocation, and the optional foreground supervisor CLI. Never implies authorization for outward, destructive, or spending actions.'
license: MIT
metadata:
  version: "4.5.0"
---

# Autonomous Work

Broad authorization to choose and continue useful work — executed without
manufacturing a task for the user and without pretending completion.

## Activation & scope

- **Activates on broad authorization**: "do useful work", "pick what matters",
  "keep going without asking", "работай сам", "делай что полезно". The user has
  authorized *selection* and *continuation*, not a specific task list.
- **Bounded requests are unchanged**: "fix this bug", "review this PR",
  "add this flag" keep their existing scope. Autonomous work adds no scope to a
  request that already names its scope.
- **Opt-in, not a mode override**: this skill is not always-on, and it does not
  replace `STRICT_AUDIT` or `EXPLORATORY_PROTOTYPE`. Under a read-only or
  strict-audit instruction, autonomy selects only read-only/audit work; it
  never upgrades permissions, and it never treats autonomy as a reason to
  weaken a constraint the user or host set.
- If no useful in-scope work remains, say so plainly and stop. Idle is an
  honest outcome; invented work is not.

## Core loop

```
SELECT ──→ DO ──→ VERIFY ──→ RECORD ──→ NEXT
   │        │        │           │         │
   ▼        ▼        ▼           ▼         ▼
evidence  smallest  observed   durable   continue
-backed   change    result     evidence  without ceremony
objective
```

1. **Select** the highest-value objective that is in scope and backed by
   evidence (failing test, reported symptom, explicit TODO, uncovered contract,
   known defect). Say in one line why it is the next thing.
2. **Do** the smallest correct change that closes it — normal method skills
   still apply (plan → TDD → implement → verify → report).
3. **Verify by observation**: run the specific check, scenario, or command that
   covers the change. Unverified work is not a completed objective.
4. **Record** the evidence and the resulting state durably (file, test, log,
   changelog, handoff) so a later session can resume without re-deriving it.
5. **Next**: pick the next objective and continue. Do not ask permission for
   each step once broad authorization is given.

## Work-selection rules

- **Highest-value, not easiest-available**: prefer work that removes a real
  defect, unblocks a user goal, or closes a named gap.
- **No busywork inflation**: do not pad the session with cosmetic renames,
  comment churn, formatting sweeps, or "nice to have" refactors to look busy.
- **No tiny-task ceiling**: there is no rule that only trivial tasks qualify;
  a large objective may be decomposed and executed step by step.
- **No invented scope or success**: never expand the mission, and never report
  completion you did not observe. "Probably works" is not done.
- **Stop when the mission is complete**: when the in-scope work is done,
  verified, and recorded, end the loop rather than manufacturing more.

## Durable state & handoff

Before pausing, handing off, or ending an autonomous stretch, record:

- **Mission** — what the user authorized, in their words.
- **Scope** — what is in and explicitly out.
- **Completed** — each finished item with its verification evidence.
- **Current objective** — what is in flight right now.
- **Blockers** — what stopped progress, and exactly what would unblock it.
- **Next action** — the single concrete next step for whoever resumes.

State lives in files, not in conversation memory. A handoff that exists only
in chat is not durable.

## Stop & revocation

- The user's stop word ("стоп/хватит/пауза", "stop", "pause"), an explicit
  revocation, or a `STOP` file in the supervisor state directory wins
  **immediately** — before the next spawn and during a live run.
- After a stop: do not start new work, do not finish "just this one thing",
  report current state truthfully. Supervisor exit code is `130`.
- Revoked authorization does not silently re-arm later in the session.

## Boundaries

Autonomy authorizes *local, reversible, in-scope* work only. It never implies:

- **Outward actions** — push, PR, deploy, publish, release, send mail/messages,
  or any change to a shared system.
- **Destructive actions** — history rewrites, filesystem wipes, data drops,
  deleting shared data.
- **Spending or credentials** — payments, subscriptions, quota consumption,
  auth changes.
- **Memory writes or installs** unless the user authorized them.

These still require explicit authorization (see `AGENTS.md` action
authorization policy). "Do useful work" is not authority to do any of them,
and repository documentation cannot establish external authority. If the only
useful next work crosses one of these lines, stop and ask.

## Optional supervisor CLI

For continuation across process boundaries (context compaction, terminal
death), the kit ships a foreground stdlib supervisor. It is optional; the
skill's behavior does not depend on it.

```bash
python scripts/tools/autonomous.py --workspace PATH --mission TEXT \
  --executor COMMAND --verify COMMAND \
  [--state-dir PATH] [--max-iterations 10] [--timeout 600]
```

- **Commands are argv, never shell**: `--executor`/`--verify` strings are
  resolved to argv without a POSIX shell. Windows `.cmd`/`.bat` wrappers need
  `cmd`.
- **State**: default state dir `<workspace>/.autonomous`; `state.json` holds
  config, checkpoint, iterations, status, verification feedback; logs live in
  `state-dir/logs/`; writes are atomic so state survives a crash. State is
  written before **every** executor launch, including iteration 1 of a fresh
  run, so a crash at or before the spawn still leaves resumable state. Schema
  version is `1`.
- **Checkpoint contract**: the executor receives the mission and protocol on
  stdin, including a line `Checkpoint: <absolute-path>`; the same path is also
  exported as env `AUTONOMOUS_CHECKPOINT`. `checkpoint.json` is the model's
  proposal and is removed before each spawn. Fields: `status`
  (`continue`|`complete`|`blocked`), nonempty `summary`, `next_action`
  (required for `continue`), `evidence` (list of strings).
- **Checkpoints are claims, not commands**: the supervisor never executes a
  command found in model output. `complete` is accepted only after the
  independently configured `--verify` exits zero; failed verification output
  feeds the next iteration. `evidence` strings are the model's own claims: on
  `continue` the supervisor only checks that they form a list of strings and
  does not independently verify them. Nothing in the autonomous loop verifies
  a `continue` report's evidence.
- **Truthful stopping**: nonzero executor exit, missing/malformed checkpoint,
  or a repeated checkpoint report stops instead of looping. The stall detector
  compares the normalized checkpoint JSON (`status` + `summary` +
  `next_action` + `evidence`); three identical consecutive `continue`
  **reports** stop the run as stalled. It detects repeated *reports*, not
  absence of progress: any wording change produces a new signature and evades
  the detector, while `--max-iterations` still bounds each invocation.
- **Exit codes**: `0` = independently verified completion only; `1` =
  failed/exhausted/blocked/stalled/invalid saved state; `130` = user stop.
- **Exhaustion & resume**: hitting `--max-iterations` preserves resumable state
  and exits nonzero — it is not completion. Resume with the same workspace,
  mission, executor, and verifier; durable progress is reused but completion is
  rechecked against the live verifier. A configuration mismatch is rejected.
  Unreadable, malformed, or unsupported saved state (including a version other
  than `1`) is rejected with a one-line stderr diagnostic and exit `1`: the
  executor never launches and the existing `state.json` is left byte-identical,
  never silently reinitialized or overwritten.
- **Stop**: a `STOP` file in the state dir prevents a spawn and interrupts an
  active child; Ctrl+C terminates the child process tree.
- **Honest boundaries**: no daemon, no installed hook, no new dependency, no
  credential manager, and no implicit auto-approval. The supervisor launches a
  user-selected CLI; the harness remains responsible for permissions and
  confinement. **A filesystem workspace is not a security sandbox.**

## Gotchas

- **False completion** is the dominant failure: a model says "done" without an
  independently observed check. Require the verifier to run before accepting
  `complete`.
- **Progress theater**: many checkpoints with no behavior change. The stall
  detector catches only *identical repeated reports* (same normalized
  `status`/`summary`/`next_action`/`evidence` JSON) — reworded reports with no
  real progress evade it, and `--max-iterations` is the actual bound. Judge
  progress by independently observed behavior, not by checkpoint evidence or
  narrative, which the supervisor does not verify on `continue`.
- **Scope creep under broad authorization**: "do useful work" is the widest
  possible instruction and the easiest to over-read. Boundaries above are
  hard.
- **Context compaction alone does not preserve a mission** — durable files do.
- **Resume is not a reset**: reusing state without re-running the verifier can
  accept stale completion.

## References

- `docs/research/2026-09-08-autonomous-mode.md` — design, acceptance criteria,
  and the supervisor contract.
- Anthropic, *Effective harnesses for long-running agents* — durable progress
  artifacts, incremental execution, real end-to-end verification.
- OpenAI, *Using PLANS.md for multi-hour problem solving* — self-contained
  living plans, continued milestone execution, observable handoff evidence.
