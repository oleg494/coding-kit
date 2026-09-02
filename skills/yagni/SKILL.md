---
name: yagni
description: 'Always-on. Law of minimalism: don''t build what wasn''t asked for. Abstraction with one consumer → inline. New dependency → only if the pain is measurable. Dead code → delete. "For the future" → not a reason. Use for ANY code change.'
metadata:
  version: "4.1.0"
---

# YAGNI — law of minimalism

Always-on skill. Apply before every code change.

## Rules

1. **Abstraction with one consumer → inline.** Extract only when a second one appears. Can you remove a layer — same behavior, less code? → remove it.

2. **New dependency → only if the pain is measurable.** 30 lines of your own code beat 300KB of someone else's. Start with stdlib/native. moment.js for a single format = no.

3. **Code that can be removed without changing behavior → remove it.** Dead code is not commented out forever.

4. **"For the future" is not a sufficient reason.** Build for the current task, not a hypothetical one.

5. **Stop when the next abstraction doesn't pay rent this week.** An abstraction must pay off now, not "someday".

## Filter before every change

- **DRY** — duplicated in 3+ places? → shared source. 2 places? → tolerate.
- **KISS** — does the simpler option close the task? → take the simple one. Complexity is justified only when the simple one doesn't cut it.
- **YAGNI** — is this needed NOW? → no → don't do it.

## Antipatterns

- Generic EventBus with a middleware pipeline for a single notification → just call the function.
- Abstract factory for two similar components → two direct components.
- Config-driven form builder for three forms → three form components.
- "Might come in handy" → it won't.

## Code review through a YAGNI lens

- Can this abstraction be removed without changing behavior? → remove it.
- Is this dependency actually needed? → check whether stdlib solves it.
- Is this code used? → no → remove it.
- Is this "for the future"? → remove it.

## Quote

"Three similar lines of code is better than a premature abstraction. Implement the naive, obviously-correct version first. Optimize only after correctness is proven with tests."