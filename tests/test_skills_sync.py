#!/usr/bin/env python3
"""Canonical .agents/skills target + drift check (wave3 Task 10).

Contract:
- deploy.py --canonical: sync KIT/skills -> .agents/skills/ inside the kit
  repo (the copy harnesses read); Windows junction via mklink /J when the
  adapter flag says link, plain copy fallback otherwise; dry-run lists the
  actions without touching the disk.
- doctor check_skills_sync: byte-compares deployed copies vs kit skills/
  (only copies that exist are compared — junctions track the master live
  and are skipped). WARN tier when no deployed copy exists anywhere
  (mirrors check_backup_freshness semantics: a missing copy must not
  block, only nag). FAIL names the drifted slugs.
"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "doctor", KIT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def make_kit_tree(root: Path, skills: dict[str, str]):
    for slug, body in skills.items():
        d = root / "skills" / slug
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")


class DriftCheckTest(unittest.TestCase):
    def _check(self, root: Path):
        with mock.patch.object(doctor, "KIT", root):
            return doctor.check_skills_sync()

    def test_no_deployed_copies_warns_not_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            with mock.patch.object(doctor, "_DEPLOYED_SKILL_DIRS", []):
                ok, detail = self._check(root)
        self.assertTrue(ok)
        self.assertIn("WARN", detail)

    def test_identical_copy_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            deployed = root / "deployed" / "skills"
            (deployed / "alpha").mkdir(parents=True)
            (deployed / "alpha" / "SKILL.md").write_text(
                "a", encoding="utf-8", newline="\n")
            ok, detail = self._check_with_deployment(root, deployed)
        self.assertTrue(ok, detail)

    def _check_with_deployment(self, root: Path, deployed: Path):
        """check_skills_sync discovers candidates; patch the candidate
        list the same way the real one builds it from known targets."""
        with mock.patch.object(doctor, "KIT", root), \
                mock.patch.object(doctor, "_DEPLOYED_SKILL_DIRS",
                                  [deployed]):
            return doctor.check_skills_sync()

    def test_drifted_copy_fails_and_names_slug(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a", "beta": "b"})
            deployed = root / "deployed" / "skills"
            (deployed / "alpha").mkdir(parents=True)
            (deployed / "alpha" / "SKILL.md").write_text(
                "DRIFTED", encoding="utf-8", newline="\n")
            (deployed / "beta").mkdir(parents=True)
            (deployed / "beta" / "SKILL.md").write_text(
                "b", encoding="utf-8", newline="\n")
            ok, detail = self._check_with_deployment(root, deployed)
        self.assertFalse(ok)
        self.assertIn("alpha", detail)
        self.assertNotIn("beta", detail)

    def test_missing_skill_in_copy_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a", "beta": "b"})
            deployed = root / "deployed" / "skills"
            (deployed / "alpha").mkdir(parents=True)
            (deployed / "alpha" / "SKILL.md").write_text(
                "a", encoding="utf-8", newline="\n")
            ok, detail = self._check_with_deployment(root, deployed)
        self.assertFalse(ok)
        self.assertIn("beta", detail)


    def test_stale_skill_directory_in_copy_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            deployed = root / "deployed" / "skills"
            (deployed / "alpha").mkdir(parents=True)
            (deployed / "alpha" / "SKILL.md").write_text(
                "a", encoding="utf-8", newline="\n")
            (deployed / "removed-skill").mkdir()
            (deployed / "removed-skill" / "SKILL.md").write_text(
                "stale", encoding="utf-8", newline="\n")
            (deployed / ".kit-manifest.json").write_text(
                '{"skills": ["alpha", "removed-skill"]}',
                encoding="utf-8", newline="\n")
            ok, detail = self._check_with_deployment(root, deployed)
        self.assertFalse(ok)
        self.assertIn("removed-skill", detail)

    def test_stray_top_level_file_in_copy_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            deployed = root / "deployed" / "skills"
            (deployed / "alpha").mkdir(parents=True)
            (deployed / "alpha" / "SKILL.md").write_text(
                "a", encoding="utf-8", newline="\n")
            (deployed / "STALE.txt").write_text(
                "stale", encoding="utf-8", newline="\n")
            ok, detail = self._check_with_deployment(root, deployed)
        self.assertFalse(ok)
        self.assertIn("STALE.txt", detail)

    def test_local_only_skill_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            deployed = root / "deployed" / "skills"
            (deployed / "alpha").mkdir(parents=True)
            (deployed / "alpha" / "SKILL.md").write_text(
                "a", encoding="utf-8", newline="\n")
            (deployed / "local-only").mkdir()
            (deployed / "local-only" / "SKILL.md").write_text(
                "local", encoding="utf-8", newline="\n")
            (deployed / ".kit-manifest.json").write_text(
                '{"skills": ["alpha"]}', encoding="utf-8", newline="\n")
            ok, detail = self._check_with_deployment(root, deployed)
        self.assertTrue(ok, detail)

    def test_junction_copy_skipped_not_flagged(self):
        """A junction tracks the master live — resolve-equal means skip."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            deployed = root / "deployed" / "skills"
            deployed.mkdir(parents=True)
            link = deployed / "alpha"
            made = _try_junction(link, root / "skills" / "alpha")
            if not made:
                self.skipTest("junction creation not permitted here")
            self.assertEqual(link.resolve(),
                             (root / "skills" / "alpha").resolve())
            ok, detail = self._check_with_deployment(root, deployed)
            self.assertTrue(ok, detail)


def _try_junction(link: Path, target: Path) -> bool:
    """mklink /J needs cmd.exe; returns False when unavailable/denied."""
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False)
        return r.returncode == 0 and link.exists()
    except OSError:
        return False


class DeployCanonicalTest(unittest.TestCase):
    def _deploy(self, root: Path, *argv):
        spec = importlib.util.spec_from_file_location(
            "deploy", KIT / "scripts" / "tools" / "deploy.py")
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)
        with mock.patch.object(deploy, "KIT", root), \
             mock.patch.object(deploy, "SKILLS", root / "skills"), \
             mock.patch.object(deploy, "VERSION", "3.7.0"), \
             mock.patch.object(deploy, "SYNC_TARGETS", []), \
             mock.patch.object(deploy, "HARNESSES", []), \
             mock.patch.object(deploy, "CLAUDE_MD",
                               root / "nonexistent" / "CLAUDE.md"), \
             mock.patch.object(deploy, "integrity_gate"), \
             mock.patch.object(sys, "argv",
                               ["deploy.py", "--canonical", *argv]):
            return deploy.main()

    def test_canonical_writes_repo_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            self._deploy(root)
            canon = root / ".agents" / "skills" / "alpha" / "SKILL.md"
            self.assertEqual(canon.read_text(encoding="utf-8"), "a")

    def test_canonical_dry_run_touches_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            self._deploy(root, "--dry-run")
            self.assertFalse((root / ".agents").exists())

    def test_canonical_sync_updates_drifted_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "new"})
            drifted = root / ".agents" / "skills" / "alpha"
            drifted.mkdir(parents=True)
            (drifted / "SKILL.md").write_text("old", encoding="utf-8")
            self._deploy(root)
            self.assertEqual(
                (drifted / "SKILL.md").read_text(encoding="utf-8"), "new")

    def test_canonical_removes_dropped_skill(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_kit_tree(root, {"alpha": "a"})
            stale = root / ".agents" / "skills" / "ghost"
            stale.mkdir(parents=True)
            (stale / "SKILL.md").write_text("old", encoding="utf-8")
            self._deploy(root)
            self.assertFalse(stale.exists())


class ProfileAdapterFlagsTest(unittest.TestCase):
    def test_profile_has_canonical_flags_default_false(self):
        text = (KIT / "profile.yml").read_text(encoding="utf-8")
        self.assertIn("canonical:", text)
        # every adapter row that declares canonical uses false by default
        self.assertNotIn("canonical: true", text)


if __name__ == "__main__":
    unittest.main()
