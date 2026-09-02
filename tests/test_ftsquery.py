#!/usr/bin/env python3
"""tests/test_ftsquery.py — P8 behavior matrix for the single sanitizer.

Pins the four classes the 2026-09-02 audit named (plan D-A + P8):
- prefix star lands OUTSIDE quotes ('body*' -> '"body"*'), including the
  special-char body case ('agent-lsp*' -> '"agent-lsp"*');
- dots are special: bare '5.3' is an FTS5 syntax error, quoted it is a
  phrase; fallback_query splits on dots for the cmd_search retry;
- operators / NEAR / ready-made quoted tokens pass through untouched;
- the masked form ('star inside quotes' = exact match) stays broken, so
  nobody "simplifies" the star back inside.
"""
import sqlite3
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
DB_TOOLS = KIT / "memory" / "db-tools"
if str(DB_TOOLS) not in sys.path:
    sys.path.insert(0, str(DB_TOOLS))

from ftsquery import fallback_query, sanitize_query  # noqa: E402


class SanitizeMatrixTest(unittest.TestCase):
    def test_prefix_star_outside_quotes(self):
        self.assertEqual(sanitize_query("prox*"), '"prox"*')
        self.assertEqual(sanitize_query("agent-lsp*"), '"agent-lsp"*')
        self.assertEqual(sanitize_query("firmware*"), '"firmware"*')

    def test_special_bodies_quoted_star_preserved(self):
        self.assertEqual(sanitize_query("agent-lsp"), '"agent-lsp"')
        self.assertEqual(sanitize_query("a(b)"), '"a(b)"')

    def test_dot_tokens_quoted(self):
        # bare '5.3' is an FTS5 syntax error; quoted = phrase [5, 3]
        self.assertEqual(sanitize_query("5.3"), '"5.3"')
        self.assertEqual(sanitize_query("v4.0.3"), '"v4.0.3"')

    def test_operators_and_quoted_passthrough(self):
        self.assertEqual(sanitize_query("alpha AND beta"),
                         "alpha AND beta")
        self.assertEqual(sanitize_query("NEAR(a,b)"), "NEAR(a,b)")
        self.assertEqual(sanitize_query('"ready-made"'), '"ready-made"')
    def test_lone_quote_escaped(self):
        # A single quote token must NOT be treated as a ready-made quoted pair
        self.assertEqual(sanitize_query('foo " bar'), 'foo """" bar')
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
        con.execute("INSERT INTO t VALUES ('foo \" bar')")
        q = sanitize_query('foo " bar')
        n = con.execute(
            "SELECT COUNT(*) FROM t WHERE t MATCH ?", (q,)).fetchone()[0]
        self.assertEqual(n, 1)
        con.close()

    def test_fallback_splits_dots(self):
        self.assertEqual(fallback_query("5.3"), '"5" "3"')
        self.assertEqual(fallback_query("v4.0.3"), '"v4" "0" "3"')
        self.assertEqual(fallback_query("plain"), '"plain"')

    def test_dot_query_executes_after_sanitize(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
        con.execute("INSERT INTO t VALUES ('release 5.3 notes')")
        q = sanitize_query("5.3")
        n = con.execute(
            "SELECT COUNT(*) FROM t WHERE t MATCH ?", (q,)).fetchone()[0]
        self.assertEqual(n, 1, f"quoted dot phrase must match: {q}")
        # and the bare form is the syntax error P8's retry exists for
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("SELECT COUNT(*) FROM t WHERE t MATCH ?", ("5.3",))
        fb = fallback_query("5.3")
        n2 = con.execute(
            "SELECT COUNT(*) FROM t WHERE t MATCH ?", (fb,)).fetchone()[0]
        self.assertEqual(n2, 1, f"fallback must match too: {fb}")
        con.close()


if __name__ == "__main__":
    unittest.main()
