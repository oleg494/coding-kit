#!/usr/bin/env python3
"""search_all.py read-only connection regression tests (v4.0.2 audit).

Two defects in the read-only SQLite connection paths:
- the URI was built with str(Path), which on Windows yields backslashes
  (file:C:\\...\\db\\agent.db) — sqlite3 URI parsing treats those as
  literal characters, so mode=ro could be ignored on real Windows roots;
- con.close() was skipped whenever execute() raised (missing FTS table,
  corrupt db, locked file), leaking a handle per skipped database — on
  Windows that keeps the .db writable-locked for the rest of the run.

Contract after the fix: URIs use Path.as_posix() and every connection
closes in finally, including query/FTS exceptions.
"""
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

KIT = Path(__file__).resolve().parents[1]
MODULE_DIR = KIT / "memory" / "db-tools"
_spec = importlib.util.spec_from_file_location(
    "search_all", MODULE_DIR / "search_all.py")
search_all = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(MODULE_DIR))
try:
    _spec.loader.exec_module(search_all)
finally:
    sys.path.pop(0)



class _FakeCon:
    """Connection double: execute may raise; close() is observable."""

    def __init__(self, execute_raises=False, rows=()):
        self.closed = False
        self.close_calls = 0
        self.execute_raises = execute_raises
        self.rows = rows

    def execute(self, sql, params=()):
        if self.execute_raises:
            raise sqlite3.OperationalError("no such table: files_fts")
        return self

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return list(self.rows)

    def close(self):
        self.close_calls += 1
        self.closed = True


class CloseOnExceptionTest(unittest.TestCase):
    """Regression: execute() raising must not leak the read-only handle."""

    def test_list_searchable_dbs_closes_on_execute_error(self):
        con = _FakeCon(execute_raises=True)
        with tempfile.TemporaryDirectory(prefix="kit-sa-") as tmp:
            (Path(tmp) / "agent.db").write_bytes(b"")
            with mock.patch.object(search_all.sqlite3, "connect",
                                   return_value=con):
                out = search_all.list_searchable_dbs(db_dir=Path(tmp))
        self.assertEqual(out, [])
        self.assertTrue(con.closed,
                        "connection leaked when execute() raised")

    def test_search_all_closes_on_execute_error(self):
        con = _FakeCon(execute_raises=True)
        with (
            mock.patch.object(
                search_all, "list_searchable_dbs",
                return_value=[Path("C:/work/db/agent.db")]),
            mock.patch.object(search_all.sqlite3, "connect", return_value=con),
        ):
            out = search_all.search_all("firmware")

        self.assertEqual(out, [])
        self.assertTrue(con.closed,
                        "connection leaked when the FTS query raised")

    def test_search_all_closes_on_success(self):
        con = _FakeCon(rows=[("src/a.py", "<b>firmware</b> update")])
        with (
            mock.patch.object(
                search_all, "list_searchable_dbs",
                return_value=[Path("C:/work/db/agent.db")]),
            mock.patch.object(search_all.sqlite3, "connect", return_value=con),
        ):
            out = search_all.search_all("firmware")

        self.assertEqual(out, [("agent", "src/a.py", "<b>firmware</b> update")])
        self.assertTrue(con.closed)


class WindowsSafeUriTest(unittest.TestCase):
    """Regression: read-only URIs must use Path.as_posix(), never str()."""

    def test_search_all_uri_from_windows_style_path(self):
        # PureWindowsPath renders with backslashes on every host OS.
        win_path = PureWindowsPath("C:/work/db/agent.db")
        con = _FakeCon(rows=[])
        with (
            mock.patch.object(
                search_all, "list_searchable_dbs", return_value=[win_path]),
            mock.patch.object(
                search_all.sqlite3, "connect", return_value=con) as connect,
        ):
            search_all.search_all("firmware")
        connect.assert_called_once()
        args, kwargs = connect.call_args
        uri = args[0] if args else kwargs.get("database", "")
        self.assertEqual(uri, "file:C:/work/db/agent.db?mode=ro")
        self.assertNotIn("\\", uri, "URI must use forward slashes")
        self.assertTrue(kwargs.get("uri"))

    def test_list_searchable_dbs_uri_from_real_db(self):
        real_connect = sqlite3.connect
        captured = []

        def spy_connect(*args, **kw):
            captured.append((args[0], kw))
            return real_connect(*args, **kw)

        with tempfile.TemporaryDirectory(prefix="kit-sa-") as tmp:
            db = Path(tmp) / "wiki.db"
            con = sqlite3.connect(db)
            con.execute("CREATE VIRTUAL TABLE files_fts USING fts5("
                        "rel_path, content)")
            con.commit()
            con.close()
            with mock.patch.object(search_all.sqlite3, "connect",
                                   side_effect=spy_connect):
                out = search_all.list_searchable_dbs(db_dir=Path(tmp))
        self.assertEqual([p.name for p in out], ["wiki.db"])
        self.assertEqual(len(captured), 1)
        uri, kw = captured[0]
        self.assertTrue(uri.startswith("file:") and uri.endswith("?mode=ro"))
        self.assertNotIn("\\", uri, "URI must use forward slashes")
        self.assertTrue(kw.get("uri"))


class ReadOnlyRoundTripTest(unittest.TestCase):
    """Green-path guard: the fixed URI form really opens read-only."""

    def test_search_real_fts_db(self):
        with tempfile.TemporaryDirectory(prefix="kit-sa-") as tmp:
            db = Path(tmp) / "proj.db"
            con = sqlite3.connect(db)
            con.executescript(
                "CREATE TABLE files(id INTEGER PRIMARY KEY, "
                "rel_path TEXT, content TEXT);"
                "CREATE VIRTUAL TABLE files_fts USING fts5(rel_path, content);")
            con.execute("INSERT INTO files(rel_path, content) VALUES (?, ?)",
                        ("src/fw/main.py", "def firmware_update(): pass"))
            con.execute("INSERT INTO files_fts(rel_path, content) VALUES (?, ?)",
                        ("src/fw/main.py", "def firmware_update(): pass"))
            con.commit()
            con.close()
            self.assertEqual(search_all.list_searchable_dbs(db_dir=Path(tmp)),
                             [db])
            rows = search_all.search_all("firmware", db_dir=Path(tmp))
        self.assertEqual([(n, rp) for n, rp, _ in rows],
                         [("proj", "src/fw/main.py")])


if __name__ == "__main__":
    unittest.main()
