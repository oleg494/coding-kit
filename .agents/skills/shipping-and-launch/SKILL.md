---
name: shipping-and-launch
description: 'Use when releasing to production: pre-launch readiness review, staged rollout or canary, feature-flag plan, rollback plan, post-launch verification. Decides what to deploy, at what exposure, and when to reverse it. Not for adding logs, metrics, traces or alerts (observability-and-instrumentation) and not for code-level hardening (security-and-hardening).'
license: MIT
metadata:
  version: "6.0.0"
---

# Shipping and launch

A launch decides exposure: what artifact runs, for whom, on what evidence, and how it reverses. Failure modes and reversal costs differ by system type.

## Readiness, gated by system type

- **Always:** risk-matched tests at the level the change can break; a reviewer other than the author; no debug prints or bypasses on shipped paths.
- **Deployed runtime:** secrets from the platform store; target-env config; health endpoint answers; logs and errors reach a human.
- **New surface, dependencies:** boundary validated, route authorized, unauthenticated endpoints rate-limited and body-capped; no reachable critical/high advisory.
- **Data:** migration applied and reversible, or converted to expand/contract.
- **Surface-specific:** bundle budget, Core Web Vitals, no N+1; store lead time and rollout controls on mobile; changelog if kept.

Name skipped lines in the launch note.

## Release shape

Direct deploy (reversal is the previous artifact), feature flag (code ships dark, exposure switched separately), canary (a slice of real traffic; needs routing and volume), blue-green (atomic switch), migration first (expand/contract). A flag has an owner, a removal criterion and a reminder; not nested; CI runs both states.

## Rollback plan, written before deploy

1. **Signal to reverse** — observable and baseline-relative: error rate ("above 2x baseline for ten minutes", not "it feels wrong"), latency regression, saturation, a business KPI.
2. **Reversal action** — flag off, previous artifact, or forward fix; dry-run it before you need it.
3. **Data.** A redeploy does not undo a destructive schema change. Reversible pattern is **expand/contract**: add the new column or table, dual-write, backfill, switch reads, drop the old shape later. A genuinely irreversible migration (destructive `ALTER`, dropped table, backfill over originals) makes the plan a **forward fix** plus a retained backup with a tested restore.
4. **Who decides, who is told** — named before exposure.

## Staged rollout, driven by gates

Staging runs the same artifact → production at zero exposure (deployed, not serving; health and errors checked) → internal cohort → a small share of real traffic → all, in steps sized by detection speed. Hold until the window beats the noise floor. Thresholds set before exposure, against a baseline measured on this service:

| Signal | Advance | Hold | Reverse |
|---|---|---|---|
| Error rate | at baseline | above, cause unknown | ~2x baseline, sustained |
| p95/p99 latency | within ~20% | 20–50% above | above ~50% |
| Saturation | within headroom | climbing | at the limit |
| Business KPI | flat or better | down, unclear | down and falling |
| New client-side error | none | under 0.1% | rising |

A service already at 3% errors needs a different red line.

## Verification window after full exposure

First window where every step of the flow served real traffic: health answers, error volume comparable with no new type, no latency or saturation step change at deploy time, the critical flow works end to end, logs and traces arrive with expected event names (an empty stream is a failure), reversal still available (flag reachable, artifact retrievable, forward fix written). Record version, signals and decisions.

Red flags: no reversal path or an unexercised one; no way to see whether the new path works; big-bang exposure of a user-visible failure; flags outliving their code; nobody on call.
