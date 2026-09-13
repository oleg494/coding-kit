---
name: requesting-code-review
description: Use when completing tasks, implementing major features, or before merging to verify work meets requirements
license: MIT
metadata:
  version: "4.6.0"
---

# Requesting Code Review

Review the complete change at a coherent verification boundary. Follow the
host's delegation rules; use an available reviewer when independent review
is required or materially useful. A skill does not create a missing agent
capability or authorize commits, publication, or a merge.

## When to review

- Review major features and changes before merge, covering their requirements
  and affected execution paths.
- For parallel work, review every contribution and the integrated behavior;
  one integrated review may cover coupled tasks. Do not require a separate
  blocking review after every worker or microstep.
- Seek a fresh perspective when evidence stalls, a complex defect persists,
  or the change has a consequential trust or compatibility boundary.
- For a small bounded change, proportionate inline review is sufficient unless
  the host, user, or applicable merge policy requires independent signoff.

## Prepare a self-contained review brief

Use the reviewer's actual host-provided name and capabilities. No external
prompt template is required. Supply:

- **Goal:** requested behavior, acceptance criteria and explicit non-goals.
- **Scope:** diff-review or whole-system audit, changed files, coupled interfaces,
  and relevant source context. Use the scope rules in `code-review-and-quality`.
- **Compared states:** the actual baseline and candidate. For uncommitted work,
  provide the working-tree diff or before/after snapshots; do not invent SHAs
  or create commits just to fill a review template.
- **Evidence:** commands and observed results, checked state, reproduction steps,
  and any verification gaps. Never present a dry-run as a behavior result.
- **Output:** actionable findings with severity, file/line, contract impact and
  supporting evidence. Use `critical`, `warning`, `suggestion` and the canonical
  report/verdict rules in `code-review-and-quality` and `fable-judge`.

The reviewer needs the work product and relevant constraints, not an entire
session transcript. In diff-review, suppress hypothetical or unrelated findings;
whole-system audits retain their broader invariant scope.

If independent review is unavailable, finish reachable implementation and
verification, report the unavailable signoff, and do not claim it was obtained.
Do not cross a merge or approval boundary that requires that signoff.

## Act on findings

- Check each finding against the actual contract and source; push back with
  evidence when it is incorrect.
- Repair material in-scope defects and verify the repair. Suggestions do not
  become automatic blockers or new requirements.
- Resolve outcome-changing ambiguity before dependent changes; continue
  independent authorized fixes. Follow `receiving-code-review`.
- Keep execution tracking separate from reviewer-owned approval. Reuse valid
  evidence, but obtain new checks or review when changes invalidate it.
- Report remaining material gaps rather than silently approving, fabricating
  review, or marking the reviewer's checkboxes yourself.

---

> Source: obra/superpowers (MIT). Adapted for coding-kit: host-aware review dispatch and coherent change boundaries.
