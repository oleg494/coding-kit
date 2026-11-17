"""Tests for scripts/tools/check_file_sizes.py exclusions and line-count parity."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "check_file_sizes", KIT / "scripts" / "tools" / "check_file_sizes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CheckFileSizesTest(unittest.TestCase):
    def test_excludes_worktrees_agents_and_eval_results(self):
        mod = _load_mod()
        with tempfile.TemporaryDirectory(prefix="kit-sizes-") as td:
            root = Path(td)
            for rel in (
                ".worktrees/exp/giant.py",
                ".agents/skills/demo/big.md",
                ".venv/Lib/big.py",
                "eval/results/run/trace.md",
            ):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("line\n" * 1200, encoding="utf-8")
            good = root / "src" / "ok.py"
            good.parent.mkdir(parents=True, exist_ok=True)
            good.write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(mod.collect(root), [])

    def test_staged_and_collect_agree_without_trailing_newline(self):
        mod = _load_mod()
        with tempfile.TemporaryDirectory(prefix="kit-sizes-git-") as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
            target = root / "doc.md"
            # 501 lines where the 501st line has NO trailing newline (500 '\n' bytes)
            content = "\n".join(f"line {i}" for i in range(501))
            target.write_bytes(content.encode("utf-8"))
            subprocess.run(["git", "add", "doc.md"], cwd=str(root), check=True)
            collected = mod.collect(root)
            staged = mod.staged_rows(root)
            self.assertEqual(len(collected), 1)
            self.assertEqual(collected[0]["lines"], 501)
            self.assertEqual(collected[0]["level"], "hard")
            self.assertEqual(staged, collected)


if __name__ == "__main__":
    unittest.main()
