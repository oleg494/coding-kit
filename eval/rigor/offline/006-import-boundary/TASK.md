---
name: import-boundary
tier: STANDARD
---
In utils.py, `clamp(val, low, high)` returns `low` when `val > high` instead of
returning `high`. Fix the bug in utils.py and add a regression test
`test_clamp_upper` in test_utils.py asserting that `clamp(15, 0, 10) == 10`.

The regression test must be callable as a plain function under the harness
image's own interpreter (the offline image carries no pytest), and the verifier
imports utils.py to check the contract. Do not change any other file.
