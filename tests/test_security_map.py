#!/usr/bin/env python3
"""Wave 1 v3.5.0 trust-surface, Task 1: OWASP ASI/AST10 map contract.

- docs/SECURITY-MAP.md must exist and name a kit control for every ASI01-10
  and AST01-10 risk (a control = doctor check, trap scenario, OPS rule, or
  an explicit "harness-owned, N/A" admission).
- doctor.check_skill_supply_chain() must flag skills with inconsistent
  optional `license:` frontmatter at WARN tier (ok=True, FILE-SIZE soft-gate
  semantics): a hygiene seed for AST02, never a hard gate.
"""
import importlib.util
import re
import shutil
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
MAP_DOC = KIT / "docs" / "SECURITY-MAP.md"

EXPECTED_IDS = tuple(
    [f"ASI{n:02d}" for n in range(1, 11)] + [f"AST{n:02d}" for n in range(1, 11)]
)

# A control cell must name at least one recognized control kind.
_KIND_RE = re.compile(r"check_[a-z_]+|trap:|OPS|doctor|harness-owned|N/A")

# Load-bearing rows: id -> substring that must appear in its control cell.
SECURITY_MAP = {
    "ASI01": "trap19_refuse_disclaimer",
    "ASI04": "integrity",
    "ASI06": "memory-poisoning",
    "ASI10": "false-done",
    "AST01": "hash",
    "AST02": "check_skill_supply_chain",
    "AST05": "Memory trust",
    "AST06": "harness permission gates",
    "AST07": "integrity",
    "AST10": "check_engine_sync",
}

_spec = importlib.util.spec_from_file_location(
    "doctor", KIT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(doctor)


def _map_rows(text: str) -> dict:
    """Table rows keyed by risk id: {id: (title, control-cell)}."""
    rows = {}
    for line in text.splitlines():
        if not line.startswith(("| ASI", "| AST")):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 4 and re.fullmatch(r"(ASI|AST)\d{2}", cells[1]):
            rows[cells[1]] = (cells[2], cells[3])
    return rows


class SecurityMapExistsTest(unittest.TestCase):
    def test_security_map_exists_and_covers_asi(self):
        self.assertTrue(MAP_DOC.is_file(), "docs/SECURITY-MAP.md must exist")
        rows = _map_rows(MAP_DOC.read_text(encoding="utf-8"))
        for rid in EXPECTED_IDS:
            self.assertIn(rid, rows, f"SECURITY-MAP.md lacks a row for {rid}")
            control = rows[rid][1]
            self.assertTrue(
                _KIND_RE.search(control),
                f"{rid} control cell names no kit control: {control!r}")

    def test_security_map_names_kit_controls(self):
        rows = _map_rows(MAP_DOC.read_text(encoding="utf-8"))
        for rid, needle in SECURITY_MAP.items():
            self.assertIn(rid, rows)
            self.assertIn(needle, rows[rid][1],
                          f"{rid} row must map to {needle!r}")


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
        ok, _detail = doctor.check_skill_supply_chain()
        self.assertTrue(ok, "WARN tier never fails, even on an empty tree")


if __name__ == "__main__":
    unittest.main()
