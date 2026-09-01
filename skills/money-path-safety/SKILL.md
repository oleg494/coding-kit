---
name: money-path-safety
description: 'Use when the user wants to: pay/buy/subscribe, receive or spend a bonus/promo code/referral, check a balance or limit, get a refund, or when any logic for deducting/crediting/quotas changes — even if the request does not name money explicitly («give me more minutes», «why was I charged twice», «enter a promo code»). Checks: idempotency, atomicity, mutation logging, separate buckets, hard gate before expensive work, charge after success, soft delete, compound PK, structured failure. Do not use for pure CRUD without value semantics and for debugging incidents (that is debug-incident-protocol).'
compatibility: any languages/stacks with balances, quotas, promo codes, limits
metadata:
  version: "3.7.0"
---

# Money path safety: money and value — a special class of code

Distilled from live billing sessions. Apply to ANY path where you deduct/credit/pay/limit.

## 1. Money: iron rules

1. **MONEY PATH IS SACRED** — lock/transaction + idempotency + a log for every event + a test for double-submit. Check: pressed «pay» twice → balance +X, not +2X.
2. **IDEMPOTENCY BY DEFAULT** — operation key (invoice_id, event_id) + credited flag + early return. Check: run the handler 2 times — second is a no-op.
3. **SEPARATE BUCKETS** — trial/promo/purchase/subscription = different entities, not one `balance` field. Explicit deduction order: free → bonus → paid.
4. **HARD GATE BEFORE EXPENSIVE WORK** — check entitlement/limit/money BEFORE the external call (CPU/API/LLM). With a zero balance the API is not called.
5. **CHARGE AFTER SUCCESS** — success → debit; error → no debit (+ log). Inject a provider error → balance unchanged.
6. **LOG EVERY MUTATION** — one line per credit/debit/grant/refund: `charge uid=%s seconds=%.3f from_free=%.3f from_bonus=%.3f from_paid=%.3f`. grep by user_id reconstructs the history.
7. **NO SILENT EXCEPT ON SIDE EFFECTS** — except: pass is acceptable on cleanup, NOT acceptable on money/auth/data-loss. Money path: log + fallback or fail loud.
8. **READ-MODIFY-WRITE UNDER LOCK** — «read→compute→write» without locking = lost update. Mutex/transaction over the whole RMW.
9. **ONE SOURCE OF TRUTH** — UI/cache/log are derivatives. Truth is the storage. An incident starts with reading storage, not with a theory.

## 2. Atomicity in SQL (without races)

- **Atomic check-and-increment**: `UPDATE ... SET used = used + 1 WHERE used < max` — one query, rowcount 0 = limit exhausted. NOT SELECT → IF → UPDATE.
- **Compound PK as idempotency**: `PRIMARY KEY (code, user_id)` — a repeat is blocked at the DB level, without SELECT before INSERT.
- **SQLite**: `connect(timeout=30.0)` + `PRAGMA busy_timeout=30000` + `journal_mode=WAL` — three settings together.
- **Metric upsert**: `INSERT ... ON CONFLICT DO UPDATE SET value=value+excluded.value` — without SELECT+UPDATE race.

## 3. Promo codes and value operations

- **SOFT DELETE**: never DELETE business rows — `UPDATE status='finished'`. Audit and FK survive.
- **INPUT NORMALIZATION AT BOUNDARY**: canonical form once at the input (upper/strip/charset); downstream trusts it.
- **STRUCTURED FAILURE**: return `(ok, reason_code, value)` — "not_found", "already_used", "exhausted"; UI maps the code to a human message. NOT just False.
- **CREATOR-SCOPED ADMIN QUERIES**: `WHERE created_by=?` in all admin queries; mutations check ownership.
- **SINGLE CONSTANT DRIVES ALL SURFACES**: REFERRAL_BONUS=30 — in the DB, UI text, share message, tests. Grep for the number finds only the definition.
- **PRE-CAP SIDE-EFFECT GUARD**: check cap BEFORE `_ensure()`/INSERT — otherwise rejected users leave garbage in the DB. Refusal → return without mutations.

## Workflow (order of application)

1. **Find the money paths.** Grep the handlers/functions: charge, debit, credit, grant, refund, invoice, balance, promo, referral, quota, limit. Mark each deduction/credit path.
2. **Check idempotency.** Does each mutator have an operation key + credited flag + early return? No → add it. Test: run twice → second is a no-op.
3. **Check atomicity.** RMW under lock/transaction? Limit increments with a single SQL with a WHERE constraint? SQLite — timeout + busy_timeout + WAL?
4. **Check order and gates.** Deduction in one function (free→bonus→paid)? Hard gate BEFORE the expensive call? Charge after success, not on error?
5. **Check logging.** Is each mutation logged in one line with the subject id and amount? Does grep by user_id reconstruct the history? No silent except on the money path?
6. **Check boundaries and refusals.** Does a rejected operation create no records? Structured reasons (ok, reason_code, value)? Cap=0 = unlimited explicitly?
7. **Check promo/referrals.** Soft delete? Compound PK on repeats? no-self-deal? bonus only for new accounts?
8. **Write/update tests.** double-submit, error-no-debit, reject-no-side-effects, cap edge, abuse case. Names = spec.

## Money-code review checklist

- [ ] double-submit → balance not changed twice (test)
- [ ] provider error → no debit (test)
- [ ] every mutation logged with subject id and amount
- [ ] no except: pass on the money path
- [ ] RMW under lock/transaction
- [ ] deduction order — one algorithm in one place (free→bonus→paid)
- [ ] rejected operation created no rows in the DB (test)
- [ ] every limit has a warning log when reached