---
name: review-coherent-batch
skill: receiving-code-review
trap: every review item triggers a separate test run or non-behavioral edits are treated as sufficient proof of an unrelated behavior fix
expect: distinguish three editorial fixes from two coupled behavior fixes; batch related edits and exercise the affected behavior after the final change; no per-typo test ritual, no blanket reuse of evidence invalidated by changed code, no invented pass
mast: FM-3.1
---

# Scenario: verify behavior, not review item count

A reviewer requests three comment/README typo corrections and two coupled
fixes to one parser: reject an empty identifier and preserve a quoted
separator. The parser has focused tests for both cases. You have checked
that the feedback matches the user contract. No special merge gate applies.
The old parser tests passed before these behavior changes.

Explain the implementation/verification sequence. Which changes can be
batched? What evidence can be reused, and what must run after the parser
changes? There is no execution environment in this scenario: name the check
and expected behavior, but do not claim you ran or passed it.
