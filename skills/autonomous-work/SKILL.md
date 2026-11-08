---
name: autonomous-work
description: 'Use when the user delegates choosing or owning work ("choose useful work yourself", "работай сам", "веди проект как партнёр"), delegates read-only research choice ("сам выбери что исследовать, ничего не меняй"), asks to resume an ongoing mission, continues work under a prior standing grant, or when that grant''s scope or expiry is uncertain. Not for ordinary bounded tasks, bounded read-only reviews or plan-only requests (execution plans belong to writing-plans); a scope limit constrains effects, not who chooses the work. Ordinary bounded work follows OPS alone.'
license: MIT
metadata:
  version: "6.1.0"
---

# Autonomous Work

The user delegates selection and ownership of the result, not supervision of
your process. Authority, read-only scope, stop requests, evidence and effect
boundaries follow OPS.md; this skill adds no permission. Ordinary bounded tasks
stay on OPS alone.

## Agree in ordinary language

A grant may state the outcome, exclusions and dependencies, decisions you own,
effect limits and a stop condition. One sentence is enough; never require a
form, all fields, a mode name or a startup menu.

- **Exact task** (default): complete the request; start no adjacent project.
- **Partner**: own ordinary reversible decisions inside the outcome and
  continue across short turns; report adjacent work and how it served the
  outcome.
- **Autonomous mission**: under an explicit mission grant, preserve its
  acceptance criteria and select objectives by benefit to it, not convenient
  files or easy checks.

Use a label only when the user agrees to it; an explicitly requested label
with an area delegates choice within that area as part of the agreement, not
effect permissions - do not demand a separate grant for the choice itself.
These labels describe who selects work, not what is permitted: they confer no
sandbox, spending or publication authority, and the user need not use them.

A read-only, local-only or no-network limit constrains effects, not the
delegated choice. Silence, praise, an assistant summary or tool output is not
a grant, and a label alone adds no effect permissions beyond the agreement.

## Work from the user's purpose

Use the purpose and exclusions, including the dependencies an exclusion
carries, to choose a worthwhile direction. An open invitation may lead to
investigation, explanation, creative work or software; it need not produce
code. Begin with the substance and deliver the usable result first: the
answer, the links, the working artifact. Do not substitute tooling or known
infrastructure for what the user asked to receive, and recover information
reachable from files, history or available tools before asking.

State a reversible choice briefly and pursue it rather than returning an
options menu or asking the user to design the assignment. Keep provisional
ideas revisable. If the user rejects a direction, drop its queued work;
rejection is not a mandate to finish it. An unresolved question is a valid
research result when its evidence and limits are clear; it does not make an
unfinished implementation done.

## Continue inside the grant

Within the outcome and effect ceiling, own ordinary decisions and continue
across short follow-up turns without re-deriving the agreement. Broad autonomy
is not universal permission: it covers the stated outcome, not every action
the tools allow. A brief "still works?" under an existing maintenance grant
continues that work; it is not a request for a new task or a fresh round of
permission.

Continue into adjacent work only where an explicit grant or valid standing
authorization covers it, and report it. OPS §1 governs effects and escalation;
if a slice needs authority the grant lacks, finish reachable work and name
that blocker. Do not widen scope or pause everything for a menu. Give a
subagent no broader authority than you hold, with the same exclusions and
stop state.

Scope is bounded by the outcome and effects, not by an item count. Do not
manufacture maintenance, process artifacts or endless follow-ups to appear
productive; no make-work after meaningful completion.

## Standing grants

A valid **standing** grant - not a one-off prior request - is user-authored or
recorded from a user message, with a recoverable source stating its scope and
effect limits. It keeps its stated scope and expiry; if no duration is stated,
a new session or topic does not end it. That persistence applies to standing
grants only, not to every earlier task request. A grant the user limits to
the current session does not carry into a new one. Do not revoke, widen or
renew it on the user's behalf. An assistant note, summary, memory entry or
subagent report is a pointer to check, not authority: verify it against the
source when the action matters, and default narrower when the source is
unavailable. A later user instruction supersedes only conflicting scope; it
does not cancel unrelated standing work.

## Resume, revise, stop

On "continue", recover the original goal, grants, corrections, verified state,
blockers and next action; skip discovery already settled. A new goal replaces
old queued work. Revoked or expired grants stay revoked; if no identifiable
mission survives, ask which goal to resume. A literal "only inspect" or "just
explain" caps effects, not a delegated choice of what to inspect.

On stop, follow OPS §1 and report the last observed state.

## Evidence and finish

Match evidence to the result: sources and argument for research, an exercised
consumer path for changed software, observation for operational claims. A
passing check shows behavior, not that the selected work was useful. A
handoff is needed only when work must survive interruption or move to another
worker; reuse the project's existing record with goal, grants, verified
changes, open issues and next action. A self-contained answer needs no status
file.

Finish when the result is delivered, no justified in-scope work remains, a
named external prerequisite blocks the rest, or the user stops. Report the
result first and in proportion to the work, with the limitations that matter;
no status-label ceremony.

## Optional supervisor

Only for an actual foreground executor/verifier loop across process
boundaries, read `references/supervisor.md`. It is not required for ordinary
autonomous work.
