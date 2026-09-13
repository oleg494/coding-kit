#!/usr/bin/env python3
"""v4.0.2 audit remediation: eval/results hygiene.

Two defect classes from the v3.5.0-v4.0.1 audit:

1. Personal-path leakage: a live trigger run recorded the operator's
   home directory (C:\\Users\\<name>\\AppData\\...) inside executor error
   strings, and the artifact was committed. Committed result JSON must
   contain no `Users\\<name>` / `Users/<name>` literals; the 2026-08-29
   trigger artifact is scrubbed to a `~` prefix.

2. Scope: this file only guards committed results. The manifest side of
   eval hygiene (scenarios/tasks/queries/baselines hashed, mutable
   results unpinned) lives in tests/test_integrity_manifest.py.

The committed set is every eval/results file git tracks — flat JSONs and
subdirectory packages alike (the 2026-09-13 research packages live one
level down). Local staging output that was never committed is out of
scope by construction: the file list comes from `git ls-files`, so a
live run's dirt never reddens this suite.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
RESULTS = KIT / "eval" / "results"

# Raw-byte forms: JSON-escaped backslashes count too — any
# Users\<name> / Users/<name> spelling contains one of these byte runs.
_PERSONAL = (
    re.compile(rb"Users\\\\oleg2"),
    re.compile(rb"Users/oleg2"),
    re.compile(rb"Users\\\\\\\\oleg2"),
)

def _tracked_result_files() -> list[Path]:
    """Tracked result artifacts (flat + subdirectory packages).

    Degrades outside a git checkout (distributed tarballs): git ls-files
    fails -> fall back to every results file, as in a repo the untracked
    ones are staging dirt only a live run just wrote.
    """
    if shutil.which("git") is None:
        return _fallback_result_files()
    proc = subprocess.run(
        ["git", "-C", str(KIT), "ls-files", "--", "eval/results"],
        capture_output=True, check=False)  # returncode handled below
    if proc.returncode != 0:  # not a git work tree (e.g. dist tarball)
        return _fallback_result_files()
    out = proc.stdout.decode("utf-8").splitlines()
    return sorted(KIT / rel for rel in out
                  if rel.endswith((".json", ".txt", ".md")))


def _fallback_result_files() -> list[Path]:
    return sorted(p for p in RESULTS.rglob("*")
                  if p.is_file() and p.suffix in (".json", ".txt", ".md"))


class ResultHygieneTest(unittest.TestCase):
    def test_committed_results_exist(self):
        self.assertTrue(_tracked_result_files(),
                        "eval/results lost its committed artifacts?")

    def test_no_personal_path_literals(self):
        for p in _tracked_result_files():
            with self.subTest(result=str(p.relative_to(KIT))):
                raw = p.read_bytes()
                for pat in _PERSONAL:
                    self.assertIsNone(pat.search(raw),
                                      f"{p.name}: personal path leaked")
                self.assertNotIn(b"oleg2", raw,
                                 f"{p.name}: username literal leaked")

    def test_tracked_results_still_parse(self):
        # Byte surgery on evidence artifacts (path scrubs) must not break
        # parsing. Every tracked JSON must load to something (null means
        # the scrub corrupted the document); arrays are legitimate shapes
        # here (recovery logs, case lists).
        tracked = _tracked_result_files()
        rels = {p.relative_to(KIT).as_posix() for p in tracked}
        for p in tracked:
            with self.subTest(result=p.relative_to(KIT).as_posix()):
                if p.suffix != ".json":
                    continue
                doc = json.loads(p.read_text(encoding="utf-8"))
                self.assertIsNotNone(doc, f"{p.name}: parses to null")

        # Shape probes are unconditional: this suite ships with the tree
        # it guards, so the 2026-09-13 packages are always present — a
        # renamed/moved/deleted artifact fails loudly instead of skipping
        # green. (The non-git fallback changes file enumeration, not
        # which files exist.)
        native = ("eval/results/autonomous-knowledge-20260913/"
                  "native-adapter-result.json")
        self.assertIn(native, rels, f"{native} missing from tracked results")
        doc = json.loads((KIT / native).read_text(encoding="utf-8"))
        self.assertEqual(doc["rc"], 0)
        inner = json.loads(doc["stdout"])
        self.assertEqual(len(inner["checks"]), 9)

        cases = ["foreign", "crlf", "binary", "anchor_failure", "legacy",
                 "preview"]
        docs = {}
        for name in ("recovery-before.json", "recovery-after.json"):
            rel = f"eval/results/knowledge-procedure-20260913/{name}"
            self.assertIn(rel, rels, f"{rel} missing from tracked results")
            docs[name] = json.loads((KIT / rel).read_text(encoding="utf-8"))
        # Semantic core of the recovery evidence: the before-probe ran
        # against the broken adapter (0/6), the after-probe against the
        # repaired one (6/6). Identical vectors would mean one of the two
        # files lost its meaning in a scrub.
        for name, doc in docs.items():
            self.assertEqual([d["case"] for d in doc], cases)
        self.assertEqual([d["pass"] for d in docs["recovery-before.json"]],
                         [False] * 6)
        self.assertEqual([d["pass"] for d in docs["recovery-after.json"]],
                         [True] * 6)


if __name__ == "__main__":
    unittest.main()
