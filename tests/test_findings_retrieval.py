#!/usr/bin/env python3
"""tests/test_findings_retrieval.py — findings search retrieval regressions.

Pins the remediated search-path defects reported 2026-10-25:

1. scoped empty/prefix retries rebuilt the parameter list WITHOUT the
   project/importance bindings, so an empty (or prefix-fallback) scoped
   query blew up with "Incorrect number of bindings supplied". Filters are
   now collected once and reused by every retry.
2. the legacy projection reused "'unknown' AS project" inside WHERE -> an
   aliased expression is invalid SQL. The SELECT alias and the WHERE
   expression are now separate.
3. --state / --verification apply in WHERE (before LIMIT): counts and pages
   agree, and a '[superseded:' tombstone (replacer deleted) still counts as
   superseded.
4. a read-only search no longer creates/migrates the store: an absent store
   is reported, not written; the desynced store is diagnosed, not healed.

Isolation: every run is a subprocess with MEMORY_ROOT_RESEARCH_DB pointed at
a temp file (the hook is pinned by test_findings_isolation.py).
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


class FindingsRetrievalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-retrieval-"))
        self.db_path = self.tmp / "research.db"
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db_path),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(FINDINGS)] + list(args),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env or self.env, timeout=120)

    def _add(self, topic, text, **kw):
        args = ["add", topic, "--text", text]
        for key, val in kw.items():
            args += ["--" + key.replace("_", "-"), str(val)]
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def _json_search(self, *args):
        r = self._run("search", *args, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    # --- defect 1: scoped retries lost their bindings ---------------------

    def test_scoped_empty_query_does_not_crash(self):
        """Empty result + --project must run the prefix retry with the SAME
        project binding (was: binding-count crash)."""
        self._add("scoped row", "scopedbodyterm alpha", project="multiproxy")
        r = self._run("search", "zzznotthere", "--project", "multiproxy")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("not found", r.stdout)
        self.assertNotIn("invalid query", r.stderr)
        self.assertNotIn("bindings", r.stderr)

    def test_scoped_prefix_retry_matches_with_filter(self):
        """A prefix hit under a project filter resolves through the prefix
        retry with the project binding intact."""
        self._add("prefix row", "prefixmatchablebody", project="multiproxy")
        self._add("other row", "prefixmatchablebody", project="coding-kit")
        r = self._run("search", "prefixmatch", "--project", "multiproxy")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("found: 1", r.stdout)

    def test_scoped_fallback_retry_keeps_importance_binding(self):
        """The P8 dot-split fallback (triggered by '=' column-filter syntax)
        must keep the importance binding instead of erroring out."""
        self._add("fallback row", "foobar body", importance="high")
        r = self._run("search", "foo=bar", "--importance", "high")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("invalid query", r.stderr)

    # --- defect 2: legacy scoped projection ------------------------------

    def test_legacy_store_scoped_filters_no_invalid_syntax(self):
        """A legacy findings table (no project/importance columns) must
        answer scoped filters instead of emitting invalid SQL."""
        legacy = self.tmp / "legacy.db"
        con = sqlite3.connect(legacy)
        con.execute(
            "CREATE TABLE findings (id INTEGER PRIMARY KEY, created TEXT NOT NULL,"
            " topic TEXT NOT NULL, text TEXT NOT NULL, tags TEXT DEFAULT '',"
            " source TEXT DEFAULT '', file TEXT DEFAULT '', symbol TEXT DEFAULT '',"
            " verify_cmd TEXT DEFAULT '', verified_at TEXT DEFAULT '')")
        con.execute("CREATE VIRTUAL TABLE findings_fts USING fts5("
                    "topic, text, content='findings', content_rowid='id')")
        con.execute("INSERT INTO findings VALUES "
                    "(1, '2026-09-01', 'legacy-t', 'legacybodyterm', '', '', '', '', '', '')")
        con.execute("INSERT INTO findings_fts(rowid, topic, text) VALUES "
                    "(1, 'legacy-t', 'legacybodyterm')")
        con.commit()
        con.close()
        env = dict(self.env, MEMORY_ROOT_RESEARCH_DB=str(legacy))

        r_plain = self._run("search", "legacybodyterm", "--json", env=env)
        self.assertEqual(r_plain.returncode, 0, r_plain.stdout + r_plain.stderr)
        self.assertEqual(len(json.loads(r_plain.stdout)), 1)

        r_proj = self._run("search", "legacybodyterm", "--project", "foo", env=env)
        self.assertEqual(r_proj.returncode, 0, r_proj.stdout + r_proj.stderr)
        self.assertIn("not found", r_proj.stdout)
        self.assertNotIn("invalid query", r_proj.stderr)

        r_imp = self._run("search", "legacybodyterm", "--importance", "high", env=env)
        self.assertEqual(r_imp.returncode, 0, r_imp.stdout + r_imp.stderr)
        self.assertIn("not found", r_imp.stdout)

        # The read must NOT migrate the legacy schema (no project column).
        con = sqlite3.connect(legacy)
        cols = {c[1] for c in con.execute("PRAGMA table_info(findings)")}
        con.close()
        self.assertNotIn("project", cols)

    # --- defect 3: lifecycle filtering before LIMIT -----------------------

    def test_state_filter_applies_before_limit(self):
        self._add("old one", "lifecycleprobe alpha")
        self._add("correction", "lifecycleprobe beta", supersedes=1)
        self._add("keep one", "lifecycleprobe gamma")
        self._add("keep two", "lifecycleprobe delta")

        r_cur = self._run("search", "lifecycleprobe", "--state", "current",
                          "--limit", "2")
        self.assertEqual(r_cur.returncode, 0, r_cur.stdout + r_cur.stderr)
        # COUNT honours the filter (3 current), so the page is 2 of 3 —
        # impossible if the lifecycle filter were applied AFTER LIMIT.
        self.assertIn("found: 3, showing: 2", r_cur.stdout)

        r_sup = self._run("search", "lifecycleprobe", "--state", "superseded")
        self.assertEqual(r_sup.returncode, 0, r_sup.stdout + r_sup.stderr)
        self.assertIn("found: 1, showing: 1", r_sup.stdout)

    def test_superseded_tombstone_counts_as_superseded(self):
        self._add("old one", "tombstoneprobe alpha")
        self._add("correction", "tombstoneprobe beta", supersedes=1)
        self._add("keep one", "tombstoneprobe gamma")
        # Deleting the replacer leaves a '[superseded:' tombstone in the old
        # row's text; it must stay superseded, never resurface as current.
        r_del = self._run("del", "2")
        self.assertEqual(r_del.returncode, 0, r_del.stdout + r_del.stderr)

        r_sup = self._run("search", "tombstoneprobe", "--state", "superseded")
        self.assertEqual(r_sup.returncode, 0, r_sup.stdout + r_sup.stderr)
        self.assertIn("found: 1, showing: 1", r_sup.stdout)

        r_cur = self._run("search", "tombstoneprobe", "--state", "current")
        self.assertEqual(r_cur.returncode, 0, r_cur.stdout + r_cur.stderr)
        self.assertIn("found: 1, showing: 1", r_cur.stdout)

    def test_verification_filter(self):
        self._add("unverified row", "verifyprobe alpha")
        self._add("verifiable row", "verifyprobe beta", verify_cmd="exit 0")
        self._add("other row", "verifyprobe gamma")
        con = sqlite3.connect(self.db_path)
        con.execute("UPDATE findings SET verified_at = '2026-01-01' WHERE id = 2")
        con.commit()
        con.close()

        r_ver = self._run("search", "verifyprobe", "--verification", "verified")
        self.assertEqual(r_ver.returncode, 0, r_ver.stdout + r_ver.stderr)
        self.assertIn("found: 1, showing: 1", r_ver.stdout)

        r_unv = self._run("search", "verifyprobe", "--verification", "unverified")
        self.assertEqual(r_unv.returncode, 0, r_unv.stdout + r_unv.stderr)
        self.assertIn("found: 2, showing: 2", r_unv.stdout)

    # --- defect 4: read-only query never creates/migrates ----------------

    def test_absent_store_is_not_created(self):
        missing = self.tmp / "missing" / "research.db"
        env = dict(self.env, MEMORY_ROOT_RESEARCH_DB=str(missing))
        r = self._run("search", "anything", env=env)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("no findings store", r.stderr)
        self.assertFalse(missing.exists(),
                         "read-only search must not create the store")

    def test_desynced_store_is_reported_not_healed(self):
        self._add("desync row", "desyncprobe body")
        con = sqlite3.connect(self.db_path)
        con.execute("DELETE FROM findings_fts WHERE rowid = 1")
        con.commit()
        con.close()
        r = self._run("search", "desyncprobe")
        # A read-only query diagnoses the desync instead of writing a repair.
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("desynced", r.stderr)

    def test_search_still_exits_zero_with_results_and_logs(self):
        """Guard against over-tightening: a normal search on an existing
        store keeps rc 0, the JSON shape, and search telemetry."""
        self._add("normal row", "normalprobe body", project="coding-kit")
        rows = self._json_search("normalprobe")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["topic"], "normal row")
        for key in ("id", "created", "topic", "tags", "source", "snippet"):
            self.assertIn(key, rows[0])
        con = sqlite3.connect(self.db_path)
        n = con.execute("SELECT COUNT(*) FROM search_log").fetchone()[0]
        con.close()
        self.assertGreaterEqual(n, 1)


if __name__ == "__main__":
    unittest.main()