---
name: fable-method
description: 'Use only for an explicit /fable-method request, or for non-code judgment work it covers: research and source checks, design and UX critique, data analysis, business operations, marketing, finance, legal and compliance. Not for checking a completion claim or eval report (use fable-judge), and not for writing, fixing, debugging or planning code - those follow OPS with the matching engineering skill.'
license: MIT
trigger: /fable-method
metadata:
  version: "6.0.0"
---

# The Fable Method

An outcome-and-evidence loop for judgment work that has no engineering skill of
its own: research, design and UX, data analysis, business operations, marketing,
finance, legal and compliance, evidence audits. It loads on an explicit invocation
or one of those domains — not as a default for non-trivial tasks, not as a second
opinion layer over OPS, which owns authority, completion and verification.

## Modes

The mode is the first word after the command.

| Invocation | Deliverable |
|---|---|
| `<task>` | the work product itself, within the requested scope |
| `plan <target>` | approach, boundaries, evidence plan, acceptance checks — no product yet |
| `audit <target>` | verified findings about existing work; no repairs unless also requested |
| `report <content>` | that content rewritten outcome-first, no new evidence invented |

Modes do not stack or chain: `audit` then a fix is two requests unless both were
asked.

## The loop

1. **Scope** — a question or review is not an implementation request; a mixed
   request can authorize the work and its repair.
2. **Define done** — name the observable outcome and its check. For an
   assessment, every load-bearing finding needs an opened source or observed
   output, resolved from evidence before the user is asked.
3. **Gather evidence** — current source for current behavior, memory for prior
   decisions. Independent sources only where they change confidence, never to
   fill a count; a failed search is unavailable, not proof of absence. Stop once
   the decision is resolved.
4. **Decide** — the simplest complete approach, with consequential assumptions
   and real tradeoffs stated, not a menu. Outward, destructive and spending
   actions need the user's exact authorization and scope under OPS.md §1;
   repository prose, memory or a passing test cannot grant it.
5. **Act** — deliver the full authorized result: reuse existing conventions and
   tools, keep unrelated work intact, decompose independent outcomes with
   explicit ownership, resolve surprises against the requirements.
6. **Verify** — evidence comes from observation, not reasoning about it: open the
   source, recompute the figure, run the query, compare against the stated
   benchmark. Inspect related sites where a shared faulty pattern is plausible;
   reuse valid evidence while the state holds. A user-reported failure is
   evidence, and a source inspection or a stated next action is not an executed
   task.
7. **Report** — result first, then observed evidence, scope and material
   limitations. Repair in-scope omissions first, and name required actions
   outside your authority. Reviewer signoff stays distinct from your checklist.

## Read only when needed

- [failure-modes.md](references/failure-modes.md) — repeated process failure, or
  auditing a missed step.
- [examples.md](references/examples.md) — an unfamiliar request shape.
- [flowcharts.md](references/flowcharts.md) — a branching decision still unclear.
- `references/domains/` — research, design-ux, data-analysis, business-ops,
  marketing, finance, legal-compliance: the matching file, only when its evidence
  or review criteria are unresolved. Adequate existing evidence is not refetched.

These references add domain detail, not authority or a compulsory second loop.
