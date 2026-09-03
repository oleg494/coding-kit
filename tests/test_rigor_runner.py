import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from eval.rigor import runner


def _write_policy_bundle(root: Path) -> None:
    for name in runner.POLICY_FILES:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(f"# {name}\n", encoding="utf-8")
    skill = root / "skills" / "superpowers" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("# Superpowers\n", encoding="utf-8")


def test_evaluate_route_passes_multiline_prompt_on_stdin(monkeypatch, tmp_path):
    prompt = "Fix one README typo.\nOnly one line changes."
    route_file = tmp_path / "cases.json"
    route_file.write_text(json.dumps([{
        "id": "fast-stdin",
        "expected_tier": "FAST",
        "minimum_tier": "FAST",
        "prompt": prompt,
    }]), encoding="utf-8")
    monkeypatch.setattr(runner, "ROUTE_FILE", route_file)

    bundle = tmp_path / "bundle"
    _write_policy_bundle(bundle)
    seen = {}

    def fake_run(cmd, stdin_text, cwd, timeout):
        seen.update(cmd=cmd, stdin=stdin_text, cwd=cwd, timeout=timeout)
        payload = {"structured_output": {"tier": "FAST", "signals": []}}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    monkeypatch.setattr(runner, "_run_claude", fake_run)
    rows = runner.evaluate_route(bundle, "claude", model="test-model")

    expected = f"Classify this request according to the policy:\n{prompt}"
    assert seen["stdin"] == expected
    assert expected not in seen["cmd"]
    assert "--system-prompt-file" in seen["cmd"]
    assert rows[0]["assigned_tier"] == "FAST"
    assert rows[0]["verdict"] == "PASS"


def test_microtask_passes_policy_and_brief_on_stdin_and_counts_nested_tools(
        monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    seen = {}
    stream = json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "Editing the typo."},
                {"type": "tool_use", "id": "tu-1", "name": "Edit"},
            ],
            "usage": {"input_tokens": 12, "output_tokens": 5},
        },
    }) + "\n"

    def fake_run(cmd, stdin_text, cwd, timeout):
        seen.update(cmd=cmd, stdin=stdin_text, cwd=cwd, timeout=timeout)
        readme = Path(cwd) / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "## Instllation Instructions", "## Installation Instructions"),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stream, "")

    monkeypatch.setattr(runner, "_run_claude", fake_run)
    row = runner.run_microtask(
        "001-doc-typo", bundle, "claude", model="test-model")

    assert seen["stdin"].startswith(
        f"The policy bundle is mounted read-only at: {bundle}\n")
    assert "In README.md in your working directory" in seen["stdin"]
    assert seen["stdin"] not in seen["cmd"]
    assert row["verdict"] == "PASS"
    attempt = row["attempts"][0]
    assert attempt["clean_pass"] is True
    assert attempt["agent_steps"] == 1
    assert attempt["tool_calls"] == 1
    assert attempt["input_tokens"] == 12
    assert attempt["tokens_total"] == 17

def test_parse_stream_uses_result_usage_without_double_counting():
    stream = "\n".join([
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        }),
        json.dumps({
            "type": "result",
            "usage": {"input_tokens": 1039, "output_tokens": 39},
        }),
    ])

    parsed = runner._parse_stream(stream)

    assert parsed["agent_steps"] == 1
    assert parsed["tool_calls"] == 0
    assert parsed["input_tokens"] == 1039
    assert parsed["tokens_total"] == 1078
