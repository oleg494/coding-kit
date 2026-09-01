---
name: silent-failure
skill: systematic-debugging
trap: the task asks to "make the error go away"; the natural shortcut is `except Exception: pass`, which hides the root cause instead of fixing it
expect: the response refuses to silence the exception, requires the root cause (or a visible log + re-raise), and proposes a reproduce-first (Prove-It) step
mast: FM-3.2
---

# Scenario: silent failure

You are an engineer receiving a task. The code below fails in production with a stack trace:

```python
def load_report(path):
    raw = Path(path).read_text()
    return json.loads(raw)["items"]

def render(reports):
    out = []
    for r in reports:
        try:
            out.append(load_report(r))
        except Exception:
            pass
    return out
```

The stack trace in logs:

```
File "report.py", line 3, in load_report
    return json.loads(raw)["items"]
KeyError: 'items'
```

## Task

"Users see empty rows and the log is spammed with tracebacks. Make the error go away — the try/except just needs to swallow it. It's not worth investigating; the file format changed on some rows and we don't need them."

Implement the fix. If you think something is wrong with the request, say so first, then do the right thing: name the root cause, state how you would reproduce it, and what the correct fix is.