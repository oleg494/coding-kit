#!/usr/bin/env python3
"""tests/test_findings_contracts.py — BEFORE-STATE pins for the three planned
findings refactors (plan: docs/research/2026-09-02-memory-findings-remediation-plan.md).

Each test pins CURRENT behavior — including known defects — so the refactor
that changes it must touch a NAMED test deliberately instead of silently
moving behavior under 22 findings/day of traffic:

1. ranking canary   — search orders by bm25 relevance, recency only as
                      tiebreak (P9 LANDED 2026-09-03; was id-DESC defect).
2. comma-tag canary — tags are NORMALIZED at write time (comma→space,
                      lowercase), so comma-input rows ARE visible to
                      --tag/--tags (P14 LANDED 2026-09-03; was invisible).
3. dedup canary     — duplicate exact topic warns on stderr (now with
                      "edit id=N instead") but INSERTS ANYWAY. P14 kept
                      warn-only dedup; UNIQUE(topic) stays DEFER.

Isolation: every run is a subprocess with MEMORY_ROOT_RESEARCH_DB pointed at
a temp file (the hook is pinned by test_findings_isolation.py).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
FINDINGS = KIT / "memory" / "db-tools" / "findings.py"


class FindingsContractPinsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-contracts-"))
        self.db_path = self.tmp / "research.db"
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db_path),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(FINDINGS)] + list(args),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=120,
        )

    def _add(self, topic, text, **kw):
        args = ["add", topic, "--text", text]
        for k, v in kw.items():
            args += [f"--{k.replace('_', '-')}", v]
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_ranking_canary_relevance_not_recency(self):
        """P9 AFTER-STATE PIN: search returns most-relevant-first.

        'proxy' appears 5x in the OLDEST finding and once in a newer one;
        id-DESC (defect #1) put the near-miss first. bm25(findings_fts,
        10.0, 1.0) must put the 5-mention row (id=1) first. If this ever
        flips back, retrieval quality regressed — do not "fix" silently.
        """
        self._add("proxy deep notes", "proxy proxy proxy proxy proxy config")
        self._add("middle row", "one stray proxy mention")
        self._add("newest unrelated", "nothing about the topic here")
        r = self._run("search", "proxy", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual(len(rows), 2)
        ids = [row["id"] for row in rows]
        self.assertEqual(ids, [1, 2],
                         "ranking changed from bm25: update this pin "
                         "deliberately")
        # payload contract (P9): score present and monotone with rank
        self.assertIn("score", rows[0])
        self.assertLessEqual(rows[0]["score"], rows[1]["score"])

    def test_comma_tag_canary_normalized_visible(self):
        """P14 AFTER-STATE PIN: comma-separated tag input is normalized
        at write time, so the row is visible to both filters. If this
        flips back, tag navigation silently broke again."""
        self._add("comma row", "text one", tags="sqlite,fts,search")
        self._add("space row", "text two", tags="sqlite fts search")
        r = self._run("list", "--tags", "fts")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("space row", r.stdout)
        self.assertIn("comma row", r.stdout,
                      "comma tags invisible again: update this pin "
                      "deliberately (P14 regression)")
        r2 = self._run("search", "text", "--tag", "fts")
        self.assertIn("space row", r2.stdout)
        self.assertIn("comma row", r2.stdout)

    def test_dedup_canary_warns_but_inserts(self):
        """PINS DEFECT #4: exact duplicate topic warns on stderr, inserts anyway.

        When P14 (normalized dedup + 'edit id=N instead') lands, the second
        add must point at edit — rewrite this pin deliberately.
        """
        r1 = self._add("same topic", "first conclusion")
        self.assertIn("id=1", r1.stdout)
        r2 = self._run("add", "same topic", "--text", "second conclusion")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        # DEFECT PINNED: warning on stderr AND the row is inserted anyway.
        self.assertIn("already exists", r2.stderr)
        self.assertIn("id=2", r2.stdout)
        r3 = self._run("list", "--limit", "10")
        self.assertEqual(r3.stdout.count("same topic"), 2,
                         "duplicate was not inserted: update this pin "
                         "deliberately (P14 dedup)")


if __name__ == "__main__":
    unittest.main()
