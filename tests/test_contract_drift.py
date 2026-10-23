#!/usr/bin/env python3
"""Contract-review pointer: materiality classification and advisory CLI.

Contract (v5.0.0, advisory — not a gate):
- scripts/tools/contract_drift.py — consumed at review time (a
  fable-judge step), NOT a doctor row (needs a diff context the doctor
  does not have).
- materiality(changed_paths: list[str]) -> str — "high" / "medium" /
  "low":
    high:   .github/workflows/*, scripts/install.py, pyproject/dep
            files, test-framework files (tests/conftest.py,
            pytest.ini, tests/_util*), major restructures (VERSION,
            profile.yml, OPS.md, AGENTS.md, adapters/*,
            integrity-manifest.json, skills/*/SKILL.md);
    medium: lint rules (ruff.toml, .ruff.toml, setup.cfg,
            tox.ini); dep files are high, not medium;
    low:    everything else.
- needs_contract_review(paths: list[str]) -> bool — True iff the diff
  touches high-materiality files. Path detection points at a possible
  contract review; it cannot prove coverage, so a contract document
  (AGENTS.md, OPS.md, CONTRIBUTING.md, README.md,
  docs/SECURITY-MAP.md, docs/CHANGELOG.md) in the same diff does NOT
  clear the pointer.
- CLI exits 0 for valid input regardless of tier; malformed input
  still fails loudly.

Behavior only: no source-text/wording pins of the docs or skills that
describe this helper.

Run: python -m pytest tests/test_contract_drift.py -v
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts" / "tools"))

import contract_drift

SCRIPT = KIT / "scripts" / "tools" / "contract_drift.py"


class MaterialityTest(unittest.TestCase):
    # --- high tier ---
    def test_workflow_files_high(self):
        self.assertEqual(
            contract_drift.materiality([".github/workflows/ci.yml"]), "high")

    def test_install_script_high(self):
        self.assertEqual(
            contract_drift.materiality(["scripts/install.py"]), "high")

    def test_pyproject_and_deps_high(self):
        for p in ("pyproject.toml", "setup.py", "requirements.txt"):
            with self.subTest(path=p):
                self.assertEqual(contract_drift.materiality([p]), "high")

    def test_test_framework_files_high(self):
        for p in ("tests/conftest.py", "pytest.ini", "tests/_util.py",
                  "eval/task_runner.py", "eval/runner.py"):
            with self.subTest(path=p):
                self.assertEqual(
                    contract_drift.materiality([p]), "high",
                    f"{p} is test-framework infrastructure")

    def test_major_restructure_high(self):
        for p in ("VERSION", "profile.yml", "OPS.md", "AGENTS.md",
                  "adapters/UNIVERSAL.md", "integrity-manifest.json",
                  "skills/fable-judge/SKILL.md"):
            with self.subTest(path=p):
                self.assertEqual(contract_drift.materiality([p]), "high")

    # --- medium tier ---
    def test_lint_rules_medium(self):
        for p in ("ruff.toml", ".ruff.toml", "tox.ini"):
            with self.subTest(path=p):
                self.assertEqual(contract_drift.materiality([p]), "medium")

    # --- low tier ---
    def test_regular_code_low(self):
        self.assertEqual(
            contract_drift.materiality(["src/app.py", "README.md"]), "low")

    def test_empty_diff_low(self):
        self.assertEqual(contract_drift.materiality([]), "low")

    def test_blank_entries_ignored(self):
        self.assertEqual(contract_drift.materiality(["", "  ", "./"]), "low")

    def test_high_wins_over_low(self):
        self.assertEqual(
            contract_drift.materiality(["README.md", "VERSION"]), "high")
        self.assertEqual(
            contract_drift.materiality(["src/app.py", "ruff.toml"]),
            "medium")

    def test_backslash_paths_normalized(self):
        self.assertEqual(
            contract_drift.materiality(["scripts\\install.py"]), "high")


class NeedsContractReviewTest(unittest.TestCase):
    """Path detection points at a contract review; contract-doc presence
    is not semantic proof, so it never clears the pointer."""

    CONTRACT_FILES = ("AGENTS.md", "OPS.md", "CONTRIBUTING.md",
                      "README.md", "docs/SECURITY-MAP.md",
                      "docs/CHANGELOG.md")

    def test_high_flags_review(self):
        for paths in ([".github/workflows/ci.yml", "src/app.py"],
                      ["scripts/install.py"],
                      ["skills\\fable-judge\\SKILL.md", "src/app.py"]):
            with self.subTest(paths=paths):
                self.assertTrue(contract_drift.needs_contract_review(paths))

    def test_contract_doc_does_not_clear_flag(self):
        for cf in self.CONTRACT_FILES:
            with self.subTest(contract=cf):
                self.assertTrue(contract_drift.needs_contract_review(
                    ["scripts/install.py", cf]))

    def test_medium_low_never_flags(self):
        for paths in (["ruff.toml", "src/app.py"], [], [""]):
            with self.subTest(paths=paths):
                self.assertFalse(contract_drift.needs_contract_review(paths))



class CliAdvisoryTest(unittest.TestCase):
    """The CLI is advisory for valid input and still fails on malformed input."""

    def _run(self, arg):
        return subprocess.run(
            [sys.executable, str(SCRIPT), arg],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120)

    def test_high_materiality_exits_zero(self):
        proc = self._run(json.dumps(
            [".github/workflows/ci.yml", "README.md"]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("HIGH", proc.stdout)
        self.assertIn(".github/workflows/ci.yml", proc.stdout)

    def test_low_materiality_exits_zero(self):
        proc = self._run(json.dumps(["src/app.py"]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("low", proc.stdout)

    def test_no_paths_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("low", proc.stdout)

    def test_malformed_input_fails(self):
        for raw in ('[not json', '"VERSION"', '{}', 'null', 'true', '7',
                    '["VERSION", null]', '[false]', '[{}]', '[["VERSION"]]'):
            with self.subTest(raw=raw):
                proc = self._run(raw)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertEqual(proc.stdout, "")
                self.assertTrue(proc.stderr.strip())
                self.assertNotIn("Traceback", proc.stderr)

    def test_extra_argument_fails_instead_of_ignoring_paths(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), '[]', '["VERSION"]'],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertTrue(proc.stderr.strip())

    def test_empty_array_is_valid(self):
        proc = self._run('[]')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("low", proc.stdout)


if __name__ == "__main__":
    unittest.main()
