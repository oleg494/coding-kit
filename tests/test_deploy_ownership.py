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
                has_conflict = any("conflict" in str(action).lower() for r in report for action in r.actions)
                self.assertTrue(has_conflict, f"Expected conflict in report: {report}")
                self.assertFalse(report[0].ok)

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


class TestResidualDefects(unittest.TestCase):
    """Tests for residual defects found in external audit of v4.3.0.

    Defect 1 (P1): sync can write OUTSIDE the destination through nested symlinks/junctions.
    Defect 2 (P2): preview/execution parity incomplete + no global preflight across destinations.
    """

    def test_scan_skill_links_detects_symlink_or_junction(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "skills"
            dest.mkdir()
            skill_dir = dest / "my_skill"
            skill_dir.mkdir()
            outside = Path(td) / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("precious", encoding="utf-8")
            junc = skill_dir / "nested_junc"
            # Try creating a junction portably on Windows or symlink on POSIX
            if sys.platform == "win32":
                import subprocess
                cmd = ["powershell", "-NoProfile", "-Command",
                       f'New-Item -ItemType Junction -Path "{junc}" -Target "{outside}" | Out-Null']
                subprocess.run(cmd, check=True)
            else:
                junc.symlink_to(outside, target_is_directory=True)

            self.assertTrue(deploy.is_link(junc))
            bad_links = deploy.scan_skill_links(dest, skill_dir)
            self.assertTrue(len(bad_links) > 0, f"Expected bad links detected, got: {bad_links}")

    def test_nested_symlink_inside_adoptable_skill_refuses_dest_and_protects_outside(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("original content", encoding="utf-8")

            master_name = deploy.master_skill_names()[0]
            target = dest / master_name
            # Copy byte-identical master skill
            shutil.copytree(deploy.SKILLS / master_name, target)

            # Plant a symlink inside target pointing to outside sentinel
            link_file = target / "evil_link.txt"
            try:
                link_file.symlink_to(sentinel)
            except OSError:
                # Windows without SeCreateSymbolicLinkPrivilege
                # Test with directory junction pointing outside
                evil_dir = target / "evil_dir"
                import subprocess
                cmd = ["powershell", "-NoProfile", "-Command",
                       f'New-Item -ItemType Junction -Path "{evil_dir}" -Target "{outside}" | Out-Null']
                res = subprocess.run(cmd)
                if res.returncode != 0:
                    self.skipTest("Cannot create symlinks or junctions in this environment")

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
                report = deploy.sync_skills()
                # Outside sentinel must still exist and be UNCHANGED
                self.assertTrue(sentinel.exists())
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "original content")
                has_conflict = any("conflict" in str(a).lower() for r in report for a in r.actions)
                self.assertTrue(has_conflict, f"Expected conflict in report: {report}")
                self.assertFalse(report[0].ok)

    def test_nested_symlink_write_through_attempt_refused_and_outside_file_intact(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "victim.txt"
            sentinel.write_text("precious original", encoding="utf-8")

            master_name = deploy.master_skill_names()[0]
            target = dest / master_name
            shutil.copytree(deploy.SKILLS / master_name, target)

            # Overwrite an existing skill file (e.g. SKILL.md) with a symlink to victim
            target_file = target / "SKILL.md"
            if target_file.exists():
                target_file.unlink()
            try:
                target_file.symlink_to(sentinel)
            except OSError:
                self.skipTest("Symlink creation not permitted without admin privilege on Windows")

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
                report = deploy.sync_skills()
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "precious original")
                has_conflict = any("conflict" in str(a).lower() for r in report for a in r.actions)
                self.assertTrue(has_conflict)
                self.assertFalse(report[0].ok)
    def test_nested_link_inside_manifest_owned_skill_refuses_dest(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("original content", encoding="utf-8")

            master_name = deploy.master_skill_names()[0]
            target = dest / master_name
            shutil.copytree(deploy.SKILLS / master_name, target)

            # Create manifest owning master_name
            mani_file = dest / deploy.MANIFEST_NAME
            mani_file.write_text(f'{{"kit_version": "{deploy.VERSION}", "skills": ["{master_name}"]}}', encoding="utf-8")

            # Create a junction pointing outside inside target/nested
            nested_target = target / "nested_outside"
            if sys.platform == "win32":
                import subprocess
                cmd = ["powershell", "-NoProfile", "-Command",
                       f'New-Item -ItemType Junction -Path "{nested_target}" -Target "{outside}" | Out-Null']
                res = subprocess.run(cmd)
                if res.returncode != 0:
                    self.skipTest("Cannot create junction")
            else:
                nested_target.symlink_to(outside, target_is_directory=True)

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
                report = deploy.sync_skills()
                # Outside sentinel must still exist and be intact
                self.assertTrue(sentinel.exists())
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "original content")
                has_conflict = any("conflict" in str(a).lower() for r in report for a in r.actions)
                self.assertTrue(has_conflict, f"Expected conflict in report: {report}")
                self.assertFalse(report[0].ok)
    def test_global_preflight_all_destinations_fail_before_any_write(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest1 = root / "dest1"
            dest2 = root / "dest2"
            dest1.mkdir()
            dest2.mkdir()

            sentinel1 = dest1 / "sentinel1.txt"
            sentinel1.write_text("dest1 original", encoding="utf-8")

            # dest2 has an unowned differing skill -> conflict
            master_name = deploy.master_skill_names()[0]
            unowned = dest2 / master_name
            unowned.mkdir(parents=True)
            (unowned / "custom.txt").write_text("user custom skill", encoding="utf-8")

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest1), str(dest2)]):
                report = deploy.sync_skills()
                # dest1 must be completely untouched!
                self.assertTrue(sentinel1.exists())
                self.assertEqual(sentinel1.read_text(encoding="utf-8"), "dest1 original")
                self.assertFalse((dest1 / deploy.MANIFEST_NAME).exists(), "dest1 manifest must NOT be written")
                self.assertFalse((dest1 / master_name).exists(), "dest1 must NOT receive any synced skills")
                dest2_conflict = any("conflict" in str(a).lower() for r in report if r.target == str(dest2) for a in r.actions)
                self.assertTrue(dest2_conflict)
                self.assertTrue(any(not r.ok for r in report))

    def test_canonical_manifest_change_advertised_in_dry_run_and_executed(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            (skills_dir / "my_skill").mkdir(parents=True)
            (skills_dir / "my_skill" / "SKILL.md").write_text("v1", encoding="utf-8")

            canon = root / ".agents" / "skills"
            (canon / "my_skill").mkdir(parents=True)
            (canon / "my_skill" / "SKILL.md").write_text("v1", encoding="utf-8")
            # Write a manifest with stale kit_version
            mani_file = canon / deploy.MANIFEST_NAME
            mani_file.write_text('{"kit_version": "0.0.1", "skills": ["my_skill"]}', encoding="utf-8")

            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical", "--dry-run"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()
                dry_out = out.getvalue()
                self.assertEqual(rc, 0)
                self.assertIn("upd .kit-manifest.json", dry_out)

                # Stale manifest should NOT have changed during dry-run
                self.assertIn('"0.0.1"', mani_file.read_text(encoding="utf-8"))

            # Now run without dry-run
            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()
                self.assertEqual(rc, 0)
                self.assertIn(deploy.VERSION, mani_file.read_text(encoding="utf-8"))

    def test_global_preflight_conflict_causes_deploy_main_failure(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest1 = root / "dest1"
            dest2 = root / "dest2"
            dest1.mkdir()
            dest2.mkdir()
            master_name = deploy.master_skill_names()[0]
            unowned = dest2 / master_name
            unowned.mkdir(parents=True)
            (unowned / "custom.txt").write_text("user custom skill", encoding="utf-8")
            fake_harnesses = [{
                "id": "test_omp",
                "router": str(root / ".omp" / "agent" / "AGENTS.md"),
                "name": "TestOMP",
                "skills_line": None,
                "skills_dir": None,
            }]
            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(dest1), str(dest2)]), \
                 mock.patch.object(deploy, "HARNESSES", fake_harnesses), \
                 mock.patch.object(deploy, "CLAUDE_MD", root / "CLAUDE.md"), \
                 mock.patch.object(deploy, "integrity_gate"):
                rc = deploy.main()
                self.assertNotEqual(rc, 0, "Deploy must fail when any destination preflight fails")
                self.assertFalse((dest1 / master_name).exists(), "dest1 must have zero writes")
                self.assertFalse((dest1 / deploy.MANIFEST_NAME).exists(), "dest1 manifest must not be written")
    def test_canonical_identical_manifest_dry_run_no_changes(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            (skills_dir / "my_skill").mkdir(parents=True)
            (skills_dir / "my_skill" / "SKILL.md").write_text("v1", encoding="utf-8")

            canon = root / ".agents" / "skills"
            (canon / "my_skill").mkdir(parents=True)
            (canon / "my_skill" / "SKILL.md").write_text("v1", encoding="utf-8")
            import json
            mani_file = canon / deploy.MANIFEST_NAME
            mani_content = json.dumps({"kit_version": deploy.VERSION, "skills": ["my_skill"]}, indent=1) + "\n"
            mani_file.write_text(mani_content, encoding="utf-8")

            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical", "--dry-run"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()
                self.assertEqual(rc, 0)
                self.assertIn("no changes", out.getvalue())
                self.assertNotIn("upd .kit-manifest.json", out.getvalue())


def _try_create_dir_link(target: Path, link: Path) -> bool:
    """Try creating junction on Windows or symlink on POSIX. Return True on success."""
    if sys.platform == "win32":
        try:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
            return True
        except Exception:
            pass
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except Exception:
        return False


class TestDeployWriteBoundariesRegression(unittest.TestCase):
    """Regression tests for:
    1. skills preflight conflict/error stops deploy BEFORE any router/Claude mutation.
    2. canonical sync rejects nested symlinks/junctions (external sentinels byte-unchanged).
    3. canonical sync rejects escaped/linked canon root or .agents ancestor.
    4. scan_skill_links catches dangling root links.
    5. safe_write_text rejects link targets and link ancestors.
    6. routers and claude_md write paths reject links.
    7. valid canonical operation works properly.
    """

    def test_skills_preflight_failure_aborts_whole_deploy_before_router_or_claude_mutations(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest1 = root / "dest1"
            dest2 = root / "dest2"
            dest1.mkdir()
            dest2.mkdir()

            # Destination 2 has unowned skill conflict
            master_name = deploy.master_skill_names()[0]
            unowned = dest2 / master_name
            unowned.mkdir(parents=True)
            (unowned / "custom.txt").write_text("user custom skill", encoding="utf-8")

            # Existing kit-owned router that would otherwise be regenerated
            router_file = root / "AGENTS.md"
            original_router_content = "# Coding Agent Router (OMP) - coding-kit v0.0.1\n# Old router\n"
            router_file.write_text(original_router_content, encoding="utf-8")

            # Existing Claude config that would otherwise be bumped
            claude_file = root / "CLAUDE.md"
            original_claude_content = "coding-kit v0.0.1 (repo master; machine CLAUDE.md refreshed 2026-01-01) (1, English)\n"
            claude_file.write_text(original_claude_content, encoding="utf-8")

            harnesses = [{
                "id": "test_omp",
                "router": str(router_file),
                "name": "OMP",
                "skills_line": None,
                "skills_dir": None,
            }]

            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(dest1), str(dest2)]), \
                 mock.patch.object(deploy, "HARNESSES", harnesses), \
                 mock.patch.object(deploy, "CLAUDE_MD", claude_file), \
                 mock.patch.object(deploy, "integrity_gate"):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                # Deploy MUST fail with non-zero exit code
                self.assertNotEqual(rc, 0, "Deploy must fail when skills preflight fails")

                # CRITICAL: Routers and Claude config must remain BYTE-UNCHANGED!
                self.assertEqual(router_file.read_text(encoding="utf-8"), original_router_content,
                                 "Router was mutated despite skills preflight failure!")
                self.assertEqual(claude_file.read_text(encoding="utf-8"), original_claude_content,
                                 "CLAUDE.md was mutated despite skills preflight failure!")

                # No backup file created either
                self.assertFalse(Path(str(router_file) + ".kit-bak").exists(),
                                 "Router backup must not be created on aborted deploy")

                # Destination 1 must have ZERO writes
                self.assertFalse((dest1 / master_name).exists(), "dest1 skills must not be written")
                self.assertFalse((dest1 / deploy.MANIFEST_NAME).exists(), "dest1 manifest must not be written")

    def test_canonical_sync_rejects_nested_link_and_leaves_external_sentinel_byte_unchanged(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            (skills_dir / "my_skill").mkdir(parents=True)
            (skills_dir / "my_skill" / "SKILL.md").write_text("evil kit content", encoding="utf-8")

            canon = root / ".agents" / "skills"
            canon.mkdir(parents=True)
            target_skill = canon / "my_skill"

            external = root / "external_victim"
            external.mkdir(parents=True)
            sentinel = external / "SKILL.md"
            original_sentinel_content = "ORIGINAL VICTIM SENTINEL DO NOT OVERWRITE"
            sentinel.write_text(original_sentinel_content, encoding="utf-8")

            if not _try_create_dir_link(external, target_skill):
                self.skipTest("Filesystem does not support directory links/junctions")

            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                # Must fail with non-zero exit code
                self.assertNotEqual(rc, 0, "canonical_mode must return non-zero when link target encountered")
                # Sentinel MUST remain byte-identical
                self.assertEqual(sentinel.read_text(encoding="utf-8"), original_sentinel_content,
                                 "External victim sentinel was overwritten through junction!")

    def test_canonical_sync_rejects_link_in_canon_or_ancestors(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            (skills_dir / "my_skill").mkdir(parents=True)
            (skills_dir / "my_skill" / "SKILL.md").write_text("kit content", encoding="utf-8")

            external = root / "external_tree"
            external.mkdir(parents=True)
            sentinel = external / "sentinel.txt"
            original_sentinel = "ORIGINAL SENTINEL"
            sentinel.write_text(original_sentinel, encoding="utf-8")

            # Make .agents directory itself a junction/link to external_tree
            agents_dir = root / ".agents"
            if not _try_create_dir_link(external, agents_dir):
                self.skipTest("Filesystem does not support directory links/junctions")

            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                self.assertNotEqual(rc, 0, "canonical_mode must fail when .agents is a link")
                self.assertEqual(sentinel.read_text(encoding="utf-8"), original_sentinel)

    def test_scan_skill_links_detects_dangling_root_link(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()
            dangling = dest / "dangling_skill"
            to_delete = root / "to_delete"
            to_delete.mkdir()
            if not _try_create_dir_link(to_delete, dangling):
                self.skipTest("Filesystem does not support directory links/junctions")
            shutil.rmtree(to_delete)

            # Must detect dangling link and report it as a problem
            bad = deploy.scan_skill_links(dest, dangling)
            self.assertTrue(len(bad) > 0, f"Expected scan_skill_links to detect dangling link, got: {bad}")
            self.assertIn("root link", bad[0])

    def test_canonical_mode_valid_operation_succeeds(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            (skills_dir / "clean_skill").mkdir(parents=True)
            (skills_dir / "clean_skill" / "SKILL.md").write_text("clean content", encoding="utf-8")

            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                self.assertEqual(rc, 0, "Valid canonical sync should succeed")
                canon_file = root / ".agents" / "skills" / "clean_skill" / "SKILL.md"
                self.assertTrue(canon_file.exists())
                self.assertEqual(canon_file.read_text(encoding="utf-8"), "clean content")
                mani_file = root / ".agents" / "skills" / deploy.MANIFEST_NAME
                self.assertTrue(mani_file.exists())

    def test_routers_and_claude_reject_link_targets_and_nested_ancestors(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_home = root / "home"
            fake_home.mkdir()

            # Setup an external victim dir with sentinels
            external = root / "ext_victim"
            external.mkdir()
            router_sentinel = external / "AGENTS.md"
            claude_sentinel = external / "CLAUDE.md"
            router_sentinel.write_text("ORIGINAL ROUTER SENTINEL", encoding="utf-8")
            claude_sentinel.write_text("ORIGINAL CLAUDE SENTINEL", encoding="utf-8")

            # Make nested router ancestor a junction: fake_home/.omp -> external
            omp_dir = fake_home / ".omp"
            if not _try_create_dir_link(external, omp_dir):
                self.skipTest("Filesystem does not support junctions/links")

            router_path = omp_dir / "agent" / "AGENTS.md"
            harnesses = [{
                "id": "test_omp",
                "router": str(router_path),
                "name": "OMP",
                "skills_line": None,
                "skills_dir": None,
            }]

            with mock.patch.object(deploy, "HARNESSES", harnesses), \
                 mock.patch.object(Path, "home", lambda: fake_home):
                # Preflight routers should report failure
                ok, errs = deploy.preflight_routers_and_claude()
                self.assertFalse(ok)
                self.assertTrue(any("link" in e.lower() or "symlink" in e.lower() for e in errs))

                actions = deploy.regen_routers()
                self.assertTrue(any("link" in act.lower() for _, act in actions),
                                f"Expected link conflict for router, got: {actions}")
                self.assertEqual(router_sentinel.read_text(encoding="utf-8"), "ORIGINAL ROUTER SENTINEL")

            # Make claude ancestor a junction: fake_home/.claude -> external
            claude_dir = fake_home / ".claude"
            if not _try_create_dir_link(external, claude_dir):
                self.skipTest("Filesystem does not support junctions/links")

            claude_md_path = claude_dir / "CLAUDE.md"
            with mock.patch.object(deploy, "CLAUDE_MD", claude_md_path), \
                 mock.patch.object(Path, "home", lambda: fake_home):
                res = deploy.bump_claude_md()
                self.assertIn("link", res.lower())
    def test_sync_skills_supported_master_junction_skipped_with_zero_writes(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_master = root / "skills"
            (skills_master / "master_skill").mkdir(parents=True)
            sentinel = skills_master / "master_skill" / "SKILL.md"
            original_sentinel = "ORIGINAL MASTER SKILL CONTENT"
            sentinel.write_text(original_sentinel, encoding="utf-8")

            # Target ~/.zcode/skills is a junction to skills_master
            zcode_dir = root / ".zcode"
            zcode_dir.mkdir()
            zcode_skills = zcode_dir / "skills"
            if not _try_create_dir_link(skills_master, zcode_skills):
                self.skipTest("Filesystem does not support directory links/junctions")

            with mock.patch.object(deploy, "SKILLS", skills_master), \
                 mock.patch.object(deploy, "master_skill_names", lambda: ["master_skill"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(zcode_skills)]):
                report = deploy.sync_skills()
                self.assertTrue(report[0].ok, f"Supported master junction must pass preflight with ok=True: {report}")
                self.assertIn("master junction", report[0].actions[0])
                # Sentinel remains completely unchanged
                self.assertEqual(sentinel.read_text(encoding="utf-8"), original_sentinel)

    def test_sync_skills_foreign_junction_refused_with_zero_writes(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_master = root / "skills"
            skills_master.mkdir()

            # Foreign external directory with sentinel
            foreign = root / "foreign_victim"
            foreign.mkdir()
            sentinel = foreign / "victim.txt"
            original_sentinel = "DO NOT WRITE TO FOREIGN VICTIM"
            sentinel.write_text(original_sentinel, encoding="utf-8")

            zcode_skills = root / "skills_target"
            if not _try_create_dir_link(foreign, zcode_skills):
                self.skipTest("Filesystem does not support directory links/junctions")

            with mock.patch.object(deploy, "SKILLS", skills_master), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(zcode_skills)]):
                report = deploy.sync_skills()
                self.assertFalse(report[0].ok)
                self.assertTrue(any("foreign" in a.lower() or "rejected" in a.lower() for a in report[0].actions))
                self.assertEqual(sentinel.read_text(encoding="utf-8"), original_sentinel)
                self.assertFalse((foreign / "master_skill").exists())

    def test_sync_skills_preflight_rejects_link_manifest(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()
            ext = root / "ext_victim"
            ext.mkdir()
            sentinel = ext / "sentinel.txt"
            sentinel.write_text("MANIFEST TARGET SENTINEL", encoding="utf-8")

            mani_path = dest / deploy.MANIFEST_NAME
            if sys.platform != "win32":
                mani_path.symlink_to(sentinel)
            else:
                # On Windows without symlink privileges, create junction at manifest path
                if not _try_create_dir_link(ext, mani_path):
                    self.skipTest("Filesystem does not support directory links/junctions")

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
                report = deploy.sync_skills()
                self.assertFalse(report[0].ok)
                self.assertTrue(any("manifest" in err.lower() and ("symlink" in err.lower() or "regular file" in err.lower() or "error" in err.lower()) for err in report[0].actions))
                # Sentinel remains completely untouched
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "MANIFEST TARGET SENTINEL")

    def test_canonical_sync_sorted_later_dangling_target_preserves_earlier_destination(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            # Create two skills: alpha and zulu
            (skills_dir / "alpha").mkdir(parents=True)
            (skills_dir / "alpha" / "SKILL.md").write_text("alpha master content", encoding="utf-8")
            (skills_dir / "zulu").mkdir(parents=True)
            (skills_dir / "zulu" / "SKILL.md").write_text("zulu master content", encoding="utf-8")

            canon = root / ".agents" / "skills"
            canon.mkdir(parents=True)
            # zulu target is a dangling junction
            zulu_target = canon / "zulu"
            to_delete = root / "to_delete"
            to_delete.mkdir()
            if not _try_create_dir_link(to_delete, zulu_target):
                self.skipTest("Filesystem does not support junctions/links")
            shutil.rmtree(to_delete)

            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                self.assertNotEqual(rc, 0, "canonical_mode must fail when zulu is a dangling link")
                # Earlier sorted skill alpha MUST NOT have been copied!
                self.assertFalse((canon / "alpha").exists(), "alpha must not be copied when later zulu has conflict/link")

            # Test dry-run also reports failure
            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical", "--dry-run"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc_dry = deploy.main()
                self.assertNotEqual(rc_dry, 0, "canonical dry-run must fail on dangling link")
                self.assertIn("ERROR:", out.getvalue())

    def test_sync_skills_rejects_destination_ancestor_link_and_avoids_mutation(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_home = root / "home"
            fake_home.mkdir()
            ext = root / "ext_victim"
            ext.mkdir()
            sentinel = ext / "sentinel.txt"
            sentinel.write_text("OUTSIDE DEST SENTINEL", encoding="utf-8")

            # make ~/.agents a junction to ext
            agents_dir = fake_home / ".agents"
            if not _try_create_dir_link(ext, agents_dir):
                self.skipTest("Filesystem does not support junctions/links")

            target_dest = agents_dir / "skills"
            with mock.patch.object(deploy, "SYNC_TARGETS", [str(target_dest)]), \
                 mock.patch.object(Path, "home", lambda: fake_home):
                report = deploy.sync_skills()
                self.assertFalse(report[0].ok)
                self.assertTrue(any("ancestor" in a.lower() for a in report[0].actions))
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "OUTSIDE DEST SENTINEL")
                self.assertFalse((ext / "skills").exists())

    def test_sync_skills_stale_removal_nested_link_refuses_preflight_before_writes(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()

            # Stale skill in manifest that has nested junction
            stale_dir = dest / "stale_old_skill"
            (stale_dir / "sub").mkdir(parents=True)
            ext = root / "ext_victim"
            ext.mkdir()
            sentinel = ext / "sentinel.txt"
            sentinel.write_text("PRESERVE STALE SENTINEL", encoding="utf-8")
            if not _try_create_dir_link(ext, stale_dir / "sub" / "junc"):
                self.skipTest("Filesystem does not support junctions/links")

            import json
            # Manifest claims ownership of stale_old_skill and a master skill
            master_name = deploy.master_skill_names()[0]
            (dest / deploy.MANIFEST_NAME).write_text(
                json.dumps({"kit_version": deploy.VERSION, "skills": [master_name, "stale_old_skill"]}),
                encoding="utf-8"
            )

            with mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]):
                report = deploy.sync_skills()
                self.assertFalse(report[0].ok)
                self.assertTrue(any("stale skill" in a.lower() and "conflict" in a.lower() for a in report[0].actions))
                # Master skill must not have been synced
                self.assertFalse((dest / master_name).exists(), "Zero writes on stale link conflict")
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "PRESERVE STALE SENTINEL")
