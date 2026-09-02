"""Multi-harness transcript normalization (wave6 Task 20) — red-first tests.

Fixture-driven: one sanitized per-harness fixture under
tests/fixtures/transcripts/; the hermes reader is exercised against an
in-test sqlite db built to the real schema. No real transcript stores are
read here."""
import importlib.util
import sqlite3
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "transcript_normalize", KIT / "eval" / "transcript_normalize.py")
tn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tn)


FIX = Path(__file__).parent / "fixtures" / "transcripts"
def _hermes_db(tmp: Path) -> Path:
    con = sqlite3.connect(tmp / "state.db")
    try:
        con.executescript("""
        CREATE TABLE sessions (id TEXT, source TEXT, user_id TEXT,
            model TEXT, model_config TEXT, system_prompt TEXT,
            parent_session_id TEXT, started_at REAL, ended_at REAL,
            end_reason TEXT, message_count INTEGER, tool_call_count INTEGER,
            input_tokens INTEGER, output_tokens INTEGER,
            cache_read_tokens INTEGER, cache_write_tokens INTEGER,
            reasoning_tokens INTEGER, cwd TEXT, title TEXT);
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, role TEXT, content TEXT, tool_call_id TEXT,
            tool_calls TEXT, tool_name TEXT, timestamp REAL,
            token_count INTEGER, finish_reason TEXT, reasoning TEXT,
            reasoning_content TEXT, reasoning_details TEXT,
            codex_reasoning_items TEXT, codex_message_items TEXT,
            platform_message_id TEXT, observed INTEGER, active INTEGER,
            compacted INTEGER, effect_disposition TEXT, api_content TEXT,
            display_kind TEXT, display_metadata TEXT);
        INSERT INTO sessions (id, model, started_at, cwd) VALUES
            ('herm-1', 'qwen3-max', 1785000000.0, 'C:/work/proj');
        INSERT INTO messages (session_id, role, content, timestamp) VALUES
            ('herm-1', 'user', 'залей на гитхаб', 1785000001.0);
        INSERT INTO messages (session_id, role, content, timestamp) VALUES
            ('herm-1', 'assistant', 'делаю', 1785000002.0);
        UPDATE messages SET tool_calls =
        '[{"id":"tc-9","function":{"name":"bash","arguments":{"command":"git push"}}}]'
        WHERE session_id = 'herm-1' AND role = 'assistant';
        INSERT INTO messages (session_id, role, content, tool_call_id,
            tool_name, timestamp) VALUES
            ('herm-1', 'tool', 'pushed ok', 'tc-9', 'bash', 1785000003.0);
        """)
        con.commit()
    finally:
        con.close()
    return tmp / "state.db"


class OmpReaderTest(unittest.TestCase):
    def test_records_shape(self):
        res = tn.normalize("omp", FIX / "omp-session.jsonl")
        recs = res["records"]
        self.assertEqual(recs[0]["type"], "meta")
        self.assertEqual(recs[0]["source"], "omp")
        self.assertEqual(recs[0]["session_id"], "omp-fix-1")
        self.assertEqual(recs[0]["cwd"], "C:/work/proj")
        types = [r["type"] for r in recs]
        self.assertIn("user", types)
        self.assertIn("assistant", types)
        tools = [r for r in recs if r["type"] == "tool"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["tool_call_id"], "call-1")
        self.assertEqual(tools[0]["name"], "bash")
        self.assertEqual(tools[0]["result"], "found 2 hits")

    def test_bad_lines_reported_not_raised(self):
        bad = FIX / "_bad.jsonl"
        bad.write_text('{"type":"message"\nnot json\n', encoding="utf-8")
        try:
            res = tn.normalize("omp", bad)
            self.assertTrue(res["diagnostics"])
        finally:
            bad.unlink()


class ClaudeReaderTest(unittest.TestCase):
    def test_tool_use_and_result_linked(self):
        res = tn.normalize("claude", FIX / "claude-session.jsonl")
        recs = res["records"]
        self.assertEqual(recs[0]["source"], "claude")
        self.assertEqual(recs[0]["cwd"], "C:/work/proj")
        self.assertEqual(recs[0]["model"], "glm-5.3")
        tools = [r for r in recs if r["type"] == "tool"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["tool_call_id"], "tu-1")
        self.assertEqual(tools[0]["name"], "Bash")
        self.assertEqual(tools[0]["result"], "3 hits")
        users = [r for r in recs if r["type"] == "user"]
        self.assertEqual(len(users), 1)  # tool_result block is not a turn
        self.assertEqual(users[0]["content"], "сделай аудит кода")


class GeminiReaderTest(unittest.TestCase):
    def test_chat_object_normalized(self):
        res = tn.normalize("gemini", FIX / "gemini-chat.json")
        recs = res["records"]
        self.assertEqual(recs[0]["source"], "gemini")
        self.assertEqual(recs[0]["session_id"], "gem-1")
        self.assertEqual(recs[0]["model"], "gemini-2.5-pro")
        types = [r["type"] for r in recs]
        self.assertEqual(types.count("user"), 1)
        self.assertEqual(types.count("assistant"), 1)  # 'gemini' -> assistant
        self.assertEqual(types.count("system"), 1)

    def test_non_chat_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.json"
            p.write_text('{"foo": 1}', encoding="utf-8")
            res = tn.normalize("gemini", p)
            self.assertEqual(res["records"], [])
            self.assertTrue(res["diagnostics"])


class HermesReaderTest(unittest.TestCase):
    def test_db_read_and_tool_linking(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = _hermes_db(Path(tmp))
            res = tn.normalize_hermes(db, "herm-1")
            recs = res["records"]
            self.assertEqual(recs[0]["source"], "hermes")
            self.assertEqual(recs[0]["model"], "qwen3-max")
            self.assertEqual(recs[0]["cwd"], "C:/work/proj")
            tools = [r for r in recs if r["type"] == "tool"]
            self.assertEqual(len(tools), 1)  # call+result merged, no halves
            tc = tools[0]
            self.assertEqual(tc["tool_call_id"], "tc-9")
            self.assertIn("git push", tc["arguments"])
            self.assertEqual(tc["result"], "pushed ok")
            users = [r for r in recs if r["type"] == "user"]
            self.assertEqual(users[0]["content"], "залей на гитхаб")


class SameConversationCrossSourceTest(unittest.TestCase):
    """The normalization contract: the same exchange in two harness shapes
    yields comparable record sequences (types + key text)."""

    def test_omp_and_claude_comparable(self):
        omp = tn.normalize("omp", FIX / "omp-session.jsonl")["records"]
        cla = tn.normalize("claude", FIX / "claude-session.jsonl")["records"]
        # both: meta first, >=1 user turn, >=1 assistant text, 1 linked tool
        for recs, src in ((omp, "omp"), (cla, "claude")):
            self.assertEqual(recs[0]["type"], "meta")
            self.assertEqual(recs[0]["source"], src)
            self.assertEqual(len([r for r in recs if r["type"] == "tool"]), 1)
            self.assertTrue(any(r["type"] == "user" for r in recs))


class DispatchTest(unittest.TestCase):
    def test_unknown_source_raises(self):
        with self.assertRaises(ValueError):
            tn.normalize("cursor", FIX / "omp-session.jsonl")


if __name__ == "__main__":
    unittest.main()
