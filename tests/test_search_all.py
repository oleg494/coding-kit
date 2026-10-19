#!/usr/bin/env python3
"""search_all.py contract tests.

Three layers:
1. Read-only connection regressions (v4.0.2 audit) — now against the
   files leg (search_files): URIs use Path.as_posix() (Windows str(Path)
   yields backslashes, which sqlite3 URI parsing treats as literal
   characters so mode=ro could be ignored), and every connection closes
   in finally even when execute() raises (a leaked handle keeps the .db
   writable-locked for the rest of the run on Windows).

2. P11 findings union: research.db used to be structurally invisible
   (list_searchable_dbs admits only files_fts databases), so the documented
   `search_all.py "X"` reflex answered "not found" while findings.py found
   hits in the same store.
   Contract: findings print as `[research] finding#<id> <topic> …<snippet>`
   plus a `findings.py show <id>` hint, and ALL results (files dbs +
   findings) come out in ONE global bm25 order — never alphabetical db
   order, never per-database blocks.

3. 4.10.1+ error-vs-absence: a query that cannot run is NEVER "not
   found in any database". Query errors (the 'term OR' syntax case AND
   the reported '{component}' FTS5 column-filter case, which answers
   "no such column: component" — not a syntax-error string) raise
   SearchError(kind="query") / exit 2 with an actionable diagnostic;
   corrupt/failed stores (files db or the research store) raise
   SearchError(kind="store", partial=...) / exit 3 with partial hits
   on stdout and an explicit PARTIAL note; only a search that ran
   everywhere and matched nothing exits 1. A missing research.db
   stays a quiet skip while healthy indexed stores answer. --json
   findings hits also expose provenance (source) and the exact
   verified_at stamp (or null).
"""
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

KIT = Path(__file__).resolve().parents[1]
MODULE_DIR = KIT / "memory" / "db-tools"
SEARCH_ALL = MODULE_DIR / "search_all.py"
_spec = importlib.util.spec_from_file_location("search_all", SEARCH_ALL)
search_all = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(MODULE_DIR))
try:
    _spec.loader.exec_module(search_all)
    import findings_db  # noqa: E402  (SCHEMA for the seeded sandbox)
finally:
    sys.path.pop(0)

MISSING_DB = "C:/nonexistent/no-research-here.db"

# Long filler so a single term mention is a WEAK bm25 hit, and repeated
# mentions in a short doc are a STRONG one (bm25 rewards term density).
FILLER = " ".join(f"filler{i}" for i in range(400))


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

    def test_search_files_closes_on_execute_error(self):
        con = _FakeCon(execute_raises=True)
        with (
            mock.patch.object(search_all, "_validated_match",
                              return_value="firmware"),
            mock.patch.object(
                search_all, "scan_searchable_dbs",
                return_value=([Path("C:/work/db/agent.db")], [])),
            mock.patch.object(search_all.sqlite3, "connect", return_value=con),
        ):
            # The store-level failure is now surfaced, not swallowed —
            # but the connection must still be closed either way.
            # (_validated_match is stubbed so the control-index connect
            # does not consume the mocked sqlite3.connect.)
            with self.assertRaises(search_all.SearchError) as cm:
                search_all.search_files("firmware")
            self.assertEqual(cm.exception.kind, "store")
        self.assertTrue(con.closed,
                        "connection leaked when the FTS query raised")

    def test_search_files_closes_on_success(self):
        con = _FakeCon(rows=[("src/a.py", "<b>firmware</b> update", -1.5)])
        with (
            mock.patch.object(search_all, "_validated_match",
                              return_value="firmware"),
            mock.patch.object(
                search_all, "scan_searchable_dbs",
                return_value=([Path("C:/work/db/agent.db")], [])),
            mock.patch.object(search_all.sqlite3, "connect", return_value=con),
        ):
            out = search_all.search_files("firmware")

        self.assertEqual(out, [(-1.5, "agent", "src/a.py",
                                "<b>firmware</b> update")])
        self.assertTrue(con.closed)



class WindowsSafeUriTest(unittest.TestCase):
    """Regression: read-only URIs must use Path.as_posix(), never str()."""
    def test_search_files_uri_from_windows_style_path(self):
        # PureWindowsPath renders with backslashes on every host OS.
        win_path = PureWindowsPath("C:/work/db/agent.db")
        con = _FakeCon(rows=[])
        with (
            mock.patch.object(search_all, "_validated_match",
                              return_value="firmware"),
            mock.patch.object(
                search_all, "scan_searchable_dbs",
                return_value=([win_path], [])),
            mock.patch.object(
                search_all.sqlite3, "connect", return_value=con) as connect,
        ):
            out = search_all.search_files("firmware")
        connect.assert_called_once()
        self.assertEqual(out, [])
        args, kwargs = connect.call_args
        uri = args[0] if args else kwargs.get("database", "")
        self.assertEqual(uri, "file:C:/work/db/agent.db?mode=ro")
        self.assertNotIn("\\", uri, "URI must use forward slashes")
        self.assertTrue(kwargs.get("uri"))

    def test_search_findings_uri_from_real_windows_path(self):
        # The URI pin needs a real present file (an absent store is
        # skipped BEFORE connecting); a 0-byte file is a present store
        # that cannot answer — under the 4.10.1+ contract that is a
        # SearchError(kind="store"), which still must be raised AFTER
        # the correctly-shaped read-only URI was used. On Windows
        # str(Path) would yield backslashes that sqlite3 URI parsing
        # treats as literal chars.
        with tempfile.TemporaryDirectory(prefix="kit-sa-") as tmp:
            db = Path(tmp) / "research.db"
            db.write_bytes(b"")
            con = _FakeCon(execute_raises=True)
            with (
                mock.patch.object(search_all, "_validated_match",
                                  return_value="workflowz"),
                mock.patch.object(search_all.sqlite3, "connect",
                                  return_value=con) as connect,
            ):
                with self.assertRaises(search_all.SearchError) as cm:
                    search_all.search_findings("workflowz", research_db=db)
                self.assertEqual(cm.exception.kind, "store")
        connect.assert_called_once()
        args, kwargs = connect.call_args
        uri = args[0] if args else kwargs.get("database", "")
        self.assertEqual(uri, f"file:{db.as_posix()}?mode=ro")
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
            rows = search_all.search_files("firmware", db_dir=Path(tmp))
        self.assertEqual([(n, rp) for _s, n, rp, _sn in rows],
                         [("proj", "src/fw/main.py")])


def _seed_files_db(path: Path, rows, trigram: bool = False) -> None:
    """A minimal build.py-shaped store: files + files_fts (+ trigram)."""
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE files(id INTEGER PRIMARY KEY, rel_path TEXT, "
        "content TEXT);"
        "CREATE VIRTUAL TABLE files_fts USING fts5(rel_path, content, "
        "content='files', content_rowid='id');")
    if trigram:
        con.execute("CREATE VIRTUAL TABLE files_fts_trigram USING fts5("
                    "rel_path, content, content='files', content_rowid='id', "
                    "tokenize='trigram')")
    for rel_path, content in rows:
        con.execute("INSERT INTO files(rel_path, content) VALUES (?, ?)",
                    (rel_path, content))
    con.execute("INSERT INTO files_fts(rowid, rel_path, content) "
                "SELECT id, rel_path, content FROM files")
    if trigram:
        con.execute("INSERT INTO files_fts_trigram(rowid, rel_path, content) "
                    "SELECT id, rel_path, content FROM files")
    con.commit()
    con.close()


def _seed_research_db(path: Path, rows) -> None:
    """findings_db.SCHEMA + rows [(topic, text)]; triggers fill the FTS."""
    con = sqlite3.connect(path)
    con.executescript(findings_db.SCHEMA)
    for topic, text in rows:
        con.execute("INSERT INTO findings(created, topic, text) "
                    "VALUES ('2026-09-02', ?, ?)", (topic, text))
    con.commit()
    con.close()


class FindingsUnionTest(unittest.TestCase):
    """P11: research.db findings answer the same query as the files dbs."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-sa-p11-"))
        self.db_dir = self.tmp / "db"
        self.db_dir.mkdir()
        self.research = self.tmp / "research.db"
        _seed_research_db(self.research, [
            ("workflowz brainstorm", f"eight lenses then a critic {FILLER}"),
        ])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _search(self, query, **kw):
        kw.setdefault("research_db", self.research)
        kw.setdefault("db_dir", self.db_dir)
        return search_all.search_all(query, **kw)

    def test_research_hit_line_format_and_hint(self):
        """(a) `[research] finding#<id> <topic> …<snippet>` + show hint."""
        rows = self._search("workflowz")
        self.assertEqual(len(rows), 1, rows)
        score, db, label, snip, fid = rows[0]
        self.assertEqual(db, "research")
        self.assertEqual(fid, 1)
        self.assertEqual(label, "finding#1 workflowz brainstorm")
        self.assertIsInstance(score, float)
        self.assertLess(score, 0, "bm25 scores are negative (lower = better)")

        out = self._print_main("workflowz")
        self.assertIn("[research] finding#1 workflowz brainstorm [unverified] …", out)
        self.assertIn("  findings.py show 1", out)
    def test_research_hit_without_files_dbs_still_answers(self):
        """D-G: no files_fts database at all — findings alone must answer
        (this is exactly the store state that used to exit 1)."""
        out = self._print_main("workflowz")
        self.assertIn("[research] finding#1", out)

    def test_research_snippet_marks_the_match(self):
        """snippet(findings_fts, 1, '[', ']', …) brackets the hit term."""
        _score, _db, _label, snip, _fid = self._search("lenses")[0]
        self.assertIn("[lenses]", snip)

    def test_limit_respected_per_leg(self):
        _seed_research_db(self.research, [
            (f"workflowz note {i}", "workflowz " * 3) for i in range(2, 6)])
        rows = self._search("workflowz", limit=2)
        self.assertEqual(len([r for r in rows if r[1] == "research"]), 2)

    def test_missing_research_db_is_skipped(self):
        """Absent store = section skipped, files leg unaffected (best-effort
        union: search_all must never fail because research.db is missing)."""
        _seed_files_db(self.db_dir / "wiki.db",
                       [("notes/a.md", "workflowz method")])
        rows = search_all.search_all("workflowz", db_dir=self.db_dir,
                                     research_db=MISSING_DB)
        self.assertEqual([r[1] for r in rows], ["wiki"])

    def test_corrupt_research_db_is_a_store_error_not_a_skip(self):
        """4.10.1+: a corrupt research store (present file that cannot
        answer) must NOT silently disappear from the union — the API
        raises SearchError(kind="store") with .partial carrying the
        hits from the stores that DID answer, and the CLI exits 3 with
        the partial hits still printed plus an explicit PARTIAL note
        (never a quiet success, never "not found")."""
        (self.tmp / "broken.db").write_bytes(b"not sqlite at all")
        _seed_files_db(self.db_dir / "wiki.db",
                       [("notes/a.md", "workflowz method")])
        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_all("workflowz", db_dir=self.db_dir,
                                  research_db=self.tmp / "broken.db")
        self.assertEqual(cm.exception.kind, "store")
        self.assertEqual([r[1] for r in cm.exception.partial], ["wiki"])
        self.assertIn("broken.db", str(cm.exception))

    def test_corrupt_research_db_cli_exits_3_with_partial_hits(self):
        """CLI: rc 3 (store error), partial hits on stdout, stderr
        names the failing store and says the results are PARTIAL — and
        --json still emits the partial payload so machines keep data
        while seeing the nonzero status."""
        (self.tmp / "broken.db").write_bytes(b"not sqlite at all")
        _seed_files_db(self.db_dir / "wiki.db",
                       [("notes/a.md", "workflowz method")])
        rc, out, err = self._main_rc("workflowz",
                                     research_db=self.tmp / "broken.db")
        self.assertEqual(rc, 3, f"rc={rc} out={out} err={err}")
        self.assertIn("[wiki] notes/a.md", out)
        self.assertIn("broken.db", err)
        self.assertIn("PARTIAL", err)
        self.assertNotIn("not found in any database", out)
        self.assertNotIn("not found in any database", err)
        rc, out, err = self._main_rc("workflowz", "--json",
                                     research_db=self.tmp / "broken.db")
        self.assertEqual(rc, 3, f"rc={rc} out={out} err={err}")
        data = json.loads(out)
        self.assertEqual([d["db"] for d in data], ["wiki"])
        self.assertIn("PARTIAL", err)

    def test_schemaless_research_db_is_a_store_error(self):
        """A db whose file exists but has no findings/fts schema is a
        PRESENT store that cannot answer (foreign schema) — a store
        error, not a silent [] that the CLI would report as "not found
        in any database"."""
        empty = self.tmp / "empty.db"
        con = sqlite3.connect(empty)
        con.execute("CREATE TABLE notes(x TEXT)")
        con.commit()
        con.close()
        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_all("workflowz", db_dir=self.db_dir,
                                  research_db=empty)
        self.assertEqual(cm.exception.kind, "store")
        self.assertIn("empty.db", str(cm.exception))

    def test_research_db_never_double_counted_as_files_db(self):
        """research.db lives in db/ and has no files_fts: the files leg must
        still skip it (otherwise a finding prints twice)."""
        shutil.copy2(self.research, self.db_dir / "research.db")
        rows = self._search("workflowz", db_dir=self.db_dir)
        self.assertEqual(len(rows), 1, rows)

    def test_json_mode_keeps_pinned_keys(self):
        """v4.0.2 machine contract: [{db, path, snippet}] — findings ride
        along with path='finding#<id> <topic>' and additive lifecycle keys."""
        import json
        payload = self._print_main("workflowz", "--json")
        data = json.loads(payload)
        self.assertEqual(len(data), 1)
        self.assertTrue({"db", "path", "snippet"}.issubset(data[0]))
        self.assertEqual(data[0]["db"], "research")
        self.assertEqual(data[0]["path"], "finding#1 workflowz brainstorm")
        self.assertIsNone(data[0]["superseded_by"])
        self.assertIs(data[0]["verified"], False)

    def test_json_mode_lifecycle_metadata(self):
        """LR-05: findings hits in JSON mode carry lifecycle metadata
        (superseded_by, verified) alongside pinned db/path/snippet keys.
        File hits keep the 3-key shape."""
        import json
        con = sqlite3.connect(self.research)
        con.execute(
            "INSERT INTO findings(id, created, topic, text, verified_at, source) "
            "VALUES (2, '2026-09-03', 'workflowz replacement', 'new workflowz content', "
            "'2026-09-03 10:00:00', 'audit')"
        )
        con.execute(
            "INSERT INTO links(from_id, to_id, kind, created) "
            "VALUES (2, 1, 'supersedes', '2026-09-03')"
        )
        con.commit()
        con.close()

        _seed_files_db(self.db_dir / "wiki.db", [
            ("Wiki/workflowz.md", f"workflowz documentation {FILLER}"),
        ])

        payload = self._print_main("workflowz", "--json")
        data = json.loads(payload)
        by_path = {item["path"]: item for item in data}

        for item in data:
            self.assertTrue({"db", "path", "snippet"}.issubset(item))
            self.assertTrue(item["snippet"])

        f1 = by_path["finding#1 workflowz brainstorm"]
        self.assertEqual(f1["db"], "research")
        self.assertEqual(f1["superseded_by"], 2)
        self.assertIs(f1["verified"], False)

        f2 = by_path["finding#2 workflowz replacement"]
        self.assertEqual(f2["db"], "research")
        self.assertIsNone(f2["superseded_by"])
        self.assertIs(f2["verified"], True)

        file_hit = by_path["Wiki/workflowz.md"]
        self.assertEqual(file_hit["db"], "wiki")
        self.assertEqual(set(file_hit.keys()), {"db", "path", "snippet"})

    def _main_rc(self, query, *extra, research_db=None):
        """main() against the sandbox with an explicit research db;
        returns (rc, stdout, stderr)."""
        import io
        buf, err = [], io.StringIO()
        rdb = Path(research_db) if research_db else self.research

        def _capture(*a, **k):
            text = " ".join(str(x) for x in a)
            f = k.get("file")
            if f is sys.stderr or f is search_all.sys.stderr:
                err.write(text + "\n")
            else:
                buf.append(text)

        argv = ["search_all.py", query, *extra]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(search_all, "DB_DIR", self.db_dir),
            mock.patch.object(search_all, "research_db_path",
                              return_value=str(rdb)),
            mock.patch("builtins.print", side_effect=_capture),
        ):
            rc = search_all.main()
        return rc, "\n".join(buf), err.getvalue()

    def _print_main(self, query, *extra):
        """main() against the seeded sandbox; returns stdout (rc 0)."""
        buf = []
        argv = ["search_all.py", query, *extra]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(search_all, "DB_DIR", self.db_dir),
            mock.patch.object(search_all, "research_db_path",
                              return_value=str(self.research)),
            mock.patch("builtins.print",
                       side_effect=lambda *a, **k: buf.append(" ".join(
                           str(x) for x in a))),
        ):
            rc = search_all.main()
        self.assertEqual(rc, 0, "\n".join(buf))
        return "\n".join(buf)


class GlobalMergeOrderTest(unittest.TestCase):
    """(b) ONE global bm25 order across every database + the findings leg."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-sa-merge-"))
        self.db_dir = self.tmp / "db"
        self.db_dir.mkdir()
        self.research = self.tmp / "research.db"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _search(self, query, **kw):
        kw.setdefault("research_db", self.research)
        return search_all.search_all(query, db_dir=self.db_dir, **kw)

    def test_scores_are_globally_descending(self):
        """Every neighbouring pair must be score-ordered, whatever db it
        came from — the merge is one sorted list, not per-db blocks."""
        _seed_files_db(self.db_dir / "aaa-clone.db",
                       [("clone/weak.md", f"workflowz {FILLER}")])
        _seed_files_db(self.db_dir / "wiki.db",
                       [("wiki/strong.md", "workflowz " * 40)])
        _seed_research_db(self.research,
                          [("workflowz method", "workflowz " * 40)])
        rows = self._search("workflowz")
        self.assertEqual(len(rows), 3, rows)
        scores = [r[0] for r in rows]
        self.assertEqual(scores, sorted(scores),
                         f"not bm25-ordered: {scores}")
        self.assertEqual(len(set(scores)), 3, "scores must differ (no tie luck)")

    def test_stronger_hit_wins_over_alphabetical_db_order(self):
        """The defect P11 fixes: wiki.db ranked AFTER its clone because the
        dbs were walked alphabetically. Same query, clone hit is weak
        (one mention in a long doc), wiki hit is dense — wiki must lead."""
        _seed_files_db(self.db_dir / "aaa-clone.db",
                       [("clone/weak.md", f"workflowz {FILLER}")])
        _seed_files_db(self.db_dir / "wiki.db",
                       [("wiki/strong.md", "workflowz " * 40)])
        rows = self._search("workflowz")
        self.assertEqual([r[1] for r in rows], ["wiki", "aaa-clone"], rows)

    def test_finding_can_rank_above_a_files_hit(self):
        """Topic carries the 10.0 bm25 weight: a finding whose TOPIC matches
        outranks a weak single-mention file hit."""
        _seed_files_db(self.db_dir / "wiki.db",
                       [("notes/weak.md", f"workflowz {FILLER}")])
        _seed_research_db(self.research,
                          [("workflowz brainstorm", f"lenses {FILLER}")])
        rows = self._search("workflowz")
        self.assertEqual([r[1] for r in rows], ["research", "wiki"], rows)

    def test_files_hit_can_rank_above_a_finding(self):
        """The mirror case — the merge is by score, not by leg: a dense file
        hit outranks a finding that mentions the term once in a long text."""
        _seed_files_db(self.db_dir / "wiki.db",
                       [("workflowz/strong.md", "workflowz " * 40)])
        _seed_research_db(self.research,
                          [("lenses", f"workflowz {FILLER}")])
        rows = self._search("workflowz")
        self.assertEqual([r[1] for r in rows], ["wiki", "research"], rows)

    def test_substring_path_merges_by_score_too(self):
        """--substring (trigram) keeps ranking by bm25 — verified live on
        SQLite >= 3.34, so no separate fallback ordering exists."""
        _seed_files_db(self.db_dir / "aaa.db",
                       [("a/weak.md", f"workflowz {FILLER}")], trigram=True)
        _seed_files_db(self.db_dir / "zzz.db",
                       [("z/strong.md", "workflowz " * 40)], trigram=True)
        rows = self._search("workflo", substring=True)
        self.assertEqual([r[1] for r in rows], ["zzz", "aaa"], rows)

    def test_no_hits_keeps_not_found_contract(self):
        """rc/semantics unchanged: empty everywhere -> not found, rc 1."""
        _seed_files_db(self.db_dir / "wiki.db", [("notes/a.md", "unrelated")])
        _seed_research_db(self.research, [("other", "unrelated text")])
        buf = []
        with (
            mock.patch.object(sys, "argv", ["search_all.py", "workflowz"]),
            mock.patch.object(search_all, "DB_DIR", self.db_dir),
            mock.patch.object(search_all, "research_db_path",
                              return_value=str(self.research)),
            mock.patch("builtins.print",
                       side_effect=lambda *a, **k: buf.append(" ".join(
                           str(x) for x in a))),
        ):
            rc = search_all.main()
        self.assertEqual(rc, 1)
        self.assertIn("not found in any database", "\n".join(buf))


class AgentsCommandContractTest(unittest.TestCase):
    """(c) The OPS §5 memory-search command, end-to-end as a subprocess:

        python <engine>/search_all.py "workflowz"

    against a sandboxed memory root (MEMORY_ROOT + MEMORY_ROOT_RESEARCH_DB)
    — rc 0 and a `[research] finding#<id>` line. This is the exact command
    shape the routing docs promise, so it is pinned by shape, not by a
    python-API call.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-sa-agents-"))
        self.root = self.tmp / "memory"
        (self.root / "db").mkdir(parents=True)
        (self.root / "db-tools").mkdir()
        (self.root / "scripts").mkdir()
        # _compat.chulan_root() markers: VERSION + db-tools + scripts/_compat.py
        (self.root / "VERSION").write_text("4.0.3\n", encoding="utf-8")
        shutil.copy2(KIT / "memory" / "scripts" / "_compat.py",
                     self.root / "scripts" / "_compat.py")
        self.research = self.tmp / "research.db"
        _seed_research_db(self.research, [
            ("workflowz brainstorm",
             f"eight lenses, critic, yagni judge {FILLER}"),
        ])
        _seed_files_db(self.root / "db" / "wiki.db",
                       [("Wiki/method/workflowz.md", f"workflowz {FILLER}")])
        self.env = {k: v for k, v in os.environ.items()
                    if k != "MEMORY_ROOT_RESEARCH_DB"}
        self.env.update(MEMORY_ROOT=str(self.root),
                        MEMORY_ROOT_RESEARCH_DB=str(self.research),
                        PYTHONIOENCODING="utf-8",
                        PYTHONUTF8="1")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SEARCH_ALL), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=120,
            cwd=str(KIT))

    def test_agents_md_command_finds_the_finding(self):
        r = self._run("workflowz")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        hit = [ln for ln in lines if ln.startswith("[research] finding#")]
        self.assertTrue(hit, f"no research line in:\n{r.stdout}")
        fid = hit[0].split("finding#")[1].split()[0]
        self.assertIn(f"findings.py show {fid}", r.stdout)
        self.assertIn("workflowz brainstorm", hit[0])

    def test_command_runs_from_the_kit_root_shape(self):
        """The documented invocation is `python ~/.memory/db-tools/
        search_all.py "X"` from an arbitrary cwd — the engine resolves its
        own root, not the cwd."""
        r = subprocess.run(
            [sys.executable, str(SEARCH_ALL), "workflowz"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=120,
            cwd=str(Path(tempfile.gettempdir())))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[research] finding#1 workflowz brainstorm", r.stdout)

    def test_files_hit_and_finding_share_one_score_ordered_listing(self):
        """Both legs answer the same command; the total line counts
        databases from BOTH legs (wiki + research = 2)."""
        r = self._run("workflowz")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[wiki] Wiki/method/workflowz.md", r.stdout)
        self.assertIn("[research] finding#1", r.stdout)
        self.assertIn("in 2 databases", r.stdout)
        scores = search_all.search_all(
            "workflowz", db_dir=self.root / "db", research_db=self.research)
        printed = [ln for ln in r.stdout.splitlines()
                   if ln.startswith("[wiki]") or ln.startswith("[research]")]
        self.assertEqual([ln.split("]")[0][1:] for ln in printed],
                         [db for _s, db, _l, _sn, _f in scores],
                         "printed order must equal the global bm25 order")


class FindingsLifecycleMetadataTest(unittest.TestCase):
    """LR-05: findings hits carry lifecycle metadata in search_all.py."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-sa-lr05-"))
        self.db_dir = self.tmp / "db"
        self.db_dir.mkdir()
        self.research = self.tmp / "research.db"
        con = sqlite3.connect(self.research)
        con.executescript(findings_db.SCHEMA)
        # 1. unverified finding
        con.execute(
            "INSERT INTO findings(id, created, topic, text, verify_cmd, verified_at) "
            "VALUES (1, '2026-09-01', 'unverified pattern', 'text about pattern', '', '')"
        )
        # 2. verified finding
        con.execute(
            "INSERT INTO findings(id, created, topic, text, verify_cmd, verified_at) "
            "VALUES (2, '2026-09-02', 'verified pattern', 'text about pattern', 'pytest', '2026-09-02 14:00')"
        )
        # 3. superseded finding (superseded by finding 4)
        con.execute(
            "INSERT INTO findings(id, created, topic, text, verify_cmd, verified_at) "
            "VALUES (3, '2026-09-03', 'superseded pattern', 'text about pattern', 'pytest', '2026-09-03 10:00')"
        )
        con.execute(
            "INSERT INTO findings(id, created, topic, text, verify_cmd, verified_at) "
            "VALUES (4, '2026-09-04', 'newer pattern', 'newer text', 'pytest', '2026-09-04 11:00')"
        )
        con.execute(
            "INSERT INTO links(from_id, to_id, kind, created) "
            "VALUES (4, 3, 'supersedes', '2026-09-04')"
        )
        con.commit()
        con.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _print_main(self, query, *extra):
        buf = []
        argv = ["search_all.py", query, *extra]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(search_all, "DB_DIR", self.db_dir),
            mock.patch.object(search_all, "research_db_path",
                              return_value=str(self.research)),
            mock.patch("builtins.print",
                       side_effect=lambda *a, **k: buf.append(" ".join(str(x) for x in a))),
        ):
            rc = search_all.main()
        self.assertEqual(rc, 0, "\n".join(buf))
        return "\n".join(buf)

    def test_search_findings_returns_lifecycle_fields(self):
        hits = search_all.search_findings("pattern", research_db=self.research)
        self.assertGreaterEqual(len(hits), 3)
        by_id = {h[1]: h for h in hits}
        # finding 1: unverified, not superseded
        h1 = by_id[1]
        self.assertIsNone(h1.superseded_by)
        self.assertFalse(h1.verified)
        # finding 2: verified, not superseded
        h2 = by_id[2]
        self.assertIsNone(h2.superseded_by)
        self.assertTrue(h2.verified)
        # finding 3: superseded by 4
        h3 = by_id[3]
        self.assertEqual(h3.superseded_by, 4)

    def test_cli_prints_badges_for_unverified_and_superseded(self):
        out = self._print_main("pattern")
        # finding 1 is unverified
        self.assertIn("[unverified]", out)
        # finding 3 is superseded by #4
        self.assertIn("[superseded by #4]", out)
        # finding 2 is verified and not superseded, should have neither badge on its line
        lines = [ln for ln in out.splitlines() if "finding#2" in ln]
        self.assertTrue(lines)
        self.assertNotIn("[unverified]", lines[0])
        self.assertNotIn("[superseded", lines[0])

    def test_search_all_exposes_lifecycle_fields(self):
        hits = search_all.search_all("pattern", db_dir=self.db_dir, research_db=self.research)
        by_id = {h[4]: h for h in hits if h[4] is not None}
        self.assertIn(3, by_id)
        self.assertEqual(by_id[3][5], 4)
        self.assertEqual(by_id[3].superseded_by, 4)
        self.assertTrue(by_id[2].verified)
        self.assertFalse(by_id[1].verified)

    def test_json_mode_provenance_and_freshness(self):
        """4.10.1: JSON findings hits expose provenance (source) and the
        EXACT verified_at stamp (or null for the '' schema sentinel);
        "verified" bool stays for compatibility."""
        import json
        payload = self._print_main("pattern", "--json")
        data = json.loads(payload)
        by_id = {item["path"].split()[0]: item for item in data
                 if item["path"].startswith("finding#")}
        # finding 1: unverified -> exact null, empty provenance
        self.assertIsNone(by_id["finding#1"]["verified_at"])
        self.assertIs(by_id["finding#1"]["verified"], False)
        self.assertEqual(by_id["finding#1"]["source"], "")
        # finding 2: verified -> the exact stamp, not just a bool
        self.assertEqual(by_id["finding#2"]["verified_at"],
                         "2026-09-02 14:00")
        self.assertIs(by_id["finding#2"]["verified"], True)


class QueryErrorVsNotFoundTest(unittest.TestCase):
    """4.10.1+: a query that cannot run is NEVER "not found".

    Query errors (malformed FTS syntax AND the reported '{component}'
    brace-column case, whose 'no such column' error the old 'syntax
    error' sniff never matched): search_all() raises
    SearchError(kind="query"); the CLI prints an actionable diagnostic
    to stderr and exits 2 — --json emits no payload (an empty list
    would read as 'searched, found nothing').

    Store errors (corrupt db/*.db or research store, nothing searchable
    at all): SearchError(kind="store", partial=...) and exit 3, with
    partial hits on stdout and an explicit PARTIAL note on stderr.

    "not found in any database" (rc 1) stays reserved for a query that
    ran everywhere it could and matched nothing.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-sa-qerr-"))
        self.db_dir = self.tmp / "db"
        self.db_dir.mkdir()
        self.research = self.tmp / "research.db"
        _seed_files_db(self.db_dir / "wiki.db",
                       [("notes/a.md", "workflowz method")])
        _seed_research_db(self.research,
                          [("workflowz brainstorm", "eight lenses")])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _main(self, query, *extra, db_dir=None, research_db=None):
        """main() against the sandbox; returns (rc, stdout, stderr)."""
        import io
        buf, err = [], io.StringIO()
        rdb = Path(research_db) if research_db else self.research

        def _capture(*a, **k):
            text = " ".join(str(x) for x in a)
            f = k.get("file")
            if f is sys.stderr or f is search_all.sys.stderr:
                err.write(text + "\n")
            else:
                buf.append(text)

        argv = ["search_all.py", query, *extra]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(search_all, "DB_DIR",
                              db_dir if db_dir is not None else self.db_dir),
            mock.patch.object(search_all, "research_db_path",
                              return_value=str(rdb)),
            # The module resolved sys.stderr at import (fix_encoding
            # reconfigured it), so routing by the file kwarg is the only
            # reliable stdout/stderr split under a print patch.
            mock.patch("builtins.print", side_effect=_capture),
        ):
            rc = search_all.main()
        return rc, "\n".join(buf), err.getvalue()

    def test_files_leg_raises_search_error_on_malformed_query(self):
        """'workflowz OR' is FTS5 syntax garbage: the API must raise
        SearchError instead of silently returning [] (= "not found")."""
        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_files("workflowz OR", db_dir=self.db_dir)
        self.assertEqual(cm.exception.kind, "query")

    def test_findings_leg_raises_search_error_on_malformed_query(self):
        """Same contract for the findings leg — no files dbs needed."""
        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_findings("workflowz OR",
                                       research_db=self.research)
        self.assertEqual(cm.exception.kind, "query")

    def test_brace_column_filter_query_is_a_query_error(self):
        """The reported defect, pinned by shape: '{component}' parses
        as an FTS5 brace column filter and answers 'no such column:
        component' — an error the old code never matched (it sniffed
        only the literal 'syntax error', so this silently returned []
        and the CLI claimed 'not found in any database'). Must raise
        SearchError(kind='query') on BOTH legs."""
        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_files("{component}", db_dir=self.db_dir)
        self.assertEqual(cm.exception.kind, "query")
        self.assertIn("malformed FTS query", str(cm.exception))

        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_findings("{component}",
                                       research_db=self.research)
        self.assertEqual(cm.exception.kind, "query")

        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_all("{component}", db_dir=self.db_dir,
                                  research_db=self.research)
        self.assertEqual(cm.exception.kind, "query")

    def test_cli_brace_query_is_not_reported_as_not_found(self):
        """The exact user-reported failure: '{component}' must exit 2
        with a query-error diagnostic, never rc 1 'not found' and
        never an empty JSON list."""
        rc, out, err = self._main("{component}")
        self.assertEqual(rc, 2, f"rc={rc} out={out} err={err}")
        self.assertIn("query error", err)
        self.assertIn("malformed FTS query", err)
        self.assertNotIn("not found in any database", out)
        self.assertNotIn("not found in any database", err)

        rc, out, err = self._main("{component}", "--json")
        self.assertEqual(rc, 2, f"rc={rc} out={out} err={err}")
        self.assertEqual(out, "", "JSON mode must emit nothing on a "
                                  "query error, not []")
        self.assertIn("query error", err)

    def test_cli_malformed_query_is_not_reported_as_not_found(self):
        rc, out, err = self._main("workflowz OR")
        self.assertEqual(rc, 2, f"rc={rc} out={out} err={err}")
        self.assertIn("query error", err)
        self.assertIn("malformed FTS query", err)
        self.assertNotIn("not found in any database", out)
        self.assertNotIn("not found in any database", err)

    def test_cli_malformed_query_json_mode_emits_no_payload(self):
        """--json must not print [] (which consumers read as 'searched,
        found nothing') when the query never ran."""
        rc, out, err = self._main("workflowz OR", "--json")
        self.assertEqual(rc, 2, f"rc={rc} out={out} err={err}")
        self.assertEqual(out, "", "JSON mode must emit nothing on a "
                                  "query error, not []")
        self.assertIn("query error", err)

    def test_valid_query_with_no_hits_keeps_not_found(self):
        """The mirror case: a VALID query that matches nothing keeps the
        historical empty behavior (rc 1, 'not found in any database')."""
        rc, out, err = self._main("zzznope")
        self.assertEqual(rc, 1, f"rc={rc} out={out} err={err}")
        self.assertIn("not found in any database", out)
        self.assertNotIn("query error", err)

    def test_no_searchable_stores_at_all_is_a_store_error(self):
        """An empty db/ with an absent research store means the query
        ran NOWHERE: [] would become the 'not found in any database'
        lie. search_all raises SearchError(kind='store') and the CLI
        exits 3 with an actionable diagnostic (rc 1 reserved for a
        search that actually ran)."""
        empty_dir = self.tmp / "empty-db"
        empty_dir.mkdir()
        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_all("workflowz", db_dir=empty_dir,
                                  research_db=MISSING_DB)
        self.assertEqual(cm.exception.kind, "store")
        rc, out, err = self._main("workflowz", db_dir=empty_dir,
                                  research_db=MISSING_DB)
        self.assertEqual(rc, 3, f"rc={rc} out={out} err={err}")
        self.assertIn("search error", err)
        self.assertNotIn("not found in any database", out)
        self.assertNotIn("not found in any database", err)

    def test_corrupt_files_db_in_dir_is_a_store_error(self):
        """A corrupt db/*.db file is caught by the scan, named in the
        error, and does not silently shrink the union: the API raises
        with .partial from the healthy stores; the CLI exits 3."""
        (self.db_dir / "corrupt.db").write_bytes(b"garbage not sqlite")
        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_files("workflowz", db_dir=self.db_dir)
        self.assertEqual(cm.exception.kind, "store")
        self.assertIn("corrupt.db", str(cm.exception))
        self.assertEqual([r[1] for r in cm.exception.partial], ["wiki"])

        rc, out, err = self._main("workflowz")
        self.assertEqual(rc, 3, f"rc={rc} out={out} err={err}")
        self.assertIn("corrupt.db", err)
        self.assertIn("PARTIAL", err)
        self.assertIn("[wiki] notes/a.md", out)
        self.assertNotIn("not found in any database", out)

    def test_importance_filter_with_missing_research_db_is_a_store_error(self):
        """An importance filter scopes the search to the findings store
        only; with that store absent nothing can answer, so [] would
        again be a 'not found' lie — the search raises instead."""
        with self.assertRaises(search_all.SearchError) as cm:
            search_all.search_all("workflowz", db_dir=self.db_dir,
                                  research_db=MISSING_DB,
                                  importance="high")
        self.assertEqual(cm.exception.kind, "store")

if __name__ == "__main__":
    unittest.main()
