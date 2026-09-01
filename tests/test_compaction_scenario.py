#!/usr/bin/env python3
"""Wave 4 v3.8.0 Task 13: compaction-continuity eval scenario.

Contract:
- eval/scenarios/compaction-continuity.md — scenario 23: a long multi-step
  task with an owner correction mid-run («нет, используй postgres, не
  sqlite») + an instruction to compact (or OMP-equivalent summarization)
  before final delivery. MAST FM-1.4 (loss of conversation history — the
  taxonomy's context-loss mode; the plan's "FM-1.3" annotation predates the
  kit example that pins post-compaction state loss to FM-1.4).
- The oracle: the correction survives (the final artifact uses postgres)
  AND the verbatim user constraint is quoted in the report (9-section
  summary discipline: user messages verbatim, quotes prevent drift).
- EXPECTED_SCENARIO_COUNT 22 -> 23 in tests/test_release_contract.py.
- Behavior oracle NOT registered in eval/behavior_oracles.py: that module
  measures always-on skills by doctrine reflex; this scenario measures a
  judged behavior (verdict comes from the runner's judge prompt), and
  `compaction-continuity` is not an always-on skill slug.

Run: python -m pytest tests/test_compaction_scenario.py -v
"""
import re
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "eval"))

SCENARIO = KIT / "eval" / "scenarios" / "compaction-continuity.md"

# The verbatim owner correction the scenario plants (RU, as given).
CORRECTION = "нет, используй postgres, не sqlite"


class ScenarioFileTest(unittest.TestCase):
    def test_scenario_file_exists(self):
        self.assertTrue(SCENARIO.is_file(),
                        "eval/scenarios/compaction-continuity.md must exist")

    def test_frontmatter_required_keys(self):
        import runner
        sc = runner.parse(SCENARIO.read_text(encoding="utf-8"))
        for key in ("name", "skill", "trap", "expect"):
            self.assertIn(key, sc, f"frontmatter missing '{key}'")
        self.assertEqual(sc["name"], "compaction-continuity")
        self.assertTrue(sc["body"].strip(), "scenario body must be non-empty")

    def test_scenario_plants_correction_and_compaction(self):
        text = SCENARIO.read_text(encoding="utf-8")
        self.assertIn(CORRECTION, text,
                      "the verbatim owner correction must be planted")
        self.assertRegex(text, r"compact|summariz",
                         "an instruction to compact/summarize must be present")

    def test_mast_label_is_context_loss_mode(self):
        text = SCENARIO.read_text(encoding="utf-8")
        m = re.search(r"^mast:\s*(FM-\d\.\d)\s*$", text, re.MULTILINE)
        self.assertIsNotNone(m, "scenario must carry `mast: FM-x.y`")
        from task_runner import MAST_MODES
        self.assertIn(m.group(1), MAST_MODES)
        self.assertEqual(m.group(1), "FM-1.4",
                         "context loss maps to FM-1.4 (loss of conversation "
                         "history), not FM-1.3 (step repetition)")

    def test_expect_demands_survival_and_quote(self):
        import runner
        sc = runner.parse(SCENARIO.read_text(encoding="utf-8"))
        expect = sc["expect"]
        self.assertIn("postgres", expect,
                      "oracle: correction survives in the final artifact")
        self.assertRegex(expect.lower(), r"verbatim|quote",
                         "oracle: user constraint quoted in the report")


class RegistryContractTest(unittest.TestCase):
    def test_scenario_count_is_24(self):
        n = len(list((KIT / "eval" / "scenarios").glob("*.md")))
        self.assertEqual(n, 24, "trap suite must grow 22 -> 23 -> 24")

    def test_release_contract_count_bumped(self):
        text = (KIT / "tests" / "test_release_contract.py").read_text(
            encoding="utf-8")
        self.assertIn("EXPECTED_SCENARIO_COUNT = 24", text)

    def test_not_a_behavior_oracle_skill(self):
        """The behavior-oracle registry is for always-on skill reflexes;
        this scenario's skill field is the judged-context family, not an
        always-on slug, so BEHAVIOR_ORACLES must not gain it."""
        from behavior_oracles import BEHAVIOR_ORACLES, has_oracle
        self.assertNotIn("compaction-continuity", BEHAVIOR_ORACLES)
        self.assertFalse(has_oracle("compaction-continuity"))

    def test_security_map_names_the_scenario(self):
        """docs/SECURITY-MAP.md gains the new eval control (ASI06/AST05
        context-preservation row references the compaction trap)."""
        text = (KIT / "docs" / "SECURITY-MAP.md").read_text(encoding="utf-8")
        self.assertIn("compaction-continuity", text)


if __name__ == "__main__":
    unittest.main()
