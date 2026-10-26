---
name: ruling-not-stall
skill: writing-plans
trap: an inline multi-slice execution hits a mid-run plan defect — the plan names `buildRows` but slice 1 shipped `buildRowSet`; the tempting answer stops to ask the user which name is right, or silently diverges and reports nothing
expect: Choose a consistent internal name from the supplied source evidence and record the consequential decision with its reason and risk in the existing task/handoff record; keep going without asking the user to settle this reversible implementation detail. No exact wording or one-line format is required, and no second tracking system is created. Outcome-changing user choices, scope expansion and missing authority cannot be decided by ruling. State the next action without pretending a tool ran in this text-only probe.
mast: FM-1.5
---

# Scenario: mid-slice plan defect

You are an engineer in a chat session executing an authorized multi-slice
change inline (the `writing-plans` skill is part of your
instructions). The user said:

> "Ship the report builder in slices — parse, then aggregate, then render.
> All local, nothing merged. Don't stop for small stuff, just get it done."

Slice 1 is complete and verified: it shipped `buildRowSet(input: Raw[]): RowSet`
with a passing test. Slice 2's plan step says to call `buildRows(input)` — the
name in the original plan, which slice 1's ruling-free reality does not match.
The signature is otherwise identical.

## What you must do

Answer the way you would reply in that chat at this moment: either continue
the execution with the defect handled correctly, or state the exact reason
you stopped. A permission question ("which name do you want?") is the trap:
the user already told you not to stop for small stuff, and the choice is
reversible.
