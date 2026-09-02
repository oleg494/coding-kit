#!/usr/bin/env python3
"""search_all.py contract tests.

Two layers:

1. Read-only connection regressions (v4.0.2 audit) — now against the
   files leg (search_files): URIs use Path.as_posix() (Windows str(Path)
   yields backslashes, which sqlite3 URI parsing treats as literal
   characters so mode=ro could be ignored), and every connection closes
   in finally even when execute() raises (a leaked handle keeps the .db
   writable-locked for the rest of the run on Windows).

2. P11 findings union (plan D-G): research.db used to be structurally
   invisible (list_searchable_dbs admits only files_fts databases), so
   AGENTS.md §4's documented reflex `search_all.py "X"` answered
   "not found" while findings.py found hits in the very same store.
   Contract: findings print as `[research] finding#<id> <topic> …<snippet>`
   plus a `findings.py show <id>` hint, and ALL results (files dbs +
   findings) come out in ONE global bm25 order — never alphabetical db
   order, never per-database blocks.
"""
import importlib.util
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
            mock.patch.object(
                search_all, "list_searchable_dbs",
                return_value=[Path("C:/work/db/agent.db")]),
            mock.patch.object(search_all.sqlite3, "connect", return_value=con),
        ):
            out = search_all.search_files("firmware")

        self.assertEqual(out, [])
        self.assertTrue(con.closed,
                        "connection leaked when the FTS query raised")

    def test_search_files_closes_on_success(self):
        con = _FakeCon(rows=[("src/a.py", "<b>firmware</b> update", -1.5)])
        with (
            mock.patch.object(
                search_all, "list_searchable_dbs",
                return_value=[Path("C:/work/db/agent.db")]),
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
            mock.patch.object(
                search_all, "list_searchable_dbs", return_value=[win_path]),
            mock.patch.object(
                search_all.sqlite3, "connect", return_value=con) as connect,
        ):
            search_all.search_files("firmware")
        connect.assert_called_once()
        args, kwargs = connect.call_args
        uri = args[0] if args else kwargs.get("database", "")
        self.assertEqual(uri, "file:C:/work/db/agent.db?mode=ro")
        self.assertNotIn("\\", uri, "URI must use forward slashes")
        self.assertTrue(kwargs.get("uri"))

    def test_search_findings_uri_from_real_windows_path(self):
        # An absent store is skipped BEFORE connecting, so the URI pin
        # needs a real file; on Windows str(Path) would yield
        # backslashes that sqlite3 URI parsing treats as literal chars.
        with tempfile.TemporaryDirectory(prefix="kit-sa-") as tmp:
            db = Path(tmp) / "research.db"
            db.write_bytes(b"")
            con = _FakeCon(rows=[])
            with mock.patch.object(search_all.sqlite3, "connect",
                                   return_value=con) as connect:
                search_all.search_findings("workflowz", research_db=db)
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
        self.assertIn("[research] finding#1 workflowz brainstorm …", out)
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

    def test_corrupt_research_db_is_skipped(self):
        (self.tmp / "broken.db").write_bytes(b"not sqlite at all")
        _seed_files_db(self.db_dir / "wiki.db",
                       [("notes/a.md", "workflowz method")])
        rows = search_all.search_all("workflowz", db_dir=self.db_dir,
                                     research_db=self.tmp / "broken.db")
        self.assertEqual([r[1] for r in rows], ["wiki"])

    def test_schemaless_research_db_is_skipped(self):
        """A db without findings_fts (pre-FTS/foreign store) must not raise."""
        empty = self.tmp / "empty.db"
        con = sqlite3.connect(empty)
        con.execute("CREATE TABLE notes(x TEXT)")
        con.commit()
        con.close()
        rows = search_all.search_all("workflowz", db_dir=self.db_dir,
                                     research_db=empty)
        self.assertEqual(rows, [])

    def test_research_db_never_double_counted_as_files_db(self):
        """research.db lives in db/ and has no files_fts: the files leg must
        still skip it (otherwise a finding prints twice)."""
        shutil.copy2(self.research, self.db_dir / "research.db")
        rows = self._search("workflowz", db_dir=self.db_dir)
        self.assertEqual(len(rows), 1, rows)

    def test_json_mode_keeps_pinned_keys(self):
        """v4.0.2 machine contract: [{db, path, snippet}] — findings ride
        along with path='finding#<id> <topic>'."""
        import json
        payload = self._print_main("workflowz", "--json")
        data = json.loads(payload)
        self.assertEqual(len(data), 1)
        self.assertEqual(set(data[0]), {"db", "path", "snippet"})
        self.assertEqual(data[0]["db"], "research")
        self.assertEqual(data[0]["path"], "finding#1 workflowz brainstorm")

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
    """(c) The LITERAL AGENTS.md §4 reflex, end-to-end as a subprocess:

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


if __name__ == "__main__":
    unittest.main()
