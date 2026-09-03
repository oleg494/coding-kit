---
name: debug-incident-protocol
description: 'Use when the user says: «it doesn''t work», «still broken», «hung/stuck», «disappeared after the update», «it used to work», «the metric is zero but the UI is fine» — or when an incident needs to be analyzed, the root cause of a hang found, and whether a process was actually restarted verified. Covers: facts before theories (storage/logs/PID), symptom vs root cause, silent failure, restart ritual, localizing hangs with a progress marker, timeouts, cache masking. Do not use for writing tests (testing-discipline).'
license: MIT
compatibility: 'any stack: processes, logs, DB, network, tests'
metadata:
  version: "4.1.0"
---

# Debug & incident protocol: facts before theories

## 1. Core: facts, not opinions

1. **FACTS BEFORE THEORIES** — order: 1) config flags, 2) DB row, 3) log lines, 4) only then a code hypothesis. The first incident report contains a fact, not an opinion.
2. **SYMPTOM ≠ ROOT CAUSE** — «minutes are not deducted» is a symptom; silent except + wrong parser is the root cause. Trace the call path to the side effect; fix the root cause ONCE.
3. **IF METRIC FLAT WHILE FEATURE «WORKS» — SILENT FAILURE** — UX success + zero metric = swallowed error. Look for except/early return on the metric path.
4. **SINGLE CONSUMER FOR EXCLUSIVE STREAMS** — long-poll/queue/lock file — one owner. Kill duplicates before start; health = exactly one PID.
5. **RESTART RITUAL IS PART OF THE FIX** — code on disk ≠ code in memory. After the fix: stop all → start one → verify log. Check: PID creation time > edit time.
6. **ENCODING OF CONSOLE ≠ ENCODING OF PRODUCT** — mojibake in the console does not mean corrupted data. Check UTF-8 in the client/file.

## 2. Localizing hangs

1. **«It can't hang» — not an argument.** Anything can hang: a network without a timeout, an interactive prompt, an infinite loop.
2. **Localize with a progress marker** — the marker («=== stage N ===») is printed at the START of the block → hang is INSIDE the last block with a marker.
3. **Progress — to a FILE, not a pipe** — `cmd 2>&1 | Out-File prog.txt`; a pipe can hang or lose the tail.
4. **Isolate the suspect BEFORE the full run** — one block with a small timeout (30-60s), not the whole set with 900s.
5. **Chain A && B && C masks the hang location** — split stages: each command separately, its own timeout.
6. **First suspect — infrastructure, not logic** — BeforeAll/modules/network/interactivity is guilty more often than an «instant» test.
7. **Compare with the last successful run** — git diff: the culprit is usually in the changes.

## 3. Cache and «still broken»

- **Old cache looks like an unfixed bug** — first check that the server IS SERVING the fixed bytes (curl + grep of the fix marker line), then force the cache to die.
- **Foreign processes on the port** — a test instance on the port blocks the real launch → looks «broken».

## Workflow (order of application)

1. **Gather facts, not theories.** config flags → DB row → log lines → code hypothesis.
2. **Rule out cache and foreign processes.** curl the served bytes + grep the fix marker. Foreign process on the port?
3. **Separate symptom from root cause.** Trace the call path to the side effect; fix the root cause ONCE.
4. **Check processes.** One consumer. PID trace chain: ParentProcessId + CreationDate + CommandLine. PID older than the edit = process on old code → restart ritual.
5. **Localize the hang with a marker.** Marker at the start of the block. Progress to a FILE. Isolate with a small timeout.
6. **Fix + verification.** stop-all-then-start-one → check fresh log lines → smoke the scenario.

## Incident checklist

- [ ] fact: config flags → DB row → log lines (before hypotheses)
- [ ] symptom separated from root cause; root cause fixed once
- [ ] progress markers present; stages separated
- [ ] timeout on every suspect
- [ ] one consumer per exclusive stream; PID new (CreationDate > edit)
- [ ] log checked by fresh lines after restart
- [ ] cache ruled out (served bytes verified)
- [ ] conclusion: fact + root cause + one fix + smoke