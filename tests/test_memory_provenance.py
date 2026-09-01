#!/usr/bin/env python3
"""Wave 1 v3.5.0 trust-surface, Task 3: ASI06 memory-provenance contract.

Memory is an attack surface (OWASP ASI06; Cisco MemoryTrap; Willison's
lethal trifecta). Repo-side deliverables, all on tmp fixtures (the real
~/.memory Wiki is user data, never touched by tests):

- lint_wiki.py gains rule check_origin: every note (outside service files
  and skip dirs) must carry `origin: web|session|subagent|manual`;
  `origin: web` additionally requires `source_url:`. Absence = WARN-tier
  error listed per file (library stays warnable, exit code unchanged).
- trap suite grows a DATA-not-INSTRUCTIONS memory-poisoning scenario:
  count 21 -> 22 in tests/test_release_contract.py.
- build.py stamps `origin: manual` on wiki notes that lack it (legacy
  default; never rewrites history — mtime-then-hash incremental untouched).
"""
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "lint_wiki", KIT / "memory" / "db-tools" / "lint_wiki.py")
lint_wiki = importlib.util.module_from_spec(_spec)
sys.modules["lint_wiki"] = lint_wiki
_spec.loader.exec_module(lint_wiki)


def _note(root: Path, rel: str, body: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8", newline="\n")


_NOTE_NO_ORIGIN = """---
type: note
title: Some web find
description: fetched from a blog
date: 2026-09-01
tags: [web]
---

Body mentioning an instruction-looking line.
"""

_NOTE_WEB_ORIGIN = """---
type: note
title: Some web find
description: fetched from a blog
date: 2026-09-01
tags: [web]
origin: web
source_url: https://example.com/post
---

Body.
"""

_NOTE_MANUAL = """---
type: note
title: Manual insight
description: written by hand
date: 2026-09-01
tags: [insight]
origin: manual
---

Body.
"""


class LintOriginTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-lint-"))
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

    def test_note_without_origin_is_warned(self):
        _note(self.wiki, "notes/some-web-find.md", _NOTE_NO_ORIGIN)
        rc, out = self._run_main()
        self.assertIn("some-web-find.md", out)
        self.assertIn("origin", out)
        self.assertEqual(rc, 0, "missing origin alone is WARN: exit stays 0")

    def test_web_origin_requires_source_url(self):
        _note(self.wiki, "notes/web-no-url.md", _NOTE_WEB_ORIGIN.replace(
            "source_url: https://example.com/post\n", ""))
        _rc, out = self._run_main()
        self.assertIn("web-no-url.md", out)
        self.assertIn("source_url", out)

    def test_web_origin_with_source_url_is_clean(self):
        _note(self.wiki, "notes/some-web-find.md", _NOTE_WEB_ORIGIN)
        _note(self.wiki, "notes/manual-note.md", _NOTE_MANUAL)
        rc, out = self._run_main()
        self.assertEqual(rc, 0, out)
        self.assertIn("library clean", out)

    def test_missing_origin_is_warn_not_error_for_legacy_notes(self):
        """The WARN tier: missing origin is listed but must not fail a
        legacy library the way a hard error would — the exit contract
        stays: real errors (bad frontmatter) -> 1, warnings alone -> 0."""
        _note(self.wiki, "notes/legacy.md", _NOTE_NO_ORIGIN)
        rc, out = self._run_main()
        self.assertEqual(rc, 0, "WARN alone must keep exit 0")
        self.assertIn("origin", out)


class BuildOriginStampTest(unittest.TestCase):
    def test_stamp_origin_defaults_to_manual(self):
        text = "---\ntype: note\ntitle: t\n---\nbody\n"
        stamped = lint_wiki.stamp_origin(text)
        self.assertIn("origin: manual", stamped)
        # idempotent: no double stamp
        self.assertEqual(lint_wiki.stamp_origin(stamped), stamped)

    def test_stamp_origin_preserves_existing(self):
        text = "---\norigin: web\nsource_url: https://x\n---\nbody\n"
        self.assertEqual(lint_wiki.stamp_origin(text), text)


class TrapScenarioCountTest(unittest.TestCase):
    def test_memory_poisoning_scenario_exists_and_defines_oracle(self):
        sc = KIT / "eval" / "scenarios" / "memory-poisoning.md"
        self.assertTrue(sc.is_file(), "memory-poisoning.md must exist")
        text = sc.read_text(encoding="utf-8")
        self.assertIn("DATA", text)
        self.assertIn("INSTRUCTIONS", text)

    def test_scenario_count_is_22(self):
        n = len(list((KIT / "eval" / "scenarios").glob("*.md")))
        self.assertEqual(n, 22, "trap suite must grow 21 -> 22")


if __name__ == "__main__":
    unittest.main()
