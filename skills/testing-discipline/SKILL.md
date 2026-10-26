---
name: testing-discipline
description: 'Use when writing or fixing tests, working test-first (TDD red-green-refactor), turning a reported bug into a failing test, or choosing a check for a boundary, limit, abuse case, outbound payload or UI flow. Not for diagnosing why something fails (use systematic-debugging) or for the final done claim (use verification-before-completion).'
license: MIT
compatibility: pytest, jest and similar; applicable to any language
metadata:
  version: "6.0.0"
---

# testing-discipline

Tests are the executable spec and the evidence that a change does what was asked. This skill shapes them; what evidence counts and how long it stays valid is OPS §3.

## 1. Test-first: red, green, refactor

**Red.** State the behavior as one named test and watch it fail for the intended reason before changing the implementation — a fresh run, or failure evidence that still covers the same state, command and environment. An import error or a typo in the test is not the intended reason. A user-reported failure is ground truth for the symptom. A check written after the fix can display behavior but cannot by itself show that the bug reproduced, so report the gap instead of claiming an unrun red.

**Green.** Write the smallest correct implementation of the whole request, not only the slice the current test exercises. Acceptance criteria that no test covers still have to be implemented.

**Refactor.** With checks green, remove duplication or complexity in the code you touched, then recheck the behavior you changed. Leave unrelated code alone.

### Targeted green and suite green

Two different claims, two different scopes:

- **Targeted green** — the check that covers this task's behavior passes after the change. This is the minimum for any behavioral change.
- **Suite green** — applicable existing checks pass on the final state. Broaden from the targeted check when the change touches shared code or a public contract, or when a targeted check exposed a failure. A self-contained change verified by a scoped probe may not need the project suite.

An existing contract test, a recorded smoke probe, or an observed rendered UI flow is the appropriate check whenever it covers the changed behavior — a new test is for behavior nothing currently defends, not a ritual per change. Keep green claims inside the scope you observed; the completion gate itself belongs to `verification-before-completion`.

**Report every failure you saw**, including ones that predate your change. A red run that scrolled past unmentioned falsifies the report by omission. Say whether a failure came from this change, existed before, or you do not know.

### Rationalizations

| Excuse | Reality |
|--------|---------|
| "Fix is obvious, test after" | Test-first is the evidence that the failure existed and that the fix addresses it |
| "Too simple to test" | Simple logic is where silent regressions live; one named assertion is enough |
| "Manual check is faster" | Manual steps are not repeatable evidence and get lost at the next refactor |
| "I'll write it once the design settles" | The test is what settles the design; a test written after tends to mirror the implementation |
| "It already passes, so it is covered" | A test that never observed the failure proves nothing about the defect |
| "Mock it, it is faster" | Mocking the logic under test tests the mock; fake only the edges |
| "One green run covers the suite claim" | That is a targeted claim; either broaden the run or narrow the claim |

## 2. What a permanent test must defend

A permanent test pays for itself only if a plausible failure or a consumer contract would break it. Do not add tests for wording, internal wiring, component presence or a route echo — they lock churn instead of behavior.

- **Name = rule.** `test_referral_no_self`, `test_crypto_idempotent`, `test_cannot_buy_while_paid_remains`. `pytest --collect-only` should read like a product checklist, not `test_1`.
- **Assert material boundaries** where the domain has them: zero or exhausted value, self-reference, double credit, empty input, overflow. No happy/edge/abuse triple for every function.
- **State, not interactions.** Assert the outcome of an operation, not which internal methods were called.
- **One concept per test.** Multiple assertions are fine when they jointly establish one behavior; split unrelated concepts.
- **DAMP over DRY.** Each test tells a complete story; shared fixtures that hide the setup make failures hard to read.
- **Arrange, act, assert** — keep the three visible, one action per test.
- **Layers by cost.** Unit tests for pure logic (milliseconds), integration tests where components or I/O boundaries meet, end-to-end only for flows no smaller layer can defend. Most rules belong in the middle two.
- **Prefer real implementations** over fakes, stubs, and mocks, in that order; mock only when the real thing is slow, non-deterministic, or has effects you cannot control.

### Domain gates

Apply the ones that describe this change; skip the rest.

- **Money or balance path** — double submit credits once (balance +X, not +2X), a confirmed provider failure leaves the balance unchanged, an unknown outcome (timeout) leaves a pending record that reconciliation resolves, a rejected operation leaves no row (`assert not user_exists(...)`). Details: `money-path-safety`.
- **Caps and quotas** — cap exhausted returns False and creates nothing; drive the limit through env/fixture rather than production data.
- **Rate limits** — two consecutive calls: the second is blocked and the external API is called at most once.
- **Growth features** (referral, promo, invite) — write the abuse case in the same change as the feature: self-referral, replay, credit farming.
- **Outbound payload** — assert the platform's byte/field limit against the encoded body before shipping it.
- **UI** — exercise the rendered flow, states and responsive behavior the change affects. Defend uncertain behavior, not component presence.
- **Wording** — assert meaning, accessibility, and wording that is genuinely contractual (legal, protocol, public interface). Ordinary editorial edits need no substring lock.

## 3. Isolation

1. **Never point tests at the production store.** Select throwaway storage before import: env override, temporary path, isolated fixture. Do not connect to production just to compare row counts.
2. **Control import side effects.** Prefer explicit dependency injection or existing isolated fixtures; use a fresh import only when a module genuinely captures storage at import time.
3. **Domain first.** Exercise the business rules directly; let integration checks cover meaningful I/O boundaries. No mandatory framework or runtime target that the task did not ask for.
4. **Fake the edges, not the core.** Replace external HTTP/messaging/API calls, never the logic under test. When persistence semantics are part of the behavior, use a real temporary database.

## 4. Workflow

1. Name the consumer-visible behavior and the failure it defends.
2. Pick the cheapest layer that can observe it; isolate external effects.
3. Establish failure evidence — a red test for new behavior, a reproduction for a reported bug, or the stated reason reproduction is unavailable.
4. Implement the complete request, then run the targeted check and the suite scope the risk justifies.
5. Exercise the affected runtime surface where behavior is the claim, and report the evidence's actual scope.

## Checklist

- [ ] New or fixed behavior was observed failing before the fix, or the missing before-fix evidence is stated
- [ ] The targeted check passes after the change; suite scope matches the risk and is stated
- [ ] Every observed failure is named, with cause attribution known or unknown
- [ ] Storage and network effects are isolated from production
- [ ] Tests assert domain behavior, boundaries or failure transitions — not wording, mocks or counts
- [ ] Domain gates that apply (money, caps, rate limits, growth abuse, payload limits, UI) are covered
- [ ] Every acceptance criterion has observed evidence appropriate to its type