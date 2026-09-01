#!/usr/bin/env python3
"""Wave 5 v3.9.0 Task 16: Cloudflare-style structured review protocol.

Contract:
- "What NOT to Flag" preamble in every review-facing skill
  (code-review-and-quality, requesting-code-review, fable-judge):
  no theoretical risks / no defense-in-depth when primary suffices /
  no issues in unchanged code / no "consider library X".
- 3-value severity: critical / warning / suggestion, machine-checkable
  counts in the report format.
- Judge rubric with approval bias — verdict RECOMPUTABLE from counts:
  critical > 0 -> REFUTED; else warning <= 2 -> VERIFIED; else
  VERIFIED WITH CAVEATS. The canonical implementation is
  verdict_from_counts(critical, warning) -> str in
  scripts/tools/review_protocol.py; the skill text carries the same
  rule as a docblock example, and tests extract that example from the
  skill text and compare behavior with the canonical function.
- Break-glass keyword ("срочно-пропустить" / "break-glass"): skipping
  the gate is allowed only with a logged note.

Run: python -m pytest tests/test_review_protocol.py -v
"""
import re
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts" / "tools"))

import review_protocol

REVIEW_SKILLS = (
    KIT / "skills" / "code-review-and-quality" / "SKILL.md",
    KIT / "skills" / "requesting-code-review" / "SKILL.md",
    KIT / "skills" / "fable-judge" / "SKILL.md",
)


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


class NotToFlagPreambleTest(unittest.TestCase):
    """Every review-facing skill carries the NOT-to-flag list."""

    NEEDLES = (
        "what not to flag",
        "theoretical",
        "defense-in-depth",
        "unchanged code",
        "consider library",
    )

    def test_all_review_skills_carry_preamble(self):
        for md in REVIEW_SKILLS:
            hay = _norm(md.read_text(encoding="utf-8"))
            for needle in self.NEEDLES:
                self.assertIn(needle, hay,
                              f"{md.parent.name}: missing NOT-to-flag: {needle}")


class SeverityScaleTest(unittest.TestCase):
    """3-value severity with machine-checkable counts."""

    def test_three_values_named_in_review_skill(self):
        text = (KIT / "skills" / "code-review-and-quality" / "SKILL.md"
                ).read_text(encoding="utf-8")
        hay = _norm(text)
        for sev in ("critical", "warning", "suggestion"):
            self.assertIn(sev, hay, f"severity tier missing: {sev}")
        self.assertNotIn("nit (optional)", hay,
                         "the old 5-value scale must be replaced")
        self.assertNotIn(", required,", hay,
                         "the old 5-value scale must be replaced")

    def test_counts_are_machine_checkable(self):
        text = (KIT / "skills" / "code-review-and-quality" / "SKILL.md"
                ).read_text(encoding="utf-8")
        hay = _norm(text)
        for needle in ("counts", "critical:", "warning:", "suggestion:"):
            self.assertIn(needle, hay,
                          f"report format must be machine-checkable: {needle}")


class VerdictFromCountsTest(unittest.TestCase):
    """verdict_from_counts: canonical implementation + skill docblock."""

    def test_zero_findings_verified(self):
        self.assertEqual(review_protocol.verdict_from_counts(0, 0), "VERIFIED")

    def test_few_warnings_verified(self):
        self.assertEqual(review_protocol.verdict_from_counts(0, 1), "VERIFIED")
        self.assertEqual(review_protocol.verdict_from_counts(0, 2), "VERIFIED")

    def test_many_warnings_caveats(self):
        self.assertEqual(review_protocol.verdict_from_counts(0, 3),
                         "VERIFIED WITH CAVEATS")
        self.assertEqual(review_protocol.verdict_from_counts(0, 10),
                         "VERIFIED WITH CAVEATS")

    def test_any_critical_refuted(self):
        self.assertEqual(review_protocol.verdict_from_counts(1, 0), "REFUTED")
        self.assertEqual(review_protocol.verdict_from_counts(3, 7), "REFUTED")

    def test_negative_counts_rejected(self):
        with self.assertRaises(ValueError):
            review_protocol.verdict_from_counts(-1, 0)
        with self.assertRaises(ValueError):
            review_protocol.verdict_from_counts(0, -2)

    def test_docblock_example_in_fable_judge_matches_canonical(self):
        """Extract the `verdict_from_counts(...)` example lines from the
        fable-judge skill text and compare their outcomes with the
        canonical function — the doc is executable spec."""
        text = (KIT / "skills" / "fable-judge" / "SKILL.md").read_text(
            encoding="utf-8")
        calls = re.findall(
            r"verdict_from_counts\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*(?:==|->)\s*"
            r"\"(VERIFIED WITH CAVEATS|VERIFIED|REFUTED)\"", text)
        self.assertGreaterEqual(len(calls), 3,
                                "skill text must carry >=3 verdict examples")
        for c, w, expected in calls:
            self.assertEqual(review_protocol.verdict_from_counts(int(c), int(w)),
                             expected,
                             f"docblock example ({c}, {w}) drifts from code")


class BreakGlassTest(unittest.TestCase):
    """Break-glass keyword skips the gate — with a logged note."""

    KEYWORDS = ("срочно-пропустить", "break-glass")

    def test_keywords_named_in_fable_judge(self):
        text = (KIT / "skills" / "fable-judge" / "SKILL.md").read_text(
            encoding="utf-8")
        hay = _norm(text)
        for kw in self.KEYWORDS:
            self.assertIn(kw, hay, f"break-glass keyword missing: {kw}")

    def test_logged_note_demanded(self):
        text = (KIT / "skills" / "fable-judge" / "SKILL.md").read_text(
            encoding="utf-8")
        hay = _norm(text)
        self.assertIn("logged note", hay,
                      "break-glass must demand a logged note")


class RecomputableVerdictTest(unittest.TestCase):
    """Judge rubric: approval bias, verdict recomputable from counts."""

    def test_fable_judge_rubric_present(self):
        text = (KIT / "skills" / "fable-judge" / "SKILL.md").read_text(
            encoding="utf-8")
        hay = _norm(text)
        self.assertIn("approval bias", hay)
        self.assertIn("recomputable", hay)

    def test_fable_judge_names_the_function(self):
        text = (KIT / "skills" / "fable-judge" / "SKILL.md").read_text(
            encoding="utf-8")
        self.assertIn("verdict_from_counts(critical, warning)", text,
                      "skill must name the canonical function")


if __name__ == "__main__":
    unittest.main()
