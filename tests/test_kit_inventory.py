#!/usr/bin/env python3
"""Kit-owned skill inventory contract tests (v4.7.0).

The profile.yml skills.always_on + skills.domain lists are the single
source of truth for what the kit owns. Everything else under skills/
(e.g. third-party firecrawl sources) is FOREIGN: never copied, never
deleted, never hashed, never validated.

Contract:
- kit_inventory: missing/invalid profile raises an explicit error
  (never a silent fallback to every directory on disk).
- deploy: only owned skills sync; foreign dirs in the destination are
  preserved untouched (deploy preservation).
- integrity manifest: only owned SKILL.md files are in scope; a tampered
  owned SKILL.md is detected; foreign SKILL.md files are not hashed.
- No consumer adopts a directory just because it exists on disk.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def make_kit(root: Path, owned=("alpha", "beta"), foreign=("firecrawl-x",),
             version="9.9.9-test") -> Path:
    """Kit tree: profile.yml inventory, owned skill dirs, foreign dirs."""
    entries = "\n".join(f"    - {s}" for s in owned)
    _write(root / "VERSION", version + "\n")
    _write(root / "profile.yml",
           "version: \"9.9.9\"\n"
           "skills:\n"
           "  always_on:\n"
           f"{entries}\n"
           "  domain: []\n")
    for s in owned:
        _write(root / "skills" / s / "SKILL.md",
               f"---\nname: {s}\ndescription: test {s}\n---\n# {s}\n")
    for s in foreign:
        _write(root / "skills" / s / "SKILL.md",
               f"---\nname: {s}\ndescription: foreign {s}\n---\n")
    return root


class InventoryHelperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-inv-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.inv = _load("kit_inventory",
                         KIT / "scripts" / "tools" / "kit_inventory.py")

    def test_owned_names_parsed(self):
        make_kit(self.tmp / "kit")
        names = self.inv.load_owned_skills(self.tmp / "kit")
        self.assertEqual(names, ["alpha", "beta"])

    def test_missing_profile_raises(self):
        with self.assertRaises(self.inv.KitInventoryError):
            self.inv.load_owned_skills(self.tmp / "empty")

    def test_missing_required_list_raises(self):
        _write(self.tmp / "bad" / "profile.yml",
               "skills:\n  always_on:\n    - foo\n")
        with self.assertRaises(self.inv.KitInventoryError):
            self.inv.load_owned_skills(self.tmp / "bad")

    def test_invalid_slug_raises(self):
        _write(self.tmp / "bad2" / "profile.yml",
               "skills:\n  always_on:\n    - foo\n  domain:\n    - Bad_Name\n")
        with self.assertRaises(self.inv.KitInventoryError):
            self.inv.load_owned_skills(self.tmp / "bad2")

    def test_empty_inventory_raises(self):
        _write(self.tmp / "empty2" / "profile.yml",
               "skills:\n  always_on: []\n  domain: []\n")
        with self.assertRaises(self.inv.KitInventoryError):
            self.inv.load_owned_skills(self.tmp / "empty2")

    def test_real_kit_inventory(self):
        names = self.inv.load_owned_skills(KIT)
        self.assertIn("superpowers", names)
        self.assertIn("yagni", names)


class DeployForeignPreservationTest(unittest.TestCase):
    """Deploy syncs ONLY owned skills; foreign dirs survive untouched."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-deploy-inv-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_foreign_dir_not_copied_and_dest_foreign_preserved(self):
        deploy = _load("deploy", KIT / "scripts" / "tools" / "deploy.py")
        kit = make_kit(self.tmp / "kit")
        dest = self.tmp / "dest" / "skills"
        # a foreign dir already living in the destination
        _write(dest / "user-owned" / "custom.txt", "user content")
        _write(dest / "firecrawl-x" / "SKILL.md", "user customized foreign")

        with mock.patch.object(deploy, "KIT", kit), \
                mock.patch.object(deploy, "SKILLS", kit / "skills"), \
                mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
            deploy.sync_skills()

        # owned skills synced
        self.assertTrue((dest / "alpha" / "SKILL.md").is_file())
        self.assertTrue((dest / "beta" / "SKILL.md").is_file())
        # foreign master dir never copied into dest
        # manifest lists owned skills only — foreign dir never claimed
        mani = json.loads((dest / ".kit-manifest.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(sorted(mani["skills"]), ["alpha", "beta"])
        # pre-existing foreign dir preserved byte-identical
        self.assertEqual(
            (dest / "user-owned" / "custom.txt").read_text(encoding="utf-8"),
            "user content")

    def test_canonical_sync_preserves_foreign_and_retires_owned(self):
        deploy = _load("deploy", KIT / "scripts" / "tools" / "deploy.py")
        kit = make_kit(self.tmp / "canonical-kit")
        dest = kit / ".agents" / "skills"
        _write(dest / "foreign" / "custom.txt", "keep exactly")
        _write(dest / "retired" / "SKILL.md", "old kit skill")
        _write(dest / ".kit-manifest.json", json.dumps({"skills": ["retired"]}))
        with mock.patch.object(deploy, "KIT", kit), \
                mock.patch.object(deploy, "SKILLS", kit / "skills"):
            self.assertEqual(deploy.canonical_mode(["--canonical"]), 0)
        self.assertEqual((dest / "foreign" / "custom.txt").read_text(), "keep exactly")
        self.assertFalse((dest / "retired").exists())
        self.assertEqual((dest / "alpha" / "SKILL.md").read_bytes(),
                         (kit / "skills" / "alpha" / "SKILL.md").read_bytes())


class IntegrityOwnedScopeTest(unittest.TestCase):
    """Integrity manifest hashes ONLY owned SKILL.md files."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-integ-inv-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.integrity = _load(
            "integrity_manifest",
            KIT / "scripts" / "tools" / "integrity_manifest.py")

    def test_missing_inventory_cannot_adopt_foreign_skills(self):
        kit = make_kit(self.tmp / "missing-profile")
        (kit / "profile.yml").unlink()
        with self.assertRaises(self.integrity.kit_inventory.KitInventoryError):
            self.integrity.build_manifest(kit)

    def test_foreign_skill_md_not_hashed(self):
        kit = make_kit(self.tmp / "kit")
        files = self.integrity.scope_files(kit)
        rels = {p.relative_to(kit).as_posix() for p in files}
        self.assertIn("skills/alpha/SKILL.md", rels)
        self.assertNotIn("skills/firecrawl-x/SKILL.md", rels)

    def test_owned_tamper_detected(self):
        kit = make_kit(self.tmp / "kit")
        self.integrity.update_or_create(kit)
        _write(kit / "skills" / "alpha" / "SKILL.md",
               "---\nname: alpha\ndescription: TAMPERED\n---\n")
        problems = self.integrity.check(
            kit, self.integrity.load_manifest(kit)["files"])
        self.assertTrue(
            any("skills/alpha/SKILL.md" in p for p in problems), problems)

    def test_foreign_tamper_not_flagged(self):
        kit = make_kit(self.tmp / "kit")
        self.integrity.update_or_create(kit)
        _write(kit / "skills" / "firecrawl-x" / "SKILL.md",
               "---\nname: firecrawl-x\ndescription: CHANGED BY USER\n---\n")
        problems = self.integrity.check(
            kit, self.integrity.load_manifest(kit)["files"])
        self.assertFalse(
            any("firecrawl-x" in p for p in problems), problems)


class MissingInventoryFailsTest(unittest.TestCase):
    """A missing/invalid inventory must FAIL consumers, not adopt all dirs."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-missing-inv-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_doctor_manifest_row_fails_on_missing_profile(self):
        doctor = _load("doctor", KIT / "scripts" / "doctor.py")
        root = self.tmp / "kit"
        root.mkdir()
        (root / "skills" / "alpha").mkdir(parents=True)
        with mock.patch.object(doctor, "KIT", root):
            ok, detail = doctor.check_manifest()
        self.assertFalse(ok)
        self.assertIn("inventory", detail.lower())

    def test_deploy_master_names_raises_on_missing_profile(self):
        deploy = _load("deploy", KIT / "scripts" / "tools" / "deploy.py")
        root = self.tmp / "kit2"
        (root / "skills" / "alpha").mkdir(parents=True)
        with mock.patch.object(deploy, "KIT", root), \
                mock.patch.object(deploy, "SKILLS", root / "skills"):
            with self.assertRaises(Exception):
                deploy.master_skill_names()

    def test_hermes_conflict_on_invalid_profile(self):
        hermes = _load("hermes_adapter",
                       KIT / "scripts" / "tools" / "hermes_adapter.py")
        kit = self.tmp / "kit3"
        _write(kit / "VERSION", "1.0\n")
        _write(kit / "profile.yml", "skills:\n  always_on:\n    - a\n")
        (kit / "skills" / "a").mkdir(parents=True)
        (kit / "skills" / "a" / "SKILL.md").write_text(
            "---\nname: a\ndescription: x\n---\n", encoding="utf-8")
        with self.assertRaises(hermes.Conflict):
            hermes.kit_skills(kit)


if __name__ == "__main__":
    unittest.main()
