"""Generated-router migration and idempotence behavior."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_deploy_ownership import load_deploy
class TestRouterGeneration(unittest.TestCase):
    """Kit-owned routers are lightweight pointers (v4.8.0):
    - ownership/version/path metadata + skills path line
    - ONE canonical contract reference (read KIT/OPS.md at session start)
    - kit AGENTS.md referenced by path, soul body NOT embedded
    - no unconditional memory-warmup startup step
    - preserved CODEGRAPH block, foreign/backup/rollback semantics unchanged
    """

    def test_generated_router_is_lightweight_pointer(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            router_path = fake_home / "AGENTS.md"
            harness = [{
                "id": "test_antigravity",
                "router": str(router_path),
                "name": "Antigravity",
                "skills_line": "# Skills: ~/.agents/skills/",
                "skills_dir": None,
            }]
            with mock.patch.object(deploy, "HARNESSES", harness):
                deploy.regen_routers()
                text = router_path.read_text(encoding="utf-8")

            # Ownership/version/path metadata present
            self.assertIn("# Coding Agent Router (Antigravity)", text)
            self.assertIn(f"coding-kit v{deploy.VERSION}", text)
            kit = deploy.KIT.as_posix()
            self.assertIn(f"{kit}/OPS.md", text)
            self.assertIn(f"{kit}/AGENTS.md", text)
            self.assertIn("# Skills: ~/.agents/skills/", text)

            # Canonical contract referenced exactly once, memory-warmup gone
            self.assertEqual(text.count(f"1. read {kit}/OPS.md"), 1,
                             "router startup must load the canonical OPS.md exactly once")
            self.assertEqual(text.count(". read "), 1,
                             "startup must not load a second instruction body")
            self.assertNotIn("memory-warmup", text,
                             "no unconditional memory feed in generated routers")

            # Soul is a pointer, not an embedded body
            self.assertNotIn(deploy.SOUL_MARKER, text,
                             "kit soul body must not be embedded in the router")
            soul_body = deploy.KIT.joinpath("AGENTS.md").read_text(encoding="utf-8")
            soul_line = next(ln for ln in soul_body.splitlines() if ln.strip())
            self.assertNotIn(soul_line, text,
                             "soul body lines must not be embedded in the router")

            # Regeneration is idempotent
            with mock.patch.object(deploy, "HARNESSES", harness):
                actions = deploy.regen_routers()
            self.assertEqual(actions, [(str(router_path), "unchanged")],
                             f"regenerating a fresh router must be a no-op: {actions}")
            self.assertEqual(router_path.read_text(encoding="utf-8"), text)

    def test_generated_router_preserves_codegraph_block_and_baks_old_soul(self):
        deploy = load_deploy()
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            router_path = fake_home / "AGENTS.md"
            codegraph = ("<!-- CODEGRAPH_START -->\nkeep me\n<!-- CODEGRAPH_END -->")
            # v4.7-era router: embedded soul + warmup + codegraph
            old = ("# Coding Agent Router (Antigravity) - coding-kit v4.7.0\n"
                   f"{deploy.SOUL_MARKER}\nold embedded soul body\n"
                   "## STARTUP (once per session)\n"
                   "1. read OPS.md\n"
                   "2. python ~/.memory/scripts/memory-warmup.py\n"
                   f"{codegraph}\n")
            router_path.write_text(old, encoding="utf-8")

            harness = [{
                "id": "test_antigravity",
                "router": str(router_path),
                "name": "Antigravity",
                "skills_line": None,
                "skills_dir": None,
            }]
            with mock.patch.object(deploy, "HARNESSES", harness):
                actions = deploy.regen_routers()

            self.assertEqual(actions, [(str(router_path), "regenerated")])
            # Old file (soul + warmup) preserved in backup, codegraph survives
            backup = Path(str(router_path) + ".kit-bak")
            self.assertEqual(backup.read_text(encoding="utf-8"), old)
            text = router_path.read_text(encoding="utf-8")
            self.assertIn(codegraph, text)
            self.assertNotIn("memory-warmup", text)
            self.assertNotIn(deploy.SOUL_MARKER, text)
            self.assertNotIn("old embedded soul body", text)
