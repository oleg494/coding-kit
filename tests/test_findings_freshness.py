#!/usr/bin/env python3
"""tests/test_findings_freshness.py — evidence lifecycle (stale verified_at).

verified_at must reflect the CURRENT evidence state, not a historical
maximum. Two defects break that today (see .autonomous/freshness-brief.json):

  1. cmd_edit (memory/db-tools/findings.py) rewrites topic/text/source/
     file/symbol/verify_cmd but never touches verified_at — an edited
     finding keeps advertising a stamp earned by the PRE-EDIT claim.
  2. cmd_verify clears nothing when the verifier FAILS (exit 1 path only
     prints; only the success path writes verified_at).

Consumer impact: search_all.py treats bool(verified_at) as the verified
flag ("verified": true in --json, [unverified] badge otherwise), so a
stale stamp is a false "verified" claim shown to every future session.

Contract pinned here (RED against current findings.py by design):
  - verify success            -> verified_at stamped, no [unverified] badge
  - substantive edit that actually changes topic/text/source/file/symbol/
    verify_cmd -> verified_at cleared, badge back
  - no-op edit (same value)   -> stamp preserved
  - tags / importance edit    -> stamp preserved (classification, not evidence)
  - failed re-verify          -> verified_at cleared
  - later successful verify   -> stamp restored

Everything runs end-to-end as subprocesses against a sandboxed memory
root (MEMORY_ROOT + MEMORY_ROOT_RESEARCH_DB): real files, real verifier
child processes, no production store, no mocked db echoes.
"""

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
DB_TOOLS = KIT / "memory" / "db-tools"
FINDINGS = DB_TOOLS / "findings.py"
SEARCH_ALL = DB_TOOLS / "search_all.py"

# Unique token present in the finding TEXT (not topic) so a topic edit
# cannot hide the row from the search_all assertions.
TOKEN = "evidencez"


def _ok_cmd() -> str:
    """Verifier that always succeeds."""
    return f'"{sys.executable}" -c "raise SystemExit(0)"'


def _fail_cmd() -> str:
    """Verifier that always fails (non-zero, distinct rc)."""
    return f'"{sys.executable}" -c "raise SystemExit(3)"'


def _flag_cmd(flag: Path) -> str:
    """Verifier that succeeds iff `flag` exists — lets one finding flip
    between pass and fail WITHOUT any edit in between (isolates defect 2
    from defect 1). Single quotes inside: cmd.exe-safe shape."""
    p = flag.as_posix()
    return (f'"{sys.executable}" -c '
            f'"import os,sys;sys.exit(0 if os.path.exists(\'{p}\') else 1)"')


class VerifiedStampLifecycleTest(unittest.TestCase):
    """Evidence lifecycle of verified_at across add/verify/edit."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-fresh-"))
        # Sandbox memory root: _compat.chulan_root() markers, so neither
        # findings.py nor search_all.py can resolve the production root
        # (search_all's DB_DIR comes from chulan_root()/db).
        self.root = self.tmp / "memory"
        (self.root / "db").mkdir(parents=True)
        (self.root / "db-tools").mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "VERSION").write_text("4.0.3\n", encoding="utf-8")
        shutil.copy2(KIT / "memory" / "scripts" / "_compat.py",
                     self.root / "scripts" / "_compat.py")
        self.db = self.tmp / "research.db"
        self.env = {k: v for k, v in os.environ.items()
                    if k != "MEMORY_ROOT_RESEARCH_DB"}
        self.env.update(
            MEMORY_ROOT=str(self.root),
            MEMORY_ROOT_RESEARCH_DB=str(self.db),
            PYTHONIOENCODING="utf-8",
            PYTHONUTF8="1",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(FINDINGS)] + list(args),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=120,
        )

    def _add_finding(self, verify_cmd: str) -> int:
        r = self._run("add", f"{TOKEN} lifecycle",
                      "--text", f"{TOKEN} lifecycle probe",
                      "--verify-cmd", verify_cmd)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = re.search(r"id=(\d+)", r.stdout)
        self.assertTrue(m, f"no id in add output: {r.stdout}")
        return int(m.group(1))

    def _verified_at(self, fid: int) -> str:
        con = sqlite3.connect(self.db)
        try:
            return con.execute(
                "SELECT verified_at FROM findings WHERE id = ?",
                (fid,)).fetchone()[0]
        finally:
            con.close()

    def _show(self, fid: int) -> str:
        r = self._run("show", str(fid))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def _search_line(self, fid: int) -> str:
        """The search_all.py human-output line for this finding — the
        surface a future session actually sees."""
        r = subprocess.run(
            [sys.executable, str(SEARCH_ALL), TOKEN],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=120,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = [ln for ln in r.stdout.splitlines()
                 if f"finding#{fid} " in ln]
        self.assertTrue(lines, f"no finding#{fid} line in:\n{r.stdout}")
        return lines[0]

    def _assert_verified(self, fid: int):
        stamp = self._verified_at(fid)
        self.assertTrue(stamp, "verified_at must be stamped after a "
                               "successful verify")
        self.assertIn(f"(last: {stamp})", self._show(fid))
        self.assertNotIn("(last: never)", self._show(fid))
        self.assertNotIn("[unverified]", self._search_line(fid))

    def _assert_unverified(self, fid: int):
        self.assertEqual(self._verified_at(fid), "",
                         "verified_at must be cleared (empty string, the "
                         "schema sentinel) when the old stamp is invalid")
        self.assertIn("(last: never)", self._show(fid))
        self.assertIn("[unverified]", self._search_line(fid))

    # -- green guard -------------------------------------------------------

    def test_verify_success_stamps_and_reports_verified(self):
        """Baseline of the cycle: a passing verifier stamps the row and
        search_all reports it as verified (no badge)."""
        fid = self._add_finding(_ok_cmd())
        r = self._run("verify", str(fid))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VERIFIED", r.stdout)
        self._assert_verified(fid)

    # -- defect 1: substantive edit keeps a stale stamp (RED) --------------

    def test_substantive_edit_invalidates_stamp(self):
        """Changing topic/text/source/file/symbol/verify_cmd drops the
        stamp earned by the PRE-EDIT claim."""
        cases = {
            "topic": ("--topic", f"{TOKEN} lifecycle revised"),
            "text": ("--text", f"{TOKEN} lifecycle probe revised"),
            "source": ("--source", "docs/research/2026-09-19-freshness.md"),
            "file": ("--file", "src/freshness_probe.py"),
            "symbol": ("--symbol", "probe_symbol"),
            "verify_cmd": ("--verify-cmd", _fail_cmd()),
        }
        for field, (flag, value) in cases.items():
            with self.subTest(field=field):
                fid = self._add_finding(_ok_cmd())
                self.assertEqual(self._run("verify", str(fid)).returncode, 0)
                self._assert_verified(fid)
                r = self._run("edit", str(fid), flag, value)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self._assert_unverified(fid)

    # -- guards: what must NOT clear the stamp ------------------------------

    def test_noop_edit_preserves_stamp(self):
        """Editing a field to its CURRENT value is not a substantive
        change — the stamp survives (guards against over-eager clearing)."""
        fid = self._add_finding(_ok_cmd())
        self.assertEqual(self._run("verify", str(fid)).returncode, 0)
        self._assert_verified(fid)
        r = self._run("edit", str(fid), "--text", f"{TOKEN} lifecycle probe")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._assert_verified(fid)

    def test_tags_edit_preserves_stamp(self):
        """Tags are bookkeeping, not evidence — the stamp survives."""
        fid = self._add_finding(_ok_cmd())
        self.assertEqual(self._run("verify", str(fid)).returncode, 0)
        r = self._run("edit", str(fid), "--tags", "alpha beta")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._assert_verified(fid)

    def test_importance_edit_preserves_stamp(self):
        """Importance (classification audit trail) is not evidence —
        the stamp survives the finding_classifications rewrite too."""
        fid = self._add_finding(_ok_cmd())
        self.assertEqual(self._run("verify", str(fid)).returncode, 0)
        r = self._run("edit", str(fid), "--importance", "high")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._assert_verified(fid)

    # -- defect 2: failed re-verify keeps a stale stamp (RED) ----------------

    def test_failed_reverify_clears_stamp(self):
        """A verifier that USED to pass and now fails must clear the
        current stamp (no edit involved — pure verify path)."""
        flag = self.tmp / "flag.txt"
        fid = self._add_finding(_flag_cmd(flag))
        flag.write_text("ok", encoding="utf-8")
        self.assertEqual(self._run("verify", str(fid)).returncode, 0)
        self._assert_verified(fid)
        flag.unlink()
        r = self._run("verify", str(fid))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAILED", r.stdout)
        self._assert_unverified(fid)

    def test_successful_reverify_restores_stamp(self):
        """After a failed verify cleared the stamp, a passing verify
        stamps it again — the badge flips back the same session."""
        flag = self.tmp / "flag.txt"
        fid = self._add_finding(_flag_cmd(flag))
        flag.write_text("ok", encoding="utf-8")
        self.assertEqual(self._run("verify", str(fid)).returncode, 0)
        flag.unlink()
        self.assertEqual(self._run("verify", str(fid)).returncode, 1)
        flag.write_text("back", encoding="utf-8")
        r = self._run("verify", str(fid))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._assert_verified(fid)

    # -- the full cycle from the defect report (RED) -------------------------

    def test_edit_then_reverify_full_cycle(self):
        """success -> substantive edit -> unverified -> success again."""
        fid = self._add_finding(_ok_cmd())
        self.assertEqual(self._run("verify", str(fid)).returncode, 0)
        self._assert_verified(fid)
        r = self._run("edit", str(fid), "--text",
                      f"{TOKEN} lifecycle probe revised")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._assert_unverified(fid)
        r = self._run("verify", str(fid))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self._assert_verified(fid)


if __name__ == "__main__":
    unittest.main()
