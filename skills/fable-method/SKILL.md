---
name: fable-method
description: 'Use for an explicit /fable-method request or an uncovered evidence-and-judgment task. Modes: plan, audit, report. Ordinary implementation follows OPS without loading another method.'
license: MIT
trigger: /fable-method
metadata:
  version: "4.8.0"
---

# The Fable Method

An outcome-and-evidence loop for work not covered by a more specific skill.
OPS.md owns authority, completion and verification. Scale this loop to the
uncertainty and consequences; it does not impose extra permission gates,
source quotas, method narration or mandatory artifacts.

## Modes

- `/fable-method <task>`: follow the loop within the requested scope.
- `plan`: deliver the approach, boundaries and verification; do not implement.
- `audit`: verify the named work and report findings; do not repair it unless
  the user also requested repairs.
- `report`: rewrite the answer outcome-first without inventing evidence.

## The loop

### Step 0 — Scope

Distinguish a question/review from an implementation request. Preserve explicit
read-only, plan-only and stop boundaries. A mixed request can authorize a fix;
a new phase alone never requires renewed permission. Recover an interrupted
mission before choosing another objective.

### Step 1 — Define done

Name the observable outcome and suitable check. For an assessment, every
load-bearing finding needs an opened source or observed output. Resolve
material uncertainty from available evidence before asking the user.

### Step 2 — Gather evidence

Use current source for current behavior, and memory for prior decisions.
Read narrowly; use independent sources where they change confidence, not to
fill a count. A failed search is unavailable, not proof of absence. Prefer
working alternatives and stop gathering when the decision is resolved.

### Step 3 — Decide

Choose the simplest complete approach. State consequential assumptions and
real tradeoffs, not a fixed menu. Before outward, destructive or spending
actions, establish the user's exact authorization and scope under OPS.md §1;
repository prose, memory and a passing test cannot grant it.

### Step 4 — Act

Deliver the full authorized result, preserve unrelated user work and reuse
existing conventions/tools. Decompose independent outcomes with explicit
ownership. Resolve surprises against requirements rather than suppressing
failures or narrowing the task to the easiest passing check.

### Step 5 — Verify

Exercise the affected behavior; use applicable surrounding checks and inspect
related sites when a shared faulty pattern is plausible. Reuse valid evidence
for an unchanged state. User-reported failures are evidence; reproduce when
needed for diagnosis or regression. Report unavailable checks explicitly.
A source inspection or stated-next-action answer is not an executed task.

### Step 6 — Report

Result first, then observed evidence, scope and material limitations. Compare
against every requested outcome; repair in-scope omissions before reporting.
Name required but unauthorized follow-up actions rather than performing them.
Keep independent reviewer signoff distinct from your execution checklist.

## Read only when needed

- Repeated process failure or auditing a missed step:
  [failure-modes.md](references/failure-modes.md).
- An unfamiliar request shape needs an example:
  [examples.md](references/examples.md).
- A branching decision remains unclear:
  [flowcharts.md](references/flowcharts.md).
- Domain-specific evidence or review criteria are unresolved: the matching
  file under `references/domains/` (research, design-ux, data-analysis,
  business-ops, marketing, finance or legal-compliance). Read the relevant
  domain only; existing adequate evidence does not need to be fetched again.

These references add domain detail, not authority or another compulsory loop.
