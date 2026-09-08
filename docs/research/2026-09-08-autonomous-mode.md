# Autonomous mode — coding-kit 4.5

## Goal and acceptance

The user explicitly requested autonomous work selection and continuation, research into existing approaches, and a 4.5 release. Autonomy is opt-in: a broad instruction to choose useful work activates it without demanding a manufactured task from the user. Ordinary bounded requests keep their existing scope.

An autonomous agent chooses evidence-backed useful work, completes and verifies it, then continues to the next useful objective without requiring another user message. It preserves a durable mission, scope, completed evidence, current objective, blockers, and next action before a handoff. User stop/revocation wins immediately. No arbitrary tiny-task ceiling, cosmetic busywork, invented success, or implicit permission to publish/delete/spend.

## Decision

Ship a portable `autonomous-work` skill, routing in the existing contract/runtime, adversarial scenarios, and an optional foreground stdlib supervisor (`scripts/tools/autonomous.py`). No daemon, installed hook, new dependency, credential manager, or implicit auto-approval. The supervisor launches a user-selected existing CLI; the harness remains responsible for permissions and confinement. A filesystem workspace is not a security sandbox.

Alternatives: prompt-only is portable but cannot restart a terminated process; a resident scheduler would provide unattended wakeups but adds an unrequested service and platform-specific lifecycle. The foreground supervisor supplies explicit cross-process continuation without changing default installation behavior.

## Supervisor interface

`python scripts/tools/autonomous.py --workspace PATH --mission TEXT --executor COMMAND --verify COMMAND [--state-dir PATH] [--max-iterations 10] [--timeout 600]`

Commands are explicitly user-configured command strings resolved into argv, never interpreted with a POSIX shell; Windows `.cmd`/`.bat` wrappers require cmd. The executor receives the mission and protocol on stdin, runs in workspace, and writes the checkpoint JSON path supplied in that prompt. Checkpoint fields: `status` (`continue`, `complete`, `blocked`), nonempty `summary`, `next_action` (required for continue), and `evidence` (list of strings). Checkpoints are untrusted claims, not commands. The supervisor never executes a command found in model output.

A complete claim is accepted only after the independently configured verification command exits zero. Failed verification feeds the output into the next iteration. A `continue` checkpoint's `evidence` strings are the model's own claims: they are only shape-checked (list of strings) and are never independently verified inside the loop. Nonzero executor exit, missing/malformed checkpoint, or a repeated checkpoint report stops truthfully rather than launching an error loop. The stall detector compares the normalized checkpoint JSON (`status` + `summary` + `next_action` + `evidence`); three identical consecutive `continue` reports count as stalled. It detects repeated *reports*, not absence of task progress: reworded text with no real progress produces a new signature and evades it, while `--max-iterations` still bounds each invocation. Iteration exhaustion preserves resumable state and exits nonzero; it is not completion. Resume with the same workspace, mission, executor, and verifier reuses durable progress but rechecks completion against the live verifier. Reject configuration mismatch. Unreadable, malformed, or unsupported saved state (including a version other than `1`) is rejected with a one-line stderr diagnostic and exit `1`, before any executor launch, leaving the existing `state.json` byte-identical — never silently reinitialized or overwritten. A STOP file in state-dir prevents a spawn and interrupts an active child; Ctrl+C also terminates the child process tree. Logs and atomic JSON state persist outside conversational context, and state is written before every executor launch (including iteration 1 of a fresh run), so a crash at or before the spawn still leaves resumable state. No automatic commit, push, rollback of user edits, or permission escalation.

## Verification plan

Subprocess integration tests use a temporary workspace and deterministic Python executors, never production state. Prove continuation after false completion, resume after an iteration limit, rejection of malformed/missing/unsupported saved state without overwriting it, executor failure, configuration mismatch, stop before launch and during execution, and termination on identical repeated `continue` reports. Note that the stall check detects repeated identical reports, not actual absence of progress: it is a loop breaker, while `--max-iterations` bounds each invocation. Run the actual CLI with a real model on a disposable two-step task and an independently written verifier. A bounded smoke is evidence for the exercised paths, not a claim of indefinite reliability or cross-harness compatibility.

Portable behavior scenarios cover broad task selection, continuing after a verified result, stop/revocation, stale handoff, and a blocked external action with useful local work remaining. Compare observed tool actions, not promises in prose.

## Primary sources

- Anthropic, [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents): durable feature/progress artifacts, incremental execution, real end-to-end verification; context compaction alone did not prevent false completion.
- OpenAI, [Using PLANS.md for multi-hour problem solving](https://developers.openai.com/cookbook/articles/codex_exec_plans): self-contained living plans, continued milestone execution without asking for next steps, observable acceptance and handoff evidence.

These sources support the architecture, not a guarantee of autonomous correctness. Recommendations from research agents are treated as secondary data; automatic commits and unconditional revert-on-failure are deliberately not adopted.

## Observed verification (2026-09-08)

- Real executor: `custom-openai/deepseek-v4.1-flash-expires-on-0910` through OMP. Disposable workspace: `C:/Users/oleg2/AppData/Local/Temp/coding-kit-autonomy-b3v8qc14/workspace`.
- Independent verifier failed before changes. Invocation 1 fixed clamp bounds and returned continue; invocation 2 consumed the handoff and fixed inclusive range parsing. Supervisor exited 0 at iteration 2; verifier output: `PASS: clamp boundaries and inclusive range`.
- One defect per invocation was an explicit handoff experiment condition, not an autonomy policy. This demonstrates bounded cross-process continuation, not indefinite reliability.
- STOP with a non-reading child and large stdin reproduced a hang before the fix. The retained regression passes with writer-owned stdin and immediate parent-side cancellation polling.
- Full regression run: 744 passed, 2 skipped, 87 subtests passed; one release-stamp failure exposed unstamped existing skills. After stamping the corpus, the lifecycle and supervisor suites passed together: 22 tests. Other passing tests were not invalidated by metadata-only stamps. The supervisor suite later grew to 37 tests when the state owner added pre-spawn durability, resume-progress, and 19-case corrupt-state rejection coverage; that file passed 37/37 after the state validation landed.
- Scenario runner dry-run parsed all 31 scenarios; it did not evaluate model behavior on the five new portable scenarios.
- Local deployment installed 37 skills and regenerated managed routers. No push, public release, daemon, or automatic background mission was started by installation.

### Autonomous task-selection experiment (2026-09-08)

- Mission deliberately withheld the choice: "choose and complete the most useful evidence-backed local improvement… Avoid cosmetic churn and speculative architecture." The disposable workspace offered three backlog items: a customer-reported CSV export corruption (fields with commas/quotes split into extra columns), a cosmetic function rename, and a speculative plugin-based export framework.
- Real executor `custom-openai/deepseek-v4.1-flash-expires-on-0910` via OMP supervisor exited `0` after one iteration in ~40 s. The independently authored verifier was outside the workspace, but not access-isolated: the worker found and ran it. It failed before the change and passed after it; Main reran it independently: `PASS: CSV round-trip preserves commas, quotes, newlines, empty fields`.
- The model selected the CSV defect and implemented it with stdlib `csv.writer`, preserving the supplied fixtures and rejecting the rename and framework. No API rename or framework was introduced. The exercised CSV cases cover commas, quotes, embedded LF newlines and empty fields; this is not a complete RFC 4180 conformance test.
- Artifacts: `C:/Users/oleg2/AppData/Local/Temp/autonomy-selection-kdruljbk/workspace` (`export.py`, `.autonomous/checkpoint.json`, `state.json`, `logs/`) and external `verify.py`.
- Scope of evidence: a single trial under one mission and one workspace. It demonstrates that this selection happened once with an independently verified outcome; it is **not** a reliability rate, not evidence that the model always prefers the real defect, and not a claim about other harnesses. The experiment also ran on the **pre-fix** runner because the state owner was still editing `scripts/tools/autonomous.py`; the final runner is regression-tested separately by its owner.

- Final integrated verification: `python -m pytest tests/test_autonomous.py tests/test_skill_lifecycle.py -q --tb=short` — 45 passed. A separate real subprocess smoke read current durable state before completing; unsupported float version and empty continuation handoff were rejected without traceback or state mutation. Repository integrity verified 152 files; repository canonical skill copy synchronized. User-level installed skill copies were intentionally not redeployed.
