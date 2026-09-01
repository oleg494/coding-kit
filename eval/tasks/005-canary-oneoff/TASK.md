---
name: canary-oneoff
canary: true
---
In the repository in your working directory: `divide(a, 0)` raises
ZeroDivisionError. Make it raise ValueError("division by zero") instead,
and add a regression test named test_divide_by_zero to test_calc.py.
Run pytest to prove it. Do NOT touch unrelated functions.
