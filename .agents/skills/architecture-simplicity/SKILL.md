---
name: architecture-simplicity
description: 'Use when designing or reviewing structure: module and layer boundaries, splitting a god file, shared core with thin adapters, where config and defaults live, service boundaries, non-destructive DB schema evolution (expand-contract, backfill, constraints, indexes, rollback), or whether an extra layer is justified. Not for minimalism in one change (ponytail), money logic (money-path-safety), or library choice (production-first-decisions).'
license: MIT
compatibility: any language and stack, architecture design/review phase
metadata:
  version: "6.0.0"
---

# Architecture & simplicity

Structure is what a change has to cross: the fewest boundaries the product needs
now, each with the change it protects named. A smaller feature set is not a
simpler design of the same requirement. Money amounts, currency handling, spend
order and refunds belong to money-path-safety; this skill decides where that
logic lives.

## Modules and boundaries

- **Split by reason to change.** Different axes of change belong in different
  modules: a PDF export must not touch billing, an auth change must not touch a
  report generator. A file that keeps changing for unrelated reasons marks a
  missing boundary, not a file that needs shortening.
- **One business core, thin adapters.** Business logic lives once; each client
  channel (CLI, HTTP, desktop, chat) is a shell of I/O, auth and presentation, so
  a polish bug is fixed in one place for every client.
- **A boundary needs a job now.** Every layer, package or service is crossed by
  callers and paid for in ops and debugging. Add it when it isolates a change
  boundary the product already has — a second client, a deployable that must
  scale or fail independently, an external protocol — not for a hypothetical
  consumer. Inside a single change, ponytail owns the minimal-code call.
- **Pure core, impure edges.** Assembly, formatting and export are pure
  functions; I/O, time, randomness and network sit where a test can substitute
  them.
- **Make invalid states unrepresentable.** Separate fields over boolean soup:
  `status: active | finished` instead of `is_active` + `is_finished` +
  `is_deleted` combinations nobody can reason about.
- **Comments carry the ceiling.** Say why the code exists and what limit it
  tolerates, not what the next line does.

## Configuration and evolution

- **Config outside the repo, defaults in code.** Secrets and per-environment
  tuning never enter git; the code carries safe defaults and the environment
  overrides them.
- **Flags serve rollout, not avoidance.** A flag is for operational variation the
  product needs, never to dodge a required cutover or keep a hypothetical
  compatibility path alive.
- **Schema evolution is non-destructive by contract.** A deploy never drops or
  rewrites a table that holds production data, and never requires a
  code-and-schema flip in the same instant. Staged expand-contract: add the new
  column or table, backfill in bounded batches while both shapes work, add the
  constraint or index once the data satisfies it (`NOT NULL`, foreign keys and
  unique indexes only after the backfill), switch reads and writes, then remove
  the old shape in a later deploy after verifying nothing reads it. Index
  creation on a large table needs its own rollout plan (concurrent/online build
  where the engine requires it) because it can lock or rewrite. State the
  rollback before running the migration: which deploy order leaves the old code
  working against the new schema, and which backup covers an irreversible step.
  Destructive maintenance on live data is an authority question (OPS §1), not a
  migration detail.
- **Deterministic rebuild beats stale cache.** Rebuilding from source is cheaper
  than debugging data whose provenance is unknown.

## Failure and provider policy

A fallback exists only where the availability contract requires it and a
compatible alternative already exists and is authorized. Otherwise fail clearly
with the real error: a second vendor or a silent degraded mode is a product
decision, not a default feature.