---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
license: MIT
metadata:
  version: "4.6.0"
---

# Writing Plans

Write enough of a plan to execute the complete request without rediscovering
scope or inventing interfaces. Planning is part of authorized implementation,
not a separate approval transaction. Plan-only requests remain plan-only.

## Scope and structure

- Start from the actual requirements or existing spec; identify what done means.
- Inspect project conventions and affected paths before naming changes.
- Split by independently testable outcomes, not file counts, elapsed time or
  individual tool calls. Include setup, docs and failure paths in the task
  whose deliverable needs them.
- State dependencies and exact shared interfaces before parallel execution.
  Keep related changes together; no unrelated refactoring.
- Define behavior checks before implementation. Bug fixes need a failing
  reproduction; do not prescribe tests that assert source text or wiring.

## Plan content

A useful plan contains:

1. **Goal and boundaries:** full requested outcome, exclusions, constraints.
2. **Approach:** existing patterns reused, important decisions and risks.
3. **Changes:** exact files/symbols and required behavioral changes, ordered by
   dependency. Include caller migration and obsolete-path removal when needed.
4. **Contracts:** inputs, outputs, failure behavior and cross-task interfaces.
5. **Verification:** scenario/command, observable expected result and isolation.

Use the task tracker or chat when sufficient. Create a plan file only when
requested or required by an applicable project workflow; the default location
then is `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`. Link the existing
spec rather than copying it. A fixed header, code for every line, or a commit
step per task is not required. Commits follow AGENTS.md.

## Self-review

Compare every requirement with its implementation task and check. Add missing
paths; resolve contradictory signatures and platform requirements. Steps such
as "handle errors" without named failure behavior are incomplete. The plan
must be actionable, but should not duplicate the entire future implementation.

## Execute

When implementation is authorized, choose inline execution by default; use
parallel workers for genuinely independent ownership when available and useful.
Do not ask the user to choose an execution method or approve the completed plan
again. If a worker cannot run, continue locally where possible rather than
making worker setup a new prerequisite. Verify integrated behavior before the
final report; an increment or checklist update is not the deliverable.

When only a plan was requested, deliver the plan and do not implement.

---

Source: obra/superpowers (MIT). Adapted for coding-kit.
