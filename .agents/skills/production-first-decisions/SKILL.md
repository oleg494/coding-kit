---
name: production-first-decisions
description: 'Use before committing to a consequential tool, library, standard or production mechanism: "should we use X", "which library", "is X maintained", auth/crypto/queue/database choices, or replacing a working one. Check project constraints first, then primary-source evidence (docs, changelogs, maintenance signals, issue trackers, benchmarks, own probe) before integration. Not for module structure (architecture-simplicity) or minimalism-only requests (ponytail); ordinary implementation needs no skill.'
license: MIT
compatibility: any project
metadata:
  version: "6.0.0"
---

# Production-first: decisions grounded in evidence

A choice that is expensive to reverse, or that everything else builds on, gets evidence before code; ordinary local choices get the existing pattern.

## Workflow

1. State the decision, the constraint it must meet (scale, latency, licence, platform, team, budget) and the evidence that would settle it.
2. Read the existing implementation, constraints and recorded decisions first; if they settle it, reuse the pattern — no research for a local definition or a known stdlib operation.
3. Gather evidence for what the project cannot answer (below), cross-checking what is hard to reverse or contested; choose by fit, correctness, maintenance and measured constraints, since adoption is not proof it fits here.
4. Probe the remaining risk, then record the decision where the project keeps such records — an ADR only if it uses them.

## Acceptable evidence

Closest to actual behavior first:

- **Official docs and changelog** for the exact version in use: migration notes, deprecations, support windows, licence terms.
- **Source code or the shipped artifact** when docs and behavior disagree.
- **Maintenance signals:** recent releases, issue-tracker response, open advisories, a support policy. "Popular in a blog post" is not one; years untouched with a long open-issue backlog is counter-evidence.
- **Issue trackers** for known failure modes and version-specific bugs; read the resolution, not the title.
- **Reproducible benchmarks** on a comparable workload with method and hardware stated; vendor benchmarks only start the search.
- **Our own probe:** the smallest test that exercises the uncertain behavior in this stack.

Say which you used and what stayed unverified; a claim with no evidence class is a guess.

## Test before integration

For an unfamiliar dependency or mechanism, probe first in a task-sized sandbox: one real call path, the edge case you doubt, the upgrade or the failure mode; benchmark only when performance drives the choice. Installation, paid calls and outward actions need authorization per OPS §1.

## Research depth

Stop once resolved: a narrow fact needs its owning source; a consequential choice needs alternatives, counterevidence and a probe of what remains. Ship the tradeoffs and remaining uncertainty with the decision.
