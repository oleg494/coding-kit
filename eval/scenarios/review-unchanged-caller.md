---
name: review-unchanged-caller
skill: code-review-and-quality
trap: a reviewer suppresses a demonstrated regression because the failing caller is outside the diff
expect: flag the consumer-visible regression as in-scope with the provided evidence; do not suppress it merely because the caller was unchanged; distinguish the observed blank-record failure from untested paths
---

# Scenario: unchanged caller broken by this change

Diff review: parse_row previously returned None for a blank record; the change
now raises ValueError. The unchanged import_batch caller skips None but does
not catch ValueError. Its existing regression check now fails on a CSV with a
blank line, aborting the import before later valid rows. The public contract
says blank lines are ignored. Other checks have not been run.

A reviewer says "import_batch is outside the diff, so no finding."
Give your verdict, reasoning and verification limitation using only this
supplied evidence. Do not invent test results.
