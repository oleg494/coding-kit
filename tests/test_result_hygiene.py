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

The committed set is every eval/results file git tracks — flat JSONs and
subdirectory packages alike (the 2026-09-13 research packages live one
level down). Local staging output that was never committed is out of
scope by construction: the file list comes from `git ls-files`, so a
live run's dirt never reddens this suite.
"""
import json
import re
import subprocess
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


def _tracked_result_files() -> list[Path]:
    """Result files git actually tracks (flat + subdirectory packages)."""
    out = subprocess.run(
        ["git", "-C", str(KIT), "ls-files", "--", "eval/results"],
        capture_output=True, check=True).stdout.decode("utf-8").splitlines()
    return sorted(KIT / rel for rel in out if rel.endswith(".json"))


class ResultHygieneTest(unittest.TestCase):
    def test_committed_results_exist(self):
        self.assertTrue(_tracked_result_files(),
                        "eval/results lost its committed artifacts?")

    def test_no_personal_path_literals(self):
        for p in _tracked_result_files():
            with self.subTest(result=str(p.relative_to(KIT))):
                raw = p.read_bytes()
                for pat in _PERSONAL:
                    self.assertIsNone(pat.search(raw),
                                      f"{p.name}: personal path leaked")
                self.assertNotIn(b"oleg2", raw,
                                 f"{p.name}: username literal leaked")

    def test_tracked_results_still_parse(self):
        # Byte surgery on evidence artifacts (path scrubs) must not break
        # parsing: every tracked result JSON loads, and the two shapes the
        # 2026-09-13 packages use survive with their semantic keys intact.
        for p in _tracked_result_files():
            with self.subTest(result=str(p.relative_to(KIT))):
                data = json.loads(p.read_text(encoding="utf-8"))
        probe = RESULTS / "autonomous-knowledge-20260913" / "native-adapter-result.json"
        if probe.is_file():
            doc = json.loads(probe.read_text(encoding="utf-8"))
            self.assertEqual(doc["rc"], 0)
            inner = json.loads(doc["stdout"])
            self.assertEqual(len(inner["checks"]), 9)
        for name, expected_cases in (("recovery-before.json", 6),
                                     ("recovery-after.json", 6)):
            probe = RESULTS / "knowledge-procedure-20260913" / name
            if probe.is_file():
                doc = json.loads(probe.read_text(encoding="utf-8"))
                self.assertEqual(len(doc), expected_cases)
                self.assertEqual([d["case"] for d in doc],
                                 ["foreign", "crlf", "binary",
                                  "anchor_failure", "legacy", "preview"])


if __name__ == "__main__":
    unittest.main()
