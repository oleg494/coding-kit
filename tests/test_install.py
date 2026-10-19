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
    """Create a link (junction on NT, symlink elsewhere) target -> dest.
    NT cannot create a junction whose target is absent (New-Item
    fails), so for a nonexistent dest a temporary target is created,
    linked, then removed — leaving a genuinely dangling junction and
    no leftover outside/ scaffolding (sentinel isolation)."""
    if os.name == "nt":
        if dest.exists():
            dangling = None
        else:
            dangling = dest  # topmost path mkdir(parents=True) creates
            while not dangling.parent.exists():
                dangling = dangling.parent
            dest.mkdir(parents=True)
        env = dict(os.environ, KIT_LINK_PATH=str(target),
                   KIT_LINK_TARGET=str(dest))
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "New-Item -ItemType Junction -Path $env:KIT_LINK_PATH "
             "-Target $env:KIT_LINK_TARGET | Out-Null"],
            check=True, env=env)
        if dangling is not None:
            shutil.rmtree(dangling)
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

    def test_fresh_install_seeds_wiki_cycle_files(self):
        """R1 (2026-09-05): a fresh root must satisfy the warmup
        integrity contract, not just the layout contract. Pre-fix this
        failed: install was green but memory-warmup reported
        'Wiki/index.md missing, Wiki/log.md missing' on first boot."""
        self.assertEqual(install.main(), 0)
        for name in ("index.md", "log.md"):
            seeded = self.root / "Wiki" / name
            self.assertTrue(seeded.is_file(), f"Wiki/{name} must be seeded")

    def test_seeded_root_is_warmup_clean(self):
        """Observable warmup status on a fresh install (real CLI,
        isolated root, separate process). Default mode is the compact
        availability summary; integrity is the --full diagnostic."""
        self.assertEqual(install.main(), 0)
        warmup = self.root / "scripts" / "memory-warmup.py"
        r = subprocess.run(
            [sys.executable, str(warmup)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
            env={**os.environ, "MEMORY_ROOT": str(self.root)},
        )
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn("memory: available", r.stdout,
                      "fresh install must report healthy memory: "
                      + r.stdout[-400:])
        self.assertNotIn("missing", r.stdout,
                         "fresh install must not report missing cycle files")
        self.assertNotIn("Integrity", r.stdout,
                         "default warmup must stay compact (no full diagnostics)")

        r_full = subprocess.run(
            [sys.executable, str(warmup), "--full"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120,
            env={**os.environ, "MEMORY_ROOT": str(self.root)},
        )
        self.assertEqual(r_full.returncode, 0, r_full.stderr[-400:])
        self.assertIn("Integrity: OK", r_full.stdout,
                      "fresh install must pass warmup integrity via --full: "
                      + r_full.stdout[-400:])

    def test_rerun_preserves_existing_wiki_cycle_files(self):
        """Seed is absent-only: a re-run never overwrites a user's
        index/log (never destroy what may be data)."""
        self.assertEqual(install.main(), 0)
        idx = self.root / "Wiki" / "index.md"
        log = self.root / "Wiki" / "log.md"
        idx.write_text("# my precious index\n| custom |\n", encoding="utf-8")
        log.write_text("# my precious log\n", encoding="utf-8")
        self.assertEqual(install.main(), 0)
        self.assertEqual(idx.read_text(encoding="utf-8"),
                         "# my precious index\n| custom |\n")
        self.assertEqual(log.read_text(encoding="utf-8"),
                         "# my precious log\n")

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
        # CR-05: Real directory must be preserved, but install must report INCOMPLETE
        # (distinct nonzero exit, e.g. 1) instead of success.
        rc = install.main()
        self.assertNotEqual(rc, 0, "Install must report incomplete when db-tools is a real directory")
        self.assertTrue((real / "precious.txt").is_file(), "Data in real dir must be preserved")
        self.assertFalse(install._is_link(real), "Real directory must not be overwritten or converted to link")

    def test_successful_install_validates_final_entry_point(self):
        # Successful install links db-tools to ENGINE and runs build/smoke against final path
        self.assertEqual(install.main(), 0)
        final_db_tools = self.root / "db-tools"
        self.assertTrue(install._is_link(final_db_tools))
        self.assertTrue((final_db_tools / "search_all.py").is_file())
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


class MemoryBoundaryPreflightTest(unittest.TestCase):
    """CR (4.10.1): link/reparse-aware preflight — a pre-existing linked
    managed path must not be able to send installer writes outside
    MEMORY_ROOT. All roots are temporary; no production memory root is
    touched."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-boundary-"))
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

    def test_fresh_trusted_root_passes_preflight_and_installs(self):
        self.assertEqual(install.main(), 0)
        self.assertTrue((self.root / "VERSION").is_file())

    def test_linked_managed_path_refused_and_outside_untouched(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "sentinel.txt").write_text("do not touch\n", encoding="utf-8")
        _make_foreign_link(self.root / "db", outside)
        with mock.patch.dict(os.environ, {"MEMORY_ROOT": str(self.root)}):
            rc = install.main()
        self.assertEqual(rc, 1, "linked managed path must fail closed")
        self.assertEqual((outside / "sentinel.txt").read_text(encoding="utf-8"),
                         "do not touch\n", "outside root must stay untouched")
        # fail closed means fail BEFORE any mutation: no layout, no VERSION
        self.assertFalse((self.root / "VERSION").exists())
        self.assertFalse((self.root / "scripts").exists())

    def test_preflight_runs_before_any_mutation(self):
        """The preflight must fire before the first mkdir/write: a
        linked VERSION (a file the installer overwrites unconditionally)
        pointing outside must abort with the root left empty apart from
        the pre-seeded probe."""
        outside = self.tmp / "outside"
        outside.mkdir()
        _make_foreign_link(self.root / "VERSION", outside)
        rc = install.main()
        self.assertEqual(rc, 1)
        self.assertFalse((self.root / "db").exists())
        self.assertFalse((self.root / "scripts").exists())
        self.assertFalse((outside / "db-tools").exists())
        self.assertFalse((outside / "Wiki").exists())

    def test_ancestor_link_managed_branch_refused(self):
        """A link on an ancestor of managed paths (scripts/) counts as
        an escape even though scripts/ itself is only created."""
        outside = self.tmp / "outside"
        outside.mkdir()
        self.root.mkdir(parents=True, exist_ok=True)
        _make_foreign_link(self.root / "scripts", outside)
        rc = install.main()
        self.assertEqual(rc, 1)
        # outside/scripts copy targets must not have been written
        self.assertFalse((outside / "memory-warmup.py").exists())

    def test_memory_root_itself_a_link_to_real_memory_refused(self):
        """Base-dir escape: MEMORY_ROOT is a link; writes would go to
        the link target, not the requested location. Fail closed."""
        outside = self.tmp / "outside"
        outside.mkdir()
        root_link = self.tmp / "memroot-link"
        _make_foreign_link(root_link, outside)
        with mock.patch.dict(os.environ, {"MEMORY_ROOT": str(root_link)}):
            rc = install.main()
        self.assertEqual(rc, 1)
        self.assertFalse((outside / "VERSION").exists())
        self.assertFalse((outside / "Wiki").exists())

    def test_in_root_link_is_allowed_and_install_succeeds(self):
        """A link that stays INSIDE the root is legitimate (versioned
        layouts); install proceeds and writes land inside the root.
        The link sits at a non-managed, non-db path: every managed
        destination and db/*.db entry must still resolve inside."""
        real_storage = self.root / "real-storage"
        real_storage.mkdir(parents=True)
        (real_storage / "keep.txt").write_text("data", encoding="utf-8")
        (self.root / "extra").mkdir(exist_ok=True)  # parent for the link
        _make_foreign_link(self.root / "extra" / "notes", real_storage)
        self.assertEqual(install.main(), 0)
        # smoke proves the engine ran inside the root's own layout
        self.assertTrue(install._is_link(self.root / "db-tools"))
        self.assertTrue((real_storage / "keep.txt").is_file())

    def test_real_db_tools_dir_still_preserved_incomplete(self):
        """Behavior preservation: the preflight must not change the
        existing real-directory preservation contract."""
        real = self.root / "db-tools"
        real.mkdir(parents=True)
        (real / "precious.txt").write_text("data", encoding="utf-8")
        rc = install.main()
        self.assertNotEqual(rc, 0)
        self.assertTrue((real / "precious.txt").is_file())
        self.assertFalse(install._is_link(real))

    def test_rerun_after_successful_install_still_idempotent(self):
        """The preflight must accept the installer's own db-tools link
        (it resolves to the kit, which is by design outside the root:
        engine links are the ONE intentional external link, created by
        the installer itself, never by an attacker)."""
        self.assertEqual(install.main(), 0)
        self.assertEqual(install.main(), 0)

def _make_file_link(target: Path, dest: Path) -> bool:
    """Create a FILE symlink target -> dest. Junctions cannot target
    files, so on Windows this needs symlink privileges: returns False
    when the platform cannot, so tests skip that path."""
    if os.name == "nt":
        try:
            target.symlink_to(dest)
            return True
        except (OSError, NotImplementedError):
            return False
    target.symlink_to(dest)
    return True


class MemoryBoundaryNestedLinkTest(unittest.TestCase):
    """CR (4.10.2): the preflight must cover intermediate ancestors
    (Wiki, db, scripts) and every db/*.db entry — including DANGLING
    links whose descendants the old check skipped — and must fail
    closed (rc 1, no mutations) on them. External sentinel files prove
    nothing escapes the root. Bootstrap is best-effort pre-mutation
    only: not a sandbox, not crash-atomic."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-boundary2-"))
        self.root = self.tmp / "mem"
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

    def _assert_no_mutations(self):
        self.assertFalse((self.root / "VERSION").exists())
        self.assertFalse((self.root / "scripts").exists())
        self.assertFalse((self.root / "db-tools").exists())

    def test_dangling_wiki_link_to_outside_refused(self):
        """A DANGLING Wiki link to a nonexistent outside path: the
        old check skipped its nonexistent descendants, so
        mkdir(Wiki/reference) would materialize the outside target."""
        self.root.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.root / "Wiki")  # swap the real dir for a link
        _make_foreign_link(self.root / "Wiki", self.tmp / "outside" / "Wiki")
        rc = install.main()
        self.assertEqual(rc, 1, "dangling ancestor link must fail closed")
        self.assertFalse((self.tmp / "outside").exists(),
                         "mkdir must not materialize the outside target")
        self._assert_no_mutations()

    def test_existing_wiki_link_to_outside_refused(self):
        """An EXISTING Wiki ancestor link to an outside dir with
        content: the managed type dirs inside would receive seeds."""
        outside = self.tmp / "outside" / "Wiki"
        outside.mkdir(parents=True)
        (outside / "sentinel.txt").write_text("do not touch\n", encoding="utf-8")
        self.root.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.root / "Wiki")  # swap the real dir for a link
        _make_foreign_link(self.root / "Wiki", outside)
        rc = install.main()
        self.assertEqual(rc, 1)
        # seeds must not have been written through the link
        for name in ("index.md", "log.md") + tuple(install.WIKI_TYPES):
            self.assertFalse((outside / name).exists(),
                             f"outside Wiki/{name} must stay untouched")
        self.assertEqual((outside / "sentinel.txt").read_text(encoding="utf-8"),
                         "do not touch\n")
        self._assert_no_mutations()

    def test_nested_db_link_to_outside_file_refused(self):
        """db/research.db (an engine rw target: search logging opens
        it read-write) as a file link to an outside file — sqlite
        would write through it. Skipped where the platform cannot
        create file symlinks."""
        outside_dir = self.tmp / "outside"
        outside_dir.mkdir()
        sentinel = outside_dir / "research.db"
        sentinel.write_text("do not touch\n", encoding="utf-8")
        (self.root / "db").mkdir(exist_ok=True)
        if not _make_file_link(self.root / "db" / "research.db", sentinel):
            self.skipTest("file symlinks unavailable on this platform")
        rc = install.main()
        self.assertEqual(rc, 1, "linked db/*.db entry must fail closed")
        self.assertEqual(sentinel.read_text(encoding="utf-8"),
                         "do not touch\n",
                         "outside db file must stay untouched")
        self._assert_no_mutations()

    def test_nested_db_dangling_link_to_outside_refused(self):
        """A DANGLING db file link (sqlite creates the target on
        first write — the write lands outside). Skipped where the
        platform cannot create file symlinks."""
        (self.root / "db").mkdir(exist_ok=True)
        if not _make_file_link(self.root / "db" / "wiki.db",
                               self.tmp / "outside" / "wiki.db"):
            self.skipTest("file symlinks unavailable on this platform")
        rc = install.main()
        self.assertEqual(rc, 1, "dangling linked db entry must fail closed")
        self.assertFalse((self.tmp / "outside").exists(),
                         "engine build must not create the outside db")
        self._assert_no_mutations()

    def test_dangling_scripts_ancestor_link_refused(self):
        """A dangling scripts/ ancestor link: the copied engine
        scripts would materialize the outside target."""
        self.root.mkdir(parents=True, exist_ok=True)
        _make_foreign_link(self.root / "scripts", self.tmp / "outside" / "scripts")
        rc = install.main()
        self.assertEqual(rc, 1)
        self.assertFalse((self.tmp / "outside").exists())
        self._assert_no_mutations()

    def test_dangling_db_ancestor_link_refused(self):
        """A dangling db/ ancestor link: build.py's wiki.db write
        would materialize the outside target."""
        self.root.mkdir(parents=True, exist_ok=True)
        _make_foreign_link(self.root / "db", self.tmp / "outside" / "db")
        rc = install.main()
        self.assertEqual(rc, 1)
        self.assertFalse((self.tmp / "outside").exists())
        self._assert_no_mutations()

    def test_real_db_dir_with_real_files_still_installs(self):
        """Behavior preservation: a real db/ directory containing
        real (non-link) .db files is preflighted and accepted."""
        (self.root / "db").mkdir(exist_ok=True)
        (self.root / "db" / "wiki.db").write_text("", encoding="utf-8")
        self.assertEqual(install.main(), 0)
        self.assertTrue(install._is_link(self.root / "db-tools"))

if __name__ == "__main__":
    unittest.main()
