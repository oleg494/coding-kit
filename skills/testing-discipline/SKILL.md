---
name: testing-discipline
description: 'Use when the user wants to: add/fix tests, understand what is covered, determine whether something is "done", reproduce a bug with a test, check limits/rate-limit/failures, or when tests are written against a real DB/network. Covers: isolation from the prod store, domain-first tests, test names as a spec, boundary cases, tests for money/limits/UI/copy, DoD (parse + import + test + live process). Do not use for debugging strategy (debug-incident-protocol).'
compatibility: pytest, jest and similar; applicable to any language
metadata:
  version: "4.0.0"
---

# Testing discipline: tests as a spec and defining "done"

## 0. TDD gate (OPS §3 Phase 2 companion)

Red test → green code → refactor. Test = spec. Test name = rule: `test_referral_no_self`, `test_payment_idempotent`. No code until a failing test exists.

## 1. Isolation and structure

1. **NEVER TOUCH PROD STORE IN TESTS** — tests on throwaway storage: env path override + temp file + fresh import. Prod row count unchanged after the suite.
2. **FRESH IMPORT FOR MODULE-LEVEL SIDE EFFECTS** — import-time connect/migrate breaks isolation: `sys.modules.pop` + importlib per test/fixture.
3. **UNIT DOMAIN FIRST, HANDLER WIRING SECOND** — business rules without a framework; handlers are thin glue with fakes for I/O. Domain suite green offline in <2s.
4. **FAKE THE EDGES, NOT THE CORE** — mock Telegram/HTTP/API; do NOT mock your own business logic "for convenience". Handler test touches the real temp DB.

## 2. Names and boundaries

- **TEST NAMES ARE THE SPEC** — `test_referral_no_self`, `test_crypto_idempotent` — name = rule. `pytest --collect-only` reads like a product checklist. NOT test_1, test_works.
- **PRODUCT RULES AS NAMED TESTS** — the spec lives in tests: `test_free_spent_first`, `test_cannot_buy_while_paid_remains`. A new developer reads the tests = understands the product.
- **ASSERT THE BOUNDARY CASES** — at minimum per function: happy + one edge + one abuse. free→0, paid edge, self-ref, double credit, empty username, overflow.
- **WRITE THE ABUSE CASE WHEN YOU WRITE THE GROWTH CASE** — referral/promo written with an anti-fraud test in the same PR.

## 3. Specific tests

- **MONEY PATH**: double-submit → balance +X not +2X; provider error injection → balance unchanged; reject → `assert not user_exists(...)`.
- **LIMITS (cap)**: test before implementation: cap exhausted → False, user not created; monkeypatch.setenv; `assert cap and invited >= cap`.
- **RATE LIMIT**: two consecutive calls → second blocked without external API: mock API → assert len(calls) <= 1.
- **UI: PRESENCE + ROUTING** — per UI addition: test_X_exists + test_X_routes_to_Y.
- **USER-FACING COPY AS REGRESSION TESTS** — `assert "key phrase" in TEXT` — copy change = breaking change.
- **PAYLOAD VALIDATION** — `assert len(body.encode("utf-8")) <= PLATFORM_LIMIT` before deploy.

## 4. DoD — defining "done"

**"Committed" ≠ "works at runtime".** Checklist of 4 items:

1. **Parse** — `python -m compileall -q` / syntax
2. **Import** — module imports without errors
3. **Test** — pytest green (domain offline; integration with fakes)
4. **One live process** — real entrypoint run, log OK

Three-step verification: **ruff → compileall → pytest** — in this order, skipping nothing.

## Workflow (order of application)

1. **Isolate the store.** Tests on throwaway storage.
2. **Define the test layer.** Domain logic — unit without a framework; handlers — thin glue with fakes.
3. **Write tests from product rules.** Name = spec. `pytest --collect-only` = checklist.
4. **Cover boundaries.** Per function: happy + edge + abuse.
5. **Add specific tests.** Money, limits, rate-limit, UI, copy, payload.
6. **Run three-step verification.** ruff → compileall → pytest.
7. **DoD before "done".** parse + import + test + live process.

## Checklist

- [ ] tests do not write to prod storage
- [ ] domain logic tested without a framework
- [ ] every rule has a named test (name = spec)
- [ ] boundaries: happy + edge + abuse
- [ ] money: double-submit, error-no-debit, no-side-effects-on-reject
- [ ] limits and rate-limit covered
- [ ] DoD: parse + import + test + live process