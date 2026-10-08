#!/usr/bin/env python3
"""Supply-chain license diagnostics remain warnings, not deployment blockers."""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "doctor", KIT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(doctor)




_SKILL_A = """---
name: skill-a
description: has license metadata
license: MIT
---

# skill-a
"""

_SKILL_B = """---
name: skill-b
description: lacks license metadata
---

# skill-b
"""


class SupplyChainWarnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-secmap-"))
        self._orig_kit = doctor.KIT
        doctor.KIT = self.tmp

    def tearDown(self):
        doctor.KIT = self._orig_kit
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _skill(self, name, body):
        d = self.tmp / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")
        # v4.7.0: fixture skills must be declared in the kit inventory
        self._declare(name)

    def _declare(self, name):
        known = set()
        mf = self.tmp / "profile.yml"
        if mf.is_file():
            for line in mf.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s.startswith("- "):
                    known.add(s[2:].strip())
        known.add(name)
        entries = "\n".join(f"    - {s}" for s in sorted(known))
        mf.write_text(
            "skills:\n  always_on:\n" + entries + "\n  domain: []\n",
            encoding="utf-8", newline="\n")

    def test_doctor_flags_skills_without_license_or_hash(self):
        self._skill("skill-a", _SKILL_A)
        self._skill("skill-b", _SKILL_B)
        ok, detail = doctor.check_skill_supply_chain()
        self.assertTrue(ok, "WARN tier must not fail the doctor (ok=True)")
        self.assertIn("WARN", detail)
        self.assertIn("skill-b", detail)

    def test_all_licensed_is_clean(self):
        self._skill("skill-a", _SKILL_A)
        ok, detail = doctor.check_skill_supply_chain()
        self.assertTrue(ok)
        self.assertNotIn("WARN", detail)

    def test_warn_tier_on_real_tree(self):
        (self.tmp / "skills").mkdir()
        # v4.7.0: an empty tree still needs a (valid, empty-ish) inventory;
        # declare a nonexistent slug — the check tolerates missing dirs
        (self.tmp / "profile.yml").write_text(
            "skills:\n  always_on:\n    - placeholder\n  domain: []\n",
            encoding="utf-8", newline="\n")
        ok, _detail = doctor.check_skill_supply_chain()
        self.assertTrue(ok, "WARN tier never fails, even on an empty tree")


if __name__ == "__main__":
    unittest.main()
