#!/usr/bin/env python3
"""usage_audit.py contract tests.

Fixtures write both transcript formats (Claude Code ~/.claude/projects and
omp ~/.omp/agent/sessions) into a temp tree and pin segregation of
kit-internal vs real sessions plus the per-session counters (human turns,
memory-engine Bash calls, skill:// reads, OPS-in-context markers).
"""
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "usage_audit", KIT / "scripts" / "tools" / "usage_audit.py")
usage_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage_audit)


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


class FixtureBuilders:
    """Reusable line builders for the two transcript formats."""

    @staticmethod
    def claude_user(text, cwd="C:\\Users\\oleg2\\Desktop\\WORK\\mp-agent"):
        return {"type": "user", "cwd": cwd, "timestamp": "2026-08-20T10:00:00Z",
                "message": {"role": "user", "content": text}}

    @staticmethod
    def claude_tool_result(content):
        return {"type": "user", "cwd": "C:\\x", "timestamp": "2026-08-20T10:00:01Z",
                "message": {"role": "user",
                            "content": [{"type": "tool_result",
                                         "content": content}]}}

    @staticmethod
    def claude_assistant(tools=(), text=None):
        blocks = []
        if text:
            blocks.append({"type": "text", "text": text})
        for name, inp in tools:
            blocks.append({"type": "tool_use", "id": "t1", "name": name,
                           "input": inp})
        return {"type": "assistant", "timestamp": "2026-08-20T10:00:02Z",
                "message": {"role": "assistant", "content": blocks}}

    @staticmethod
    def omp_session(cwd="C:/Users/oleg2/Desktop/WORK/mp-agent", title="mp"):
        return {"type": "session", "cwd": cwd, "title": title,
                "timestamp": "2026-08-20T10:00:00Z"}

    @staticmethod
    def omp_message(role, text):
        return {"type": "message", "timestamp": "2026-08-20T10:00:01Z",
                "message": {"role": role,
                            "content": [{"type": "text", "text": text}]}}

    @staticmethod
    def omp_tool_call(tool, args, id="c1"):
        return {"type": "message", "timestamp": "2026-08-20T10:00:02Z",
                "message": {"role": "assistant",
                            "content": [{"type": "toolCall", "id": id,
                                         "name": tool, "arguments": args}]}}

    @staticmethod
    def omp_tool_start(tool, args, id="c1"):
        return {"type": "custom", "customType": "tool_execution_start",
                "timestamp": "2026-08-20T10:00:03Z",
                "data": {"toolCallId": id, "toolName": tool, "args": args}}


class ClaudeFormatTest(unittest.TestCase, FixtureBuilders):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _audit(self):
        return usage_audit.audit(claude_root=self.tmp / "claude",
                                 omp_root=self.tmp / "omp", since=None)

    def test_real_session_counts(self):
        """Real session: 2 human turns, 3 memory calls, 1 skill, 2 OPS
        marks (db-tools/search_all from the command + Coding Agent OS)."""
        rows = [
            self.claude_user("почини поиск в mp-agent"),
            self.claude_assistant(tools=[
                ("Bash", {"command": 'python C:/Users/oleg2/.memory/db-tools/search_all.py "mp-agent"'}),
                ("Read", {"path": "skill://memory"}),
            ]),
            self.claude_tool_result("found 3 rows"),
            self.claude_user("теперь добавь вывод в findings.py"),
            self.claude_assistant(tools=[
                ("Bash", {"command": "python C:/Users/oleg2/.memory/db-tools/findings.py add mp --text x"}),
                ("Bash", {"command": "python C:/Users/oleg2/.memory/scripts/memory-warmup.py"}),
            ]),
            self.claude_assistant(text="Done. Follows OPS.md (Coding Agent OS) rules."),
        ]
        _write_jsonl(self.tmp / "claude" / "C--Users-oleg2-Desktop-WORK-mp-agent"
                     / "s1.jsonl", rows)
        res = self._audit()
        self.assertEqual(len(res["sessions"]), 1)
        s = res["sessions"][0]
        self.assertEqual(s["source"], "claude")
        self.assertFalse(s["kit_internal"])
        self.assertEqual(s["human_turns"], 2)
        self.assertEqual(s["memory_calls"], 3)
        self.assertEqual(s["skill_reads"], ["memory"])
        self.assertEqual(s["ops_markers"], 2)

    def test_kit_internal_by_slug(self):
        rows = [
            self.claude_user(
                "kit-eval task", cwd="C:\\Users\\oleg2\\AppData\\Local"
                                    "\\Temp\\kit-eval-ab12cd"),
            self.claude_assistant(tools=[
                ("Bash", {"command": "python memory-warmup.py"}),
            ]),
        ]
        _write_jsonl(self.tmp / "claude" / "C--Users-oleg2-AppData-Local-Temp-"
                     "kit-eval-ab12cd" / "s2.jsonl", rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertTrue(s["kit_internal"])
        self.assertEqual(s["memory_calls"], 1)

    def test_kit_internal_by_first_human_turn(self):
        rows = [
            self.claude_user("напомни про код кит: что мы решили?"),
            self.claude_assistant(tools=[]),
        ]
        _write_jsonl(self.tmp / "claude" / "C--Users-oleg2" / "s3.jsonl", rows)
        res = self._audit()
        self.assertTrue(res["sessions"][0]["kit_internal"])

    def test_tool_results_not_human_turns(self):
        rows = [
            self.claude_user("go"),
            self.claude_tool_result("<system-reminder>noise</system-reminder>"),
            self.claude_assistant(tools=[]),
        ]
        _write_jsonl(self.tmp / "claude" / "C--Users-oleg2-Desktop-WORK-x"
                     / "s4.jsonl", rows)
        res = self._audit()
        self.assertEqual(res["sessions"][0]["human_turns"], 1)


class OmpFormatTest(unittest.TestCase, FixtureBuilders):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _audit(self):
        return usage_audit.audit(claude_root=self.tmp / "claude",
                                 omp_root=self.tmp / "omp", since=None)

    def test_real_session_counts_toolcall_and_start(self):
        """toolCall blocks AND tool_execution_start events both count; the
        same call emitted in both forms (same toolCallId) counts once."""
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/oxtest",
                             title="oxtest search"),
            self.omp_message("user", "найди что мы знаем про oxtest"),
            self.omp_tool_call("bash",
                               {"command": "python search_all.py oxtest --substring"},
                               id="c1"),
            self.omp_tool_start("bash",
                                {"command": "python search_all.py oxtest --substring"},
                                id="c1"),
            self.omp_message("assistant", "see skill://memory and OPS (Execution Lock)"),
            self.omp_message("user", "ок, добавь в базу"),
            self.omp_tool_start("bash",
                                {"command": "python findings.py add ox --text y"},
                                id="c2"),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-oxtest" / "u1.jsonl", rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["source"], "omp")
        self.assertFalse(s["kit_internal"])
        self.assertEqual(s["human_turns"], 2)
        self.assertEqual(s["memory_calls"], 2)
        self.assertEqual(s["skill_reads"], [])
        self.assertEqual(s["ops_markers"], 1)

    def test_kit_internal_omp(self):
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/coding-kit",
                             title="kit work"),
            self.omp_message("user", "run check_file_sizes"),
            self.omp_tool_call("bash", {"command": "python check_file_sizes.py --ci"}),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-coding-kit" / "u2.jsonl", rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertTrue(s["kit_internal"])
        self.assertEqual(s["memory_calls"], 1)


class SkillReadEvidenceTest(unittest.TestCase, FixtureBuilders):
    def test_mentions_do_not_hide_unused_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rows = [
                self.claude_user("Please consider skill://user-mentioned"),
                self.claude_assistant(text="Used skill://claimed"),
                self.claude_assistant(tools=[
                    ("Read", {"path": "notes.txt", "i": "skill://intent"}),
                ]),
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1",
                     "content": "Available: skill://catalog-only"}]}},
                self.claude_assistant(tools=[
                    ("Write", {"path": "notes.txt", "content": "skill://written"}),
                    ("Bash", {"command": "echo skill://echoed"}),
                ]),
            ]
            _write_jsonl(root / "claude" / "project" / "s.jsonl", rows)
            result = usage_audit.audit(root / "claude", root / "omp", None)
            self.assertEqual(result["sessions"][0]["skill_reads"], [])
            report = usage_audit.retirement_report(
                result, ["claimed", "catalog-only"], skills_root=root)
            self.assertEqual(report["zero_use"], ["catalog-only", "claimed"])

    def test_explicit_read_targets_include_paths_and_parallel_calls(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rows = [self.omp_session(), self.omp_message("user", "Fix search")]
            targets = [
                ("read", {"path": "skill://superpowers"}),
                ("Read", {"file_path": "C:\\kit\\skills\\yagni\\SKILL.md"}),
                ("read_file", {"absolute_path": "/kit/skills/ponytail/SKILL.md"}),
                ("read", {"path": "skills/testing-discipline/SKILL.md:1-40"}),
                ("read", {"path": "skill://superpowers:1-20"}),
                ("multi_tool_use.parallel", {"tool_uses": [
                    {"recipient_name": "functions.read", "parameters": {
                        "path": "skill://fable-judge"}},
                    {"recipient_name": "functions.write", "parameters": {
                        "path": "notes.txt", "content": "skill://not-read"}},
                ]}),
            ]
            rows.extend(self.omp_tool_call(name, args, id=f"c{i}")
                        for i, (name, args) in enumerate(targets))
            _write_jsonl(root / "omp" / "project" / "s.jsonl", rows)
            result = usage_audit.audit(root / "claude", root / "omp", None)
            self.assertEqual(result["sessions"][0]["skill_reads"], [
                "fable-judge", "ponytail", "superpowers", "testing-discipline",
                "yagni"])


class AggregationTest(unittest.TestCase, FixtureBuilders):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_aggregates_and_json_shape(self):
        _write_jsonl(
            self.tmp / "claude" / "C--Users-oleg2-Desktop-coding-kit" / "a.jsonl",
            [self.claude_user("x", cwd="C:\\Users\\oleg2\\Desktop\\coding-kit"),
             self.claude_assistant(tools=[("Bash", {"command": "doctor.py"})])])
        _write_jsonl(
            self.tmp / "omp" / "-Desktop-WORK-realproj" / "b.jsonl",
            [self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/realproj"),
             self.omp_message("user", "y"),
             self.omp_tool_call("bash", {"command": "memory-warmup.py"})])
        res = usage_audit.audit(claude_root=self.tmp / "claude",
                                omp_root=self.tmp / "omp", since=None)
        agg = res["aggregate"]
        self.assertEqual(agg["kit_internal"]["sessions"], 1)
        self.assertEqual(agg["kit_internal"]["memory_calls"], 1)
        self.assertEqual(agg["real"]["sessions"], 1)
        self.assertEqual(agg["real"]["memory_calls"], 1)
        self.assertEqual(agg["real"]["human_turns"], 1)
        # machine shape: stable keys
        for key in ("generated", "since", "roots", "sessions", "aggregate"):
            self.assertIn(key, res)

    def test_since_filters_old_sessions(self):
        p = self.tmp / "claude" / "C--Users-oleg2-Desktop-WORK-old" / "old.jsonl"
        _write_jsonl(p, [self.claude_user("old task")])
        old = 1_000_000_000  # 2001-09-09, always older than --since 2026-01-01
        os.utime(p, (old, old))
        res = usage_audit.audit(claude_root=self.tmp / "claude",
                                omp_root=self.tmp / "omp",
                                since=date(2026, 1, 1))
        self.assertEqual(res["sessions"], [])


if __name__ == "__main__":
    unittest.main()
