"""Tests for scripts/tools/hermes_adapter.py — Hermes-only kit integration.

Contract under test (plan 2026-09-12-hermes-adapter-first-package.md H2):
  - preview never mutates the target home
  - apply touches ONLY the three owned surfaces (projection tree,
    skills.external_dirs config entry, delimited SOUL.md block)
  - idempotence, update/remove of owned skills, foreign-file preservation
  - legacy local skills/coding-kit/ requires explicit --retire-legacy
  - restore reverses to exact prior state; mid-apply failure rolls back
  - collision detection (local same-name, bundled-manifest names) is reported

No Hermes import: the adapter is a kit-side file/config tool; native
rendering is exercised on the server (H3 drills).
"""
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent


def load_adapter():
    spec = importlib.util.spec_from_file_location(
        "hermes_adapter", KIT / "scripts" / "tools" / "hermes_adapter.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def make_kit(root: Path, skills=("alpha", "beta"), version="9.9.9-test") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    for s in skills:
        d = root / "skills" / s
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {s}\ndescription: test skill {s}\n---\n# {s}\nbody\n",
            encoding="utf-8")
    return root

def snapshot(root: Path) -> dict:
    """Exact bytes and directory membership; no newline normalization."""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        out[rel] = p.read_bytes() if p.is_file() else "<dir>"
    return out


class AdapterTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hermes-adapter-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.kit = make_kit(self.tmp / "kit")
        self.home = self.tmp / "hermes-home"
        (self.home / "skills").mkdir(parents=True)
        (self.home / "config.yaml").write_text(
            "model:\n  default: m1\n# keep my comment\nskills:\n  external_dirs: []\n",
            encoding="utf-8")
        (self.home / "SOUL.md").write_text(
            "# Soul\n\npersonal notes stay\n", encoding="utf-8")
        self.adapter = load_adapter()

    def run_cli(self, *args):
        return self.adapter.main([
            "--kit", str(self.kit), "--hermes-home", str(self.home), *args])

    def ext_root(self):
        return self.home / "kit-skills"

    # ---------- preview is read-only ----------

    def test_preview_mutates_nothing(self):
        before = snapshot(self.home)
        rc = self.run_cli("preview")
        self.assertEqual(rc, 0)
        self.assertEqual(before, snapshot(self.home))


    # ---------- apply: owned surfaces only ----------

    def test_apply_creates_projection_config_and_soul_block(self):
        rc = self.run_cli("apply")
        self.assertEqual(rc, 0, self.adapter.last_report_text)
        cat = self.ext_root() / "coding-kit"
        self.assertTrue((cat / "alpha" / "SKILL.md").is_file())
        self.assertTrue((cat / "beta" / "SKILL.md").is_file())
        cfg = (self.home / "config.yaml").read_text(encoding="utf-8")
        self.assertIn(str(self.ext_root().as_posix()), cfg)
        self.assertIn("model:", cfg)          # unrelated keys preserved
        self.assertIn("# keep my comment", cfg)  # comments preserved
        soul = (self.home / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("personal notes stay", soul)
        self.assertEqual(soul.count(self.adapter.MARK_BEGIN.format(version="9.9.9-test")), 1)
        self.assertIn("coding-kit", soul)

    def test_apply_is_idempotent(self):
        self.run_cli("apply")
        before = snapshot(self.home)
        rc = self.run_cli("apply")
        self.assertEqual(rc, 0)
        self.assertEqual(before, snapshot(self.home))

    def test_apply_updates_changed_and_removes_retired_skill(self):
        self.run_cli("apply")
        (self.kit / "skills" / "alpha" / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: changed\n---\nnew body\n", encoding="utf-8")
        shutil.rmtree(self.kit / "skills" / "beta")
        rc = self.run_cli("apply")
        self.assertEqual(rc, 0)
        cat = self.ext_root() / "coding-kit"
        self.assertIn("changed", (cat / "alpha" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertFalse((cat / "beta").exists())

    def test_apply_never_deletes_unknown_dir_in_owned_category(self):
        self.run_cli("apply")
        foreign = self.ext_root() / "coding-kit" / "hand-made"
        foreign.mkdir()
        (foreign / "SKILL.md").write_text(
            "---\nname: hand-made\ndescription: x\n---\n", encoding="utf-8")
        rc = self.run_cli("apply")
        self.assertEqual(rc, 0)
        self.assertTrue((foreign / "SKILL.md").is_file())

    # ---------- config shapes ----------

    def test_config_block_list_shape(self):
        (self.home / "config.yaml").write_text(
            "skills:\n  external_dirs:\n    - /other/place\n",
            encoding="utf-8")
        rc = self.run_cli("apply")
        self.assertEqual(rc, 0)
        cfg = (self.home / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("/other/place", cfg)
        self.assertIn(str(self.ext_root().as_posix()), cfg)
        self.assertEqual(cfg.count(str(self.ext_root().as_posix())), 1)

    def test_config_without_skills_section(self):
        (self.home / "config.yaml").write_text("model:\n  default: m1\n", encoding="utf-8")
        rc = self.run_cli("apply")
        self.assertEqual(rc, 0)
        cfg = (self.home / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("external_dirs", cfg)

    def test_existing_entry_not_duplicated(self):
        self.run_cli("apply")
        self.run_cli("apply")
        cfg = (self.home / "config.yaml").read_text(encoding="utf-8")
        self.assertEqual(cfg.count(str(self.ext_root().as_posix())), 1)

    # ---------- SOUL block ownership ----------

    def test_soul_block_replaced_between_markers_only(self):
        self.run_cli("apply")
        soul_path = self.home / "SOUL.md"
        soul_path.write_text(
            "HEADER-FOREIGN\n" + soul_path.read_text(encoding="utf-8")
            + "TRAILER-FOREIGN\n", encoding="utf-8")
        rc = self.run_cli("apply")
        self.assertEqual(rc, 0)
        soul = soul_path.read_text(encoding="utf-8")
        self.assertTrue(soul.startswith("HEADER-FOREIGN"))
        self.assertTrue(solar_end := soul.endswith("TRAILER-FOREIGN\n"))
        self.assertEqual(soul.count(self.adapter.MARK_BEGIN.format(version="9.9.9-test")), 1)

    # ---------- legacy + collisions ----------

    def test_legacy_local_copy_blocks_apply_without_flag(self):
        legacy = self.home / "skills" / "coding-kit"
        (legacy / "alpha").mkdir(parents=True)
        (legacy / "alpha" / "SKILL.md").write_text("old\n", encoding="utf-8")
        rc = self.run_cli("apply")
        self.assertEqual(rc, 1)                       # refused
        self.assertTrue((legacy / "alpha" / "SKILL.md").is_file())
        rc = self.run_cli("apply", "--retire-legacy")
        self.assertEqual(rc, 0, self.adapter.last_report_text)
        self.assertFalse(legacy.exists())            # moved out of skills/
        self.assertTrue((self.ext_root() / "coding-kit" / "alpha" / "SKILL.md").is_file())


    # ---------- restore + failure rollback ----------

    def test_restore_reverses_to_exact_prior_state(self):
        pre = snapshot(self.home)
        self.run_cli("apply")
        self.assertNotEqual(pre, snapshot(self.home))
        rc = self.run_cli("restore")
        self.assertEqual(rc, 0)
        self.assertEqual(pre, snapshot(self.home))

    def test_mid_apply_failure_rolls_back(self):
        pre = snapshot(self.home)
        orig = self.adapter.safe_write_text

        def boom(path, content, boundary=None, encoding="utf-8"):
            # fail once the projection exists (first config/SOUL write after copies)
            if path.name == "SOUL.md":
                raise OSError("injected failure")
            return orig(path, content, boundary=boundary, encoding=encoding)

        self.adapter.safe_write_text = boom
        rc = self.run_cli("apply")
        self.adapter.safe_write_text = orig
        self.assertEqual(rc, 1)
        self.assertEqual(pre, snapshot(self.home))

    def test_restore_anchors_to_first_integration(self):
        # second apply (update) must NOT move the pre-integration rollback point
        self.run_cli("apply")
        (self.kit / "VERSION").write_text("9.9.10-second\n", encoding="utf-8")
        rc = self.run_cli("apply")
        self.assertEqual(rc, 0)
        # restore must return config/SOUL to their state BEFORE the first apply
        rc = self.run_cli("restore")
        self.assertEqual(rc, 0)
        cfg = (self.home / "config.yaml").read_text(encoding="utf-8")
        soul = (self.home / "SOUL.md").read_text(encoding="utf-8")
        self.assertEqual(cfg, "model:\n  default: m1\n# keep my comment\nskills:\n  external_dirs: []\n".replace("\\n", "\n"))
        self.assertNotIn("<!-- kit:begin", soul)
        self.assertIn("personal notes stay", soul)

    def test_missing_kit_skills_conflict(self):
        shutil.rmtree(self.kit / "skills")
        before = snapshot(self.home)
        rc = self.run_cli("apply")
        self.assertEqual(rc, 1)
        self.assertEqual(before, snapshot(self.home))

    def test_restore_preserves_foreign_files_in_explicit_root(self):
        ext = self.home / "custom-external"
        foreign = ext / "coding-kit" / "hand-made" / "data.bin"
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b"\x00\xffforeign\r\n")
        before = snapshot(self.home)
        self.assertEqual(self.run_cli("--ext-root", str(ext), "apply"), 0)
        self.assertEqual(self.run_cli("restore"), 0)
        self.assertEqual(snapshot(self.home), before)

    def test_restore_retains_foreign_files_added_after_apply(self):
        self.assertEqual(self.run_cli("apply"), 0)
        foreign = self.ext_root() / "hand-made.bin"
        foreign.write_bytes(b"\xffnew user data\r\n")
        self.assertEqual(self.run_cli("restore"), 0)
        self.assertEqual(foreign.read_bytes(), b"\xffnew user data\r\n")

    def test_restore_preserves_crlf_and_binary_support_files(self):
        for name in ("config.yaml", "SOUL.md"):
            p = self.home / name
            p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        binary = self.kit / "skills" / "alpha" / "asset.bin"
        binary.write_bytes(b"\x00\xff\r\n\x80")
        before = snapshot(self.home)
        self.assertEqual(self.run_cli("apply"), 0)
        self.assertEqual((self.ext_root() / "coding-kit/alpha/asset.bin").read_bytes(), binary.read_bytes())
        self.assertEqual(self.run_cli("restore"), 0)
        self.assertEqual(snapshot(self.home), before)

    def test_recovery_anchor_failure_rolls_back_legacy_and_all_writes(self):
        legacy = self.home / "skills" / "coding-kit"
        shutil.copytree(self.kit / "skills", legacy)
        before = snapshot(self.home)
        original = self.adapter.safe_write_text
        def fail_anchor(path, content, boundary=None, encoding="utf-8"):
            if path.name == self.adapter.RESTORE_NAME:
                raise OSError("injected recovery anchor failure")
            return original(path, content, boundary=boundary, encoding=encoding)
        self.adapter.safe_write_text = fail_anchor
        self.addCleanup(setattr, self.adapter, "safe_write_text", original)
        self.assertEqual(self.run_cli("apply", "--retire-legacy"), 1)
        self.assertEqual(snapshot(self.home), before)

    def test_migrated_legacy_leaves_discovery_tree_and_restores_exactly(self):
        legacy = self.home / "skills" / "coding-kit"
        shutil.copytree(self.kit / "skills", legacy)
        before = snapshot(self.home)
        self.assertEqual(self.run_cli("apply", "--retire-legacy"), 0)
        self.assertEqual(list((self.home / "skills").rglob("SKILL.md")), [])
        self.assertEqual(self.run_cli("restore"), 0)
        self.assertEqual(snapshot(self.home), before)

    def test_preview_does_not_retire_foreign_directory(self):
        self.assertEqual(self.run_cli("apply"), 0)
        foreign = self.ext_root() / "coding-kit" / "hand-made"
        foreign.mkdir()
        before = snapshot(self.home)
        plan = self.adapter.plan(self.kit, self.home, self.ext_root(), False)
        self.assertEqual(plan["retired"], 0)
        self.assertEqual(self.run_cli("apply"), 0)
        self.assertEqual(snapshot(self.home), before)

    def test_external_root_escape_is_rejected_without_writes(self):
        before = snapshot(self.tmp)
        self.assertEqual(self.run_cli("--ext-root", str(self.tmp / "outside"), "apply"), 1)
        self.assertEqual(snapshot(self.tmp), before)

    def test_newly_owned_skill_on_update_restores_original_foreign_bytes(self):
        self.assertEqual(self.run_cli("apply"), 0)
        foreign = self.ext_root() / "coding-kit" / "gamma"
        foreign.mkdir()
        (foreign / "original.bin").write_bytes(b"\xffuser\r\n")
        (foreign / "empty").mkdir()
        before = snapshot(foreign)
        make_kit(self.kit, skills=("gamma",), version="10.0")
        self.assertEqual(self.run_cli("apply"), 0)
        self.assertEqual(self.run_cli("restore"), 0)
        self.assertEqual(snapshot(foreign), before)

    def test_failure_during_restore_keeps_installed_state_and_recovery(self):
        self.assertEqual(self.run_cli("apply"), 0)
        before = snapshot(self.home)
        original = self.adapter.restore_path
        calls = 0
        def fail_second(path, image, remove):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected restore write failure")
            return original(path, image, remove)
        self.adapter.restore_path = fail_second
        self.addCleanup(setattr, self.adapter, "restore_path", original)
        self.assertEqual(self.run_cli("restore"), 1)
        self.assertEqual(snapshot(self.home), before)


if __name__ == "__main__":
    unittest.main()
