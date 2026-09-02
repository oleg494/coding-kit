#!/usr/bin/env python3
"""tests/test_findings_migration.py — the restore-bomb (defect D-C).

External-content FTS5 is kept in sync by INSERT/UPDATE/DELETE triggers
(findings_db.SCHEMA), but rows that EXISTED BEFORE the virtual table was
created are never indexed: CREATE TRIGGER has no backfill. Repro path:
restore a pre-FTS backup (or any db created by an older schema) over
research.db -> connect() soft-migrates the columns and creates findings_fts
-> every old finding becomes permanently invisible to search while stats/
list look healthy and PRAGMA integrity_check passes.

Pinned contract after P5:
1. connect() on a pre-FTS db WITH rows makes those rows searchable;
2. connect() is idempotent (second call changes nothing);
3. `findings.py doctor` exits 0 on a healthy db and detects+heals an
   FTS/table desync (rebuild), exiting non-zero only if healing fails.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
DB_TOOLS = KIT / "memory" / "db-tools"
FINDINGS = DB_TOOLS / "findings.py"

# Schema as it looked BEFORE findings_fts existed (the backup era).
PRE_FTS_SCHEMA = """
CREATE TABLE findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    topic TEXT NOT NULL,
    text TEXT NOT NULL,
    tags TEXT DEFAULT '',
    source TEXT DEFAULT ''
);
CREATE TABLE links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL,
    to_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'related',
    note TEXT DEFAULT '',
    created TEXT NOT NULL
);
"""


def _seed_pre_fts(path):
    con = sqlite3.connect(path)
    con.executescript(PRE_FTS_SCHEMA)
    con.execute(
        "INSERT INTO findings (created, topic, text) VALUES "
        "('2026-08-01 10:00', 'ancient row', 'knowledge about trigram widgets')")
    con.execute(
        "INSERT INTO findings (created, topic, text) VALUES "
        "('2026-08-02 10:00', 'second old row', 'more widget lore')")
    con.commit()
    con.close()


class PreFtsMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-migration-"))
        self.db = self.tmp / "research.db"
        _seed_pre_fts(self.db)
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db),
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

    def test_pre_existing_rows_searchable_after_migration(self):
        """RED before P5: MATCH returns [] because the triggers only fire on
        NEW writes; the two seeded rows are invisible forever."""
        r = self._run("search", "trigram", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        import json
        rows = json.loads(r.stdout)
        self.assertEqual(len(rows), 1,
                         f"pre-FTS row invisible to search after connect() "
                         f"migration — FTS backfill missing: {r.stdout}")
        self.assertEqual(rows[0]["topic"], "ancient row")

    def test_migration_is_idempotent(self):
        """Two connects must not duplicate index rows or corrupt the table.
        Query 'row' — the exact token shared by both seeded topics ('ancient
        row', 'second old row'); 'widget' would hit the unicode61 no-stemming
        gap (row 1 text says 'widgets', row 2 'widget')."""
        self._run("list")       # connect #1 (via subprocess)
        self._run("list")       # connect #2
        r = self._run("search", "row", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        import json
        rows = json.loads(r.stdout)
        ids = [row["id"] for row in rows]
        self.assertEqual(sorted(ids), [1, 2],
                         f"expected both rows exactly once, got {ids}")
        # direct shadow-size pin: connect()'s backfill must leave the
        # index EXACTLY the size of the content table (no bloat, no
        # stale docsize rows from repeated rebuilds)
        con = sqlite3.connect(self.db)
        n_fts = con.execute(
            "SELECT COUNT(*) FROM findings_fts_docsize").fetchone()[0]
        n_tab = con.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        con.close()
        self.assertEqual(n_fts, n_tab,
                         "FTS index row count must equal table")


class DoctorCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-doctor-"))
        self.db = self.tmp / "research.db"
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db),
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

    def test_doctor_ok_on_healthy_db(self):
        self._run("add", "healthy", "--text", "all good")
        r = self._run("doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)
        # detection power pin: a healthy store must NOT report a desync,
        # else "always rebuilds" and "detects" are indistinguishable
        self.assertNotIn("desync", r.stdout.lower())
        self.assertNotIn("integrity-check failed", r.stdout.lower())

    def test_doctor_detects_and_heals_partial_desync(self):
        """PARTIAL desync (index non-empty but incomplete) is doctor's
        domain: connect()'s backfill only fires on the empty-index case
        (reads must stay cheap), so a lost trigger row survives until
        doctor runs, detects count mismatch, rebuilds, re-verifies."""
        self._run("add", "row one", "--text", "findme alpha")
        self._run("add", "row two", "--text", "findme beta")
        con = sqlite3.connect(self.db)
        con.execute("DELETE FROM findings_fts WHERE rowid = 1")
        con.commit()
        n_fts = con.execute(
            "SELECT COUNT(*) FROM findings_fts_docsize").fetchone()[0]
        con.close()
        self.assertEqual(n_fts, 1, "fixture must leave a PARTIAL desync")
        r = self._run("doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("findings=2", r.stdout, r.stdout)
        self.assertIn("indexed=1", r.stdout, r.stdout)
        # healed: search finds the deleted row again
        r2 = self._run("search", "alpha", "--json")
        self.assertIn("row one", r2.stdout)

    def test_doctor_rank1_detects_stale_content_equal_counts(self):
        """Stale index content with EQUAL counts is invisible to the count
        comparison and to rank=0 integrity-check (shadow-internal only,
        SQLite docs §6.7); rank=1 raises checksum mismatch, so doctor must
        detect and heal it. Fixture drops the triggers first so the
        out-of-band UPDATE desyncs index vs table."""
        self._run("add", "stale row", "--text", "alpha beta gamma")
        con = sqlite3.connect(self.db)
        con.execute("DROP TRIGGER findings_au")
        con.execute("UPDATE findings SET text = 'zzz qqq www' WHERE id = 1")
        con.commit()
        n_fts = con.execute(
            "SELECT COUNT(*) FROM findings_fts_docsize").fetchone()[0]
        n_tab = con.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        con.close()
        self.assertEqual(n_fts, n_tab, "fixture must keep counts equal")
        r = self._run("doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("integrity-check failed", r.stdout.lower(),
                      "rank=1 must NAME the stale-content detection; "
                      "counts agree so the desync line cannot fire")
        r2 = self._run("search", "zzz", "--json")
        self.assertIn("stale row", r2.stdout,
                      "healed index must serve the NEW content")

    def test_doctor_integrity_check_rank1_passes_on_healthy(self):
        """The rank=1 form is the real content detector (docs §6.7): it
        must run clean on a healthy store — the bare rank=0 form proves
        nothing about index↔table agreement."""
        self._run("add", "integrity probe", "--text", "content here")
        con = sqlite3.connect(self.db)
        try:
            con.execute("INSERT INTO findings_fts(findings_fts, rank) "
                        "VALUES('integrity-check', 1)")
        except sqlite3.DatabaseError as e:
            self.fail(f"rank=1 integrity-check failed on healthy db: {e}")
        finally:
            con.close()


class ReadOnlyConnectTest(unittest.TestCase):
    """P7 (D-K): reads must not take the write lock; a store needing
    healing must still heal (D-C) rather than search silently empty."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-ro-"))
        self.db = self.tmp / "research.db"
        sys.path.insert(0, str(DB_TOOLS))
        import findings_db
        con = sqlite3.connect(self.db)
        con.executescript(findings_db.SCHEMA)
        con.execute("INSERT INTO findings(created, topic, text) VALUES "
                    "('2026-09-01', 'ro row', 'readonly probe text')")
        con.commit()
        con.execute("PRAGMA journal_mode=WAL")  # prod runs WAL
        con.close()
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _connect_read(self):
        import subprocess
        code = ("import sys; sys.path.insert(0, %r);"
                "import findings_db;"
                "con = findings_db.connect_read();"
                "print(con.execute('SELECT topic FROM findings')"
                ".fetchone()[0]);"
                "con.execute(\"INSERT INTO findings(created, topic, text) "
                "VALUES ('x','y','z')\")"
                % str(DB_TOOLS))
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=60)

    def test_connect_read_is_readonly(self):
        r = self._connect_read()
        self.assertIn("ro row", r.stdout, r.stderr)
        self.assertIn("readonly", (r.stderr or "").lower(),
                      "write through connect_read must raise")

    def test_connect_read_heals_empty_index(self):
        """D-C on the read path: ro open succeeds on a desynced store, so
        connect_read must route healing to the rw connect() — search must
        NOT return empty on a restored pre-FTS db."""
        con = sqlite3.connect(self.db)
        con.execute("DELETE FROM findings_fts WHERE rowid = 1")
        con.commit()
        con.close()
        r = subprocess.run(
            [sys.executable, str(FINDINGS), "search", "readonly",
             "--json"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        import json
        self.assertEqual(len(json.loads(r.stdout)), 1, r.stdout)

    def test_connect_skips_writes_under_write_lock(self):
        """D-K pin: with the schema present, connect() must not write —
        a RESERVED (write-intent) lock held elsewhere would block any
        write inside connect(); readers must pass. (Before the guard,
        executescript(SCHEMA) took the write lock on every connect.)"""
        lock = sqlite3.connect(self.db, timeout=0.2)
        lock.execute("BEGIN IMMEDIATE")
        try:
            code = ("import sys; sys.path.insert(0, %r);"
                    "import findings_db;"
                    "con = findings_db.connect();"
                    "print('connected', con.execute("
                    "'SELECT COUNT(*) FROM findings').fetchone()[0])"
                    % str(DB_TOOLS))
            r = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=self.env, timeout=60)
            self.assertIn("connected 1", r.stdout,
                          f"connect() wrote under EXCLUSIVE lock: "
                          f"{r.stderr}")
        finally:
            lock.rollback()
            lock.close()

    def test_connect_restores_dropped_sync_trigger(self):
        """The DDL guard must not lose trigger self-healing: a dropped
        findings_au used to be re-created by every connect(); with a
        tables-only presence check the index would drift silently on
        every UPDATE (advisory 2026-09-03)."""
        import findings_db
        con = sqlite3.connect(self.db)
        con.execute("DROP TRIGGER findings_au")
        con.commit()
        con.close()
        old = findings_db.DB
        findings_db.DB = str(self.db)  # never the prod store
        try:
            findings_db.connect().close()
        finally:
            findings_db.DB = old
        con = sqlite3.connect(self.db)
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        con.close()
        self.assertIn("findings_au", names)

    def test_search_log_skips_ddl_when_schema_present(self):
        """P7 honesty: search still WRITES telemetry (one INSERT), but
        log._connect must not re-run executescript on every call: a
        present search_log table skips DDL (a partial one keeps its
        missing index — proof the script did not run), a fresh file
        gets the full schema (advisory 2026-09-03)."""
        import log
        old = log.DB
        try:
            fresh = self.tmp / "logfresh.db"
            log.DB = str(fresh)
            log._connect().close()
            con = sqlite3.connect(fresh)
            names = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master")}
            con.close()
            self.assertIn("idx_search_log_ts", names)
            partial = self.tmp / "logpartial.db"
            con = sqlite3.connect(partial)
            con.execute(
                "CREATE TABLE search_log (id INTEGER PRIMARY KEY "
                "AUTOINCREMENT, ts TEXT, tool TEXT, db_name TEXT, "
                "query TEXT, hits INTEGER)")
            con.commit()
            con.close()
            log.DB = str(partial)
            log._connect().close()
            con = sqlite3.connect(partial)
            names = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master")}
            con.close()
            self.assertNotIn("idx_search_log_ts", names,
                             "present table must skip the DDL script")
        finally:
            log.DB = old


if __name__ == "__main__":
    unittest.main()
