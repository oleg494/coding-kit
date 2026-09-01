---
name: production-first-decisions
description: 'Use for ANY "how to do it" decision: choosing an approach/tool/library/standard, designing, "what if", adopting a new mechanism — when the answer must not come out of your head. Covers: the production-first order (formulate the question → web search as the industry does → verify your hypothesis → do it the industry way), the "everyone does it" criterion (measured, not felt), test-before-integration spike→ADR, research depth per task, and the three decision principles DRY/KISS/YAGNI.'
compatibility: any project
metadata:
  version: "3.8.0"
---

# Production-first: decisions by industry practice, not from your head

The source of truth is the industry; knowledge is a hypothesis until verified.

## Workflow (order of application)

1. **Formulate the question "how is this done in production?"** — explicitly, before any action.
2. **Web search**: 5-10 queries from different angles — manuals, official guides, GitHub, practitioner articles, ADRs. Primary sources, not retellings.
3. **Cross-check YOUR hypothesis against what you found.** Your own knowledge is only an assumption; web search is source of truth #1. "Thought it through" without searching = a guess, not a decision.
4. **Do it the industry way.** Readiness criterion for a decision: "everyone does it this way, not just me alone." Not confirmed by sources → it's a hypothesis: verify by search before writing code.

## Test-before-integration (spike → ADR)

A new tool/library/approach — FIRST benchmark, THEN integration:

1. **Question:** what are we checking — functionality, fit to the stack?
2. **Benchmark in a sandbox:** install it, run a real case, compare with alternatives AND with "doing nothing" (doing nothing is always an option).
3. **Record the conclusion in Wiki/decisions/:** what was chosen, what was rejected, the benchmarks.
4. **Integrate only after proof.** Without a benchmark, integration is a guess.

## Research depth — by task

- **Reference** (syntax, command) — 2-3 sources, one pass.
- **Decision/choice** — DEEP research: breadth (5-10 queries in parallel), then depth; canonical repos, PRs, issues, ADRs; "everyone does it" — measure (how many production projects actually do), not feel.

## Three decision principles (filter before code)

- **DRY** — one piece of logic and one piece of knowledge in one place. Duplication = two places that must change together.
- **KISS** — the simpler option, if it closes the task. Complexity is justified when the simple one can't cope, not "for the future".
- **YAGNI** — don't build what wasn't asked for. "Might come in handy" is an insufficient reason.

A decision that violates at least one principle without a clear reason → reconsider.

## Checklist before a decision

- [ ] the "how in production?" question is formulated
- [ ] 5-10 queries from different angles, primary sources
- [ ] hypothesis cross-checked against what was found (not "I think so")
- [ ] new tool — benchmarked in sandbox + doing nothing
- [ ] conclusion recorded (what was chosen, what was rejected, why)