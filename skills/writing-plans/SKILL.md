---
name: writing-plans
description: 'Use when specified work needs an execution plan or hits a plan defect mid-execution: coupled or multi-slice changes, work split across agents, several independently landable outcomes, or a plan that disagrees with what a slice already shipped. Not for deciding what to build (use brainstorming); not for a single small change.'
license: MIT
metadata:
  version: "6.0.0"
---

# Writing Plans

This skill decides *how* to execute work whose shape is already known: order,
slice boundaries, ownership, interfaces that cross a boundary, and the check
that closes each slice. What to build and why lives in `brainstorming`; a
spec or the user's stated acceptance criteria is the input here.

Write enough of a plan that an implementer can execute the complete request
without rediscovering scope or inventing interfaces. Planning is part of
authorized implementation, not a separate approval transaction. Plan-only
requests remain plan-only.

The plan is the set of decisions an implementer cannot make alone: which files
and symbols change, which checks prove each outcome, and — when work is split
or delegated — which interfaces cross a boundary. Everything a competent
implementer derives from the codebase stays out. If implementation bodies
dominate, replace them with signatures and checks. Lines that decide nothing
("handle edge cases", "add appropriate validation") are the opposite failure.

## Scope and structure

- Start from the requirements or spec; identify what done means for each slice.
- Inspect project conventions and affected paths before naming changes.
- Split by independently verifiable outcomes, not file counts, elapsed time or
  tool calls. That is what "one logical thing" means here: after the slice, a
  stated behavior is verifiably done, and the rest of the request is still
  reachable. A slice that only moves code leaves nothing to verify.
- Fold setup, configuration, scaffolding and documentation into the slice
  whose deliverable needs them; split only where a whole outcome is separately
  rejectable. Include failure paths in the slice whose deliverable needs them.
- State dependencies, and the exact shared interfaces that actually cross a
  boundary, before parallel execution. Keep related changes together; no
  unrelated refactoring.
- Define behavior checks before implementation. For bugs, use applicable
  failure evidence or reproduce when needed; do not prescribe tests that
  assert source text or wiring. Report unavailable reproduction honestly.

## Slicing patterns

**Vertical:** one complete path through the stack beats a whole layer half-done.

```
Slice 1: Create (DB + API + UI) → a user can create
Slice 2: List (query + API + UI) → a user can see
Slice 3: Edit (update + API + UI) → a user can modify
```

**Contract-first:** when two sides are developed in parallel.

```
Slice 0: define the contract (types, signatures, error shapes)
Slice 1a / 1b: each side implements against the contract
Slice 2: integrate the real halves and verify end-to-end
```

**Risk-first:** do the piece most likely to fail first, so a wrong assumption
costs one slice instead of the whole plan.

## Plan content

A plan carries the sections that decide something; a section with nothing to
decide is omitted rather than filled in:

1. **Scope delta:** what the spec does not already say — exclusions, ordering
   constraints, work split off to another change. Do not restate the spec.
2. **Approach:** existing patterns reused, decisions and risks not obvious
   from the codebase.
3. **Global constraints:** project-wide requirements from the spec or user —
   version floors, dependency limits, naming or copy rules, platform
   requirements — one line each with exact values, verbatim. Every slice
   implicitly includes this section; do not restate it per slice.
4. **Slices:** exact files/symbols and required behavioral changes, ordered by
   dependency, each with its check. Include caller migration and obsolete-path
   removal where the change leaves them.
5. **Boundary interfaces:** for split or delegated work only — the exact names,
   signatures and value shapes a slice **consumes** from another and
   **produces** for another. A self-contained slice needs no block; internal
   wiring is not an interface.
6. **Review focus:** where the spec implies boundary or failure inputs —
   empty/oversized/malformed input, the "impossible" state a caller can still
   build, platform or locale edges — that no slice's check would otherwise
   exercise: one line each naming the input, the behavior a reasonable person
   would expect and the slice that owns the code. Omit when the spec implies
   none.
7. **Verification:** scenario or command, observable expected result, isolation.

Steps are decisions, not transcripts. A code step carries the exact signature
only where the spec pins the value or the signature crosses a delegation
boundary; a function body appears only for an algorithm that the signature and
checks do not determine. A check step carries the command and the output that
means it passed.

Use the task tracker or chat when sufficient. Create a plan file only when
requested or required by an applicable project workflow; reuse the project's
plan location, otherwise `docs/plans/YYYY-MM-DD-<feature-name>.md`. Link the spec
rather than copying it. A fixed header, code for every line, or a commit step
per slice is not required. Commits follow OPS §1.

## Self-review

Compare every requirement with its slice and check. Add missing paths; resolve
contradictory signatures and platform requirements; confirm each name that
crosses a slice boundary is spelled identically on both sides — `clearLayers()`
in slice 3 and `clearFullLayers()` in slice 7 is a bug. "Handle errors" without
named failure behavior is incomplete. Cover each review-focus line with checks
in its owning slice. The plan must be actionable, but should not duplicate the
future implementation.

## Execute

Runtime shape:

```
check → implement → verify → next slice → integrated verification
```

Honor the user's execution strategy and the host's delegation rules. Otherwise
choose from the work's shape: inline by default; parallel workers for genuinely
independent ownership when they are available and useful. Scale review to
risk, not one reviewer per slice. Do not ask the user to choose again or
reapprove the same authorized work. If a worker cannot run, continue locally
where possible rather than making worker setup a new prerequisite.

Per slice:

- **One concern.** A slice changes one logical thing and finishes it.
- **Simplest thing that works**, reusing existing patterns.
- **Scope stays put.** Do not clean up adjacent code, refactor imports in
  files you merely touched, or modernize syntax you only read. Note it instead.
- **Recoverable, verified state.** Check affected paths as they become
  executable; run integration checks once shared mutations settle. When slices
  are committed, each commit reverts cleanly on its own; without commits, every
  slice still ends in a state you could stop at and explain.
- **No incomplete delivery.** A feature flag is for a real rollout
  requirement, never a disguise for unfinished behavior; a temporary mock is
  not completed integration.
- **Safe defaults** for new code: conservative behavior on missing or bad input.

Settle minor reversible implementation ambiguities — a renamed helper, an
internal signature the plan got slightly wrong — from the user's intent, the
spec and the current code. When the decision is consequential, record it with
its reason and risk in the existing task or handoff record, then continue; no
fixed "Ruling:" wording, no second tracking system. A decision cannot overwrite
intent, expand scope or grant authority: those, and only those, are worth
asking about.

When only a plan was requested, deliver the plan and do not implement.

## Progress and evidence

Per slice, before moving on:

- Applicable checks ran and their output was read, or valid unchanged evidence
  was reused. If a named check became obsolete or cannot run, record why and
  what remains unverified rather than claiming it passed.
- Expected outcomes were compared with observed results. A check passing
  before the implementation can establish existing behavior; it cannot show a
  bug was reproduced.
- Consequential deviations and their reasons are recorded.

Record progress where the session already tracks it (task tracker, existing
handoff or status file) — never a second parallel ledger. The record must let a
fresh or compacted context resume: which slices are done with their evidence,
which are not, and which decision changed which interface. Resume from the
record and the current repository state, and reuse evidence only while it
still covers that state.

Verify integrated behavior before the final report; a finished slice or a
checked-off list is not the deliverable.

## Red flags

- A large unverified uncertainty accumulating across slices.
- Several unrelated changes in one slice.
- "Let me just quickly add this too."
- Part of the request reported complete because one slice passed.
- A deviation made without a recorded decision.
- Progress tracked in two places, or in one the next session cannot read.
- Re-running completed work after compaction instead of resuming from the record.
- Progress recorded without observation. "Seems to work" is not evidence.
- A worktree created or removed as a plan step: that is `using-git-worktrees`'
  job, set up once, not per slice.
- A commit, review or slice boundary treated as permission to stop.

---

Source: obra/superpowers (MIT); incremental implementation absorbed from
coding-kit v5.1. Adapted for coding-kit.