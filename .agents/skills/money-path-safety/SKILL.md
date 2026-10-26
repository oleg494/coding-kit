---
name: money-path-safety
description: 'Use when touching money or quota logic: pay/buy/subscribe, promo or referral codes, balance or limit checks, refunds, or any code that deducts, credits, grants, or expires value — even when the request does not name money ("give me more minutes", "why was I charged twice"). Covers idempotency, three payment outcomes, atomic updates, audit records. Not for plain CRUD without value semantics or live incident diagnosis (systematic-debugging).'
license: MIT
compatibility: any languages/stacks with balances, quotas, promo codes, limits
metadata:
  version: "6.0.0"
---

# Money path safety

Applies to any path that deducts, credits, grants, expires or limits value: payments, balances, quotas, promo codes, referrals, subscriptions. A bug here is silent, permanent and spends real money.

## Rules

1. **Lock, idempotency, audit record, double-submit test.** Pressing "pay" twice leaves balance +X, not +2X.
2. **Idempotency by default:** operation key (invoice id, event id, request id) + recorded outcome + early return. Run the handler twice — the second run is a no-op.
3. **Three outcomes, not two.** For every payment or value-provider call, classify what came back:
   - confirmed success → debit exactly once;
   - confirmed failure → no debit, record the rejection;
   - unknown — timeout, reset connection, 5xx, process death between the call and your write → neither debit nor refund yet.
   An unknown outcome may exist on the provider side: write a pending record under the idempotency key, then reconcile with the provider (query by key, webhook, statement) before debiting or refunding. Never charge twice, never drop the case silently. A timeout is not a failure.
4. **Separate buckets.** Trial, promo, purchase and subscription are distinct entities, not one `balance`; the deduction order (free → bonus → paid) lives in one function.
5. **Gate before expensive work.** Check entitlement, limit and money before the external call (CPU, API, LLM); at zero balance it never happens.
6. **Audit record per mutation** — one per credit, debit, grant, refund or expiry, with subject (or pseudonymous) id, amount, currency or unit, operation, idempotency key, outcome. Grep by subject reconstructs the history. Identifiers only: no secrets, tokens, card numbers or free-form personal data; the trail is access-controlled, and application logs are not a substitute.
7. **No silent except on side effects.** Swallowing an exception is fine in cleanup, never on money, auth or data loss: log and fall back, or fail loudly.
8. **Read-modify-write under one lock or transaction**; reading, computing and writing without it is a lost update.
9. **One source of truth.** UI, cache and logs are derivatives; read incidents from the store.

## Atomicity in the store

- **Atomic check-and-increment:** `UPDATE ... SET used = used + 1 WHERE used < max`; rowcount 0 means exhausted — never SELECT → IF → UPDATE.
- **Compound primary key as idempotency:** `PRIMARY KEY (code, user_id)` blocks a repeat at the store, without a read first.
- **Counter upsert:** `INSERT ... ON CONFLICT DO UPDATE SET value = value + excluded.value`.
- **SQLite:** `connect(timeout=30.0)`, `PRAGMA busy_timeout=30000` and `journal_mode=WAL` together; any one alone still surfaces "database is locked" under concurrent writers.
- **Non-relational store:** conditional write with a version or compare-and-set, unique key on the idempotency pair, atomic counter increment. Where none exists, serialize mutations per subject through a single owner (a queue partitioned by subject id).

## Promo codes and value operations

- **Soft delete** where history or foreign keys point at the row: `UPDATE status='finished'`, not DELETE; in an append-only store, write a compensating event.
- **Normalize once at the boundary** (case, whitespace, charset); downstream trusts the canonical form.
- **Structured failure:** `(ok, reason_code, value)` with codes such as `not_found`, `already_used`, `exhausted`; the UI maps the code to a message. A bare `False` loses the reason.
- **Creator-scoped admin queries:** `created_by = ?` on every query, ownership checked on every mutation.
- **One constant drives every surface:** `REFERRAL_BONUS = 30` in store, UI text, share message and tests, so grep finds only the definition.
- **Pre-cap guard:** check the cap before creating rows, so a refusal returns without side effects; state "unlimited" explicitly rather than cap 0.

## Workflow

1. **Find the paths.** Grep handlers for charge, debit, credit, grant, refund, invoice, balance, promo, referral, quota, limit, expire; mark every deduction and credit.
2. **Check each mutator** against rules 2–8, and classify every provider call into the three outcomes; a missing unknown branch needs the pending record and reconciliation.
3. **Check refusals and promos:** no rows on refusal, a reason code, "unlimited" stated explicitly; promos soft-deleted, keyed against repeats, no self-referral, bonus only for new accounts.
4. **Write the tests, names as the spec:** double-submit; confirmed failure; timeout/unknown → pending, reconciled; refusal without side effects; cap edge; abuse case; warning at a limit.
