#!/usr/bin/env python3
"""Wave 4 v3.8.0 Task 14: memory hygiene taxonomy (Wiki).

Contract (lint rules over tmp wiki fixtures — the real ~/.memory/Wiki is
NEVER touched by these tests; the parent does the real backfill):
- `type` frontmatter must be one of {user, feedback, project, reference};
  other/missing values are WARN-tier (legacy notes: errors/howto/... stay
  valid at WARN, never fail the lint).
- `Wiki/index.md` is hard-capped at 200 lines (Anthropic memory-tool cap):
  over-cap is an ERROR (FAIL, exit 1) demanding consolidation — the tail
  is never silently dropped.
- freshness: a note whose `date`/`modified` is older than 180 days WARNs.
- `modified` ISO-8601 stamp: writers auto-maintain it (stamp_modified
  idempotent; build.py stamps wiki notes into the indexed copy like the
  wave1 origin stamp); lint checks format when present (malformed = WARN).
- Exit contract unchanged: real errors -> 1, warnings alone -> 0.

Run: python -m pytest tests/test_wiki_hygiene.py -v
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "memory" / "db-tools"))
import lint_wiki

NOTE_OK = """---
type: reference
title: "Fresh note"
description: "recently touched"
date: 2026-08-20
modified: 2026-08-30
tags: [hygiene]
origin: manual
---

Body.
"""

NOTE_LEGACY_TYPE = """---
type: error
title: "Legacy bug note"
description: "old taxonomy"
date: 2026-08-20
tags: [legacy]
origin: session
---

Body.
"""


def _note(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8", newline="\n")


class WikiHygieneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-hygiene-"))
        self.wiki = self.tmp / "Wiki"
        self.wiki.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_main(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = lint_wiki.main([str(self.wiki)])
        return rc, buf.getvalue()

    # -- taxonomy: type in {user, feedback, project, reference} -----------

    def test_typed_stamped_note_passes_clean(self):
        _note(self.wiki, "reference/fresh-note.md", NOTE_OK)
        rc, out = self._run_main()
        self.assertEqual(rc, 0, out)
        self.assertIn("library clean", out)

    def test_legacy_type_warns_not_fails(self):
        _note(self.wiki, "errors/legacy-bug.md", NOTE_LEGACY_TYPE)
        rc, out = self._run_main()
        self.assertEqual(rc, 0, "legacy type alone is WARN: exit stays 0")
        self.assertIn("type", out)
        self.assertIn("legacy", out.lower())

    def test_missing_type_warns(self):
        _note(self.wiki, "notes/notyped.md", NOTE_LEGACY_TYPE.replace(
            "type: error\n", ""))
        rc, out = self._run_main()
        self.assertEqual(rc, 0)
        self.assertIn("type", out)

    # -- index.md hard cap ------------------------------------------------

    def test_index_over_cap_fails(self):
        lines = ["# Index — каталог Wiki", "", "| a | b |", "|---|---|"]
        lines += [f"| row {i} | x |" for i in range(200)]
        _note(self.wiki, "index.md", "\n".join(lines) + "\n")
        _note(self.wiki, "reference/fresh-note.md", NOTE_OK)
        rc, out = self._run_main()
        self.assertEqual(rc, 1, "index over cap must FAIL (exit 1)")
        self.assertIn("index.md", out)
        self.assertIn("200", out)
        self.assertIn("consolidat", out.lower())

    def test_index_at_cap_passes(self):
        lines = ["# Index", "", "| a | b |", "|---|---|"]
        lines += [f"| row {i} | x |" for i in range(196)]
        _note(self.wiki, "index.md", "\n".join(lines) + "\n")
        _note(self.wiki, "reference/fresh-note.md", NOTE_OK)
        rc, out = self._run_main()
        self.assertEqual(rc, 0, out)

    # -- freshness (WARN > 180 days) ---------------------------------------

    def test_stale_note_warns(self):
        stale = NOTE_OK.replace("date: 2026-08-20", "date: 2025-12-01")
        stale = stale.replace("modified: 2026-08-30", "modified: 2025-12-05")
        _note(self.wiki, "reference/stale.md", stale)
        rc, out = self._run_main()
        self.assertEqual(rc, 0, "staleness alone is WARN: exit stays 0")
        self.assertIn("stale.md", out)
        self.assertIn("180", out)

    def test_stale_with_recent_modified_is_fresh(self):
        _note(self.wiki, "reference/kept-fresh.md", NOTE_OK.replace(
            "date: 2026-08-20", "date: 2025-12-01"))
        rc, out = self._run_main()
        # NOTE_OK carries modified: 2026-08-30 — fresh edit wins
        self.assertEqual(rc, 0, out)
        self.assertNotIn("kept-fresh.md", out.split("Warnings:")[1]
                         if "Warnings:" in out else out)

    # -- modified ISO-8601 stamp -------------------------------------------

    def test_malformed_modified_warns(self):
        _note(self.wiki, "reference/badstamp.md", NOTE_OK.replace(
            "modified: 2026-08-30", "modified: last tuesday"))
        rc, out = self._run_main()
        self.assertEqual(rc, 0, "malformed modified is WARN, not FAIL")
        self.assertIn("modified", out)

    def test_stamp_modified_is_idempotent_and_today(self):
        import datetime
        text = "---\ntype: reference\ntitle: t\ndescription: d\ndate: 2026-01-01\ntags: [x]\n---\nbody\n"
        stamped = lint_wiki.stamp_modified(text)
        today = datetime.date.today().isoformat()
        self.assertIn(f"modified: {today}", stamped)
        again = lint_wiki.stamp_modified(stamped)
        self.assertEqual(again, stamped, "stamp must be idempotent")

    def test_stamp_modified_preserves_existing(self):
        self.assertEqual(lint_wiki.stamp_modified(NOTE_OK), NOTE_OK)

    def test_build_stamps_modified_into_indexed_copy(self):
        """build.py stamps `modified` on wiki notes lacking it — in the
        indexed copy only (file on disk never rewritten, wave1 pattern)."""
        import build
        text = "---\ntype: reference\ntitle: t\ndescription: d\ndate: 2026-01-01\ntags: [x]\n---\nbody\n"
        content, digest_changed = build.stamp_wiki_frontmatter(
            "Wiki/reference/x.md", text, "oldhash")
        self.assertIn("modified:", content)
        self.assertTrue(digest_changed)


if __name__ == "__main__":
    unittest.main()
