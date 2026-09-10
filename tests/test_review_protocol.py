#!/usr/bin/env python3
"""Observable verdict precedence and invalid-count handling."""
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts" / "tools"))

import review_protocol

class VerdictFromCountsTest(unittest.TestCase):
    """Counts determine the verdict; missing evidence cannot earn approval."""

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
    def test_unverified_claims_yield_caveats(self):
        self.assertEqual(
            review_protocol.verdict_from_counts(0, 0, unverified=1),
            "VERIFIED WITH CAVEATS",
        )
        self.assertEqual(
            review_protocol.verdict_from_counts(0, 2, unverified=1),
            "VERIFIED WITH CAVEATS",
        )
        self.assertEqual(
            review_protocol.verdict_from_counts(0, 0, unverified=5),
            "VERIFIED WITH CAVEATS",
        )

    def test_unverified_ignored_when_critical_present(self):
        self.assertEqual(
            review_protocol.verdict_from_counts(1, 0, unverified=1),
            "REFUTED",
        )
        self.assertEqual(
            review_protocol.verdict_from_counts(2, 4, unverified=3),
            "REFUTED",
        )

    def test_negative_unverified_rejected(self):
        with self.assertRaises(ValueError):
            review_protocol.verdict_from_counts(0, 0, unverified=-1)

if __name__ == "__main__":
    unittest.main()
