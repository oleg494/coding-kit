import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class TestAdaptiveRigorCandidate(unittest.TestCase):
    def test_superpowers_declares_tiers(self):
        text = (ROOT / "skills" / "superpowers" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("FAST", text)
        self.assertIn("STANDARD", text)
        self.assertIn("HIGH ASSURANCE", text)
        self.assertIn("no observable runtime behavior change", text)

    def test_agents_declares_adaptive_routing(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("FAST", text)
        self.assertIn("STANDARD", text)
        self.assertIn("HIGH ASSURANCE", text)

    def test_ops_retires_universal_split(self):
        text = (ROOT / "OPS.md").read_text(encoding="utf-8")
        self.assertIn("FAST", text)
        self.assertIn("STANDARD", text)
        self.assertIn("HIGH ASSURANCE", text)
        self.assertNotIn(">3 files → split into atomic tasks", text)
