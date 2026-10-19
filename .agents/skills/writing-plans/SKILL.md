---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
license: MIT
metadata:
  version: "4.10.3"
---

# Writing Plans

Write enough of a plan to execute the complete request without rediscovering
scope or inventing interfaces. Planning is part of authorized implementation,
not a separate approval transaction. Plan-only requests remain plan-only.

The plan is the set of decisions an implementer cannot make alone: what done
means, which files and symbols, which interfaces cross task boundaries, which
checks prove each outcome. Everything a competent implementer derives from the
codebase stays out. If implementation bodies dominate, replace them with
signatures and checks. Lines that decide nothing ("handle edge cases", "add
appropriate validation") are the opposite failure.

## Scope and structure

- Start from the actual requirements or existing spec; identify what done means.
- Inspect project conventions and affected paths before naming changes.
- Split by independently testable outcomes, not file counts, elapsed time or
  individual tool calls. Fold setup, configuration, scaffolding and
  documentation into the task whose deliverable needs them; split only where
  a whole outcome is separately rejectable. Include failure paths in the task
  whose deliverable needs them.
- State dependencies and exact shared interfaces before parallel execution.
  Keep related changes together; no unrelated refactoring.
- Define behavior checks before implementation. Bug fixes need a failing
  reproduction; do not prescribe tests that assert source text or wiring.

## Plan content

A useful plan contains:

1. **Goal and boundaries:** full requested outcome, exclusions, constraints.
2. **Approach:** existing patterns reused, important decisions and risks.
3. **Global constraints:** project-wide requirements from the spec or user —
   version floors, dependency limits, naming or copy rules, platform
   requirements — one line each with exact values, verbatim. Every task
   implicitly includes this section; do not restate it per task.
4. **Changes:** exact files/symbols and required behavioral changes, ordered by
   dependency. Include caller migration and obsolete-path removal when needed.
5. **Per-task contracts:** for each task, inputs/outputs/failure behavior and
   the interfaces it **consumes** from earlier tasks and **produces** for later
   ones — exact names, signatures and value shapes. A worker who sees only
   their own task learns neighboring names from these blocks, not from the
   other tasks' bodies.
6. **Review focus:** boundary and failure inputs the spec implies but no task's
   checks exercise — empty/oversized/malformed input, the "impossible" state
   a caller can still build, platform or locale edge — one line each, most
   likely to bite a real user first. Each line names the input, the behavior
   a reasonable person would expect, and the task that owns the code; the
   check is added to that owning task. An empty section means you checked and
   found none, not that you skipped the check.
7. **Verification:** scenario/command, observable expected result and isolation.

Steps should be decisions, not transcripts: a code step carries the exact
signature, file location and the spec-pinned values; a function body appears
only for an algorithm the signature and checks do not determine. A check step
carries the command and the output that means it passed.

Use the task tracker or chat when sufficient. Create a plan file only when
requested or required by an applicable project workflow; the default location
then is `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`. Link the existing
spec rather than copying it. A fixed header, code for every line, or a commit
step per task is not required. Commits follow OPS.md §1.

## Self-review

Compare every requirement with its implementation task and check. Add missing
paths; resolve contradictory signatures and platform requirements; confirm
per-task Produces/Consumes blocks agree — a function named `clearLayers()` in
task 3 but `clearFullLayers()` in task 7 is a bug. Steps such as "handle
errors" without named failure behavior are incomplete. Cover the Review Focus
lines with checks in their owning tasks. The plan must be actionable, but
should not duplicate the entire future implementation.

## Execute

Honor the user's execution strategy and the host's delegation rules. Otherwise
choose from the work's shape: inline by default; parallel workers for genuinely
independent ownership when available and useful. Scale review to risk, not one
reviewer per task by rule. Do not ask the user to choose again or reapprove
the same authorized work.
If a worker cannot run, continue locally where possible rather than making
worker setup a new prerequisite. Verify integrated behavior before the final
report; an increment or checklist update is not the deliverable.

While executing, settle minor reversible implementation ambiguities from the
user's intent, spec and current code. Record consequential deviations and why
in the existing task/handoff record, then continue; no second tracking system
or fixed wording is required. Do not rule over an outcome-changing choice,
expand scope, or grant missing authority. Ask only for the unavailable user
decision that actually blocks the affected work.

When only a plan was requested, deliver the plan and do not implement.

---

Source: obra/superpowers (MIT). Adapted for coding-kit.
