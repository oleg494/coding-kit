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


class TestDeployRollbackRegression(unittest.TestCase):
    """Acceptance tests for handled-I/O transactional rollback in deploy.py:

    1. Canonical Mode Rollback:
       Earlier copied skill, updated skill, and deleted skill are all restored
       to their exact pre-mutation state if an I/O exception occurs on a later target.
       The temporary transaction backup is cleaned up on successful rollback.

    2. Full Deploy Cross-Domain Rollback:
       If an I/O failure occurs late in the deploy (during router regeneration or Claude bump,
       or verify failure), all skill mutations, created directories, prior router files,
       and prior .kit-bak files are restored to their exact original bytes or absent state.

    3. Rollback Failure Preservation:
       If an error prevents full rollback, the recovery snapshot directory is preserved
       and reported cleanly.
    """

    def test_canonical_mode_handled_io_error_restores_earlier_mutations(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            (skills_dir / "alpha").mkdir(parents=True)
            (skills_dir / "alpha" / "SKILL.md").write_text("alpha new", encoding="utf-8")
            (skills_dir / "beta").mkdir(parents=True)
            (skills_dir / "beta" / "SKILL.md").write_text("beta new", encoding="utf-8")
            (skills_dir / "gamma").mkdir(parents=True)
            (skills_dir / "gamma" / "SKILL.md").write_text("gamma new", encoding="utf-8")

            canon = root / ".agents" / "skills"
            canon.mkdir(parents=True)

            # beta already exists with old content
            (canon / "beta").mkdir(parents=True)
            (canon / "beta" / "SKILL.md").write_text("beta old original", encoding="utf-8")

            # ghost is a stale skill that should be removed
            (canon / "ghost").mkdir(parents=True)
            (canon / "ghost" / "SKILL.md").write_text("ghost original", encoding="utf-8")

            # Manifest already exists with old skills
            old_manifest_content = '{"kit_version": "1.0.0", "skills": ["beta", "ghost"]}\n'
            (canon / deploy.MANIFEST_NAME).write_text(old_manifest_content, encoding="utf-8")

            # Injected failure: fail when writing gamma
            original_safe_copytree = deploy.safe_copytree

            def failing_copytree(src: Path, target: Path, boundary: Path):
                if "gamma" in str(target):
                    raise OSError("Simulated disk full error during gamma copy!")
                return original_safe_copytree(src, target, boundary)

            with mock.patch.object(deploy, "KIT", root), \
                 mock.patch.object(deploy, "SKILLS", skills_dir), \
                 mock.patch.object(deploy, "safe_copytree", failing_copytree), \
                 mock.patch.object(sys, "argv", ["deploy.py", "--canonical"]):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                # Deploy must report failure
                self.assertNotEqual(rc, 0, "canonical deploy must fail when I/O error occurs")

                # VERIFY ROLLBACK:
                # 1. alpha was planned to be added before gamma -> must be removed!
                self.assertFalse((canon / "alpha").exists(), "alpha must be removed on rollback")
                # 2. beta was updated before gamma -> must be restored to old content!
                self.assertEqual((canon / "beta" / "SKILL.md").read_text(encoding="utf-8"), "beta old original")
                # 3. ghost must still exist with original content!
                self.assertEqual((canon / "ghost" / "SKILL.md").read_text(encoding="utf-8"), "ghost original")
                # 4. Manifest must be restored to old content!
                self.assertEqual((canon / deploy.MANIFEST_NAME).read_text(encoding="utf-8"), old_manifest_content)

    def test_full_deploy_late_router_failure_restores_skills_and_prior_routers(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()

            # Existing skill in dest that will be updated
            master_name = deploy.master_skill_names()[0]
            (dest / master_name).mkdir(parents=True)
            original_skill_content = "user existing skill content"
            (dest / master_name / "file.txt").write_text(original_skill_content, encoding="utf-8")

            # Existing manifest in dest
            old_manifest = f'{{"kit_version": "0.0.1", "skills": ["{master_name}"]}}\n'
            (dest / deploy.MANIFEST_NAME).write_text(old_manifest, encoding="utf-8")

            # Two routers
            router1 = root / ".omp" / "agent" / "AGENTS.md"
            router1.parent.mkdir(parents=True)
            router1_content = "# Coding Agent Router (OMP) - coding-kit v0.0.1\n# Old OMP router\n"
            router1.write_text(router1_content, encoding="utf-8")
            # Existing .kit-bak for router1
            bak1 = Path(str(router1) + ".kit-bak")
            bak1_content = "# Oldest backup content for OMP\n"
            bak1.write_text(bak1_content, encoding="utf-8")

            router2 = root / "AGENTS.md"
            router2_content = "# Coding Agent Router (Antigravity) - coding-kit v0.0.1\n# Old Antigravity\n"
            router2.write_text(router2_content, encoding="utf-8")

            fake_harnesses = [
                {"id": "omp", "router": str(router1), "name": "OMP", "skills_line": None, "skills_dir": None},
                {"id": "antigravity", "router": str(router2), "name": "Antigravity", "skills_line": None, "skills_dir": None},
            ]

            # Injected failure on router2 write
            original_safe_write_text = deploy.safe_write_text

            def failing_write_text(path: Path, content: str, boundary: Path | None = None, encoding="utf-8"):
                if path == router2:
                    raise OSError("Simulated I/O write error on router2!")
                return original_safe_write_text(path, content, boundary, encoding)

            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]), \
                 mock.patch.object(deploy, "HARNESSES", fake_harnesses), \
                 mock.patch.object(deploy, "CLAUDE_MD", root / "CLAUDE.md"), \
                 mock.patch.object(deploy, "safe_write_text", failing_write_text), \
                 mock.patch.object(deploy, "integrity_gate"):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                self.assertNotEqual(rc, 0, "deploy must fail on router write error")

                # VERIFY ROLLBACK:
                # 1. Skills in dest must be restored to original content!
                self.assertEqual((dest / master_name / "file.txt").read_text(encoding="utf-8"), original_skill_content)
                # 2. Manifest in dest must be restored to old content!
                self.assertEqual((dest / deploy.MANIFEST_NAME).read_text(encoding="utf-8"), old_manifest)
                # 3. Router 1 must be restored to original content!
                self.assertEqual(router1.read_text(encoding="utf-8"), router1_content)
                # 4. Router 1 prior .kit-bak must be restored to original content!
                self.assertEqual(bak1.read_text(encoding="utf-8"), bak1_content)
                # 5. Router 2 must remain original content!
                self.assertEqual(router2.read_text(encoding="utf-8"), router2_content)

    def test_verify_false_triggers_rollback(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()

            master_name = deploy.master_skill_names()[0]
            (dest / master_name).mkdir(parents=True)
            original_skill_content = "original skill before failed verify"
            (dest / master_name / "file.txt").write_text(original_skill_content, encoding="utf-8")

            old_manifest = f'{{"kit_version": "0.0.1", "skills": ["{master_name}"]}}\n'
            (dest / deploy.MANIFEST_NAME).write_text(old_manifest, encoding="utf-8")

            router1 = root / ".omp" / "agent" / "AGENTS.md"
            router1.parent.mkdir(parents=True)
            router1_content = "# Coding Agent Router (OMP) - coding-kit v0.0.1\n# Old OMP router\n"
            router1.write_text(router1_content, encoding="utf-8")

            fake_harnesses = [
                {"id": "omp", "router": str(router1), "name": "OMP", "skills_line": None, "skills_dir": None},
            ]

            # Simulate verify() returning False
            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]), \
                 mock.patch.object(deploy, "HARNESSES", fake_harnesses), \
                 mock.patch.object(deploy, "CLAUDE_MD", root / "CLAUDE.md"), \
                 mock.patch.object(deploy, "verify", lambda: False), \
                 mock.patch.object(deploy, "integrity_gate"):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                self.assertNotEqual(rc, 0, "deploy must fail when verify returns False")

                # Rollback must restore dest and router1
                self.assertEqual((dest / master_name / "file.txt").read_text(encoding="utf-8"), original_skill_content)
                self.assertEqual((dest / deploy.MANIFEST_NAME).read_text(encoding="utf-8"), old_manifest)
                self.assertEqual(router1.read_text(encoding="utf-8"), router1_content)


    def test_rollback_failure_preserves_recovery_directory_and_reports_location(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canon = root / ".agents" / "skills"
            canon.mkdir(parents=True)
            target_dir = canon / "my_skill"
            target_dir.mkdir(parents=True)
            (target_dir / "SKILL.md").write_text("v1", encoding="utf-8")

            tx = deploy.DeployTransaction()
            with tx:
                tx.snapshot_target(target_dir)
                tx.mark_mutations_started()

                real_rmtree = shutil.rmtree
                def failing_rmtree(path, *args, **kwargs):
                    if "kit-deploy-tx-" not in str(path):
                        raise PermissionError("Rollback failure on target!")
                    return real_rmtree(path, *args, **kwargs)

                out = io.StringIO()
                with mock.patch.object(shutil, "rmtree", failing_rmtree), \
                     mock.patch.object(sys, "stdout", out):
                    ok = tx.rollback("simulated initial I/O failure")

                self.assertFalse(ok)
                out_text = out.getvalue()
                self.assertIn("Recovery snapshot preserved at:", out_text)
                self.assertIn("FATAL: Deployment failed and rollback encountered secondary errors!", out_text)
                self.assertTrue(tx.tx_dir.exists(), "Transaction snapshot dir must be preserved on rollback failure")


    def test_full_deploy_failure_in_middle_of_skills_restores_earlier_skills(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()

            # Two skills in master: skill_a and skill_b
            names = deploy.master_skill_names()
            name_a, name_b = names[0], names[1]

            # Destination already has name_a with old content
            (dest / name_a).mkdir(parents=True)
            old_content_a = "original content of skill A before failure"
            (dest / name_a / "old.txt").write_text(old_content_a, encoding="utf-8")
            old_manifest = f'{{"kit_version": "0.0.1", "skills": ["{name_a}"]}}\n'
            (dest / deploy.MANIFEST_NAME).write_text(old_manifest, encoding="utf-8")

            # Fail when copying second skill (name_b)
            original_safe_copytree = deploy.safe_copytree

            def failing_safe_copytree(src: Path, target: Path, boundary: Path):
                if name_b in str(target):
                    raise OSError(f"Simulated I/O failure while copying {name_b}!")
                return original_safe_copytree(src, target, boundary)

            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]), \
                 mock.patch.object(deploy, "HARNESSES", []), \
                 mock.patch.object(deploy, "CLAUDE_MD", root / "CLAUDE.md"), \
                 mock.patch.object(deploy, "safe_copytree", failing_safe_copytree), \
                 mock.patch.object(deploy, "integrity_gate"):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                self.assertNotEqual(rc, 0, "deploy must fail when failure occurs in middle of skills")

                # VERIFY ROLLBACK:
                # 1. skill_a must be restored to its exact old state!
                self.assertEqual((dest / name_a / "old.txt").read_text(encoding="utf-8"), old_content_a)
                # 2. skill_b must not exist
                self.assertFalse((dest / name_b).exists(), "skill B must not exist after rollback")
                # 3. manifest must be restored to old content
                self.assertEqual((dest / deploy.MANIFEST_NAME).read_text(encoding="utf-8"), old_manifest)

    def test_malformed_traversal_manifest_preflight_prevents_snapshots_of_external_paths(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "skills"
            dest.mkdir()
            ext = root / "outside"
            ext.mkdir()
            (ext / "secret.txt").write_text("outside secret", encoding="utf-8")

            # Manifest contains directory traversal to outside path
            traversal_manifest = '{"kit_version": "1.0.0", "skills": ["../outside"]}\n'
            (dest / deploy.MANIFEST_NAME).write_text(traversal_manifest, encoding="utf-8")

            with mock.patch.object(sys, "argv", ["deploy.py"]), \
                 mock.patch.object(deploy, "SYNC_TARGETS", [str(dest)]), \
                 mock.patch.object(deploy, "HARNESSES", []), \
                 mock.patch.object(deploy, "CLAUDE_MD", root / "CLAUDE.md"), \
                 mock.patch.object(deploy, "integrity_gate"):
                out = io.StringIO()
                with mock.patch.object(sys, "stdout", out):
                    rc = deploy.main()

                self.assertNotEqual(rc, 0, "deploy must abort on traversal manifest")
                # Output should report preflight conflict/error
                self.assertIn("DEPLOY ABORTED:", out.getvalue())
if __name__ == "__main__":
    unittest.main()
