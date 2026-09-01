#!/usr/bin/env python3
"""Skill lifecycle: metadata.version + zero-use retirement report
(wave3 Task 11).

Contract:
- Every SKILL.md carries metadata.version (semver-ish, stamped 3.7.0 at
  adoption; doctor WARNs — WARN tier, not FAIL — when a skill lacks it).
- usage_audit.py --retirement-report --since D lists skills with 0 firings
  across the audited sessions as a findings-style proposal (never
  auto-deletes — owner decision, v3.4.6 precedent). Skills whose eval
  queries exist but never appear in any transcript skill:// read count as
  zero-use; kit-internal sessions are excluded from the firings count.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parents[1]

doctor_spec = importlib.util.spec_from_file_location(
    "doctor", KIT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(doctor_spec)
doctor_spec.loader.exec_module(doctor)

audit_spec = importlib.util.spec_from_file_location(
    "usage_audit", KIT / "scripts" / "tools" / "usage_audit.py")
usage_audit = importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(usage_audit)


def write_skill(root: Path, slug: str, fm_extra: str = "") -> None:
    d = root / "skills" / slug
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: 'x'\n{fm_extra}---\n",
        encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


class DoctorVersionWarnTest(unittest.TestCase):
    def test_version_missing_warns_not_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_skill(root, "no-version")
            write_skill(root, "has-version",
                        'metadata:\n  version: "3.7.0"\n')
            with mock.patch.object(doctor, "KIT", root):
                ok, detail = doctor.check_frontmatter_spec()
        self.assertTrue(ok, detail)
        self.assertIn("no-version", detail)
        self.assertNotIn("has-version", detail)

    def test_all_real_skills_have_version(self):
        ok, detail = doctor.check_frontmatter_spec()
        self.assertTrue(ok, detail)
        self.assertNotIn("metadata.version", detail)


class RetirementReportTest(unittest.TestCase):
    def _audit(self, tmp: Path):
        rows = [
            {"type": "user", "cwd": "C:\\WORK\\proj",
             "message": {"role": "user", "content": "do things"}},
            {"type": "assistant", "message": {"role": "assistant",
             "content": [{"type": "tool_use", "id": "t1", "name": "Read",
                          "input": {"path": "skill://superpowers"}}]}},
            {"type": "assistant", "message": {"role": "assistant",
             "content": [{"type": "tool_use", "id": "t2", "name": "Read",
                          "input": {"path": "skill://yagni"}}]}},
        ]
        write_jsonl(tmp / "claude" / "proj" / "s1.jsonl", rows)
        return usage_audit.audit(
            claude_root=tmp / "claude", omp_root=tmp / "omp", since=None)

    def test_zero_use_skills_listed_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            res = self._audit(tmp)
            report = usage_audit.retirement_report(
                res, all_skills=["superpowers", "yagni", "ponytail",
                                 "fable-judge"])
        self.assertEqual(report["zero_use"], ["fable-judge", "ponytail"])

    def test_report_shape_is_proposal_not_action(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            res = self._audit(tmp)
            report = usage_audit.retirement_report(
                res, all_skills=["superpowers", "yagni", "ponytail"])
        self.assertEqual(report["action"], "proposal-only")
        self.assertIn("count", report)

    def test_kit_internal_sessions_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rows = [
                {"type": "user", "cwd": "C:\\Temp\\kit-eval-ab12",
                 "message": {"role": "user", "content": "kit eval"}},
                {"type": "assistant", "message": {"role": "assistant",
                 "content": [{"type": "tool_use", "id": "t1", "name": "Read",
                              "input": {"path": "skill://ponytail"}}]}},
            ]
            write_jsonl(tmp / "claude" / "kit" / "s1.jsonl", rows)
            res = usage_audit.audit(
                claude_root=tmp / "claude", omp_root=tmp / "omp", since=None)
            report = usage_audit.retirement_report(
                res, all_skills=["ponytail"])
        self.assertEqual(report["zero_use"], ["ponytail"])

    def test_human_report_names_skills(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            res = self._audit(tmp)
            report = usage_audit.retirement_report(
                res, all_skills=["superpowers", "yagni", "ponytail"])
            text = usage_audit.retirement_report_human(report)
        self.assertIn("ponytail", text)
        self.assertIn("proposal", text.lower())

    def test_cli_flag_exists(self):
        r = subprocess.run(
            [sys.executable, str(KIT / "scripts" / "tools" /
                                 "usage_audit.py"), "--help"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=True)
        self.assertIn("--retirement-report", r.stdout)


class StampedCorpusTest(unittest.TestCase):
    # Since v4.0.0 the WHOLE corpus is restamped at every release
    # boundary (parent integrator) — one kit version, one skill version.
    def test_all_36_skills_stamped(self):
        import re
        stamped = 0
        for md in sorted(KIT.glob("skills/*/SKILL.md")):
            fm = md.read_text(encoding="utf-8").split("---")[1]
            m = re.search(r"^metadata:\s*\n(?:\s+.*)*?^\s+version:\s*"
                          r"\"?([0-9.]+)\"?", fm, re.MULTILINE)
            slug = md.parent.name
            self.assertIsNotNone(m, f"{slug}: no metadata.version")
            self.assertEqual(m.group(1), "4.0.0",
                             f"{slug}: expected 4.0.0")
            stamped += 1
        self.assertEqual(stamped, 36)


if __name__ == "__main__":
    unittest.main()
