---
name: production-first-decisions
description: 'Use for consequential choices of tools, libraries, standards or production mechanisms. Check existing project constraints first, research unresolved external facts in primary sources, and test unfamiliar mechanisms before integration. No web-search quota for local facts or established repository patterns.'
license: MIT
compatibility: any project
metadata:
  version: "4.6.0"
---

# Production-first: decisions grounded in relevant evidence

## Workflow

1. Define the decision and acceptance criteria. Read the existing implementation,
   project constraints and known decisions before inventing a second convention.
2. If those sources settle an ordinary local choice, reuse the existing pattern.
   Do not require web research for a local definition or a known stdlib operation.
3. Research unresolved external facts through current primary documentation,
   source code and relevant production experience. Cross-check disputed or
   high-impact claims. No fixed source/query count or popularity gate.
4. Choose by fit, correctness, maintenance and measured constraints. Widespread
   adoption is evidence, not proof that an approach fits this project.

## Test-before-integration

For an unfamiliar dependency or mechanism, run a task-sized sandbox probe of
the uncertain behavior before integrating. Benchmark only when performance
motivates the choice; compare a simpler existing option when material.
Installation, paid calls and outward actions still follow AGENTS.md authority.
Record consequential decisions in the existing project record or authorized
memory; an ADR is not a mandatory artifact for every implementation detail.

## Research depth

- Narrow authoritative fact: read the owning source and stop when resolved.
- Consequential or uncertain choice: compare relevant alternatives, seek
  counterevidence and test the remaining risk. Broaden only when it could change the decision.

## Three decision principles (filter before code)

- **DRY** — one piece of logic and one piece of knowledge in one place. Duplication = two places that must change together.
- **KISS** — the simpler option, if it closes the task. Complexity is justified when the simple one can't cope, not "for the future".
- **YAGNI** — don't build what wasn't asked for. "Might come in handy" is an insufficient reason.

A decision that violates at least one principle without a clear reason → reconsider.

## Checklist before a decision

- [ ] Existing project constraints and patterns considered
- [ ] Material external uncertainty checked against appropriate primary sources
- [ ] Unfamiliar behavior exercised before integration; performance claims measured
- [ ] Chosen approach meets the full request without unnecessary machinery
- [ ] Remaining uncertainty and consequential tradeoffs reported