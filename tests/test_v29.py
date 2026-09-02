#!/usr/bin/env python3
"""v2.9 contract tests (audit 2026-08-22 round 2):

- findings carry verify-commands: memory entries that can be re-run
  (VERIFIED/FAILED), not prose that rots;
- build.py refuses to default a project named 'research' into
  db/research.db (the findings store);
- a failed full rebuild leaves the previous index intact (atomic rename);
- memory-warmup honors MEMORY_ROOT (OPS §5 declares it a contract);
- sanitize_query lives in ONE module (ftsquery.py) — the three drifting
  copies (search / memory-warmup / findings) are gone.
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
from datetime import datetime, timedelta

KIT = Path(__file__).resolve().parents[1]
DB_TOOLS = KIT / "memory" / "db-tools"
FINDINGS = DB_TOOLS / "findings.py"
BUILD = DB_TOOLS / "build.py"
WARMUP = KIT / "memory" / "scripts" / "memory-warmup.py"


def _run(script, args, env):
    return subprocess.run([sys.executable, str(script)] + args,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env,
                          timeout=120)


class _FakeRoot:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-v29-"))
        self.root = self.tmp / "mem"
        (self.root / "db").mkdir(parents=True)
        (self.root / "VERSION").write_text("2.9\n", encoding="utf-8")
        (self.root / "db-tools").mkdir()
        (self.root / "scripts").mkdir()
        shutil.copy2(KIT / "memory" / "scripts" / "_compat.py",
                     self.root / "scripts" / "_compat.py")
        shutil.copy2(DB_TOOLS / "ftsquery.py",
                     self.root / "db-tools" / "ftsquery.py")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("PYTHON")}
        self.env["MEMORY_ROOT"] = str(self.root)

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class FindingsVerifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-findings-"))
        self.db = self.tmp / "research.db"
        self.env = dict(os.environ,
                        MEMORY_ROOT_RESEARCH_DB=str(self.db))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _findings(self, *args):
        return _run(FINDINGS, list(args), self.env)

    def test_add_stores_and_verify_runs_command(self):
        r = self._findings("add", "topic-x", "--text", "conclusion",
                           "--verify-cmd", "python -c \"print('fresh')\"")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self._findings("verify", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VERIFIED", r.stdout)
        con = sqlite3.connect(self.db)
        verified_at = con.execute(
            "SELECT verified_at FROM findings WHERE id=1").fetchone()[0]
        con.close()
        self.assertTrue(verified_at, "verified_at must be recorded")

    def test_verify_failure_is_loud(self):
        self._findings("add", "topic-y", "--text", "conclusion",
                       "--verify-cmd", "python -c \"raise SystemExit(3)\"")
        r = self._findings("verify", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAILED", r.stdout)

    def test_verify_without_command(self):
        self._findings("add", "topic-z", "--text", "conclusion")
        r = self._findings("verify", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no verify-cmd", r.stdout + r.stderr)


class BuildGuardsTest(unittest.TestCase):
    def setUp(self):
        self.fx = _FakeRoot()

    def tearDown(self):
        self.fx.close()

    def test_project_named_research_refused(self):
        proj = self.fx.tmp / "research"
        proj.mkdir()
        (proj / "a.md").write_text("x", encoding="utf-8")
        r = _run(BUILD, ["-r", str(proj)], self.fx.env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse((self.fx.root / "db" / "research.db").exists(),
                         "the findings store must not be touched")

    def test_case_insensitive_root_still_maps_to_wiki(self):
        # lowercase drive/path must hit the wiki branch, not create a
        # stray db/<basename>.db duplicate index (audit m4)
        lower_root = str(self.fx.root).lower()
        if lower_root == str(self.fx.root):
            self.skipTest("case-fold made no difference")
        r = _run(BUILD, ["-r", lower_root], self.fx.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.fx.root / "db" / "wiki.db").exists())
        made = [p.name for p in (self.fx.root / "db").glob("*.db")]
        self.assertEqual(made, ["wiki.db"], made)


class AtomicFullBuildTest(unittest.TestCase):
    def setUp(self):
        self.fx = _FakeRoot()
        self.proj = self.fx.tmp / "proj"
        self.proj.mkdir()
        (self.proj / "a.md").write_text("alpha", encoding="utf-8")
        self.db = self.fx.tmp / "p.db"
        r = _run(BUILD, ["-r", str(self.proj), "-o", str(self.db)],
                 self.fx.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def tearDown(self):
        self.fx.close()

    def _import_build(self):
        saved = os.environ.get("MEMORY_ROOT")
        self.addCleanup(os.environ.pop, "MEMORY_ROOT", None)
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, "MEMORY_ROOT", saved)
        os.environ["MEMORY_ROOT"] = str(self.fx.root)
        for mod in ("build", "_compat", "parsers"):
            sys.modules.pop(mod, None)
        self.addCleanup(sys.path.remove, str(DB_TOOLS))
        sys.path.insert(0, str(DB_TOOLS))
        import build  # noqa: F401 — resolves ROOT from MEMORY_ROOT env
        return build

    def test_failed_full_build_keeps_old_index(self):
        build = self._import_build()

        def boom(con, root, *a, **k):
            raise RuntimeError("disk died mid-build")

        build.full_build = boom
        with self.assertRaises(RuntimeError):
            build.atomic_full_build(str(self.db), str(self.proj),
                                    set(), set())
        con = sqlite3.connect(self.db)
        rows = [r[0] for r in con.execute("SELECT rel_path FROM files")]
        con.close()
        self.assertEqual(rows, ["a.md"], "old index must survive")
        self.assertFalse(os.path.exists(str(self.db) + ".tmp-full"))

    def test_successful_full_rebuild_replaces_content(self):
        build = self._import_build()
        (self.proj / "b.md").write_text("beta", encoding="utf-8")
        stats = build.atomic_full_build(str(self.db), str(self.proj),
                                        set(), set())
        self.assertEqual(stats["new"], 2)
        con = sqlite3.connect(self.db)
        rows = sorted(r[0] for r in con.execute("SELECT rel_path FROM files"))
        con.close()
        self.assertEqual(rows, ["a.md", "b.md"])
        self.assertFalse(os.path.exists(str(self.db) + ".tmp-full"))


class WarmupMemoryRootTest(unittest.TestCase):
    def test_warmup_reads_memory_root_env(self):
        fx = _FakeRoot()
        try:
            (fx.root / "Wiki").mkdir()
            (fx.root / "Wiki" / "one.md").write_text(
                "---\ntitle: one\n---\nbody", encoding="utf-8")
            r = _run(BUILD, [], fx.env)  # default root -> wiki.db
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            w = _run(WARMUP, ["--json", "--stats"], fx.env)
            self.assertEqual(w.returncode, 0, w.stdout + w.stderr)
            data = json.loads(w.stdout)
            self.assertEqual(data["stats"]["wiki_entries"], 1,
                             "warmup must read MEMORY_ROOT, not __file__")
        finally:
            fx.close()


class WarmupGitStaleTest(unittest.TestCase):
    """git_stale_days backs variant A of the git-hygiene decision (plan §Q3):
    warmup WARNS how stale the memory repo is; a human commits."""

    def _load_warmup(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_mw_under_test", WARMUP)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.addCleanup(sys.modules.pop, "_mw_under_test", None)
        return mod

    def test_non_repo_returns_minus_one(self):
        mw = self._load_warmup()
        tmp = Path(tempfile.mkdtemp(prefix="kit-gitstale-"))
        try:
            self.assertEqual(mw.git_stale_days(tmp), -1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_backdated_commit_reports_days(self):
        if not shutil.which("git"):
            self.skipTest("git not on PATH")
        from datetime import datetime, timedelta, timezone
        mw = self._load_warmup()
        tmp = Path(tempfile.mkdtemp(prefix="kit-gitstale-"))
        repo = tmp / "mem"
        try:
            repo.mkdir()

            def git(*a, env=None):
                e = dict(os.environ)
                if env:
                    e.update(env)
                subprocess.run(["git", "-C", str(repo)] + list(a),
                               check=True, capture_output=True, env=e)

            git("init", "-q")
            git("config", "user.email", "t@t")
            git("config", "user.name", "T")
            (repo / "f.txt").write_text("x", encoding="utf-8")
            git("add", "-A")
            back = (datetime.now(timezone.utc) - timedelta(days=30)) \
                .strftime("%Y-%m-%dT%H:%M:%S+0000")
            git("commit", "-q", "-m", "old",
                env={"GIT_AUTHOR_DATE": back, "GIT_COMMITTER_DATE": back})
            days = mw.git_stale_days(repo)
            self.assertTrue(29 <= days <= 31,
                            f"expected ~30 days stale, got {days}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class SanitizeUnificationTest(unittest.TestCase):
    def test_single_implementation_no_copies(self):
        self.assertTrue((DB_TOOLS / "ftsquery.py").is_file(),
                        "ftsquery.py module must exist")
        for rel in ("memory/db-tools/search.py",
                    "memory/db-tools/findings.py",
                    "memory/scripts/memory-warmup.py"):
            src = (KIT / rel).read_text(encoding="utf-8")
            self.assertIn("from ftsquery import", src, rel)
            self.assertNotIn("def sanitize_query", src, rel)
            self.assertNotIn("def _sanitize", src, rel)

    def test_behavior_operators_kept_and_specials_quoted(self):
        sys.path.insert(0, str(DB_TOOLS))
        from ftsquery import sanitize_query
        self.assertEqual(sanitize_query("alpha AND beta"), "alpha AND beta")
        self.assertEqual(sanitize_query("agent-lsp"),
                         '"agent-lsp"')
        self.assertEqual(sanitize_query('"quoted-token"'),
                         '"quoted-token"')

    def test_quoted_prefix_still_matches(self):
        """P8 (D-A): the stem must NOT be a full token — 'firmware' masked
        the defect because it is both prefix and exact token. 'prox' is a
        prefix of 'proxies'/'proxying' only; '"prox*"' (star INSIDE
        quotes) matches 0 rows, sanitize_query must emit '"prox"*'."""
        sys.path.insert(0, str(DB_TOOLS))
        from ftsquery import sanitize_query
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
        con.executemany("INSERT INTO t VALUES (?)",
                        [("proxies config",), ("proxying notes",),
                         ("unrelated row",)])
        q = sanitize_query("prox*")
        self.assertEqual(q, '"prox"*')
        n = con.execute("SELECT COUNT(*) FROM t WHERE t MATCH ?",
                        (q,)).fetchone()[0]
        self.assertEqual(n, 2, f"prefix must match both prox-rows: {q}")
        # the masked form, pinned as broken: star inside quotes = exact
        n0 = con.execute("SELECT COUNT(*) FROM t WHERE t MATCH ?",
                         ('"prox*"',)).fetchone()[0]
        self.assertEqual(n0, 0)
        con.close()


class BaselineAndEvalHygieneTest(unittest.TestCase):
    def test_file_size_baseline_is_empty(self):
        baseline_file = KIT / "scripts" / "file_size_baseline.json"
        self.assertTrue(baseline_file.is_file(), f"{baseline_file} must exist")
        data = json.loads(baseline_file.read_text(encoding="utf-8"))
        self.assertEqual(data, {}, "file size baseline must be exactly empty object")

    def test_superseded_plan_is_absent(self):
        superseded = KIT / "docs" / "superpowers" / "plans" / "2026-08-24-eval-metrics-and-evolution.md"
        self.assertFalse(superseded.exists(), f"superseded plan {superseded.name} must be absent")

    def test_no_dry_run_debris_present(self):
        eval_results_dir = KIT / "eval" / "results"
        if eval_results_dir.exists():
            debris = list(eval_results_dir.glob("trap-dry-run-*.json"))
            self.assertEqual(debris, [], f"trap-dry-run debris found in eval/results: {debris}")
        debris_repo = [p for p in KIT.rglob("trap-dry-run-*.json") if ".git" not in p.parts]
        self.assertEqual(debris_repo, [], f"trap-dry-run debris found in repo: {debris_repo}")


class WarmupUnsureFeedTest(unittest.TestCase):
    """P12: warmup pushes what memory is NOT sure about — open contradicts
    links + last-7d rows anchored to neither verify_cmd nor source + a pull
    hint — instead of the raw newest-topics feed (junk id-DESC topics were
    a hidden curriculum teaching new agents to imitate junk)."""

    def _seed(self, fx):
        """research.db from the PROD schema (single owner: findings_db) with
        3 contradicts links (LIMIT 2 keeps the newest), fresh unanchored
        rows (LIMIT 3 keeps the newest), anchored + old decoys that must
        stay out of the feed."""
        db_tools = KIT / "memory" / "db-tools"
        if str(db_tools) not in sys.path:
            sys.path.insert(0, str(db_tools))
        saved = os.environ.get("MEMORY_ROOT")
        os.environ["MEMORY_ROOT"] = str(fx.root)
        try:
            import findings_db
        finally:
            if saved is None:
                os.environ.pop("MEMORY_ROOT", None)
            else:
                os.environ["MEMORY_ROOT"] = saved
        now = datetime.now()
        fresh = now.strftime("%Y-%m-%d %H:%M")
        old = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
        con = sqlite3.connect(fx.root / "db" / "research.db")
        con.executescript(findings_db.SCHEMA)
        rows = [
            # id 1-6: contradiction endpoints (must not leak as unanchored)
            (fresh, "claim alpha", "anchored"),
            (fresh, "claim beta", "anchored"),
            (fresh, "stale gamma", "anchored"),
            (fresh, "stale delta", "anchored"),
            (fresh, "ephem one", "anchored"),
            (fresh, "ephem two", "anchored"),
            # id 7-10: fresh unanchored; ORDER BY id DESC LIMIT 3 keeps
            # ids 10, 9, 8 — id 7 (loose oldest) drops out
            (fresh, "loose oldest", ""),
            (fresh, "loose older", ""),
            (fresh, "loose middle", ""),
            (fresh, "loose newest", ""),
            # id 11 fresh but verify-anchored; id 12 unanchored but >7d old
            (fresh, "anchored fresh", ""),
            (old, "ancient unanchored", ""),
        ]
        for created, topic, source in rows:
            con.execute(
                "INSERT INTO findings (created, topic, text, source) "
                "VALUES (?,?,?,?)", (created, topic, "body", source))
        con.execute("UPDATE findings SET verify_cmd='python -V' "
                    "WHERE topic='anchored fresh'")
        # oldest link first: ORDER BY l.id DESC LIMIT 2 must drop #1vs#2
        for a, b in ((1, 2), (3, 4), (5, 6)):
            con.execute(
                "INSERT INTO links (from_id, to_id, kind, note, created) "
                "VALUES (?,?,'contradicts','',?)", (a, b, fresh))
        con.commit()
        con.close()

    def test_full_warmup_prints_unsure_feed_not_raw_topics(self):
        fx = _FakeRoot()
        try:
            self._seed(fx)
            r = _run(WARMUP, [], fx.env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            out = r.stdout
            # contradictions: newest 2 links only, both endpoint topics shown
            self.assertIn("contradiction: #5 vs #6", out)
            self.assertIn("ephem one | ephem two", out)
            self.assertIn("contradiction: #3 vs #4", out)
            self.assertNotIn("#1 vs #2", out)
            self.assertEqual(out.count("contradiction:"), 2)
            # unanchored: newest 3 fresh rows with empty verify_cmd AND source
            self.assertIn("unanchored: #10 loose newest", out)
            self.assertIn("unanchored: #9 loose middle", out)
            self.assertIn("unanchored: #8 loose older", out)
            self.assertNotIn("loose oldest", out)
            self.assertEqual(out.count("unanchored:"), 3)
            # decoys: anchored fresh row and old unanchored row stay out
            self.assertNotIn("anchored fresh", out)
            self.assertNotIn("ancient unanchored", out)
            # literal pull hint (exact prefix is the contract)
            self.assertIn('pull: search_all.py', out)
            # the hint is a TEMPLATE, not a fixed junk query pushed on
            # every boot (advisory 2026-09-03)
            self.assertNotIn('pull: search_all.py "memory"', out)
            self.assertIn('pull: search_all.py "<your topic>"', out)
            # raw date-stamped topic feed is gone
            self.assertNotIn("Findings:", out)
            # budget: the added block stays under ~250 tokens
            block = out[out.index("Unsure"):out.index("Integrity")]
            self.assertLess(len(block), 1200,
                            f"unsure block too big ({len(block)} chars)")
        finally:
            fx.close()

    def test_json_feed_is_list_of_lines_with_pull_hint(self):
        fx = _FakeRoot()
        try:
            self._seed(fx)
            r = _run(WARMUP, ["--json"], fx.env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            feed = json.loads(r.stdout)["findings"]
            self.assertIsInstance(feed, list)
            self.assertTrue(any(s.startswith("contradiction: #") for s in feed))
            self.assertTrue(any(s.startswith("unanchored: #") for s in feed))
            self.assertTrue(any(s.startswith("pull: search_all.py")
                                for s in feed))
        finally:
            fx.close()

    def test_missing_research_db_degrades_to_empty(self):
        fx = _FakeRoot()
        try:
            r = _run(WARMUP, ["--json"], fx.env)  # no research.db seeded
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(json.loads(r.stdout)["findings"], [])
        finally:
            fx.close()

if __name__ == "__main__":
    unittest.main()
