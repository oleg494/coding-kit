---
name: systematic-debugging
description: 'Use when something fails or behaves unexpectedly: a bug, a failing test or build, a hung or stale process, a service that broke after an update or restart, a zero metric on a feature that looks fine, or "it used to work". Covers root-cause investigation before fixes, boundary evidence and runtime incidents. Not for writing the regression test (use testing-discipline) or the closing claim (use verification-before-completion).'
license: MIT
metadata:
  version: "6.0.0"
---

# systematic-debugging

Find the cause before changing behavior. A fix that only silences the symptom comes back, usually with a sibling.

## When this applies

Code-level failures — bugs, test failures, build failures, unexpected values, performance regressions, integration breaks — and runtime incidents: a hung or stale process, a zero metric on a feature users call working, a regression after an update or restart, a service that was fine yesterday.

It applies most when a fix looks obvious, when you are in a hurry, when an earlier fix did not stick, or when you still do not understand the issue. "Simple" bugs have root causes too, and guessing costs more than reading.

Do not change code to see what happens. Investigate until a cause is named, then change it.

## Proportionality

Match depth to the failure. A typo, a renamed symbol, or a failure whose stack trace names the exact argument needs a look at the cited location and a recheck, not the full sequence below. A failure with unknown cause, an intermittent or data-affecting symptom, a money path, or a second failed attempt earns the full investigation. When you take the short path, say what you ruled in and how you checked it.

## Phase 1: root cause investigation

- **Read the error completely.** Stack traces, line numbers, paths, error codes, the wording of warnings. They frequently contain the answer that makes guessing unnecessary.
- **Reproduce consistently.** What are the exact steps, how often, under what conditions? A user-reported failure is ground truth for the symptom; reproduce locally when diagnosis needs it, when building a regression check, or when the report alone cannot localize the fault. Not reproducible with the evidence at hand → gather more data and name what is unavailable instead of assuming the report is wrong.
- **Check recent changes.** `git diff`, recent commits, new dependencies, config edits, environment differences — the cause usually sits in what changed.
- **In multi-component systems, observe the boundaries.** When the path crosses layers (CI → build → signing, API → service → database), log what enters and exits each boundary and what environment each layer sees, run once to learn *where* the break is, then investigate that component. Example: separately probe whether the secret is visible in the workflow, whether the build script's environment has it, and what the signing tool reports — the first layer that loses a value is the one to inspect.
- **Trace data flow backward.** When the failure is deep, walk up the call chain: where did the bad value originate, what passed it on, and from where. Fix at the source, not where the bad value surfaced.

## Phase 2: pattern analysis

- Find a similar place that works in the same codebase and compare them.
- When applying an existing pattern, read the reference implementation completely rather than adapting from a skim; partial understanding reproduces the bug you are fixing.
- List every difference between working and broken, including ones that "cannot matter".
- List the dependencies the code needs: settings, config, environment, assumptions about callers.

## Phase 3: hypothesis and testing

- State one specific hypothesis: "X is the cause because Y". Write it down; vague ideas cannot be refuted.
- Test it minimally — one variable, the smallest change that distinguishes the hypothesis from its alternative, with a bounded run.
- Verify before continuing. Confirmed → Phase 4. Not confirmed → form a new hypothesis; do not stack another fix on the unconfirmed one.
- When you do not know, say so and gather the missing evidence. Ask the user only for what tools cannot obtain: access, intent, business rules, or a decision.

## Phase 4: implementation

- **Establish failure evidence** — an existing check, an isolated probe, or the user's report; see testing-discipline for designing the regression test and OPS §3 for reuse. State what before-fix evidence is unavailable.
- **One fix for the named cause.** No "while I'm here" improvements, no bundled refactoring.
- **Verify the fix and its neighborhood.** The original symptom is gone, adjacent behavior still works, applicable checks pass.
- **Sweep for the same pattern.** Once the cause is understood, search for the same faulty shape elsewhere — the same parser, the same missing timeout, the same swallowed exception. Fix what plausibly recurs; mention the rest.
- **If the fix fails**, return to investigation with the new evidence. Repeated failures change the hypothesis or the scope, not the retry count.
- **If evidence points at architecture** — shared-state coupling, a repair that needs broad refactoring, a new symptom at every boundary — investigate that before adding another patch; several failed patches alone do not prove it. Ask only if the repair needs authority beyond the task or carries an unresolved product tradeoff.

## Runtime and process incidents

Incidents usually provide plenty of facts and little interpretation. Collect facts first, then form one theory.

- **Order evidence by directness.** For a data-driven service the cheap facts are the config flags, the database row, the log lines — and only then a code hypothesis. That order is an example, not a ritual: start where the fault most likely lives, and prefer reading the actual state over reasoning about it.
- **Symptom ≠ cause.** "Minutes are not deducted" is a symptom; a silently swallowed exception plus a wrong parser is the cause. Trace the call path to the side effect and fix the cause once.
- **Zero metric on a "working" feature is a silent failure.** UX success plus a flat metric means the write path never happened: look for an `except` or an early return on the metric path.
- **One consumer per exclusive stream.** Long-poll, queue, or lock file: duplicates split or steal events. Health is exactly one process for the stream; stop duplicates only when this task started them or the user named them.
- **Restart ritual after any fix.** Code on disk is not code in memory. Stop every instance this task owns (or the user named), start one, and read the fresh log lines. A cheap check is process creation time against the edit time; an older process is running the old code.
- **Serving versus caching.** "Still broken" often means the server never served the fixed bytes. Fetch the served output and look for the fix marker before hunting the bug again, and rule out a foreign process on the port — an old test instance there looks exactly like a broken build.
- **Console encoding is not product encoding.** Mojibake on the terminal does not mean stored data is corrupted; check the encoding of the real artifact.

### Localizing a hang

- "It cannot hang" is not an argument. A network call without a timeout, an interactive prompt, and an infinite loop all hang.
- Mark each stage at its start and write progress to a file, not down a pipe that can stall or truncate the tail. The hang is inside the last stage whose marker appeared.
- Isolate the suspect stage with a short timeout (tens of seconds) instead of rerunning the whole sequence at a long one.
- Split `A && B && C`: a chain hides which stage stalled.
- Suspect infrastructure before logic — setup hooks, module loading, network, interactivity fail more often than the "instant" step.
- Compare against the last successful run; the culprit is usually in the diff since then.

### Scope discipline

Read-only or review-only work means diagnose and report. Read logs, configs, process state and served bytes, but do not add instrumentation, caches or log files to the tree; describe the instrumentation you would add instead. A local implementation task may add temporary probes, and should remove them before finishing.

Stop, restart or kill only processes this task started or that the user explicitly named. Another instance's process is user data: report what you see and ask.

## Red flags

You are guessing rather than debugging when you catch yourself:

- proposing a fix before tracing how the bad value got there
- "quick fix now, investigate later", or "just try changing X and see"
- changing several things at once, so no result can be attributed
- assuming "it is probably X" without evidence that distinguishes X from Y
- adapting a reference pattern without reading it
- listing fixes instead of causes
- repeating a fix that already failed, with nothing new learned
- watching each fix expose a new problem somewhere else

Any of these means return to Phase 1.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, no process needed" | Simple issues have causes too, and the process is fast for them |
| "Emergency, no time for process" | Reading the error costs less than a round of failed patches |
| "Just try this first, then investigate" | The first guess sets the pattern; start with evidence |
| "I'll write the test after confirming the fix" | Untested fixes do not stick; the failing check is how the fix is confirmed |
| "Multiple fixes at once saves time" | Nothing can be attributed, and new bugs hide among them |
| "Reference is long, I'll adapt it" | Partial understanding reproduces the bug; read it completely |
| "I see the problem, let me fix it" | Seeing the symptom is not knowing the cause |
| "One more attempt" with no new evidence | A new trace or probe justifies a bounded retry; a retry count does not |
| "It worked before the update, so the update broke it" | A stale process or a cache explains it just as often; verify what is running and served |
| "The metric is just delayed" | A working UX with a flat metric is usually a swallowed error; check the write path |
| "A restart will clear it" | A restart without a cause hides the leak and it returns; use it to test a hypothesis, not to close one |

## Triage shortcuts

**Test failure after a code change** — did you touch code it covers? Then decide whether test or code is wrong. Touched unrelated code? Look at shared state, imports, globals, order dependence. Already flaky? Check timing and isolation.

**Build failure** — type error: read the cited location and its types. Import error: module exists, exports match, paths correct. Config error: the build config files. Dependency error: the manifest, then install. Environment error: tool version, OS.

**Runtime incident** — fresh or stale process? Served bytes current? One consumer? Then symptom → metric/log path → call chain.

## When the cause is genuinely external

If investigation shows the trigger is environmental, timing-dependent, or outside the repository, the investigation is complete: document what you checked and which hypotheses were ruled out, then handle it (retry with a bound, timeout, clearer error) and add the logging or monitoring that makes the next occurrence diagnosable. Before concluding "no root cause", name the hypotheses you tested and the evidence still unavailable — missing evidence is not proof of absence.

## Supporting techniques

- **Condition-based waiting** — wait for an observable condition with a bounded timeout; prefer native events over arbitrary sleeps or unbounded polling.
- **Defense in depth** — add boundary validation only where the demonstrated failure can still enter; do not harden unrelated layers.

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: cross-references made local.