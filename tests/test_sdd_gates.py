#!/usr/bin/env python3
"""Wave 5 v3.9.0 Task 15: spec-kit SDD gates into the superpowers cycle.

Contract:
- Three contract rules bind the superpowers cycle —
  (a) clarify-before-plan: <=5 targeted questions folded back into the
      spec BEFORE any plan exists (home: skills/brainstorming/SKILL.md);
  (b) checklist sovereignty: reviewer-owned `- [ ]` markers — the
      implementer NEVER toggles one; counts unchecked and asks;
  (c) converge pass: strictly append-only anti-false-done audit; its
      ONLY write is ADDING missed work to the task list, severity-graded.
  Surfaces: skills/superpowers/SKILL.md (method anchor) + OPS.md §3
  (condensed) + skills/brainstorming/SKILL.md (gate (a)).
- Trap scenario 24: eval/scenarios/converge-audit.md — oracle: the
  false-done claim must be caught by the converge pass; mast: FM-3.1
  (premature termination).
- EXPECTED_SCENARIO_COUNT 23 -> 24 in tests/test_release_contract.py
  and the wave4 per-wave pins (test_compaction_scenario,
  test_memory_provenance).
- Touched skills restamped 3.9.0 (test_skill_lifecycle pins the corpus).

Run: python -m pytest tests/test_sdd_gates.py -v
"""
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "eval"))

SUPER = KIT / "skills" / "superpowers" / "SKILL.md"
BRAIN = KIT / "skills" / "brainstorming" / "SKILL.md"
OPS = KIT / "OPS.md"
SCENARIO = KIT / "eval" / "scenarios" / "converge-audit.md"


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


class SuperpowersGatesTest(unittest.TestCase):
    """Gate rules (a)-(c) present in the method anchor skill."""

    NEEDLES = (
        "clarify before plan", "5 targeted questions",
        "before any plan exists",
        "checklist sovereignty", "reviewer-owned", "never toggles",
        "converge pass", "append-only", "adding missed work",
        "severity-graded",
    )

    def test_three_gates_present_in_superpowers_skill(self):
        hay = _norm(SUPER.read_text(encoding="utf-8"))
        for needle in self.NEEDLES:
            self.assertIn(needle, hay,
                          f"skills/superpowers/SKILL.md missing gate: {needle}")

    def test_gates_are_contract_rules_not_advice(self):
        hay = _norm(SUPER.read_text(encoding="utf-8"))
        self.assertIn("contract rules", hay,
                      "the gates must be framed as contract rules")


class OpsSection3GatesTest(unittest.TestCase):
    """OPS.md §3 carries the condensed gate block (always-loaded core)."""

    NEEDLES = (
        "clarify before plan", "5 targeted questions",
        "checklist sovereignty", "reviewer-owned",
        "converge pass", "append-only", "severity-graded",
    )

    def test_section3_carries_condensed_gates(self):
        text = OPS.read_text(encoding="utf-8")
        self.assertIn("## 3.", text)
        sec3 = text.split("## 3.")[1].split("## 4.")[0]
        hay = _norm(sec3)
        for needle in self.NEEDLES:
            self.assertIn(needle, hay, f"OPS.md §3 missing gate: {needle}")

    def test_banner_names_trap_suite_24(self):
        text = OPS.read_text(encoding="utf-8")
        self.assertIn("trap-suite 24", text,
                      "OPS banner must track the trap-suite size")


class BrainstormingClarifyGateTest(unittest.TestCase):
    """Gate (a) lives in brainstorming: questions die before the plan."""

    NEEDLES = (
        "clarify-before-plan gate", "5 targeted",
        "fold every answer back into the spec",
        "before any plan exists",
    )

    def test_clarify_gate_present(self):
        hay = _norm(BRAIN.read_text(encoding="utf-8"))
        for needle in self.NEEDLES:
            self.assertIn(needle, hay,
                          f"skills/brainstorming/SKILL.md missing: {needle}")


class ConvergeAuditScenarioTest(unittest.TestCase):
    """Trap scenario 24: the converge pass must catch a false-done claim."""

    def test_scenario_exists_and_parses(self):
        import runner
        self.assertTrue(SCENARIO.is_file(),
                        "eval/scenarios/converge-audit.md must exist")
        sc = runner.parse(SCENARIO.read_text(encoding="utf-8"))
        for key in ("name", "skill", "trap", "expect"):
            self.assertIn(key, sc, f"frontmatter missing '{key}'")
        self.assertEqual(sc["name"], "converge-audit")
        self.assertEqual(sc["skill"], "superpowers")
        self.assertTrue(sc["body"].strip(), "scenario body must be non-empty")

    def test_mast_label_is_premature_termination(self):
        import runner
        from task_runner import MAST_MODES
        sc = runner.parse(SCENARIO.read_text(encoding="utf-8"))
        self.assertEqual(sc.get("mast"), "FM-3.1",
                         "false-done-by-converge maps to FM-3.1")
        self.assertIn("FM-3.1", MAST_MODES)

    def test_oracle_demands_append_only_catch(self):
        import runner
        sc = runner.parse(SCENARIO.read_text(encoding="utf-8"))
        expect = _norm(sc["expect"])
        for needle in ("append-only", "severity", "done"):
            self.assertIn(needle, expect,
                          f"oracle (expect) must demand: {needle}")

    def test_body_plants_checklist_and_false_done_claim(self):
        import runner
        body = runner.parse(SCENARIO.read_text(encoding="utf-8"))["body"]
        self.assertIn("- [ ]", body,
                      "checklist sovereignty needs reviewer-owned markers")
        self.assertRegex(body, r"Done\.",
                         "a false-done claim must be planted")


class RegistryContractTest(unittest.TestCase):
    def test_scenario_count_is_24(self):
        n = len(list((KIT / "eval" / "scenarios").glob("*.md")))
        self.assertEqual(n, 24, "trap suite must grow 23 -> 24")

    def test_release_contract_count_bumped(self):
        text = (KIT / "tests" / "test_release_contract.py").read_text(
            encoding="utf-8")
        self.assertIn("EXPECTED_SCENARIO_COUNT = 24", text)

    def test_wave4_count_pins_bumped(self):
        """The wave4 per-wave count pins must move to 24, not stay stale."""
        for name in ("test_compaction_scenario.py",
                     "test_memory_provenance.py"):
            text = (KIT / "tests" / name).read_text(encoding="utf-8")
            self.assertNotIn("assertEqual(n, 23", text,
                             f"{name}: stale scenario-count pin")
            self.assertIn("assertEqual(n, 24", text,
                          f"{name}: count pin must move to 24")

    def test_security_map_names_the_scenario(self):
        text = (KIT / "docs" / "SECURITY-MAP.md").read_text(
            encoding="utf-8")
        self.assertIn("converge-audit", text,
                      "SECURITY-MAP must track the new eval control")


if __name__ == "__main__":
    unittest.main()
