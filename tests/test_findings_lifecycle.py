#!/usr/bin/env python3
"""tests/test_findings_lifecycle.py — P13/P14/P15 write-path integrity.

P13: supersedes link + badge + --related existence validation.
P14: tag normalization, normalized dedup hint, source auto-promote,
     topic-style warning, topic index present.
P15: verify_cmd runs as a SHELL line (cd … && …), edit whitelist covers
     verify_cmd/file/symbol, quote-balance reject at add.
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


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-lifecycle-"))
        self.db = self.tmp / "research.db"
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args, stdin=None):
        return subprocess.run(
            [sys.executable, str(FINDINGS)] + list(args),
            input=stdin, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=self.env, timeout=120)

    def test_supersedes_link_and_badge(self):
        self._run("add", "old conclusion", "--text", "first")
        r = self._run("add", "new conclusion", "--text", "second",
                      "--supersedes", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("supersedes: 1", r.stdout)
        rs = self._run("search", "old conclusion", "--json")
        rows = json.loads(rs.stdout)
        self.assertEqual(rows[0]["id"], 1)
        self.assertEqual(rows[0]["superseded_by"], 2, rows)
        rl = self._run("list")
        self.assertIn("superseded by #2", rl.stdout)

    def test_second_supersedes_does_not_fan_out_rows(self):
        """Two `--supersedes N` links on row N must not duplicate it in
        search/list/--json (a LEFT JOIN fans out; the scalar subquery
        with MIN does not) and found/showing must agree (advisory
        2026-09-03)."""
        self._run("add", "old conclusion", "--text", "first")
        self._run("add", "new conclusion", "--text", "second",
                  "--supersedes", "1")
        self._run("add", "newer conclusion", "--text", "third",
                  "--supersedes", "1")
        rs = self._run("search", "old conclusion", "--json")
        rows = json.loads(rs.stdout)
        self.assertEqual([r["id"] for r in rows], [1], rows)
        self.assertEqual(rows[0]["superseded_by"], 2, rows)
        rl = self._run("list")
        self.assertEqual(rl.stdout.count("[1] "), 1, rl.stdout)
        self.assertIn("superseded by #2", rl.stdout)

    def test_auto_promote_url_only_and_strips_punctuation(self):
        """URL-shape only: prose 'Sec. A' must NOT fill source (it would
        silence the provenance hint); a sentence-final dot is stripped
        (advisory 2026-09-03)."""
        ra = self._run("add", "prose row", "--text", "see Sec. A for proof")
        self.assertIn("--source not set", ra.stderr, ra.stderr)
        r = self._run("show", "1")
        self.assertNotIn("source: Sec", r.stdout, r.stdout)
        self._run("add", "url row",
                  "--text", "see https://example.com/a. for proof")
        r = self._run("show", "2")
        self.assertIn("source: https://example.com/a", r.stdout)
        self.assertNotIn("source: https://example.com/a.", r.stdout)

    def test_related_nonexistent_id_refused(self):
        r = self._run("add", "orphan link row", "--text", "x",
                      "--related", "99999")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no finding with id=99999", r.stderr)

    def test_tag_normalization_at_write(self):
        self._run("add", "tagged row", "--text", "x", "--tags", "A,B  c")
        r = self._run("show", "1")
        self.assertIn("a b c", r.stdout, r.stdout)

    def test_dedup_hint_points_at_edit(self):
        self._run("add", "same topic", "--text", "one")
        r = self._run("add", "same topic", "--text", "two")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("edit id=1 instead", r.stderr)
        self.assertIn("id=2", r.stdout)

    def test_source_auto_promote_from_text(self):
        r = self._run("add", "url row",
                      "--text", "see https://example.com/a for proof")
        self.assertEqual(r.returncode, 0, r.stderr)
        rs = self._run("show", "1")
        self.assertIn("https://example.com/a", rs.stdout)

    def test_topic_style_warns(self):
        r = self._run("add", "2026-09-03 junk session", "--text", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("date-prefixed topic", r.stderr)

    def test_verify_cmd_runs_shell_line(self):
        marker = self.tmp / "verified.txt"
        cmd = f"cd {self.tmp} && python -c \"open('verified.txt','w').write('ok')\""
        r = self._run("add", "shell verify row", "--text", "x",
                      "--verify-cmd", cmd)
        self.assertEqual(r.returncode, 0, r.stderr)
        rv = self._run("verify", "1")
        self.assertEqual(rv.returncode, 0, rv.stdout + rv.stderr)
        self.assertIn("VERIFIED", rv.stdout)
        self.assertTrue(marker.is_file(), "shell line did not execute")

    def test_verify_failure_rc_and_no_stamp(self):
        self._run("add", "failing verify row", "--text", "x",
                  "--verify-cmd", "python -c \"import sys; sys.exit(3)\"")
        rv = self._run("verify", "1")
        self.assertEqual(rv.returncode, 1)
        self.assertIn("FAILED", rv.stdout)

    def test_edit_whitelist_covers_verify_cmd_file_symbol(self):
        self._run("add", "edit target", "--text", "x")
        r = self._run("edit", "1", "--verify-cmd", "python -c pass",
                      "--file", "a/b.py", "--symbol", "fn")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rs = self._run("show", "1")
        self.assertIn("a/b.py", rs.stdout)
        self.assertIn("fn", rs.stdout)

    def test_unbalanced_quotes_refused_at_add(self):
        r = self._run("add", "quote row", "--text", "plain body",
                      "--verify-cmd",
                      "python -c \"print(1 verify-cmd shape")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unbalanced", r.stderr.lower())

    def test_topic_index_present(self):
        import sqlite3
        self._run("add", "index row", "--text", "x")
        con = sqlite3.connect(self.db)
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")]
        con.close()
        self.assertIn("idx_findings_topic", names)



class DeployedParityTest(unittest.TestCase):
    """The deployed copy (~/.memory) is copy2-synced by install.py, NOT
    junctioned — a kit-only edit silently leaves prod on the old code
    (observed 2026-09-03: _compat.run without shell= raised TypeError
    from the deployed findings.py while the suite stayed green)."""

    ROOT = Path.home() / ".memory"

    def setUp(self):
        if not (self.ROOT / "db-tools" / "findings.py").is_file():
            self.skipTest("kit not deployed at ~/.memory")
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-deployed-"))
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.tmp / "research.db"),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deployed_scripts_byte_identical(self):
        import hashlib
        for rel in ("scripts/_compat.py", "scripts/memory-warmup.py"):
            kit = KIT / "memory" / rel
            dep = self.ROOT / rel
            if not dep.is_file():
                continue
            self.assertEqual(
                hashlib.sha256(kit.read_bytes()).hexdigest(),
                hashlib.sha256(dep.read_bytes()).hexdigest(),
                f"{rel} drifted from the kit — re-run scripts/install.py")

    def test_deployed_verify_runs_shell_line(self):
        """P15's Verify column names the DEPLOYED command; pin it."""
        deployed = self.ROOT / "db-tools" / "findings.py"
        marker = self.tmp / "v.txt"
        cmd = (f"cd {self.tmp} && python -c "
               f"\"open('v.txt','w').write('ok')\"")
        r = subprocess.run(
            [sys.executable, str(deployed), "add", "deployed verify",
             "--text", "x", "--verify-cmd", cmd],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rv = subprocess.run(
            [sys.executable, str(deployed), "verify", "1"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=120)
        self.assertEqual(rv.returncode, 0, rv.stdout + rv.stderr)
        self.assertTrue(marker.is_file(), "deployed verify did not run")

if __name__ == "__main__":
    unittest.main()
