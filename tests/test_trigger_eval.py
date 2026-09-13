"""Contract tests for eval/trigger_eval.py — query validation, signal
detection, and threshold summary. No model calls."""
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from trigger_eval import detect, summarize, validate
import trigger_eval
import runner
import behavior_oracles

MOCK_SPEC = "docker:python:3.12-alpine python"
# resolve_cmd is a pure parse (no backend probing), so the mocked-run_prompt
# tests need no live docker daemon; run_prompt itself is always faked here.
_MOCK_RECORD = runner.resolve_cmd(MOCK_SPEC)


class ValidateTest(unittest.TestCase):
    def test_ok_queries_pass(self):
        qs = [{"skill": "yagni", "should": True, "query": "add a cache?"},
              {"skill": "yagni", "should": False, "query": "two plus two"}]
        self.assertEqual(validate(qs), [])

    def test_missing_should_not_queries(self):
        qs = [{"skill": "yagni", "should": True, "query": "add a cache?"}]
        problems = validate(qs)
        self.assertTrue(any("no should-not" in p for p in problems))

    def test_should_not_must_not_name_its_skill(self):
        qs = [{"skill": "yagni", "should": True, "query": "add a cache?"},
              {"skill": "yagni", "should": False,
               "query": "should I use yagni here?"}]
        problems = validate(qs)
        self.assertTrue(any("near-miss must not" in p for p in problems))

    def test_duplicate_pairs_flagged(self):
        qs = [{"skill": "yagni", "should": True, "query": "add a cache?"},
              {"skill": "yagni", "should": False, "query": "two plus two"},
              {"skill": "yagni", "should": True, "query": "add a cache?"}]
        problems = validate(qs)
        self.assertTrue(any("duplicate" in p for p in problems))

    def test_empty_file_flag(self):
        self.assertTrue(validate([]))


class DetectTest(unittest.TestCase):
    def test_standalone_token(self):
        self.assertTrue(detect("yagni", "I loaded the yagni skill"))
        self.assertTrue(detect("yagni", "SKILLS LOADED: yagni"))
        self.assertTrue(detect("yagni", "YAGNI says cut it"))

    def test_word_boundaries(self):
        self.assertFalse(detect("yagni", "yagni2 is a fork"))
        self.assertFalse(detect("yagni", "ayagni appeared"))
        self.assertFalse(detect("yagni", "no skill was loaded"))

    def test_hyphenated_slug(self):
        self.assertTrue(detect("dev-wiki", "loaded dev-wiki"))
        self.assertFalse(detect("dev-wiki", "dev wiki is my friend"))


class SummarizeTest(unittest.TestCase):
    def test_below_threshold_flags_failed_queries(self):
        rows = {"yagni": [("q1", True, True), ("q2", True, False),
                          ("q3", True, False), ("q4", True, False),
                          ("n1", False, False), ("n2", False, False)]}
        problems, stats = summarize(rows)
        self.assertTrue(any("trigger rate" in p for p in problems))
        self.assertAlmostEqual(stats["yagni"]["trigger"], 0.25)
        self.assertEqual(stats["yagni"]["false"], 0.0)

    def test_false_rate_above_threshold(self):
        rows = {"yagni": [("q1", True, True), ("n1", False, True),
                          ("n2", False, True), ("n3", False, True)]}
        problems, _ = summarize(rows)
        self.assertTrue(any("false rate" in p for p in problems))


class TimeoutPassthroughTest(unittest.TestCase):
    """--timeout must reach run_prompt (audit 2026-08-22, M4: the flag was
    parsed and documented but never used — run_prompt hardcoded 600s)."""

    def test_run_query_passes_timeout(self):
        seen = {}

        def fake_run_prompt(cmd, prompt, timeout=None):
            seen["timeout"] = timeout
            return "SKILLS LOADED: yagni"

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = fake_run_prompt
        try:
            _, passed = trigger_eval.run_query(
                _MOCK_RECORD, {"skill": "yagni", "query": "q"}, 1, timeout=42)
        finally:
            trigger_eval.run_prompt = orig
        self.assertTrue(passed)
        self.assertEqual(seen["timeout"], 42)


class LiveNoJsonCompletionTest(unittest.TestCase):
    def test_live_no_json_completes_without_saving(self):
        saved = []

        def fake_save(*args, **kwargs):
            saved.append((args, kwargs))

        def fake_run_prompt(cmd, prompt, timeout=None):
            if "USE THIS ONE" in prompt:
                return "SKILLS LOADED: yagni"
            return "SKILLS LOADED: none"

        with tempfile.TemporaryDirectory() as tmp:
            queries_file = Path(tmp) / "q.json"
            queries_file.write_text(json.dumps([
                {"skill": "yagni", "should": True, "query": "USE THIS ONE"},
                {"skill": "yagni", "should": False, "query": "OTHER TASK"},
            ]), encoding="utf-8")
            test_argv = [
                "trigger_eval.py",
                "--queries", str(queries_file),
                "--executor", MOCK_SPEC,
            ]
            orig_argv = sys.argv
            orig_run = trigger_eval.run_prompt
            trigger_eval.run_prompt = fake_run_prompt
            try:
                sys.argv = test_argv
                with unittest.mock.patch("results_io.save_result", fake_save):
                    rc = trigger_eval.main()
            finally:
                sys.argv = orig_argv
                trigger_eval.run_prompt = orig_run
        self.assertEqual(rc, 0)
        self.assertEqual(len(saved), 0)


class ModelExecutorSeparationTest(unittest.TestCase):
    def test_explicit_model_and_executor_passed_to_save_result(self):
        calls = []
        def fake_save_result(kind, model, payload, path=None, *, executor_spec=None, results_dir=None):
            calls.append({"kind": kind, "model": model, "payload": payload, "path": path, "executor_spec": executor_spec})
            return Path("mock_path.json")

        class Args:
            json = "auto"
            executor = MOCK_SPEC
            model = "gemini-2.5-pro"

        with unittest.mock.patch("results_io.save_result", fake_save_result):
            trigger_eval._emit_json(Args(), mode="live", total=10, passed=10, fired=10, misses=[], rows=[])

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["kind"], "trigger")
        self.assertEqual(calls[0]["model"], "gemini-2.5-pro")
        self.assertEqual(calls[0]["executor_spec"], MOCK_SPEC)
        self.assertEqual(calls[0]["payload"]["passed"], 10)
        self.assertEqual(calls[0]["payload"]["fired"], 10)

    def test_live_emit_without_model_is_rejected(self):
        calls = []
        def fake_save_result(kind, model, payload, path=None, *, executor_spec=None, results_dir=None):
            calls.append((kind, model, payload, path, executor_spec))
            return Path("mock_path.json")

        class Args:
            json = "auto"
            executor = MOCK_SPEC
            model = None

        with unittest.mock.patch("results_io.save_result", fake_save_result):
            with self.assertRaises(ValueError):
                trigger_eval._emit_json(Args(), mode="live", total=10, passed=10, fired=10, misses=[], rows=[])

        self.assertEqual(len(calls), 0)


class TelemetryEmitTest(unittest.TestCase):
    def test_live_attaches_duration_and_reported_usage(self):
        calls = []

        def fake_save(kind, model, payload, path=None, *, executor_spec=None, results_dir=None):
            calls.append(payload)
            return Path("mock.json")

        class Args:
            json = "auto"
            executor = MOCK_SPEC
            model = "gemini-2.5-pro"

        rows = [
            {"query": "q", "fired": True,
             "attempts": [{"fired": True, "duration_s": 2.0},
                          {"fired": True, "duration_s": 4.0}]},
        ]
        with unittest.mock.patch("results_io.save_result", fake_save):
            trigger_eval._emit_json(
                Args(), mode="live", total=1, passed=1, fired=1, misses=[],
                rows=rows, reported_usage={"tokens_total": 5, "cost_usd": 0.01})

        self.assertEqual(len(calls), 1)
        payload = calls[0]
        self.assertEqual(payload["duration_s_total"], 6.0)
        self.assertEqual(payload["duration_s_mean"], 3.0)
        self.assertEqual(payload["reported_usage"], {"tokens_total": 5, "cost_usd": 0.01})

    def test_dry_emit_never_attaches_reported_usage(self):
        calls = []

        def fake_save(kind, model, payload, path=None, *, executor_spec=None, results_dir=None):
            calls.append(payload)
            return Path("mock.json")

        class Args:
            json = "auto"
            executor = None
            model = None

        with unittest.mock.patch("results_io.save_result", fake_save):
            trigger_eval._emit_json(
                Args(), mode="dry-run", total=0, passed=0, fired=0, misses=[],
                rows=[], reported_usage={"cost_usd": 0.1})

        self.assertEqual(len(calls), 1)
        payload = calls[0]
        self.assertEqual(payload["duration_s_total"], 0.0)
        self.assertEqual(payload["duration_s_mean"], 0.0)
        self.assertNotIn("reported_usage", payload)


class RowAttemptEvidenceTest(unittest.TestCase):
    def test_run_query_detailed_records_attempts_and_verdict(self):
        def fake_run_prompt(cmd, prompt, timeout=None):
            return "SKILLS LOADED: yagni"

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = fake_run_prompt
        try:
            row = trigger_eval.run_query_detailed(
                _MOCK_RECORD, {"skill": "yagni", "should": True, "query": "write simple code"}, runs=3, timeout=50
            )
        finally:
            trigger_eval.run_prompt = orig

        self.assertEqual(row["query"], "write simple code")
        self.assertEqual(row["skill"], "yagni")
        self.assertTrue(row["expected"])
        self.assertTrue(row["fired"])
        self.assertEqual(row["verdict"], "PASS")
        self.assertIsInstance(row["duration_s"], float)
        self.assertEqual(len(row["attempts"]), 3)
        for att in row["attempts"]:
            self.assertTrue(att["fired"])
            self.assertIsInstance(att["duration_s"], float)
            self.assertNotIn("error", att)

    def test_majority_vote_detection(self):
        call_count = 0
        def alternating_prompt(cmd, prompt, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "no skill loaded"
            return "SKILLS LOADED: yagni"

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = alternating_prompt
        try:
            row = trigger_eval.run_query_detailed(
                _MOCK_RECORD, {"skill": "yagni", "should": True, "query": "yagni query"}, runs=3
            )
        finally:
            trigger_eval.run_prompt = orig

        self.assertTrue(row["fired"])
        self.assertEqual(row["verdict"], "PASS")
        self.assertEqual(len(row["attempts"]), 3)
        self.assertFalse(row["attempts"][0]["fired"])
        self.assertTrue(row["attempts"][1]["fired"])
        self.assertTrue(row["attempts"][2]["fired"])


class ErrorCaptureTest(unittest.TestCase):
    def test_executor_exception_captured_as_attempt_error(self):
        def failing_prompt(cmd, prompt, timeout=None):
            raise RuntimeError("network down or model crashed")

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = failing_prompt
        try:
            row = trigger_eval.run_query_detailed(
                _MOCK_RECORD, {"skill": "yagni", "should": True, "query": "query"}, runs=2
            )
        finally:
            trigger_eval.run_prompt = orig

        self.assertFalse(row["fired"])
        self.assertEqual(row["verdict"], "FAIL")
        self.assertEqual(len(row["attempts"]), 2)
        for att in row["attempts"]:
            self.assertFalse(att["fired"])
            self.assertIn("RuntimeError", att.get("error", ""))

    def test_timeout_expired_captured_with_trace_tail(self):
        import subprocess
        def timeout_prompt(cmd, prompt, timeout=None):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout or 300, stderr="stderr trace from subprocess")

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = timeout_prompt
        try:
            row = trigger_eval.run_query_detailed(
                _MOCK_RECORD, {"skill": "yagni", "should": True, "query": "query"}, runs=1, timeout=25
            )
        finally:
            trigger_eval.run_prompt = orig

        self.assertFalse(row["fired"])
        self.assertEqual(row["verdict"], "FAIL")
        att = row["attempts"][0]
        self.assertIn("TimeoutExpired", att.get("error", ""))
        self.assertEqual(att.get("trace_tail"), "stderr trace from subprocess")



class TopLevelFiredVsPassedSemanticsTest(unittest.TestCase):
    def test_correct_should_not_query_passed_not_fired(self):
        saved = []
        def fake_save_result(kind, model, payload, path=None, *, executor_spec=None, results_dir=None):
            saved.append(payload)
            return Path("mock.json")

        def fake_run_prompt(cmd, prompt, timeout=None):
            return "SKILLS LOADED: none"

        with tempfile.TemporaryDirectory() as tmp:
            queries_file = Path(tmp) / "q.json"
            queries_file.write_text(json.dumps([
                {"skill": "yagni", "should": True, "query": "should I add an unused abstraction?"},
                {"skill": "yagni", "should": False, "query": "calculate fibonacci"},
            ]), encoding="utf-8")
            test_argv = [
                "trigger_eval.py",
                "--queries", str(queries_file),
                "--executor", MOCK_SPEC,
                "--model", "mock-model",
                "--json", "auto",
            ]
            orig_argv = sys.argv
            orig_run = trigger_eval.run_prompt
            trigger_eval.run_prompt = fake_run_prompt
            try:
                sys.argv = test_argv
                with unittest.mock.patch("results_io.save_result", fake_save_result):
                    trigger_eval.main()
            finally:
                sys.argv = orig_argv
                trigger_eval.run_prompt = orig_run

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["total"], 2)
        self.assertEqual(saved[0]["passed"], 1)
        self.assertEqual(saved[0]["fired"], 0)
        should_not = next(row for row in saved[0]["rows"] if not row["expected"])
        self.assertEqual(should_not["verdict"], "PASS")
        self.assertFalse(should_not["fired"])

    def test_never_fire_model_mixed_corpus(self):
        saved = []
        def fake_save_result(kind, model, payload, path=None, *, executor_spec=None, results_dir=None):
            saved.append(payload)
            return Path("mock.json")

        def fake_run_prompt(cmd, prompt, timeout=None):
            return "SKILLS LOADED: none"

        with tempfile.TemporaryDirectory() as tmp:
            queries_file = Path(tmp) / "q.json"
            queries_file.write_text(json.dumps([
                {"skill": "yagni", "should": True, "query": "should I add an unused abstraction?"},
                {"skill": "yagni", "should": True, "query": "speculative generalization query"},
                {"skill": "yagni", "should": False, "query": "calculate fibonacci"},
                {"skill": "yagni", "should": False, "query": "what is 2 + 2"},
            ]), encoding="utf-8")
            test_argv = [
                "trigger_eval.py",
                "--queries", str(queries_file),
                "--executor", MOCK_SPEC,
                "--model", "mock-model",
                "--json", "auto",
            ]
            orig_argv = sys.argv
            orig_run = trigger_eval.run_prompt
            trigger_eval.run_prompt = fake_run_prompt
            try:
                sys.argv = test_argv
                with unittest.mock.patch("results_io.save_result", fake_save_result):
                    trigger_eval.main()
            finally:
                sys.argv = orig_argv
                trigger_eval.run_prompt = orig_run

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["total"], 4)
        self.assertEqual(saved[0]["passed"], 2)
        self.assertEqual(saved[0]["fired"], 0)

    def test_perfect_mixed_corpus(self):
        saved = []
        def fake_save_result(kind, model, payload, path=None, *, executor_spec=None, results_dir=None):
            saved.append(payload)
            return Path("mock.json")

        def fake_run_prompt(cmd, prompt, timeout=None):
            if "add an unused abstraction" in prompt or "generalization" in prompt:
                return "SKILLS LOADED: yagni"
            return "SKILLS LOADED: none"

        with tempfile.TemporaryDirectory() as tmp:
            queries_file = Path(tmp) / "q.json"
            queries_file.write_text(json.dumps([
                {"skill": "yagni", "should": True, "query": "add an unused abstraction?"},
                {"skill": "yagni", "should": True, "query": "generalization query"},
                {"skill": "yagni", "should": False, "query": "calculate fibonacci"},
                {"skill": "yagni", "should": False, "query": "what is 2 + 2"},
            ]), encoding="utf-8")
            test_argv = [
                "trigger_eval.py",
                "--queries", str(queries_file),
                "--executor", MOCK_SPEC,
                "--model", "mock-model",
                "--json", "auto",
            ]
            orig_argv = sys.argv
            orig_run = trigger_eval.run_prompt
            trigger_eval.run_prompt = fake_run_prompt
            try:
                sys.argv = test_argv
                with unittest.mock.patch("results_io.save_result", fake_save_result):
                    trigger_eval.main()
            finally:
                sys.argv = orig_argv
                trigger_eval.run_prompt = orig_run

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["total"], 4)
        self.assertEqual(saved[0]["passed"], 4)
        self.assertEqual(saved[0]["fired"], 2)


class ShouldNotErrorFailsRowTest(unittest.TestCase):
    def test_execution_error_on_should_not_is_fail(self):
        def failing_prompt(cmd, prompt, timeout=None):
            raise RuntimeError("network down or model crashed")

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = failing_prompt
        try:
            row = trigger_eval.run_query_detailed(
                _MOCK_RECORD, {"skill": "yagni", "should": False, "query": "query"}, runs=2
            )
        finally:
            trigger_eval.run_prompt = orig

        self.assertFalse(row["fired"])
        self.assertEqual(row["verdict"], "FAIL")
        self.assertEqual(len(row["attempts"]), 2)
        self.assertIn("RuntimeError", row["error"])
        for att in row["attempts"]:
            self.assertFalse(att["fired"])
            self.assertIn("RuntimeError", att.get("error", ""))

    def test_nonzero_exit_on_should_not_is_fail_with_trace(self):
        def nonzero_prompt(cmd, prompt, timeout=None):
            raise runner.ExecutorError(
                "subprocess exited with code 1", stdout="", stderr="executor trace tail")

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = nonzero_prompt
        try:
            row = trigger_eval.run_query_detailed(
                _MOCK_RECORD, {"skill": "yagni", "should": False, "query": "query"}, runs=1
            )
        finally:
            trigger_eval.run_prompt = orig

        self.assertFalse(row["fired"])
        self.assertEqual(row["verdict"], "FAIL")
        self.assertIn("ExecutorError", row["error"])
        self.assertEqual(row["trace_tail"], "executor trace tail")


class LiveJsonModelGateTest(unittest.TestCase):
    def test_main_rejects_live_json_without_model_before_calls(self):
        calls = []
        saved = []

        def fake_run_prompt(cmd, prompt, timeout=None):
            calls.append(1)
            return "SKILLS LOADED: none"

        def fake_save_result(*args, **kwargs):
            saved.append(1)
            return Path("mock.json")

        with tempfile.TemporaryDirectory() as tmp:
            queries_file = Path(tmp) / "q.json"
            queries_file.write_text(json.dumps([
                {"skill": "yagni", "should": True, "query": "add a cache?"},
                {"skill": "yagni", "should": False, "query": "two plus two"},
            ]), encoding="utf-8")
            test_argv = [
                "trigger_eval.py",
                "--queries", str(queries_file),
                "--executor", MOCK_SPEC,
                "--json", "auto",
            ]
            orig_argv = sys.argv
            orig_run = trigger_eval.run_prompt
            trigger_eval.run_prompt = fake_run_prompt
            try:
                sys.argv = test_argv
                with unittest.mock.patch("results_io.save_result", fake_save_result):
                    rc = trigger_eval.main()
            finally:
                sys.argv = orig_argv
                trigger_eval.run_prompt = orig_run

        self.assertEqual(rc, 2)
        self.assertEqual(calls, [])
        self.assertEqual(saved, [])


class OutOptionRemovedTest(unittest.TestCase):
    def test_out_flag_no_longer_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            queries_file = Path(tmp) / "q.json"
            queries_file.write_text(json.dumps([
                {"skill": "yagni", "should": True, "query": "add a cache?"},
                {"skill": "yagni", "should": False, "query": "two plus two"},
            ]), encoding="utf-8")
            out_file = Path(tmp) / "o.jsonl"
            r = subprocess.run(
                [sys.executable, str(ROOT / "eval" / "trigger_eval.py"),
                 "--queries", str(queries_file), "--out", str(out_file)],
                capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--out", r.stderr)
        self.assertFalse(out_file.exists())

    def test_out_flag_not_documented(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "eval" / "trigger_eval.py"), "--help"],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("--out", r.stdout)

class BehaviorOracleTest(unittest.TestCase):
    def test_fired_matches_machinery_not_slug(self):
        # The oracle must measure doctrine application (the memory reflex
        # commands), never the skill's own name — naming is exactly the
        # signal that fails for ambient always-on skills.
        self.assertTrue(behavior_oracles.behavior_fired(
            "dev-wiki", 'python ~/.memory/db-tools/search_all.py "x"'))
        self.assertTrue(behavior_oracles.behavior_fired(
            "dev-wiki", 'python ~/.memory/db-tools/findings.py add "t"'))
        self.assertFalse(behavior_oracles.behavior_fired(
            "dev-wiki", "the dev-wiki skill handles memory"))

    def test_has_oracle_only_for_always_on(self):
        self.assertTrue(behavior_oracles.has_oracle("dev-wiki"))
        self.assertFalse(behavior_oracles.has_oracle("yagni"))

    def test_signal_fired_falls_back_to_name_detection(self):
        # Non-oracle skills keep the slug-name signal.
        self.assertTrue(trigger_eval.signal_fired("yagni", "SKILLS LOADED: yagni"))
        self.assertFalse(trigger_eval.signal_fired("yagni", "no skill named"))
        # Oracle skills ignore the name and check doctrine machinery.
        self.assertTrue(trigger_eval.signal_fired(
            "dev-wiki", "run search_all.py first"))
        self.assertFalse(trigger_eval.signal_fired(
            "dev-wiki", "I'll save that to memory for later"))

    def test_run_query_detailed_records_oracle_mode(self):
        def fake_run_prompt(cmd, prompt, timeout=None):
            return "I'd run search_all.py to look that up"

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = fake_run_prompt
        try:
            row = trigger_eval.run_query_detailed(
                _MOCK_RECORD,
                {"skill": "dev-wiki", "should": True, "query": "what do we know"},
                runs=1)
        finally:
            trigger_eval.run_prompt = orig

        self.assertEqual(row["mode"], "oracle")
        self.assertTrue(row["fired"])
        self.assertEqual(row["verdict"], "PASS")
        self.assertTrue(row["attempts"][0]["fired"])

    def test_name_skills_record_name_mode(self):
        def fake_run_prompt(cmd, prompt, timeout=None):
            return "SKILLS LOADED: yagni"

        orig = trigger_eval.run_prompt
        trigger_eval.run_prompt = fake_run_prompt
        try:
            row = trigger_eval.run_query_detailed(
                _MOCK_RECORD,
                {"skill": "yagni", "should": True, "query": "add a cache?"},
                runs=1)
        finally:
            trigger_eval.run_prompt = orig

        self.assertEqual(row["mode"], "name")
        self.assertTrue(row["fired"])

class HostExecutorRejectionTest(unittest.TestCase):
    """A host executor spec must fail closed at the CLI: readable nonzero
    error, no traceback, no query executed."""

    def _queries_file(self, tmp):
        qf = Path(tmp) / "q.json"
        qf.write_text(json.dumps([
            {"skill": "yagni", "should": True, "query": "add a cache?"},
            {"skill": "yagni", "should": False, "query": "two plus two"},
        ]), encoding="utf-8")
        return qf

    def test_cli_rejects_host_executor_spec_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            qf = self._queries_file(tmp)
            r = subprocess.run(
                [sys.executable, str(ROOT / "eval" / "trigger_eval.py"),
                 "--queries", str(qf), "--executor", "gemini -p -"],
                capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("host prompt execution refused", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_cli_rejects_malformed_docker_spec_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            qf = self._queries_file(tmp)
            r = subprocess.run(
                [sys.executable, str(ROOT / "eval" / "trigger_eval.py"),
                 "--queries", str(qf), "--executor", "docker:img"],
                capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docker:", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

if __name__ == "__main__":
    unittest.main()
