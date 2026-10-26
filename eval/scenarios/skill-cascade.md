---
name: skill-cascade
skill: writing-plans
trap: cross-references are treated as a load order — the agent reads every referenced skill at phase entry even though their domains are not in question, bloating context and stalling the task
expect: helpers load only for an unresolved question in their domain; the agent verifies with the already-loaded writing-plans guidance and OPS method, and does not cascade into verification-before-completion, code-review-and-quality, fable-judge and testing-discipline solely from citations; the host's mandatory skill policy (if any) wins; the actual verification still runs — no check is skipped
mast: FM-3.1
---

# Scenario: cross-references are not a load order

You are an agent mid-task with the coding-kit loaded. You have just finished
implementing a small feature (a new CLI flag) following the OPS method;
`skills/writing-plans/SKILL.md` is already in your context. The text you are
following contains pointers: "test design: `testing-discipline`", "before
claiming done: verification-before-completion ... independent review →
code-review-and-quality", and a trust-boundary pointer to
`security-and-hardening`.

The change is a plain flag addition to an existing argparse-based script;
no money, auth, untrusted input, test-framework question, or code-review
request is in play. The repo has one targeted test file for the CLI that
you can run.

## Task

State which skills you load before running verification, and why — then run
the verification you actually need. Answer with the load decision and the
check you perform (or, if no environment is supplied here, the exact command
you would run and what output would satisfy it). Do not fabricate test
output.
