---
name: bounded-bug
tier: STANDARD
---
In utils.py, `clamp(val, low, high)` returns `low` when `val > high` instead of returning `high`.
Fix the bug in utils.py and add a regression test `test_clamp_upper` in test_utils.py verifying that `clamp(15, 0, 10) == 10`.
Run pytest to verify.
