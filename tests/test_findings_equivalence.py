#!/usr/bin/env python3
"""tests/test_findings_equivalence.py — permanent isolated equivalence tests for findings.

Verifies:
1. Re-export equivalence: findings.py re-exports DB, SCHEMA, connect from findings_db,
   link helpers (_print_chain, _row_links, cmd_link_add, cmd_link_list, cmd_link_rm,
   cmd_related) from findings_links, and OPS.
2. Isolated database operations: with MEMORY_ROOT_RESEARCH_DB pointed to a temp file,
   real CLI add, search, show, list, edit, del, link add/list/rm, and related commands
   behave correctly.
3. Bidirectional link graph traversal and formatting.
4. FTS5 indexing, search filtering (query, source, tag), and trigger maintenance.
5. In-process helper contract and schema integrity without touching any real research.db.
"""

import datetime
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
SCRIPTS = KIT / "memory" / "scripts"
FINDINGS = DB_TOOLS / "findings.py"

# Ensure db-tools and scripts are in sys.path for direct imports
if str(DB_TOOLS) not in sys.path:
    sys.path.insert(0, str(DB_TOOLS))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import findings
import findings_db
import findings_links


def _run(script, args, env):
    return subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


class FindingsReexportEquivalenceTest(unittest.TestCase):
    """Assert findings.py maintains full re-export equivalence for DB and link helpers."""

    def test_db_exports_identity(self):
        self.assertIs(
            findings.SCHEMA,
            findings_db.SCHEMA,
            "findings.SCHEMA must be identical to findings_db.SCHEMA",
        )
        self.assertIs(
            findings.connect,
            findings_db.connect,
            "findings.connect must be identical to findings_db.connect",
        )
        self.assertEqual(
            findings.DB,
            findings_db.DB,
            "findings.DB must match findings_db.DB value",
        )

    def test_link_helpers_identity(self):
        self.assertIs(
            findings._row_links,
            findings_links._row_links,
            "findings._row_links must be identical to findings_links._row_links",
        )
        self.assertIs(
            findings._print_chain,
            findings_links._print_chain,
            "findings._print_chain must be identical to findings_links._print_chain",
        )
        self.assertIs(
            findings.cmd_link_add,
            findings_links.cmd_link_add,
            "findings.cmd_link_add must be identical to findings_links.cmd_link_add",
        )
        self.assertIs(
            findings.cmd_link_list,
            findings_links.cmd_link_list,
            "findings.cmd_link_list must be identical to findings_links.cmd_link_list",
        )
        self.assertIs(
            findings.cmd_link_rm,
            findings_links.cmd_link_rm,
            "findings.cmd_link_rm must be identical to findings_links.cmd_link_rm",
        )
        self.assertIs(
            findings.cmd_related,
            findings_links.cmd_related,
            "findings.cmd_related must be identical to findings_links.cmd_related",
        )

    def test_ops_reexport(self):
        self.assertEqual(
            findings.OPS,
            {"AND", "OR", "NOT", "NEAR"},
            "findings.OPS must contain standard FTS query operators",
        )

    def test_schema_definition_integrity(self):
        schema = findings.SCHEMA
        self.assertIn("CREATE TABLE IF NOT EXISTS findings", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS links", schema)
        self.assertIn("CREATE VIRTUAL TABLE IF NOT EXISTS findings_fts USING fts5", schema)
        self.assertIn("CREATE TRIGGER IF NOT EXISTS findings_ai", schema)
        self.assertIn("CREATE TRIGGER IF NOT EXISTS findings_ad", schema)
        self.assertIn("CREATE TRIGGER IF NOT EXISTS findings_au", schema)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_links_from", schema)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_links_to", schema)


class FindingsInProcessScratchTest(unittest.TestCase):
    """In-process isolated connection test covering helper return shapes and schema."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-findings-scratch-"))
        self.db_path = self.tmp / "scratch.db"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scratch_schema_and_row_links_helper_shape(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.executescript(findings.SCHEMA)
        cur = con.cursor()

        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        cur.execute(
            "INSERT INTO findings (created, topic, text, tags, source, file, symbol) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, "Topic Alpha", "Text Alpha", "tag-a", "src/a.py", "a.py", "func_a"),
        )
        id_a = cur.lastrowid
        cur.execute(
            "INSERT INTO findings (created, topic, text, tags, source, file, symbol) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, "Topic Beta", "Text Beta", "tag-b", "src/b.py", "b.py", "func_b"),
        )
        id_b = cur.lastrowid

        cur.execute(
            "INSERT INTO links (from_id, to_id, kind, note, created) VALUES (?, ?, ?, ?, ?)",
            (id_a, id_b, "extends", "alpha to beta note", now),
        )
        con.commit()

        # Test _row_links helper return shape and direction from perspective of id_a
        links_a = findings._row_links(cur, id_a)
        self.assertEqual(len(links_a), 1)
        link_id, direction, kind, topic, note = links_a[0]
        self.assertEqual(direction, "->")
        self.assertEqual(kind, "extends")
        self.assertEqual(topic, "Topic Beta")
        self.assertEqual(note, "alpha to beta note")

        # Test _row_links helper from perspective of id_b (reverse direction)
        links_b = findings._row_links(cur, id_b)
        self.assertEqual(len(links_b), 1)
        link_id_b, direction_b, kind_b, topic_b, note_b = links_b[0]
        self.assertEqual(link_id_b, link_id)
        self.assertEqual(direction_b, "<-")
        self.assertEqual(kind_b, "extends")
        self.assertEqual(topic_b, "Topic Alpha")
        self.assertEqual(note_b, "alpha to beta note")

        con.close()


class FindingsCLIEquivalenceTest(unittest.TestCase):
    """Test CLI add/search/show/list/link/related operations against an isolated temp DB."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-findings-cli-"))
        self.db_path = self.tmp / "research.db"
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db_path),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _findings(self, *args):
        return _run(FINDINGS, list(args), self.env)

    def _get_db(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def test_cli_two_findings_links_and_fts_workflow(self):
        # 1. Add Finding 1
        r1 = self._findings(
            "add",
            "SQLite FTS5 Tokenizer Rules",
            "--text",
            "Prefix matching requires trailing asterisk in MATCH query syntax",
            "--tags",
            "sqlite fts search",
            "--source",
            "https://sqlite.org/fts5.html",
            "--file",
            "memory/db-tools/search.py",
            "--symbol",
            "search_fts",
        )
        self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        self.assertIn("[✓] added:", r1.stdout)
        self.assertIn("SQLite FTS5 Tokenizer Rules", r1.stdout)
        self.assertIn("(id=1)", r1.stdout)

        # 2. Add Finding 2
        r2 = self._findings(
            "add",
            "Sanitize Query Helper Behavior",
            "--text",
            "Sanitize helper quotes individual words and strips operator noise for safe FTS5 queries",
            "--tags",
            "search sanitize query",
            "--source",
            "memory/scripts/ftsquery.py",
        )
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("[✓] added:", r2.stdout)
        self.assertIn("Sanitize Query Helper Behavior", r2.stdout)
        self.assertIn("(id=2)", r2.stdout)

        # 3. Assert database rows directly
        con = self._get_db()
        cur = con.cursor()
        rows = cur.execute("SELECT * FROM findings ORDER BY id").fetchall()
        self.assertEqual(len(rows), 2)

        f1 = rows[0]
        self.assertEqual(f1["id"], 1)
        self.assertEqual(f1["topic"], "SQLite FTS5 Tokenizer Rules")
        self.assertEqual(f1["text"], "Prefix matching requires trailing asterisk in MATCH query syntax")
        self.assertEqual(f1["tags"], "sqlite fts search")
        self.assertEqual(f1["source"], "https://sqlite.org/fts5.html")
        self.assertEqual(f1["file"], "memory/db-tools/search.py")
        self.assertEqual(f1["symbol"], "search_fts")
        self.assertTrue(f1["created"])

        f2 = rows[1]
        self.assertEqual(f2["id"], 2)
        self.assertEqual(f2["topic"], "Sanitize Query Helper Behavior")
        self.assertEqual(f2["text"], "Sanitize helper quotes individual words and strips operator noise for safe FTS5 queries")
        self.assertEqual(f2["tags"], "search sanitize query")
        self.assertEqual(f2["source"], "memory/scripts/ftsquery.py")
        self.assertTrue(f2["created"])
        con.close()

        # 4. Assert FTS Search Behavior via CLI
        # Query matching only finding 1
        r_s1 = self._findings("search", "Tokenizer")
        self.assertEqual(r_s1.returncode, 0, r_s1.stdout + r_s1.stderr)
        self.assertIn("found: 1", r_s1.stdout)
        self.assertIn("[1]", r_s1.stdout)
        # P9: human search line carries the highlighted topic
        self.assertIn("SQLite FTS5 [Tokenizer] Rules", r_s1.stdout)

        # Query matching only finding 2
        r_s2 = self._findings("search", "Sanitize")
        self.assertEqual(r_s2.returncode, 0, r_s2.stdout + r_s2.stderr)
        self.assertIn("found: 1", r_s2.stdout)
        self.assertIn("[2]", r_s2.stdout)
        self.assertIn("[Sanitize] Query Helper Behavior", r_s2.stdout)

        # Query matching both findings on common indexed term "FTS5"
        r_s_both = self._findings("search", "FTS5")
        self.assertEqual(r_s_both.returncode, 0, r_s_both.stdout + r_s_both.stderr)
        self.assertIn("found: 2", r_s_both.stdout)

        # Filter by source substring
        r_s_src = self._findings("search", "FTS5", "--source", "sqlite.org")
        self.assertEqual(r_s_src.returncode, 0)
        self.assertIn("found: 1", r_s_src.stdout)
        self.assertIn("[1]", r_s_src.stdout)

        # Filter by tag
        r_s_tag = self._findings("search", "FTS5", "--tag", "sqlite")
        self.assertEqual(r_s_tag.returncode, 0)
        self.assertIn("found: 1", r_s_tag.stdout)
        self.assertIn("[1]", r_s_tag.stdout)

        # Search non-matching term
        r_s_none = self._findings("search", "unmatchedtermnothere")
        self.assertEqual(r_s_none.returncode, 0)
        self.assertIn("not found for", r_s_none.stdout)

        # 5. Assert Show command output
        r_show1 = self._findings("show", "1")
        self.assertEqual(r_show1.returncode, 0)
        self.assertIn("SQLite FTS5 Tokenizer Rules", r_show1.stdout)
        self.assertIn("tags: sqlite fts search", r_show1.stdout)
        self.assertIn("source: https://sqlite.org/fts5.html", r_show1.stdout)
        self.assertIn("Prefix matching requires trailing asterisk in MATCH query syntax", r_show1.stdout)

        # 6. Assert Link Add CLI and both directions of traversal
        r_link_add = self._findings(
            "link",
            "add",
            "1",
            "2",
            "--kind",
            "extends",
            "--note",
            "implements safe query construction for tokenizer",
        )
        self.assertEqual(r_link_add.returncode, 0, r_link_add.stdout + r_link_add.stderr)
        self.assertIn("[✓] link: 1 --extends--> 2", r_link_add.stdout)

        # Direct DB inspection of links table
        con = self._get_db()
        links = con.execute("SELECT * FROM links").fetchall()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["from_id"], 1)
        self.assertEqual(links[0]["to_id"], 2)
        self.assertEqual(links[0]["kind"], "extends")
        self.assertEqual(links[0]["note"], "implements safe query construction for tokenizer")
        con.close()

        # Link list for finding 1 (forward direction)
        r_ll1 = self._findings("link", "list", "1")
        self.assertEqual(r_ll1.returncode, 0)
        self.assertIn("links of finding [1]:", r_ll1.stdout)
        self.assertIn("->", r_ll1.stdout)
        self.assertIn("extends", r_ll1.stdout)
        self.assertIn("Sanitize Query Helper Behavior", r_ll1.stdout)
        self.assertIn("(implements safe query construction for tokenizer)", r_ll1.stdout)

        # Link list for finding 2 (backward direction)
        r_ll2 = self._findings("link", "list", "2")
        self.assertEqual(r_ll2.returncode, 0)
        self.assertIn("links of finding [2]:", r_ll2.stdout)
        self.assertIn("<-", r_ll2.stdout)
        self.assertIn("extends", r_ll2.stdout)
        self.assertIn("SQLite FTS5 Tokenizer Rules", r_ll2.stdout)
        self.assertIn("(implements safe query construction for tokenizer)", r_ll2.stdout)

        # Related command for finding 1
        r_rel1 = self._findings("related", "1")
        self.assertEqual(r_rel1.returncode, 0)
        self.assertIn("linked to [1]:", r_rel1.stdout)
        self.assertIn("->", r_rel1.stdout)
        self.assertIn("extends", r_rel1.stdout)
        self.assertIn("Sanitize Query Helper Behavior", r_rel1.stdout)

        # Related command for finding 2
        r_rel2 = self._findings("related", "2")
        self.assertEqual(r_rel2.returncode, 0)
        self.assertIn("linked to [2]:", r_rel2.stdout)
        self.assertIn("<-", r_rel2.stdout)
        self.assertIn("extends", r_rel2.stdout)
        self.assertIn("SQLite FTS5 Tokenizer Rules", r_rel2.stdout)

        # Show finding 1 should now display links
        r_show1_linked = self._findings("show", "1")
        self.assertEqual(r_show1_linked.returncode, 0)
        self.assertIn("links:", r_show1_linked.stdout)
        self.assertIn("->", r_show1_linked.stdout)
        self.assertIn("Sanitize Query Helper Behavior", r_show1_linked.stdout)

        # 7. Delete link via CLI
        r_lrm = self._findings("link", "rm", "1")
        self.assertEqual(r_lrm.returncode, 0)
        self.assertIn("[✓] link deleted: 1 --extends--> 2", r_lrm.stdout)

        con = self._get_db()
        remaining_links = con.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        self.assertEqual(remaining_links, 0)
        con.close()

        r_ll1_empty = self._findings("link", "list", "1")
        self.assertIn("finding [1] has no links", r_ll1_empty.stdout)

    def test_cli_fts_trigger_updates_and_deletions(self):
        """Ensure FTS index updates dynamically on edit and delete operations."""
        # Add finding
        self._findings("add", "Initial FTS Topic", "--text", "Initial unique body text keywordAlpha")
        r_s1 = self._findings("search", "keywordAlpha")
        self.assertIn("found: 1", r_s1.stdout)

        # Edit finding
        self._findings("edit", "1", "--topic", "Modified FTS Topic", "--text", "Modified body text keywordBeta")
        # Old keyword must not be found
        r_s_old = self._findings("search", "keywordAlpha")
        self.assertIn("not found for", r_s_old.stdout)
        # New keyword must match
        r_s_new = self._findings("search", "keywordBeta")
        self.assertIn("found: 1", r_s_new.stdout)
        self.assertIn("Modified FTS Topic", r_s_new.stdout)

        # Delete finding
        r_del = self._findings("del", "1")
        self.assertEqual(r_del.returncode, 0)
        self.assertIn("[✓] deleted: id=1 \"Modified FTS Topic\"", r_del.stdout)

        # Search should find nothing
        r_s_del = self._findings("search", "keywordBeta")
        self.assertIn("not found for", r_s_del.stdout)

    def test_cli_link_validation_and_errors(self):
        """Assert link validation fails cleanly when finding IDs do not exist."""
        self._findings("add", "Single Finding", "--text", "Only finding in DB")
        # Try linking to non-existent finding ID 999
        r = self._findings("link", "add", "1", "999")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no finding with id=999", r.stderr)

        # Link list on non-existent finding
        r_ll = self._findings("link", "list", "999")
        self.assertIn("no finding with id=999", r_ll.stdout)

        # Show on non-existent finding
        r_show = self._findings("show", "999")
        self.assertIn("no finding with id=999", r_show.stdout)

    def test_cli_multi_hop_related_chain(self):
        """Assert multi-hop recursive link traversal via 'related --depth'."""
        self._findings("add", "Node A", "--text", "Root node in chain")
        self._findings("add", "Node B", "--text", "Intermediate node in chain")
        self._findings("add", "Node C", "--text", "Leaf node in chain")

        self._findings("link", "add", "1", "2", "--kind", "extends")
        self._findings("link", "add", "2", "3", "--kind", "depends")

        r_chain = self._findings("related", "1", "--depth", "2")
        self.assertEqual(r_chain.returncode, 0, r_chain.stdout + r_chain.stderr)
        self.assertIn("link graph [1] (depth 2):", r_chain.stdout)
        self.assertIn("[2] d=1  Node B", r_chain.stdout)
        self.assertIn("[3] d=2  Node C", r_chain.stdout)
        self.assertIn("path:", r_chain.stdout)


if __name__ == "__main__":
    unittest.main()
