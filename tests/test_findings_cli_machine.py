#!/usr/bin/env python3
"""tests/test_findings_cli_machine.py — machine-mode CLI tests (findings #166).

Covers the two highest-friction CLI paths with real subprocess runs against
an isolated temp DB (MEMORY_ROOT_RESEARCH_DB):
1. add --stdin      — conclusion text from stdin: no shell quoting at all.
2. search --json    — valid JSON list [{id, created, topic, tags, source,
                      snippet}, ...]; empty result -> [] with exit 0.
Human (non-flag) output must keep working unchanged.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
FINDINGS = KIT / "memory" / "db-tools" / "findings.py"


class FindingsCLIMachineModeTest(unittest.TestCase):
    """--stdin (no shell quoting) and --json (machine output)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-findings-cli-json-"))
        self.db_path = self.tmp / "research.db"
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db_path),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _findings(self, *args, stdin=None):
        data = stdin.encode("utf-8") if stdin is not None else None
        return subprocess.run(
            [sys.executable, str(FINDINGS)] + list(args),
            capture_output=True, env=self.env,
            timeout=120, input=data,
        )

    def test_stdin_add_and_json_search_workflow(self):
        tricky = 'кавычки "обе" и \'одинарные\' — плюс `backticks` & $VAR'
        r1 = self._findings(
            "add", "Quoting Survival Topic",
            "--stdin", "--tags", "cli",
            "--source", "tests/test_findings_cli_machine.py",
            stdin=tricky,
        )
        self.assertEqual(r1.returncode, 0, r1.stdout.decode('utf-8','replace') + r1.stderr.decode('utf-8','replace'))
        self.assertIn("[✓] added:", r1.stdout.decode("utf-8","replace"))

        # the tricky text survived verbatim into the DB
        con = sqlite3.connect(self.db_path)
        row = con.execute("SELECT text FROM findings WHERE id=1").fetchone()
        con.close()
        self.assertEqual(row[0], tricky)

        # human search still works
        r2 = self._findings("search", "quoting")
        self.assertEqual(r2.returncode, 0, r2.stdout.decode('utf-8','replace') + r2.stderr.decode('utf-8','replace'))
        # P9: the human line carries the highlighted topic ([Quoting])
        self.assertIn("[Quoting] Survival Topic",
                      r2.stdout.decode("utf-8", "replace"))

        # machine search: valid JSON list with the contract fields
        r3 = self._findings("search", "quoting", "--json")
        self.assertEqual(r3.returncode, 0, r3.stdout.decode('utf-8','replace') + r3.stderr.decode('utf-8','replace'))
        rows = json.loads(r3.stdout.decode("utf-8","replace"))
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["topic"], "Quoting Survival Topic")
        self.assertEqual(row["tags"], "cli")
        self.assertEqual(row["source"],
                         "tests/test_findings_cli_machine.py")
        for key in ("id", "created", "snippet"):
            self.assertIn(key, row)

        # empty result -> [] with exit 0 (not "not found" prose)
        r4 = self._findings("search", "nonexistentzzz", "--json")
        self.assertEqual(r4.returncode, 0, r4.stdout.decode('utf-8','replace') + r4.stderr.decode('utf-8','replace'))
        self.assertEqual(json.loads(r4.stdout.decode("utf-8","replace")), [])

    def test_stdin_and_text_are_mutually_exclusive(self):
        r = self._findings(
            "add", "Both Flags Topic", "--stdin", "--text", "x",
        )
        self.assertNotEqual(r.returncode, 0)

    def test_stdin_empty_is_rejected(self):
        r = self._findings("add", "Empty Stdin Topic", "--stdin", stdin="")
        self.assertNotEqual(r.returncode, 0)

    def test_stdin_win_crlf_and_no_trailing_newline(self):
        body = "line one\r\nline two with \"quotes\"\r\nline three"
        r = self._findings(
            "add", "CRLF Topic", "--stdin", stdin=body,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        con = sqlite3.connect(self.db_path)
        row = con.execute("SELECT text FROM findings WHERE id=1").fetchone()
        con.close()
        # CRLF normalized to LF (Windows pipes/here-strings send CRLF)
        self.assertEqual(row[0], body.replace("\r\n", "\n"))


if __name__ == "__main__":
    unittest.main()
