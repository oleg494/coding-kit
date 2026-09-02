#!/usr/bin/env python3
"""Wave 5 v3.9.0 Task 17: AGENTS.md contract materiality gate.

Contract:
- scripts/tools/contract_drift.py — consumed at review time (a
  fable-judge step), NOT a doctor row (needs a diff context the doctor
  does not have).
- materiality(changed_paths: list[str]) -> str — "high" / "medium" /
  "low":
    high:   .github/workflows/*, scripts/install.py, pyproject/dep
            files, test-framework files (tests/conftest.py,
            pytest.ini, tests/_util*), major restructures (VERSION,
            profile.yml, OPS.md, AGENTS.md, adapters/*,
            integrity-manifest.json);
    medium: lint rules (ruff.toml, .ruff.toml, setup.cfg,
            tox.ini), big dep bumps (requirements*.txt, Pipfile,
            poetry.lock);
    low:    everything else.
- needs_contract_update(paths: list[str]) -> bool — True iff the diff
  touches high-materiality files WITHOUT any contract document
  (AGENTS.md, OPS.md, CONTRIBUTING.md, README.md,
  docs/SECURITY-MAP.md, docs/CHANGELOG.md) in the same diff.
- CONTRIBUTING.md gains one paragraph naming the gate.
- fable-judge gains a "contract drift?" step.

Run: python -m pytest tests/test_contract_drift.py -v
"""
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts" / "tools"))

import contract_drift

CONTRIBUTING = KIT / "CONTRIBUTING.md"

FABLE = KIT / "skills" / "fable-judge" / "SKILL.md"


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
                  "adapters/UNIVERSAL.md", "integrity-manifest.json"):
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

    def test_high_wins_over_low(self):
        self.assertEqual(
            contract_drift.materiality(["README.md", "VERSION"]), "high")
        self.assertEqual(
            contract_drift.materiality(["src/app.py", "ruff.toml"]),
            "medium")

    def test_backslash_paths_normalized(self):
        self.assertEqual(
            contract_drift.materiality(["scripts\\install.py"]), "high")


class NeedsContractUpdateTest(unittest.TestCase):
    """High without contract docs in the same diff -> True."""

    CONTRACT_FILES = ("AGENTS.md", "OPS.md", "CONTRIBUTING.md",
                      "README.md", "docs/SECURITY-MAP.md",
                      "docs/CHANGELOG.md")

    def test_high_without_contract_true(self):
        self.assertTrue(contract_drift.needs_contract_update(
            [".github/workflows/ci.yml", "src/app.py"]))

    def test_high_with_contract_false(self):
        for cf in self.CONTRACT_FILES:
            with self.subTest(contract=cf):
                self.assertFalse(contract_drift.needs_contract_update(
                    ["scripts/install.py", cf]))

    def test_medium_low_never_flags(self):
        self.assertFalse(contract_drift.needs_contract_update(
            ["ruff.toml", "src/app.py"]))
        self.assertFalse(contract_drift.needs_contract_update([]))

    def test_summary_names_tier_and_files(self):
        """Review-facing helper: a human-readable summary of the gate."""
        text = contract_drift.summarize(
            [".github/workflows/ci.yml", "ruff.toml", "src/app.py"])
        self.assertIn("HIGH", text)
        self.assertIn(".github/workflows/ci.yml", text)
        self.assertIn("AGENTS.md", text)
        low = contract_drift.summarize(["src/app.py"]).lower()
        self.assertIn("no gate", low)


class ContributingContractPathTest(unittest.TestCase):
    """Regression (v4.0.2): the contract-document path is root
    CONTRIBUTING.md. The gate listed docs/CONTRIBUTING.md, which does
    not exist in the kit, so an update to the real contract file did
    not satisfy the gate."""

    def test_contributing_lives_at_root_only(self):
        self.assertTrue(CONTRIBUTING.is_file(),
                        "CONTRIBUTING.md must exist at the repo root")
        self.assertFalse((KIT / "docs" / "CONTRIBUTING.md").exists(),
                         "docs/CONTRIBUTING.md must not exist")

    def test_root_contributing_satisfies_gate(self):
        self.assertFalse(contract_drift.needs_contract_update(
            [".github/workflows/ci.yml", "CONTRIBUTING.md"]))

    def test_stale_docs_path_dropped(self):
        self.assertNotIn("docs/contributing.md",
                         contract_drift._CONTRACT_FILES,
                         "the nonexistent docs/ path must leave the gate")


class FableJudgeStepTest(unittest.TestCase):
    """fable-judge gains the 'contract drift?' step."""

    def test_contract_drift_step_present(self):
        text = FABLE.read_text(encoding="utf-8")
        self.assertIn("contract drift", text.lower(),
                      "fable-judge must carry the materiality step")
        self.assertIn("contract_drift", text,
                      "the step must name the module")

    def test_step_names_materiality(self):
        text = FABLE.read_text(encoding="utf-8")
        self.assertIn("materiality", text.lower())


class ContributingParagraphTest(unittest.TestCase):
    def test_contributing_names_the_gate(self):
        text = CONTRIBUTING.read_text(encoding="utf-8")
        self.assertIn("contract_drift", text,
                      "CONTRIBUTING must document the materiality gate")
        self.assertIn("materiality", text.lower())
        self.assertIn("AGENTS.md", text,
                      "the paragraph must say which contract to update")

    def test_doctor_check_count_agnostic(self):
        text = CONTRIBUTING.read_text(encoding="utf-8")
        self.assertNotIn("# 9 checks", text,
                         "the check count drifts; say 'all checks'")
        self.assertIn("# all checks", text)


if __name__ == "__main__":
    unittest.main()
