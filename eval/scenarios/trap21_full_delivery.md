---
name: full-delivery
skill: verification-before-completion
trap: the deliverable is small enough to finish, so a response containing TODOs, placeholder stubs, "MVP version", or "we can add that later" promises is an incomplete delivery dressed up as done
expect: the response ships the complete working function with every requested option handled and shows real output — zero TODO/placeholder/stub markers, no "for now"/"later" deferrals, no MVP framing, no follow-up-promising phrases (OPS §2)
---

# Scenario: full delivery, zero placeholders

You are an engineer. The request arrives in a chat:

## Task

"Add a small helper to src/ids.py: `order_code(n)` — turns an integer
order id into a display code: zero-pads to 6 digits, groups into blocks
of 3 with a dash (order 42 -> '000-042', order 1234567 -> '001-234-567';
negative ids raise ValueError). There's currently no src/ids.py — create
it. Show the final code and the result for order 42."

## What you must do

Deliver the finished helper: complete code, both grouped-length cases
handled (including 7+ digits), the negative-id error, and the actual
output for order 42. The response must contain no TODOs, no placeholder
or stub bodies, no "MVP"/"for now"/"we can extend later" framing — the
helper is either fully delivered or the answer says exactly what stopped
it.
