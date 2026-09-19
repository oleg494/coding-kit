#!/usr/bin/env python3
"""tests/test_supersedes_resolution.py — supersede resolution contract.

The documented consumer protocol (AGENTS.md routing) is:
    found -> check lifecycle badges: [superseded by #N] -> resolve to #N
    before use.
These tests pin the surfaces an agent actually uses to follow it:

1. `show` on a superseded row must PRINT the replacing id (the agent sees
   the badge only on the search line; if it drills into the row first,
   "resolve to #N" is impossible without the id).
2. `show` on a replacing row must print which id it supersedes.
3. Deleting the replacing row must leave the superseded row marked
   tombstoned (dangling supersedes must not resurrect the stale text as
   the apparent current conclusion).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
FINDINGS = KIT / "memory" / "db-tools" / "findings.py"


class SupersedesResolutionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-supersedes-"))
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.tmp / "research.db"),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(FINDINGS)] + list(args),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=self.env, timeout=120)

    def _seed_pair(self):
        self._run("add", "stale beta", "--text", "old wrong conclusion")
        self._run("add", "beta corrected", "--text", "right conclusion",
                  "--supersedes", "1")

    def test_show_superseded_prints_replacing_id(self):
        self._seed_pair()
        r = self._run("show", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("superseded by #2", r.stdout,
                      "drilling into a stale row must name the replacer id")

    def test_show_replacing_prints_superseded_id(self):
        self._seed_pair()
        r = self._run("show", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("replaces: #1", r.stdout,
                      "the current row must name what it replaced")

    def test_deleting_replacer_tombstones_stale_row(self):
        """Dangling supersedes link after `del` of the replacer: the stale
        row must still be marked (not silently current again)."""
        self._seed_pair()
        self._run("del", "2")
        r = self._run("show", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("superseded", r.stdout,
                      "stale row must not silently become current "
                      "when its replacer was deleted")
        rlist = self._run("list")
        self.assertIn("superseded", rlist.stdout)


if __name__ == "__main__":
    unittest.main()
