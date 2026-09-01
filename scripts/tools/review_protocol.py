#!/usr/bin/env python3
"""review_protocol.py — canonical review verdict arithmetic (wave5 Task 16).

The structured review protocol (Cloudflare-style): reviewers report
machine-checkable counts by 3-value severity —

    critical   — blocks merge (real bug, broken contract, fraud)
    warning    — must fix before proceeding (not merge-blocking alone)
    suggestion — optional improvement (never blocks)

and the verdict is RECOMPUTABLE from the counts, never a mood:

    verdict_from_counts(critical, warning) ->
        "REFUTED"              if critical > 0
        "VERIFIED WITH CAVEATS" elif warning > 2
        "VERIFIED"              otherwise

The rubric's approval bias is deliberate: a clean report plus a couple
of warnings is an approval, not a negotiation. The skill texts
(skills/fable-judge/SKILL.md, skills/code-review-and-quality/SKILL.md,
skills/requesting-code-review/SKILL.md) carry this rule as prose; their
`verdict_from_counts(...)` example lines are extracted by
tests/test_review_protocol.py and compared against this function, so
doc and code cannot drift.

Break-glass: the keyword "срочно-пропустить" (or "break-glass") skips
the verdict gate — only with a logged note naming who asked and why
(BREAK_GLASS_KEYWORDS). The note is the audit trail; no keyword, no skip.

Stdlib only; no runtime dependencies on the rest of the kit.
"""
from __future__ import annotations

BREAK_GLASS_KEYWORDS = ("срочно-пропустить", "break-glass")

VERIFIED = "VERIFIED"
CAVEATS = "VERIFIED WITH CAVEATS"
REFUTED = "REFUTED"


def verdict_from_counts(critical: int, warning: int) -> str:
    """Recompute the review verdict from severity counts.

    >>> verdict_from_counts(0, 0)
    'VERIFIED'
    >>> verdict_from_counts(0, 2)
    'VERIFIED'
    >>> verdict_from_counts(0, 3)
    'VERIFIED WITH CAVEATS'
    >>> verdict_from_counts(1, 0)
    'REFUTED'
    """
    if critical < 0 or warning < 0:
        raise ValueError("counts must be non-negative")
    if critical > 0:
        return REFUTED
    if warning > 2:
        return CAVEATS
    return VERIFIED


def is_break_glass(text: str) -> bool:
    """True when the text carries a break-glass keyword."""
    lowered = text.lower()
    return any(kw in lowered for kw in BREAK_GLASS_KEYWORDS)


if __name__ == "__main__":
    import doctest
    failures, _ = doctest.testmod()
    raise SystemExit(1 if failures else 0)
