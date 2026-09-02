#!/usr/bin/env python3
"""install.py contract tests (stdlib unittest, no deps).

Covers the silent-failure class that bit the kit three times:
layout creation, idempotent re-run, engine link re-pointing,
real-dir preservation, smoke exit-code propagation, and the CLI
argv guard ("--help" prints usage instead of installing, unknown
argv refused).

Run: python -m unittest discover -s tests -v
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "install_under_test", KIT / "scripts" / "install.py")
install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)

PROBE = "warmup"  # matches memory-warmup.py, indexed on every OS

def _make_foreign_link(target: Path, dest: Path) -> None:
    """Create a link (junction on NT, symlink elsewhere) target -> dest."""
    if os.name == "nt":
        env = dict(os.environ, KIT_LINK_PATH=str(target),
                   KIT_LINK_TARGET=str(dest))
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "New-Item -ItemType Junction -Path $env:KIT_LINK_PATH "
             "-Target $env:KIT_LINK_TARGET | Out-Null"],
            check=True, env=env)
    else:
        target.symlink_to(dest, target_is_directory=True)


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-install-"))
        self.root = self.tmp / "mem"
        # a probe post makes the post-install smoke search succeed
        (self.root / "Wiki" / "reference").mkdir(parents=True)
        (self.root / "Wiki" / "reference" / "probe.md").write_text(
            "---\ntype: reference\ntitle: probe\n---\n"
            "warmup: the agent searches the memory database\n", encoding="utf-8")
        self._env = os.environ.get("MEMORY_ROOT")
        os.environ["MEMORY_ROOT"] = str(self.root)

    def tearDown(self):
        if self._env is None:
            os.environ.pop("MEMORY_ROOT", None)
        else:
            os.environ["MEMORY_ROOT"] = self._env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_install_creates_layout(self):
        self.assertEqual(install.main(), 0)
        self.assertTrue((self.root / "VERSION").is_file())
        self.assertEqual(
            (self.root / "VERSION").read_text(encoding="utf-8").strip(),
            install.ENGINE_VERSION,
        )
        self.assertEqual(install.ENGINE_VERSION, "2.9")
        for t in install.WIKI_TYPES:
            self.assertTrue((self.root / "Wiki" / t).is_dir(), t)
        self.assertTrue((self.root / "db").is_dir())
        self.assertTrue((self.root / "scripts" / "memory-warmup.py").is_file())
        self.assertTrue((self.root / "scripts" / "_compat.py").is_file())
        link = self.root / "db-tools"
        self.assertTrue(install._is_link(link))
        self.assertEqual(link.resolve(), install.ENGINE.resolve())

    def test_rerun_is_idempotent(self):
        self.assertEqual(install.main(), 0)
        self.assertEqual(install.main(), 0)

    def test_foreign_link_is_repointed(self):
        foreign = self.tmp / "other-engine"
        foreign.mkdir()
        _make_foreign_link(self.root / "db-tools", foreign)
        self.assertEqual(install.main(), 0)
        self.assertEqual((self.root / "db-tools").resolve(),
                         install.ENGINE.resolve())

    def test_real_dir_is_preserved(self):
        real = self.root / "db-tools"
        real.mkdir(parents=True)
        (real / "precious.txt").write_text("data", encoding="utf-8")
        self.assertEqual(install.main(), 0)
        self.assertTrue((real / "precious.txt").is_file())
        self.assertFalse(install._is_link(real))

    def test_smoke_failure_fails_install(self):
        real_run = subprocess.run

        def fake_run(cmd, **kw):
            if "search_all.py" in str(cmd[1]):
                return subprocess.CompletedProcess(cmd, 1, "", "boom")
            return real_run(cmd, **kw)

        with mock.patch.object(install.subprocess, "run", side_effect=fake_run):
            self.assertEqual(install.main(), 1)


class InstallCliGuardTest(unittest.TestCase):
    def _run(self, args):
        return subprocess.run(
            [sys.executable, str(KIT / "scripts" / "install.py")] + args,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180)

    def test_help_prints_usage_and_does_not_install(self):
        r = self._run(["--help"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("usage", r.stdout.lower())
        self.assertNotIn("Install done", r.stdout)

    def test_unknown_arg_refused(self):
        r = self._run(["--frobnicate"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Install done", r.stdout)


class InstallMemoryRootValidationTest(unittest.TestCase):
    def test_relative_memory_root_rejected_by_memory_root_helper(self):
        with mock.patch.dict(os.environ, {"MEMORY_ROOT": "relative/path"}):
            with self.assertRaises(RuntimeError) as ctx:
                install.memory_root()
            self.assertIn("MEMORY_ROOT must be an absolute path", str(ctx.exception))

    def test_relative_memory_root_rejected_by_main_without_creating_anything(self):
        tmp = Path(tempfile.mkdtemp(prefix="kit-rel-test-"))
        try:
            rel_target = tmp / "relative_mem_root"
            with mock.patch.dict(os.environ, {"MEMORY_ROOT": "relative_mem_root"}), \
                 mock.patch("os.getcwd", return_value=str(tmp)):
                ret = install.main()
                self.assertNotEqual(ret, 0)
                self.assertFalse(rel_target.exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

class LinkEngineHardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-link-test-"))
        self.root = self.tmp / "mem"
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_powershell_preflight_on_nt_raises(self):
        with mock.patch("os.name", "nt"), \
             mock.patch.object(install.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                install.link_engine(self.root)
            self.assertIn("PowerShell executable", str(ctx.exception))
            self.assertIn("not found", str(ctx.exception))

    def test_link_creation_failure_rolls_back_previous_link(self):
        target = self.root / "db-tools"
        other_engine = self.tmp / "other-engine"
        other_engine.mkdir()
        _make_foreign_link(target, other_engine)
        self.assertTrue(install._is_link(target))

        if os.name == "nt":
            real_run = subprocess.run
            call_count = 0
            def failing_run(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise subprocess.CalledProcessError(1, "powershell", output="boom")
                return real_run(*args, **kwargs)

            with mock.patch.object(install.subprocess, "run", side_effect=failing_run):
                with self.assertRaises(RuntimeError) as ctx:
                    install.link_engine(self.root)
                self.assertIn("Failed to link engine", str(ctx.exception))
                self.assertIn("Restored previous link", str(ctx.exception))
                self.assertTrue(install._is_link(target))
                self.assertEqual(target.resolve(), other_engine.resolve())
        else:
            original_symlink = Path.symlink_to
            call_count = 0
            def failing_symlink(p, dest, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise OSError("symlink failed")
                return original_symlink(p, dest, **kwargs)

            with mock.patch.object(Path, "symlink_to", side_effect=failing_symlink, autospec=True):
                with self.assertRaises(RuntimeError) as ctx:
                    install.link_engine(self.root)
                self.assertIn("Failed to link engine", str(ctx.exception))
                self.assertIn("Restored previous link", str(ctx.exception))
                self.assertTrue(install._is_link(target))
                self.assertEqual(target.resolve(), other_engine.resolve())


class PythonEnvironmentCheckTest(unittest.TestCase):
    def test_default_environment_passes(self):
        ok, msg = install.check_python_environment()
        self.assertTrue(ok, msg)

    def test_isolated_flag_rejected(self):
        flags = mock.Mock(isolated=1, no_site=0)
        ok, msg = install.check_python_environment(flags=flags, executable=sys.executable)
        self.assertFalse(ok)
        self.assertIn("isolated", msg.lower())
        self.assertIn("standard", msg.lower())

    def test_no_site_flag_rejected(self):
        flags = mock.Mock(isolated=0, no_site=1)
        ok, msg = install.check_python_environment(flags=flags, executable=sys.executable)
        self.assertFalse(ok)
        self.assertIn("no_site", msg.lower())
        self.assertIn("standard", msg.lower())

    def test_embedded_pth_file_rejected(self):
        tmp = Path(tempfile.mkdtemp(prefix="kit-pth-test-"))
        try:
            fake_exe = tmp / "python.exe"
            fake_exe.touch()
            pth = tmp / "python311._pth"
            pth.write_text("import site\n", encoding="utf-8")
            flags = mock.Mock(isolated=0, no_site=0)
            ok, msg = install.check_python_environment(flags=flags, executable=fake_exe)
            self.assertFalse(ok)
            self.assertIn("embedded", msg.lower())
            self.assertIn("python311._pth", msg)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_venv_like_environment_passes(self):
        tmp = Path(tempfile.mkdtemp(prefix="kit-venv-test-"))
        try:
            fake_exe = tmp / "Scripts" / "python.exe"
            fake_exe.parent.mkdir(parents=True)
            fake_exe.touch()
            (tmp / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
            flags = mock.Mock(isolated=0, no_site=0)
            ok, msg = install.check_python_environment(flags=flags, executable=fake_exe)
            self.assertTrue(ok, msg)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_main_rejects_unsupported_python_environment(self):
        tmp = Path(tempfile.mkdtemp(prefix="kit-unsup-test-"))
        try:
            with mock.patch.dict(os.environ, {"MEMORY_ROOT": str(tmp / "mem")}), \
                 mock.patch.object(install, "check_python_environment",
                                   return_value=(False, "isolated Python detected")):
                self.assertEqual(install.main(), 1)
                self.assertFalse((tmp / "mem").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
if __name__ == "__main__":
    unittest.main()
