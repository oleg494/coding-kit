import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parent.parent


def load_deploy():
    spec = importlib.util.spec_from_file_location(
        "deploy", KIT / "scripts" / "tools" / "deploy.py"
    )
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    return deploy


class TestCR01Ownership(unittest.TestCase):
    """CR-01: Kit ownership before write.
    A skill dir is kit-owned iff:
    (a) target manifest lists it, or
    (b) does not exist yet, or
    (c) exists and is byte-identical to master (safe adoption).
    An existing, differing, unlisted skill dir = CONFLICT: never touch it, report it,
    and make overall run signal incomplete.

    Routers: kit-owned iff it carries kit header marker ("# Coding Agent Router" or soul marker).
    Existing router without marker = conflict (skip + report), never destroy foreign text.
    Backup before replacing owned router: <path>.kit-bak
    """

    def test_unowned_differing_skill_is_not_overwritten_and_causes_conflict(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            dest = fake_home / "skills"
            dest.mkdir(parents=True)
            # Create a skill with the same name as one in master, but different content and NO manifest
            master_name = deploy.master_skill_names()[0]
            unowned = dest / master_name
            unowned.mkdir(parents=True)
            (unowned / "custom.txt").write_text("user custom skill", encoding="utf-8")

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
                report = deploy.sync_skills()
                # Custom file must still be there, unowned skill must not be deleted or overwritten
                self.assertTrue((unowned / "custom.txt").exists())
                self.assertEqual((unowned / "custom.txt").read_text(encoding="utf-8"), "user custom skill")
                # Report must contain conflict
                has_conflict = any("conflict" in str(action).lower() for _, actions, _ in report for action in actions)
                self.assertTrue(has_conflict, f"Expected conflict in report: {report}")

    def test_unowned_skill_conflict_causes_deploy_main_failure(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            dest = fake_home / "skills"
            dest.mkdir(parents=True)
            master_name = deploy.master_skill_names()[0]
            unowned = dest / master_name
            unowned.mkdir(parents=True)
            (unowned / "custom.txt").write_text("user custom skill", encoding="utf-8")
            fake_harnesses = [{
                "id": "test_omp",
                "router": str(fake_home / ".omp" / "agent" / "AGENTS.md"),
                "name": "TestOMP",
                "skills_line": None,
                "skills_dir": None,
            }]
            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]), \
                 mock.patch.object(deploy, "HARNESSES", fake_harnesses), \
                 mock.patch.object(deploy, "CLAUDE_MD", fake_home / "CLAUDE.md"), \
                 mock.patch.object(deploy, "integrity_gate"):
                rc = deploy.main()
                self.assertNotEqual(rc, 0, "Deploy must return non-zero exit code when a conflict prevents full deployment")

    def test_byte_identical_unlisted_skill_is_adopted_and_manifested(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            dest = fake_home / "skills"
            dest.mkdir(parents=True)
            # Create a skill identical to master
            master_name = deploy.master_skill_names()[0]
            src = deploy.SKILLS / master_name
            target = dest / master_name
            shutil.copytree(src, target)

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
                deploy.sync_skills()
                # Manifest should now be written and list master_name
                mani = deploy.load_manifest(dest)
                self.assertIsNotNone(mani)
                self.assertIn(master_name, mani.get("skills", []))
    def test_foreign_router_without_marker_is_not_destroyed(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            router_path = fake_home / "AGENTS.md"
            user_content = "# My Custom Personal Agent Config\nDo not overwrite me!\n"
            router_path.write_text(user_content, encoding="utf-8")

            harness = [{
                "id": "test_antigravity",
                "router": str(router_path),
                "name": "Antigravity",
                "skills_line": None,
                "skills_dir": None,
            }]
            with mock.patch.object(deploy, "HARNESSES", harness):
                actions = deploy.regen_routers()
                self.assertEqual(router_path.read_text(encoding="utf-8"), user_content)
                has_conflict = any("conflict" in act.lower() for _, act in actions)
                self.assertTrue(has_conflict, f"Expected conflict for foreign router: {actions}")

    def test_owned_router_replacement_creates_backup(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            router_path = fake_home / "AGENTS.md"
            # Router with kit marker but older content
            old_kit_router = f"# Coding Agent Router (Antigravity) - coding-kit v1.0.0\n{deploy.SOUL_MARKER}\nold content\n"
            router_path.write_text(old_kit_router, encoding="utf-8")

            harness = [{
                "id": "test_antigravity",
                "router": str(router_path),
                "name": "Antigravity",
                "skills_line": None,
                "skills_dir": None,
            }]
            with mock.patch.object(deploy, "HARNESSES", harness):
                deploy.regen_routers()
                backup_path = Path(str(router_path) + ".kit-bak")
                self.assertTrue(backup_path.exists(), "Backup .kit-bak must be created before replacing owned router")
                self.assertEqual(backup_path.read_text(encoding="utf-8"), old_kit_router)

    def test_foreign_router_conflict_causes_deploy_main_failure(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            router_path = fake_home / "AGENTS.md"
            user_content = "# My Custom Personal Agent Config\nDo not overwrite me!\n"
            router_path.write_text(user_content, encoding="utf-8")
            fake_harnesses = [{
                "id": "test_antigravity",
                "router": str(router_path),
                "name": "Antigravity",
                "skills_line": None,
                "skills_dir": None,
            }]
            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", []), \
                 mock.patch.object(deploy, "HARNESSES", fake_harnesses), \
                 mock.patch.object(deploy, "CLAUDE_MD", fake_home / "CLAUDE.md"), \
                 mock.patch.object(deploy, "integrity_gate"):
                rc = deploy.main()
                self.assertNotEqual(rc, 0, "Deploy must fail verify and return non-zero when router has foreign conflict")
                self.assertEqual(router_path.read_text(encoding="utf-8"), user_content)


class TestCR02ManifestValidation(unittest.TestCase):
    """CR-02: validate the ENTIRE manifest BEFORE any mutation of that destination:
    JSON object with skills: list of single-component names (no path separators,
    no absolute paths, no "." / "..", must resolve inside dest, entry must not be a symlink/junction).
    Malformed manifest -> fail closed for that dest BEFORE sync starts (no writes), clear error.
    """

    def test_validate_manifest_accepts_valid_manifest(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            mani = {"kit_version": "4.2.0", "skills": ["skill_a", "skill_b"]}
            ok, err = deploy.validate_manifest(dest, mani)
            self.assertTrue(ok)
            self.assertIsNone(err)

    def test_validate_manifest_rejects_non_dict_or_missing_skills(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            for bad in ["not json", [1, 2], {"kit_version": "1.0"}, {"skills": "not a list"}]:
                ok, err = deploy.validate_manifest(dest, bad)
                self.assertFalse(ok)
                self.assertIsNotNone(err)

    def test_validate_manifest_rejects_traversal_and_absolute(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            for bad_name in ["../escape", "..", ".", "foo/bar", "foo\\bar", "C:/escaped", "/escaped"]:
                mani = {"skills": [bad_name]}
                ok, err = deploy.validate_manifest(dest, mani)
                self.assertFalse(ok, f"Expected {bad_name} to be rejected")
                self.assertIsNotNone(err)

    def test_sync_skills_fails_closed_before_sync_on_malformed_manifest(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            dest = fake_home / "skills"
            dest.mkdir(parents=True)
            # Write a poisoned manifest with traversal
            poison = dest / deploy.MANIFEST_NAME
            poison.write_text('{"skills": ["../outside_victim"]}', encoding="utf-8")
            outside_victim = fake_home / "outside_victim"
            outside_victim.mkdir()
            (outside_victim / "sentinel.txt").write_text("precious", encoding="utf-8")

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
                # sync_skills should report an error / fail closed and not write new skills or touch outside
                deploy.sync_skills()
                # Sentinel must stay intact
                self.assertTrue((outside_victim / "sentinel.txt").exists())
                # No new skills created in dest because manifest validation failed closed BEFORE sync
                master_names = deploy.master_skill_names()
                self.assertGreater(len(master_names), 0)
                first_skill = dest / master_names[0]
                self.assertFalse(first_skill.exists(), "Must not write skills when manifest is malformed")

    def test_sync_skills_malformed_manifest_causes_deploy_main_failure(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            dest = fake_home / "skills"
            dest.mkdir(parents=True)
            poison = dest / deploy.MANIFEST_NAME
            poison.write_text('{"skills": ["../escape"]}', encoding="utf-8")
            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]), \
                 mock.patch.object(deploy, "HARNESSES", []), \
                 mock.patch.object(deploy, "CLAUDE_MD", fake_home / "CLAUDE.md"), \
                 mock.patch.object(deploy, "integrity_gate"):
                rc = deploy.main()
                self.assertNotEqual(rc, 0, "Deploy must fail verify and return non-zero when manifest is malformed")

class TestCR03Preflight(unittest.TestCase):
    """CR-03: Missing ~/.claude/CLAUDE.md must not crash:
    treat as "harness not present" - skip bump_claude_md, make verify() skip/report that target instead of crashing.
    The real full deploy path run against a fully isolated temp home with no .claude dir completes successfully
    (or refuses with zero mutations) - no FileNotFoundError, no partial state.
    """

    def test_full_deploy_with_missing_claude_md_does_not_crash(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            missing_claude_md = fake_home / ".claude" / "CLAUDE.md"
            fake_targets = [str(fake_home / ".agents" / "skills")]
            fake_harnesses = [{
                "id": "test_omp",
                "router": str(fake_home / ".omp" / "agent" / "AGENTS.md"),
                "name": "TestOMP",
                "skills_line": None,
                "skills_dir": None,
            }]

            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "CLAUDE_MD", missing_claude_md), \
                 mock.patch.object(deploy, "SYNC_TARGETS", fake_targets), \
                 mock.patch.object(deploy, "HARNESSES", fake_harnesses), \
                 mock.patch.object(deploy, "integrity_gate"):
                # Must not raise FileNotFoundError!
                rc = deploy.main()
                self.assertEqual(rc, 0)
                # verify bump_claude_md returned "skipped" or similar
                self.assertFalse(missing_claude_md.exists())


class TestCR04SinglePlan(unittest.TestCase):
    """CR-04: canonical_mode computes ONE change plan (add/upd/del/rm-dir).
    --dry-run prints exactly that plan; execution applies exactly that plan and nothing else.
    Stale file inside a skill and a stale skill dir appear in the dry-run output;
    after execution the advertised changes and only those happened.
    """

    def test_canonical_dry_run_includes_deletions_and_matches_execution(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            (skills_dir / "my_skill").mkdir(parents=True)
            (skills_dir / "my_skill" / "SKILL.md").write_text("v1", encoding="utf-8")

            canon = root / ".agents" / "skills"
            # Pre-populate canon with an obsolete skill dir and an extra stale file in my_skill
            (canon / "my_skill").mkdir(parents=True)
            (canon / "my_skill" / "SKILL.md").write_text("v1", encoding="utf-8")
            (canon / "my_skill" / "stale_inner.txt").write_text("stale", encoding="utf-8")
            (canon / "obsolete_skill").mkdir(parents=True)
            (canon / "obsolete_skill" / "SKILL.md").write_text("gone", encoding="utf-8")

            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical", "--dry-run"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()
                dry_run_output = out.getvalue()
                self.assertEqual(rc, 0)
                self.assertIn("del my_skill/stale_inner.txt", dry_run_output)
                self.assertIn("rm-dir obsolete_skill", dry_run_output)

                # Now execute without dry-run
                with mock.patch.object(sys, "argv", ["deploy.py", "--canonical"]):
                    exec_out = io.StringIO()
                    with mock.patch.object(sys, "stdout", exec_out):
                        rc = deploy.main()
                self.assertEqual(rc, 0)
                self.assertFalse((canon / "my_skill" / "stale_inner.txt").exists())
                self.assertFalse((canon / "obsolete_skill").exists())
