#!/usr/bin/env python3
"""usage_audit.py contract tests.

Fixtures write both transcript formats (Claude Code ~/.claude/projects and
omp ~/.omp/agent/sessions) into a temp tree and pin segregation of
kit-internal vs real sessions plus the per-session counters (human turns,
memory-engine command entries, kit diagnostic calls, skills_search skill
discovery calls, skill:// reads, OPS-in-context markers). Regressions pin
the entry-based attribution: reads and echo mentions of entrypoints are
not executions, nested parallel wrappers are walked recursively, and
skills_search is reported separately from memory."""
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
                # echo strings mentioning entrypoints are not executions
                ("Bash", {"command": "echo 'ran search_all.py earlier'"}),
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

    def test_read_of_findings_and_echo_mention_do_not_count(self):
        """Reading findings.py with the read tool and echoing an
        entrypoint name are not memory executions; the actual python
        script call still counts."""
        rows = [
            self.claude_user("покажи что в findings"),
            self.claude_assistant(tools=[
                ("Read", {"path": "C:/Users/oleg2/.memory/db-tools/findings.py"}),
                ("Bash", {"command": "echo 'findings.py updated yesterday'"}),
                ("Grep", {"pattern": "search_all",
                          "path": "C:/Users/oleg2/.memory/db-tools"}),
                ("Bash", {"command": "python findings.py add z --text w"}),
            ]),
        ]
        _write_jsonl(self.tmp / "claude" / "C--Users-oleg2-Desktop-WORK-r"
                     / "s5.jsonl", rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["memory_calls"], 1)
        self.assertEqual(s["skill_search_calls"], 0)
        self.assertEqual(s["kit_diag_calls"], 0)


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
        self.assertEqual(s["memory_calls"], 0)
        self.assertEqual(s["kit_diag_calls"], 1)

    def test_unrelated_project_build_does_not_count_as_memory(self):
        """A real-project build.py with no memory marker is not a
        memory-engine call."""
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/other-app",
                             title="other app build"),
            self.omp_message("user", "rebuilt the project"),
            self.omp_tool_call("bash", {"command": "python build.py --full"}),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-other-app" / "u3.jsonl",
                     rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertFalse(s["kit_internal"])
        self.assertEqual(s["memory_calls"], 0)
        self.assertEqual(s["kit_diag_calls"], 0)

    def test_kit_diagnostics_do_not_inflate_memory_calls(self):
        """kit doctor.py / check_file_sizes go to kit_diag_calls, not
        memory_calls; skills_search is kit skill discovery with its own
        counter, not a memory call."""
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/proj",
                             title="proj diagnostics"),
            self.omp_message("user", "run diagnostics"),
            self.omp_tool_call("bash",
                               {"command": "python scripts/doctor.py"},
                               id="d1"),
            self.omp_tool_start("bash",
                                {"command": "python check_file_sizes.py --ci"},
                                id="d2"),
            self.omp_tool_start("bash",
                                {"command": "python scripts/tools/skills_search.py 'money'"},
                                id="d3"),
            # assistant prose mentioning diagnostics is not a tool call
            self.omp_message("assistant",
                             "will run doctor.py and check_file_sizes next"),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-proj" / "u4.jsonl", rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["memory_calls"], 0)
        self.assertEqual(s["kit_diag_calls"], 2)
        self.assertEqual(s["skill_search_calls"], 1)

    def test_memory_build_and_db_tools_paths_count(self):
        """db-tools/build.py under .memory counts; a project db-tools
        build.py also carries the marker and counts."""
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/proj",
                             title="proj"),
            self.omp_message("user", "rebuild index"),
            self.omp_tool_call("bash",
                               {"command": "python C:/Users/oleg2/.memory/db-tools/build.py --full"},
                               id="d1"),
            self.omp_tool_start("bash",
                                {"command": "cd db-tools && python build.py"},
                                id="d2"),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-proj" / "u5.jsonl", rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["memory_calls"], 2)
        self.assertEqual(s["kit_diag_calls"], 0)

    def test_nested_parallel_wrapper_memory_call_recognized(self):
        """A parallel tool wrapper nested inside another wrapper, with
        decoded JSON-string arguments, still yields its inner shell
        memory calls; prose/echo entries inside are ignored."""
        inner = json.dumps({"tool_uses": [
            {"recipient_name": "functions.bash", "parameters": {
                "command": "python findings.py add n --text t"}},
            {"recipient_name": "functions.bash", "parameters": {
                "command": "echo 'memory-warmup.py just ran'"}},
            {"recipient_name": "functions.read", "parameters": {
                "path": "C:/Users/oleg2/.memory/db-tools/search_all.py"}},
        ]})
        outer = {"tool_uses": [
            {"recipient_name": "tools.parallel", "parameters": inner},
        ]}
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/nest",
                             title="nested"),
            self.omp_message("user", "do it in parallel"),
            self.omp_tool_call("multi_tool_use.parallel", outer, id="w1"),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-nest" / "u6.jsonl",
                     rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["memory_calls"], 1)
        self.assertEqual(s["skill_search_calls"], 0)
        self.assertEqual(s["kit_diag_calls"], 0)

    def test_skills_search_reported_as_skill_discovery(self):
        """skills_search.py inside a parallel wrapper and as a direct
        call counts as skill discovery diagnostics, never as memory."""
        wrapper = {"tool_uses": [
            {"recipient_name": "functions.bash", "parameters": {
                "command": "python scripts/tools/skills_search.py yagni"}},
            {"recipient_name": "functions.bash", "parameters": {
                "command": "python doctor.py"}},
        ]}
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/proj",
                             title="search"),
            self.omp_message("user", "find the skill"),
            self.omp_tool_call("multi_tool_use.parallel", wrapper, id="p1"),
            self.omp_tool_call("bash",
                               {"command": "bash -c 'python skills_search.py money'"},
                               id="p2"),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-proj" / "u7.jsonl",
                     rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["memory_calls"], 0)
        self.assertEqual(s["skill_search_calls"], 2)
        self.assertEqual(s["kit_diag_calls"], 1)

    def test_bash_c_quoted_script_split_quote_aware(self):
        """bash -c "search_all.py q; echo done": the `;` inside the
        quoted script is not an outer command separator — the inner
        script parses recursively and the memory entry counts once (the
        echo mention is not a second execution)."""
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/qa",
                             title="quoted script"),
            self.omp_message("user", "find it"),
            self.omp_tool_call(
                "bash",
                {"command": 'bash -c "search_all.py q; echo done"'},
                id="q1"),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-qa" / "u8.jsonl", rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["memory_calls"], 1)
        self.assertEqual(s["skill_search_calls"], 0)
        self.assertEqual(s["kit_diag_calls"], 0)

    def test_bash_c_cd_marker_kept_for_build(self):
        """bash -c "cd ~/.memory/db-tools && python build.py": the cd
        marker carries into the inner script, so build.py counts."""
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/qa",
                             title="quoted build"),
            self.omp_message("user", "rebuild"),
            self.omp_tool_call(
                "bash",
                {"command": 'bash -c "cd ~/.memory/db-tools && python build.py"'},
                id="q2"),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-qa" / "u9.jsonl", rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["memory_calls"], 1)

    def test_uv_run_resolves_executed_script(self):
        """uv run <script> records the script, not the `run`
        subcommand; uv run python <script> resolves past the nested
        runner to the actually executed script."""
        rows = [
            self.omp_session(cwd="C:/Users/oleg2/Desktop/WORK/qa",
                             title="uv scripts"),
            self.omp_message("user", "warm up"),
            self.omp_tool_call("bash",
                               {"command": "uv run memory-warmup.py"},
                               id="u1"),
            self.omp_tool_call("bash",
                               {"command": "uv run python findings.py add z --text t"},
                               id="u2"),
        ]
        _write_jsonl(self.tmp / "omp" / "-Desktop-WORK-qa" / "u10.jsonl",
                     rows)
        res = self._audit()
        s = res["sessions"][0]
        self.assertEqual(s["memory_calls"], 2)
        self.assertEqual(s["skill_search_calls"], 0)
        self.assertEqual(s["kit_diag_calls"], 0)


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

    def test_nested_skill_payload_reads_map_to_their_skill(self):
        """Any file under a named skill payload (references, evals,
        assets, arbitrary nesting) maps to that skill; mentions and
        write payloads still don't count."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rows = [self.omp_session(), self.omp_message("user", "Dig in")]
            targets = [
                ("read", {"path": "skills/fable-method/references/"
                                  "failure-modes.md:10-30"}),
                ("Read", {"file_path": "C:\\kit\\skills\\superpowers\\"
                                       "evals\\evals.json"}),
                ("read_file", {"absolute_path": "/kit/skills/ponytail/"
                                                "assets/diagram.svg"}),
                ("read", {"path": "skill://fable-judge/references/"
                                  "workflow-authoring.md"}),
                ("read", {"path": "skill://dev-wiki/SKILL.md:5-9"}),
                # non-read tools on payload paths: not counted
                ("Write", {"path": "skills/yagni/notes.txt",
                           "content": "x"}),
                ("Bash", {"command": "cat skills/ponytail/SKILL.md"}),
            ]
            rows.extend(self.omp_tool_call(name, args, id=f"p{i}")
                        for i, (name, args) in enumerate(targets))
            _write_jsonl(root / "omp" / "project" / "s.jsonl", rows)
            result = usage_audit.audit(root / "claude", root / "omp", None)
            self.assertEqual(result["sessions"][0]["skill_reads"], [
                "dev-wiki", "fable-judge", "fable-method", "ponytail",
                "superpowers"])


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
        self.assertEqual(agg["kit_internal"]["memory_calls"], 0)
        self.assertEqual(agg["kit_internal"]["kit_diag_calls"], 1)
        self.assertEqual(agg["real"]["sessions"], 1)
        self.assertEqual(agg["real"]["memory_calls"], 1)
        self.assertEqual(agg["real"]["kit_diag_calls"], 0)
        self.assertEqual(agg["real"]["human_turns"], 1)
        # machine shape: stable keys plus new additive fields
        for key in ("generated", "since", "roots", "sessions", "aggregate"):
            self.assertIn(key, res)
        for label in ("kit_internal", "real"):
            self.assertIn("kit_diag_calls", agg[label])
            self.assertIn("skill_search_calls", agg[label])
        self.assertIn("memory_calls_note", res)

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
