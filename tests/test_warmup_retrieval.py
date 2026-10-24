#!/usr/bin/env python3
"""memory-warmup.py retrieval + Wiki-stat regressions.

Warmup is a thin adapter over the canonical engine (search_all.py):

- it must return the SAME lexical results as the `search_all.py` CLI — one
  retrieval implementation, one machine shape (`_json_hits`), findings
  lifecycle metadata included;
- it must propagate the engine's error contract: exit 2 = the query never ran
  (no result list at all), exit 3 = a store that should have answered failed
  (whatever the other stores returned is printed and marked PARTIAL). A failed
  search is never an empty success;
- Wiki stats/recent must work in BOTH real index layouts — root-wide
  (default `build.py` over MEMORY_ROOT: notes carry a `Wiki/` prefix and
  unrelated project Markdown is indexed in the same store) and legacy
  Wiki-rooted (the existing ~/.memory store: `notes/...` at the top level,
  either separator) — without ever counting the unrelated Markdown.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
WARMUP = KIT / "memory" / "scripts" / "memory-warmup.py"
ENGINE = KIT / "memory" / "db-tools"
SEARCH_ALL = ENGINE / "search_all.py"
BUILD = ENGINE / "build.py"
FINDINGS = ENGINE / "findings.py"


def _run(script, args, env):
    return subprocess.run([sys.executable, str(script)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=180)


def _write_files_db(path: Path, rows, mtime: int = None):
    """A minimal index store: only the columns the Wiki queries read."""
    stamp = int(mtime if mtime is not None else time.time())
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE files (rel_path TEXT, ext TEXT, mtime INTEGER)")
    con.executemany("INSERT INTO files (rel_path, ext, mtime) VALUES (?,?,?)",
                    [(rel, ext, stamp) for rel, ext in rows])
    con.commit()
    con.close()


class _Sandbox:
    """Isolated memory ROOT (the store) satisfying the MEMORY_ROOT markers.

    The engine is deliberately NOT copied here: warmup must reach db-tools
    relative to its own script, independent of the store path, so the sandbox
    store proving that is exactly a root without an engine tree.
    """

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-warmup-"))
        self.root = self.tmp / "mem"
        (self.root / "db").mkdir(parents=True)
        (self.root / "VERSION").write_text("2.9\n", encoding="utf-8")
        (self.root / "db-tools").mkdir()
        (self.root / "scripts").mkdir()
        shutil.copy2(KIT / "memory" / "scripts" / "_compat.py",
                     self.root / "scripts" / "_compat.py")
        (self.root / "Wiki").mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("PYTHON")}
        self.env.pop("MEMORY_ROOT_RESEARCH_DB", None)
        self.env["MEMORY_ROOT"] = str(self.root)
        # one resolver for the sandbox: warmup and the engine both read the
        # findings store through MEMORY_ROOT_RESEARCH_DB / the root default.
        self.env["MEMORY_ROOT_RESEARCH_DB"] = str(
            self.root / "db" / "research.db")

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def warmup(self, *args):
        return _run(WARMUP, args, self.env)

    def search_all_cli(self, *args):
        return _run(SEARCH_ALL, args, self.env)

    def build(self, *args):
        return _run(BUILD, args, self.env)

    def findings(self, *args):
        return _run(FINDINGS, args, self.env)

    def seed_wiki_note(self, rel: str, text: str = "---\ntitle: n\n---\nbody"):
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


class FindingsOnlyQueryTest(unittest.TestCase):
    """A research.db hit must answer alone, keep its lifecycle metadata, and
    match the search_all.py CLI exactly (lexical default)."""

    def test_findings_only_query_matches_search_all_and_keeps_metadata(self):
        fx = _Sandbox()
        try:
            r = fx.findings("add", "zqmarker warmup topic", "--text",
                            "body about zqmarker", "--project", "coding-kit",
                            "--importance", "high")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            con = sqlite3.connect(fx.root / "db" / "research.db")
            con.execute("UPDATE findings SET verified_at='2026-01-02 03:04', "
                        "source='src/evidence.py' WHERE id=1")
            con.commit()
            con.close()
            stores = sorted(p.name for p in (fx.root / "db").glob("*.db"))
            self.assertEqual(stores, ["research.db"], stores)

            w = fx.warmup("--json", "--query", "zqmarker")
            self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
            warmup_hits = json.loads(w.stdout)["search"]["results"]

            s = fx.search_all_cli("--json", "zqmarker")
            self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
            self.assertEqual(warmup_hits, json.loads(s.stdout),
                             "warmup must return the engine's own lexical "
                             "results and machine shape")

            self.assertTrue(warmup_hits, "findings alone must produce hits")
            hit = warmup_hits[0]
            self.assertEqual(hit["db"], "research:coding-kit")
            self.assertEqual(hit["path"], "finding#1 zqmarker warmup topic")
            self.assertEqual(hit["verified"], True)
            self.assertEqual(hit["verified_at"], "2026-01-02 03:04")
            self.assertEqual(hit["source"], "src/evidence.py")
            self.assertEqual(hit["project"], "coding-kit")
            self.assertEqual(hit["importance"], "high")
            self.assertIsNone(hit["superseded_by"])
            self.assertIs(hit["superseded"], False)
        finally:
            fx.close()


class WarmupErrorContractTest(unittest.TestCase):
    """exit 2 = the query never ran; exit 3 = a store failed (PARTIAL kept).

    Regression: the draft swallowed SearchError and returned [], so a broken
    store looked like a clean "nothing matched"."""

    def _good_store(self, fx, marker: str = "zqgood"):
        src = fx.tmp / "docs"
        src.mkdir(exist_ok=True)
        (src / "note.md").write_text(f"# note\n{marker} marker body\n",
                                     encoding="utf-8")
        r = fx.build("-r", str(src), "-o", str(fx.root / "db" / "good.db"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_store_error_exits_3_and_preserves_partial_results(self):
        fx = _Sandbox()
        try:
            self._good_store(fx)
            (fx.root / "db" / "broken.db").write_bytes(b"not a sqlite database")

            w = fx.warmup("--json", "--query", "zqgood")
            self.assertEqual(w.returncode, 3, w.stdout + w.stderr)
            self.assertIn("PARTIAL", w.stderr)
            partial = json.loads(w.stdout)["search"]["results"]
            self.assertTrue(
                any(h["db"] == "good" and h["path"] == "note.md"
                    for h in partial),
                f"hits from the healthy store must survive: {partial}")
        finally:
            fx.close()

    def test_query_error_exits_2_without_emitting_results(self):
        fx = _Sandbox()
        try:
            self._good_store(fx)
            w = fx.warmup("--json", "--query", "zqgood AND")
            self.assertEqual(w.returncode, 2, w.stdout + w.stderr)
            self.assertEqual(w.stdout.strip(), "",
                             "an unrun query must not emit a result list")
            self.assertIn("query error", w.stderr)
        finally:
            fx.close()

    def test_absent_stores_are_never_an_empty_success(self):
        fx = _Sandbox()
        try:
            w = fx.warmup("--json", "--query", "zqgood")
            self.assertEqual(w.returncode, 3, w.stdout + w.stderr)
            self.assertEqual(w.stdout.strip(), "")
            self.assertIn("search error", w.stderr)

            human = fx.warmup("--query", "zqgood")
            self.assertEqual(human.returncode, 3, human.stdout + human.stderr)
            self.assertNotIn("0 results", human.stdout)
        finally:
            fx.close()


class WikiStatsLayoutTest(unittest.TestCase):
    """Both index layouts, either separator, unrelated Markdown excluded."""

    def test_root_wide_layout_counts_only_wiki_notes(self):
        fx = _Sandbox()
        try:
            fx.seed_wiki_note("Wiki/notes/alpha.md")
            fx.seed_wiki_note("Wiki/index.md", "# index\n")
            fx.seed_wiki_note("Wiki/log.md", "# log\n")
            fx.seed_wiki_note("Wiki/_templates/post.md")
            fx.seed_wiki_note("src/design.md", "# unrelated project doc\n")
            fx.seed_wiki_note("docs/notes.md", "# unrelated project doc\n")

            r = fx.build("--full")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            con = sqlite3.connect(fx.root / "db" / "wiki.db")
            indexed = [row[0].replace("\\", "/")
                       for row in con.execute("SELECT rel_path FROM files")]
            con.close()
            self.assertIn("Wiki/notes/alpha.md", indexed)
            self.assertIn("src/design.md", indexed)
            self.assertTrue(any(p.endswith("VERSION") for p in indexed),
                            f"the default build root is MEMORY_ROOT: {indexed}")

            stats = json.loads(fx.warmup("--json", "--stats").stdout)["stats"]
            self.assertEqual(stats["wiki_entries"], 1, stats)
            self.assertEqual(stats["recent_7d"], 1, stats)
        finally:
            fx.close()

    def test_root_wide_store_without_wiki_tree_never_counts_project_markdown(self):
        """Markers prove the store is root-wide, so an empty Wiki subtree must
        not promote every project .md in the index to a memory note."""
        fx = _Sandbox()
        try:
            fx.seed_wiki_note("src/design.md", "# unrelated\n")
            fx.seed_wiki_note("tests/plan.md", "# unrelated\n")
            r = fx.build("--full")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            stats = json.loads(fx.warmup("--json", "--stats").stdout)["stats"]
            self.assertEqual(stats["wiki_entries"], 0, stats)
        finally:
            fx.close()

    def test_legacy_wiki_rooted_layout_counts_notes_both_separators(self):
        """The existing ~/.memory store was built over the Wiki directory:
        notes sit at the top level (`notes\\x.md`, mixed separators) and the
        40 legacy .md rows must not read as zero."""
        fx = _Sandbox()
        try:
            _write_files_db(fx.root / "db" / "wiki.db", [
                ("README.md", ".md"),
                ("index.md", ".md"),
                ("log.md", ".md"),
                ("_templates\\post.md", ".md"),
                ("notes\\first.md", ".md"),
                ("notes\\second.md", ".md"),
                ("notes\\sub/third.md", ".md"),
            ])
            w = fx.warmup("--json", "--stats")
            self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
            stats = json.loads(w.stdout)["stats"]
            self.assertEqual(stats["wiki_entries"], 3, stats)
            self.assertEqual(stats["recent_7d"], 3, stats)

            full = json.loads(fx.warmup("--json", "--full").stdout)
            paths = [r["path"] for r in full["recent"]]
            self.assertIn("notes/first.md", paths)
            self.assertIn("notes/sub/third.md", paths)
            self.assertNotIn("README.md", paths)
            self.assertNotIn("_templates/post.md", paths)
        finally:
            fx.close()


class RootOverrideTest(unittest.TestCase):
    """MEMORY_ROOT selects the store: source and installed invocations alike."""

    def test_memory_root_override_selects_the_store(self):
        small, large = _Sandbox(), _Sandbox()
        try:
            for fx, count in ((small, 1), (large, 3)):
                for i in range(count):
                    fx.seed_wiki_note(f"Wiki/notes/n{i}.md")
                r = fx.build("--full")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            a = json.loads(small.warmup("--json", "--stats").stdout)["stats"]
            b = json.loads(large.warmup("--json", "--stats").stdout)["stats"]
            self.assertEqual(a["wiki_entries"], 1, a)
            self.assertEqual(b["wiki_entries"], 3, b)
        finally:
            small.close()
            large.close()


class EngineResolutionTest(unittest.TestCase):
    """db-tools is found next to the script, never through MEMORY_ROOT."""

    def test_engine_is_script_relative_and_lazy(self):
        import importlib.util
        fx = _Sandbox()
        saved = {name: os.environ.get(name)
                 for name in ("MEMORY_ROOT", "MEMORY_ROOT_RESEARCH_DB")}
        os.environ["MEMORY_ROOT"] = str(fx.root)  # store WITHOUT an engine
        os.environ.pop("MEMORY_ROOT_RESEARCH_DB", None)
        try:
            spec = importlib.util.spec_from_file_location(
                "_warmup_under_test", WARMUP)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            sys.modules.pop("_warmup_under_test", None)
            fx.close()

        self.assertEqual(Path(mod._engine_dir()), ENGINE)
        self.assertEqual(mod.PROFILE_ROOT, fx.root,
                         "the store root still follows MEMORY_ROOT")
        self.assertEqual(mod.RESEARCH_DB,
                         fx.root / "db" / "research.db",
                         "the root default is used when no override is set")
        self.assertIsNone(mod._ENGINE_API,
                          "diagnostic modes must not import the engine")
        self.assertEqual(mod._sanitize.__module__, "ftsquery")


if __name__ == "__main__":
    unittest.main()