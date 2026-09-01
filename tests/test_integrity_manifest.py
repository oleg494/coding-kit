#!/usr/bin/env python3
"""Wave 1 v3.5.0 trust-surface, Task 2: CBSE integrity manifest contract.

Cymulate CBSE threat model: the writable control plane (config, hooks,
bootfiles, kit scripts) is the real security boundary — hash it and fail
loudly on drift. Contract:

- build_manifest(kit_root) -> {relpath: sha256} over the exact declared
  scope (OPS.md, AGENTS.md, profile.yml, SKILL_RUNTIME.md, adapters/*.md,
  scripts/**/*.py, eval/*.py, memory/db-tools/*.py, memory/scripts/*.py,
  skills/*/SKILL.md), \\n-normalized utf-8, sorted.
- check(root, manifest) -> [drifted/added/removed relpaths].
- --update regenerates; default CLI mode checks.
- doctor check_integrity() FAILs on tamper (monkeypatched KIT).
- deploy refuses to copy a drifted tree (exit 3).
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "integrity_manifest", KIT / "scripts" / "tools" / "integrity_manifest.py")
integrity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(integrity)


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def _seed(root: Path):
    """Minimal kit tree covering every scope family."""
    _write(root / "OPS.md", "# ops\n")
    _write(root / "AGENTS.md", "# agents\n")
    _write(root / "profile.yml", "version: \"3.5.0\"\n")
    _write(root / "SKILL_RUNTIME.md", "# runtime\n")
    _write(root / "adapters" / "zcode.md", "# adapter\n")
    _write(root / "scripts" / "doctor.py", "x = 1\n")
    _write(root / "scripts" / "tools" / "deploy.py", "x = 2\n")
    _write(root / "eval" / "runner.py", "x = 3\n")
    _write(root / "memory" / "db-tools" / "build.py", "x = 4\n")
    _write(root / "memory" / "scripts" / "memory-warmup.py", "x = 5\n")
    _write(root / "skills" / "demo" / "SKILL.md", "---\nname: demo\n---\n")
    # out-of-scope files: never hashed
    _write(root / "README.md", "readme\n")
    _write(root / "eval" / "results" / "x.json", "{}\n")
    _write(root / "skills" / "demo" / "reference.md", "ref\n")


class BuildManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-integrity-"))
        self.root = self.tmp / "kit"
        _seed(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scope_covers_declared_families_only(self):
        m = integrity.build_manifest(self.root)
        expected = {
            "OPS.md", "AGENTS.md", "profile.yml", "SKILL_RUNTIME.md",
            "adapters/zcode.md", "scripts/doctor.py",
            "scripts/tools/deploy.py", "eval/runner.py",
            "memory/db-tools/build.py", "memory/scripts/memory-warmup.py",
            "skills/demo/SKILL.md",
        }
        self.assertEqual(set(m), expected)
        self.assertEqual(sorted(m), sorted(expected))
        # posix sort: lowercase 'scripts' < 'skills' even though Windows
        self.assertLess(next(k for k in m if k.startswith("scripts/")),
                        next(k for k in m if k.startswith("skills/")))
        (self.root / "OPS.md").write_text("# ops\r\n", encoding="utf-8",
                                          newline="")
        m = integrity.build_manifest(self.root)
        self.assertEqual(m["OPS.md"],
                         integrity._sha256_text("# ops\n"))

    def test_manifest_json_has_kit_version_stamp(self):
        integrity.update_or_create(self.root, version="9.9.9")
        data = json.loads((self.root / "integrity-manifest.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(data["kit_version"], "9.9.9")
        self.assertIn("OPS.md", data["files"])

    def test_sorted_order_is_posix_sort_not_windows_casefold(self):
        m = integrity.build_manifest(self.root)
        self.assertEqual(list(m), sorted(m))


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-integrity-"))
        self.root = self.tmp / "kit"
        _seed(self.root)
        self.manifest = integrity.build_manifest(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tamper_one_file_is_reported(self):
        _write(self.root / "OPS.md", "# ops TAMPERED\n")
        self.assertEqual(integrity.check(self.root, self.manifest),
                         ["drifted: OPS.md"])

    def test_added_unlisted_py_flagged(self):
        _write(self.root / "scripts" / "evil.py", "x = 9\n")
        self.assertEqual(integrity.check(self.root, self.manifest),
                         ["added: scripts/evil.py"])

    def test_removed_file_flagged(self):
        (self.root / "eval" / "runner.py").unlink()
        self.assertEqual(integrity.check(self.root, self.manifest),
                         ["removed: eval/runner.py"])

    def test_clean_tree_returns_empty(self):
        self.assertEqual(integrity.check(self.root, self.manifest), [])

    def test_update_round_trip_is_clean(self):
        m2 = integrity.build_manifest(self.root)
        self.assertEqual(integrity.check(self.root, m2), [])


class DoctorIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-integrity-doc-"))
        self.root = self.tmp / "kit"
        _seed(self.root)
        # doctor.check_integrity loads the tool from <KIT>/scripts/tools/,
        # so the fixture tree needs a copy to import.
        shutil.copy2(KIT / "scripts" / "tools" / "integrity_manifest.py",
                     self.root / "scripts" / "tools"
                     / "integrity_manifest.py")
        (self.root / "integrity-manifest.json").write_text(
            json.dumps({"kit_version": "test", "files":
                        integrity.build_manifest(self.root)}, indent=1),
            encoding="utf-8", newline="\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _doctor(self):
        spec = importlib.util.spec_from_file_location(
            "doctor2", KIT / "scripts" / "doctor.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _with_kit(self, doctor):
        orig = doctor.KIT
        doctor.KIT = self.root
        try:
            return doctor.check_integrity()
        finally:
            doctor.KIT = orig

    def test_doctor_integrity_fail_row_on_tamper(self):
        _write(self.root / "OPS.md", "# ops TAMPERED\n")
        ok, detail = self._with_kit(self._doctor())
        self.assertFalse(ok)
        self.assertIn("OPS.md", detail)

    def test_doctor_integrity_green_on_clean_tree(self):
        ok, detail = self._with_kit(self._doctor())
        self.assertTrue(ok, detail)

    def test_doctor_integrity_fails_without_manifest(self):
        (self.root / "integrity-manifest.json").unlink()
        ok, _detail = self._with_kit(self._doctor())
        self.assertFalse(ok)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-integrity-cli-"))
        self.root = self.tmp / "kit"
        _seed(self.root)
        # deploy.integrity_gate imports the tool from <KIT>/scripts/tools/;
        # give the fixture tree its own copy.
        shutil.copy2(KIT / "scripts" / "tools" / "integrity_manifest.py",
                     self.root / "scripts" / "tools"
                     / "integrity_manifest.py")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *cli_args):
        import subprocess
        return subprocess.run(
            [sys.executable, str(KIT / "scripts" / "tools" /
                                 "integrity_manifest.py"), *cli_args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace",
            env={"MEMORY_ROOT": str(self.tmp),
                 "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                 "PATH": os.environ.get("PATH", "")},
            cwd=str(self.root), timeout=60, check=False)

    def test_default_checks_exit_1_on_drift_exit_0_clean(self):
        r = self._run("--root", str(self.root))
        self.assertEqual(r.returncode, 2, "no manifest yet -> fail loudly")
        r = self._run("--root", str(self.root), "--update")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.root / "integrity-manifest.json").is_file())
        r = self._run("--root", str(self.root))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        _write(self.root / "profile.yml", "version: \"9.9.9\"\n")
        r = self._run("--root", str(self.root))
        self.assertEqual(r.returncode, 1)
        self.assertIn("profile.yml", r.stdout)

    def test_deploy_refuses_on_drift(self):
        # deploy reads ~/.claude etc. — only test its gate function in-process
        spec = importlib.util.spec_from_file_location(
            "deploy", KIT / "scripts" / "tools" / "deploy.py")
        dep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dep)
        dep.KIT = self.root
        integrity.update_or_create(self.root)
        _write(self.root / "OPS.md", "# ops TAMPERED\n")
        with self.assertRaises(SystemExit) as cm:
            dep.integrity_gate()
        self.assertEqual(cm.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
