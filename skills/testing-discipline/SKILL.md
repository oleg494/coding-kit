---
name: testing-discipline
description: 'Use when adding/fixing tests, reproducing bugs, checking limits or failures, or deciding what evidence establishes completion. Covers isolated storage, real domain logic, meaningful boundary regressions and verification of the affected runtime/UI surface. Debugging strategy lives in debug-incident-protocol.'
license: MIT
compatibility: pytest, jest and similar; applicable to any language
metadata:
  version: "4.5.1"
---

# Testing discipline: tests as a spec and defining "done"

## 0. TDD gate (OPS §3 Phase 2 companion)

Define observable acceptance and a suitable check before changing behavior. Bug fixes require a failing reproduction followed by a passing result. Preserve meaningful existing tests; keep a new regression when a plausible recurring bug would fail it. Smoke probes and rendered UI interaction are valid evidence, not an obligation to add permanent test files.

## 1. Isolation and structure

1. **NEVER TOUCH PROD STORE IN TESTS** — use throwaway storage selected before import: env override, temporary path and isolated fixture. Do not connect to production merely to compare row counts.
2. **CONTROL IMPORT SIDE EFFECTS** — prefer explicit dependency injection or existing isolated fixtures; use a fresh import when a module actually captures storage at import time.
3. **DOMAIN FIRST** — exercise business rules directly; integration checks cover meaningful I/O boundaries. No arbitrary runtime target or mandatory framework bypass.
4. **FAKE THE EDGES, NOT THE CORE** — replace external Telegram/HTTP/API calls, not the business logic under test. Use a real temporary DB when persistence semantics are part of the behavior.

## 2. Names and boundaries

- **TEST NAMES ARE THE SPEC** — `test_referral_no_self`, `test_crypto_idempotent` — name = rule. `pytest --collect-only` reads like a product checklist. NOT test_1, test_works.
- **PRODUCT RULES AS NAMED TESTS** — the spec lives in tests: `test_free_spent_first`, `test_cannot_buy_while_paid_remains`. A new developer reads the tests = understands the product.
- **ASSERT MATERIAL BOUNDARIES** — choose plausible failure modes: zero/exhausted value, self-referral, double credit, empty input, overflow. No happy/edge/abuse quota for every function.
- **WRITE THE ABUSE CASE WHEN YOU WRITE THE GROWTH CASE** — referral/promo written with an anti-fraud test in the same PR.

## 3. Specific tests

- **MONEY PATH**: double-submit → balance +X not +2X; provider error injection → balance unchanged; reject → `assert not user_exists(...)`.
- **LIMITS (cap)**: test before implementation: cap exhausted → False, user not created; monkeypatch.setenv; `assert cap and invited >= cap`.
- **RATE LIMIT**: two consecutive calls → second blocked without external API: mock API → assert len(calls) <= 1.
- **UI** — exercise the actual rendered user flow, states and responsive behavior affected by the change. Permanent tests defend uncertain behavior, not component presence or routing echoes.
- **COPY** — verify meaning, accessibility and any legal/protocol wording that is genuinely contractual. Ordinary editorial changes do not need substring-lock tests.
- **PAYLOAD VALIDATION** — `assert len(body.encode("utf-8")) <= PLATFORM_LIMIT` before deploy.

## 4. DoD — defining "done"

Completion covers every requested behavior, not merely passing tests.

- Run syntax/import/build checks applicable to the changed implementation.
- Run focused existing tests, broadening for shared code or exposed failures.
- Exercise the changed entrypoint, API or rendered UI when runtime behavior is
  the claim. A startup log alone does not prove the changed path.
- A documentation or read-only task does not require an unrelated live service.
  Missing runtime capability: use an isolated smoke probe where possible and
  state exactly what remains unverified.
- Reuse evidence valid for the final checked state; a chat turn alone does not
  invalidate it. See `verification-before-completion`.

## Workflow

1. Define consumer-visible acceptance and the failure being defended.
2. Select the appropriate layer and isolate external side effects.
3. Reproduce bugs before fixing them; for new behavior define a focused check.
4. Implement the complete request, run the check and applicable existing suite.
5. Verify the affected runtime surface and report the evidence's actual scope.

## Checklist

- [ ] Storage and network effects are isolated from production
- [ ] Checks exercise real domain behavior, boundaries or failure transitions
- [ ] No source-text, wording, mock-echo or test-count padding
- [ ] Money and limits retain idempotency and no-side-effects-on-reject coverage
- [ ] Every acceptance criterion has appropriate observed evidence