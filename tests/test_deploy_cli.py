"""Regression test for scripts/tools/deploy.py CLI argument parsing.

Ensures:
- `deploy.py --help` / `-h` prints help, exits 0, and causes ZERO mutations.
- Unknown arguments exit 2 (argparse standard), print error, and cause ZERO mutations.
- `deploy.py --dry-run` WITHOUT `--canonical` is rejected (exit 2) before any
  deploy step runs — the parser once accepted it and silently fell through to
  the full global rollout (same bug class as the 2026-09-06 --help incident).
- `deploy.py` (no args) still runs the full documented deploy sequence,
  including bump_claude_md (behavioral replacement for the deleted
  source-text pin in test_release_contract.py).
"""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parent.parent


class DeployCliTest(unittest.TestCase):
    def _run_deploy_in_isolated_sandbox(self, argv: list[str]):
        """Runs deploy.main() with completely isolated sandbox paths.

        Returns (returncode, stdout, stderr, created_files_in_fake_home).
        """
        spec = importlib.util.spec_from_file_location(
            "deploy", KIT / "scripts" / "tools" / "deploy.py"
        )
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)

        with tempfile.TemporaryDirectory(prefix="test-deploy-home-") as td:
            fake_home = Path(td)
            out_buf = io.StringIO()
            err_buf = io.StringIO()

            # Set up mock targets pointing into fake_home
            fake_claude_md = fake_home / ".claude" / "CLAUDE.md"
            fake_sync_targets = [
                str(fake_home / ".claude" / "skills"),
                str(fake_home / ".agents" / "skills"),
            ]
            fake_harnesses = [
                {
                    "id": "test_omp",
                    "router": str(fake_home / ".omp" / "agent" / "AGENTS.md"),
                    "name": "TestOMP",
                    "skills_line": None,
                    "skills_dir": None,
                }
            ]

            with mock.patch.object(sys, "argv", ["deploy.py", *argv]), \
                 mock.patch.object(sys, "stdout", out_buf), \
                 mock.patch.object(sys, "stderr", err_buf), \
                 mock.patch.object(deploy, "CLAUDE_MD", fake_claude_md), \
                 mock.patch.object(deploy, "SYNC_TARGETS", fake_sync_targets), \
                 mock.patch.object(deploy, "HARNESSES", fake_harnesses):

                rc = None
                try:
                    res = deploy.main()
                    rc = 0 if res is None else res
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)

            created_files = [
                str(p.relative_to(fake_home))
                for p in fake_home.rglob("*")
                if p.is_file()
            ]
            return rc, out_buf.getvalue(), err_buf.getvalue(), created_files

    def test_help_flag_exits_zero_and_causes_zero_mutations(self):
        for flag in ["--help", "-h"]:
            with self.subTest(flag=flag):
                rc, stdout, stderr, created = self._run_deploy_in_isolated_sandbox([flag])
                self.assertEqual(rc, 0, f"{flag} must exit 0, got {rc}")
                self.assertIn("usage:", stdout.lower() + stderr.lower())
                self.assertEqual(
                    created, [],
                    f"{flag} must not mutate or create files, found: {created}"
                )

    def test_unknown_argument_exits_2_and_causes_zero_mutations(self):
        rc, stdout, stderr, created = self._run_deploy_in_isolated_sandbox(["--bogus-flag"])
        self.assertEqual(rc, 2, f"Unknown arg must exit 2 (argparse), got {rc}")
        self.assertEqual(
            created, [],
            f"Unknown arg must not mutate or create files, found: {created}"
        )



class DeployDryRunBoundaryTest(unittest.TestCase):
    """The deploy steps are replaced with recorders, so a parser fall-through
    is observable (the recorded sequence) instead of being masked by the
    integrity gate's exit 3 or by mutating anything real."""

    def _main_with_recorders(self, argv: list[str]):
        spec = importlib.util.spec_from_file_location(
            "deploy", KIT / "scripts" / "tools" / "deploy.py"
        )
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)

        calls: list[str] = []
        out_buf = io.StringIO()
        err_buf = io.StringIO()

        def rec(name, result=None):
            def _fn(*args, **kwargs):
                calls.append(name)
                return result
            return _fn

        with mock.patch.object(deploy, "integrity_gate", rec("integrity_gate")), \
             mock.patch.object(deploy, "preflight_routers_and_claude", rec("preflight_routers_and_claude", (True, []))), \
             mock.patch.object(deploy, "preflight_skills", rec("preflight_skills", (True, [], []))), \
             mock.patch.object(deploy, "execute_skills", rec("execute_skills", [])), \
             mock.patch.object(deploy, "regen_routers", rec("regen_routers", [])), \
             mock.patch.object(deploy, "bump_claude_md",
                               rec("bump_claude_md", "unchanged")), \
             mock.patch.object(deploy, "verify", rec("verify", True)), \
             mock.patch.object(sys, "argv", ["deploy.py", *argv]), \
             mock.patch.object(sys, "stdout", out_buf), \
             mock.patch.object(sys, "stderr", err_buf):
            try:
                res = deploy.main()
                rc = 0 if res is None else res
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        return rc, calls, out_buf.getvalue(), err_buf.getvalue()

    def test_standalone_dry_run_rejected_before_any_deploy_step(self):
        rc, calls, _out, err = self._main_with_recorders(["--dry-run"])
        self.assertEqual(
            rc, 2,
            f"standalone --dry-run must be rejected with argparse rc 2, got {rc}")
        self.assertEqual(
            calls, [],
            f"parser must reject before ANY deploy step runs, ran: {calls}")
        self.assertIn("--dry-run", err)

    def test_no_args_still_runs_full_deploy_sequence(self):
        rc, calls, _out, _err = self._main_with_recorders([])
        self.assertEqual(rc, 0)
        self.assertEqual(
            calls,
            ["integrity_gate", "preflight_routers_and_claude", "preflight_skills",
             "execute_skills", "regen_routers", "bump_claude_md", "verify"],
            "no-args deploy must run the documented sequence, including the "
            "CLAUDE.md bump (verify() fails on every VERSION bump without it)")

if __name__ == "__main__":
    unittest.main()
