---
name: brainstorming
description: 'Use before designing features, components, new subsystems, or behavior changes. Resolve intent, constraints, interfaces and acceptance before implementation; scale design depth to uncertainty without adding approval gates to authorized work.'
license: MIT
metadata:
  version: "4.5.1"
---

# Brainstorming Ideas Into Designs

Understand the requested outcome, inspect existing patterns, choose a complete
solution, and continue through implementation when that is what the user asked.
Authorization and stop conditions come from AGENTS.md, not the design phase.
A requested local auth, schema or dependency change needs risk-appropriate
checks, not redundant permission merely because of its category.

## Choose the necessary design depth

- **Investigation/spike:** answer a feasibility question with a bounded probe.
  Define what the probe measures, run it, report evidence and limitations.
  Do not silently turn a requested investigation into a permanent feature.
- **Bounded change:** trace the existing flow and affected callers, resolve
  details from code, state the approach briefly, implement and verify.
- **Architectural change:** map responsibilities, interfaces, state transitions,
  compatibility and failure handling before code. Decompose independent
  capabilities with explicit integration contracts; complete every requested
  capability, not only the first sub-project.

Complexity determines design depth, not permission. Reclassify when new facts
change the approach; no mandatory heavier-path tie-break or approval pause.
Plan/design-only requests stop at their requested deliverable.

## Design workflow

1. **Inspect context.** Read the relevant implementation, configuration and
   existing decisions. Reuse project conventions rather than adding a parallel
   design. Do not ask the user for repository-provided information.
2. **Define done.** Capture required behaviors, compatibility, constraints,
   excluded work and observable acceptance. A simpler implementation must still
   deliver all requested formats, paths, error behavior and quality.
3. **Resolve uncertainty.** Decide ordinary details from evidence and explain
   consequential defaults. Ask only when an unavailable answer would materially
   change the outcome or an action lacks authority. Batch related questions;
   continue independent authorized work when possible.
4. **Compare real alternatives.** Include alternatives only when they have
   meaningful tradeoffs. Prefer the simplest complete approach; do not invent
   options to fill a quota. Existing proven patterns may settle the decision.
5. **Design the change.** Cover components, data flow, errors, integration,
   migration and verification at the depth needed. Separate units by reason
   for change, keep concrete interfaces, avoid unrelated restructuring.
6. **Check the design.** Resolve contradictions, placeholders, missing required
   paths and uncertain boundaries. Map acceptance to checks before coding.
7. **Continue.** Use writing-plans for complex execution, then implement and
   verify without asking the user to approve the same authorized work again.

## Artifacts and review

Use chat or the task tracker for a short design. Write a durable design file
when requested or needed by an explicitly required project workflow; default
location is `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` when applicable.
A design file need not contain the entire implementation. Record enough for
another engineer to understand decisions, contracts and acceptance.

User review is a gate only when the user requested it or a real project
approval governs the action. Do not ask after every section, force spec-file
approval, or end with an execution-method menu when implementation is already
authorized. Commits follow AGENTS.md.

## Failure patterns

- New subsystem treated as new authorization: design thoroughly, then execute.
- Missing info guessed despite incompatible outcomes: inspect, then ask.
- Local security fix stalled solely because it touches auth: fix with isolated
  positive and negative checks; no production mutation implied.
- CSV-only shipped when CSV and JSON were requested: incomplete, not minimal.
- A procedural skill says stop: reconcile it with scope and authority; do not
  leave reachable implementation undone or ignore an explicit user stop.

---

Source: obra/superpowers (MIT). Adapted for coding-kit.
