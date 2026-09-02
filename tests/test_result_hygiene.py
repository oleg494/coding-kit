#!/usr/bin/env python3
"""v4.0.2 audit remediation: eval/results hygiene.

Two defect classes from the v3.5.0-v4.0.1 audit:

1. Personal-path leakage: a live trigger run recorded the operator's
   home directory (C:\\Users\\<name>\\AppData\\...) inside executor error
   strings, and the artifact was committed. Committed result JSON must
   contain no `Users\\<name>` / `Users/<name>` literals; the 2026-08-29
   trigger artifact is scrubbed to a `~` prefix.

2. Scope: this file only guards committed results. The manifest side of
   eval hygiene (scenarios/tasks/queries/baselines hashed, mutable
   results unpinned) lives in tests/test_integrity_manifest.py.

`eval/results/*.json` is the committed set plus whatever a live run just
wrote; the scan ignores subdirectories (staging dirs) so it stays
focused on the flat artifacts git tracks.
"""
import json
import re
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
RESULTS = KIT / "eval" / "results"

# Raw-byte forms: JSON-escaped backslashes count too — any
# Users\<name> / Users/<name> spelling contains one of these byte runs.
_PERSONAL = (
    re.compile(rb"Users\\\\oleg2"),
    re.compile(rb"Users/oleg2"),
    re.compile(rb"Users\\\\\\\\oleg2"),
)


def _committed_results() -> list[Path]:
    """Committed result JSONs; staging subdirectories are not tracked."""
    return sorted(p for p in RESULTS.glob("*.json")
                  if p.is_file() and not p.name.endswith(".staging"))


class ResultHygieneTest(unittest.TestCase):
    def test_committed_results_exist(self):
        self.assertTrue(_committed_results(),
                        "eval/results lost its committed artifacts?")

    def test_no_personal_path_literals(self):
        for p in _committed_results():
            with self.subTest(result=p.name):
                raw = p.read_bytes()
                for pat in _PERSONAL:
                    self.assertIsNone(pat.search(raw),
                                      f"{p.name}: personal path leaked")
                self.assertNotIn(b"oleg2", raw,
                                 f"{p.name}: username literal leaked")

    def test_scrubbed_trigger_artifact_still_parses(self):
        scrubbed = [p for p in _committed_results()
                    if p.name.startswith("trigger-20260829-093013")]
        self.assertTrue(scrubbed, "scrubbed trigger artifact missing")
        for p in scrubbed:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "trigger")


if __name__ == "__main__":
    unittest.main()
