import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from eval.rigor import runner

# A confined executor spec: host CLIs are refused by CK-03, so the fake
# executor below is declared like a real one (image + argv inside it).
SPEC = ("docker:test-image @ro:/harness:/rigor "
        "python /rigor/offline_executor.py fix")


def _fake_cli(seen: dict | None = None, edit=None, stream: str = ""):
    def fake(record, argv, workdir, *, ro_mounts=(), stdin=None,
             timeout=600, retries=1):
        if seen is not None:
            seen.update(record=record, argv=argv, workdir=workdir,
                        mounts=ro_mounts, stdin=stdin, timeout=timeout)
        if edit is not None:
            edit(workdir)
        return {"rc": 0, "stdout": stream, "stderr": "", "timed_out": False,
                "name": "fake", "argv": []}
    return fake


def _verifier(rc: int):
    def fake(verify, workdir, *, task_dir, image, timeout=120):
        return {"rc": rc, "stdout": "", "stderr": "", "timed_out": False,
                "name": "fake", "argv": []}
    return fake


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

    payload = {"structured_output": {"tier": "FAST", "signals": []}}
    monkeypatch.setattr(runner, "_run_cli",
                        _fake_cli(seen, stream=json.dumps(payload)))
    rows = runner.evaluate_route(bundle, SPEC, model="test-model")

    expected = f"Classify this request according to the policy:\n{prompt}"
    assert seen["stdin"] == expected
    assert expected not in seen["argv"]
    assert seen["record"]["mode"] == "container"
    assert seen["record"]["image"] == "test-image"
    assert "--system-prompt-file" in seen["argv"]
    assert "/route/system_prompt.txt" in seen["argv"]
    assert [dst for _, dst in seen["mounts"]] == [runner.ROUTE_MOUNT]
    assert rows[0]["assigned_tier"] == "FAST"
    assert rows[0]["verdict"] == "PASS"


def test_evaluate_route_runs_each_case_three_times(monkeypatch, tmp_path):
    route_file = tmp_path / "cases.json"
    route_file.write_text(json.dumps([{
        "id": "fast-repeated",
        "expected_tier": "FAST",
        "minimum_tier": "FAST",
        "prompt": "Fix one README typo.",
    }]), encoding="utf-8")
    monkeypatch.setattr(runner, "ROUTE_FILE", route_file)

    bundle = tmp_path / "bundle"
    _write_policy_bundle(bundle)
    calls = []

    payload = {"structured_output": {"tier": "FAST", "signals": []}}
    fake = _fake_cli(stream=json.dumps(payload))
    inner = fake

    def counting(record, argv, workdir, *, ro_mounts=(), stdin=None,
                 timeout=600, retries=1):
        calls.append(stdin)
        return inner(record, argv, workdir, ro_mounts=ro_mounts, stdin=stdin,
                     timeout=timeout, retries=retries)

    monkeypatch.setattr(runner, "_run_cli", counting)
    rows = runner.evaluate_route(bundle, SPEC, model="test-model")

    assert len(calls) == 3
    assert [row["repetition"] for row in rows] == [1, 2, 3]
    assert all(row["verdict"] == "PASS" for row in rows)


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

    def edit(workdir):
        readme = Path(workdir) / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "## Instllation Instructions", "## Installation Instructions"),
            encoding="utf-8",
        )

    monkeypatch.setattr(runner, "_run_cli", _fake_cli(seen, edit=edit,
                                                     stream=stream))
    monkeypatch.setattr(runner.confinement, "run_verifier", _verifier(0))
    row = runner.run_microtask(
        "001-doc-typo", bundle, SPEC, model="test-model")

    assert seen["stdin"].startswith(
        f"The policy bundle is mounted read-only at: {runner.confinement.POLICY_MOUNT}\n")
    assert "In README.md in your working directory" in seen["stdin"]
    assert seen["record"]["mode"] == "container"
    assert seen["record"]["image"] == "test-image"
    assert [dst for _, dst in seen["mounts"]] == [runner.confinement.POLICY_MOUNT]
    assert runner.confinement.POLICY_MOUNT in seen["argv"]
    assert row["verdict"] == "PASS"
    attempt = row["attempts"][0]
    assert attempt["clean_pass"] is True
    assert attempt["agent_steps"] == 1
    assert attempt["tool_calls"] == 1
    assert attempt["input_tokens"] == 12
    assert attempt["tokens_total"] == 17
    assert attempt["verifier"]["rc"] == 0
    assert attempt["escaped"] == []
    assert not any(attempt["escape_markers"].values())


def test_microtask_refuses_a_host_executor(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    with pytest.raises(runner.confinement.IsolationUnavailable) as excinfo:
        runner.run_microtask("001-doc-typo", bundle, "claude -p")
    assert "outside" in str(excinfo.value)


def test_microtask_marks_an_escaped_candidate_not_clean(monkeypatch, tmp_path):
    """A candidate that writes outside the workspace is never a clean pass."""
    bundle = tmp_path / "bundle"
    markers = {"rigor-verifier-escape.txt": True}
    monkeypatch.setattr(
        runner, "_run_cli",
        _fake_cli(stream=json.dumps({"type": "assistant",
                                     "message": {"content": []}})))
    monkeypatch.setattr(runner.confinement, "run_verifier", _verifier(0))
    monkeypatch.setattr(runner.confinement, "escape_markers",
                        lambda workdir: dict(markers))
    row = runner.run_microtask("001-doc-typo", bundle, SPEC, model="m")

    assert row["attempts"][0]["verdict"] == "PASS"
    assert row["attempts"][0]["clean_pass"] is False
    assert row["attempts"][0]["escaped"] == ["rigor-verifier-escape.txt"]
    assert row["verdict"] == "FAIL"


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


def test_parse_stream_counts_cached_input_and_prefers_final_totals():
    usage = {"input_tokens": 50, "cache_read_input_tokens": 100000,
             "cache_creation_input_tokens": 1000, "output_tokens": 20}
    stream = "\n".join([
        json.dumps({"type": "assistant", "message": {"usage": usage}}),
        json.dumps({"type": "result", "usage": usage}),
    ])

    parsed = runner._parse_stream(stream)

    assert parsed["input_tokens"] == 101050
    assert parsed["tokens_total"] == 101070


def test_parse_stream_counts_cache_when_only_model_usage_is_available():
    stream = json.dumps({"type": "result", "modelUsage": {
        "primary": {"inputTokens": 10, "cacheReadInputTokens": 100,
                    "cacheCreationInputTokens": 20, "outputTokens": 5},
        "secondary": {"inputTokens": 2, "cacheReadInputTokens": 30,
                      "cacheCreationInputTokens": 4, "outputTokens": 1},
    }})

    parsed = runner._parse_stream(stream)

    assert parsed["input_tokens"] == 166
    assert parsed["tokens_total"] == 172


def test_parse_stream_counts_cache_without_final_result():
    stream = json.dumps({"type": "assistant", "message": {"usage": {
        "input_tokens": 0, "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 20, "output_tokens": 5,
    }}})

    parsed = runner._parse_stream(stream)

    assert parsed["input_tokens"] == 120
    assert parsed["tokens_total"] == 125


def test_parse_stream_empty_result_usage_falls_back_to_model_usage():
    stream = "\n".join([
        json.dumps({"type": "assistant", "message": {
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }}),
        json.dumps({"type": "result", "usage": {},
                    "modelUsage": {"primary": {
                        "inputTokens": 40, "outputTokens": 6}}}),
    ])

    parsed = runner._parse_stream(stream)

    assert parsed["input_tokens"] == 40
    assert parsed["tokens_total"] == 46


def test_parse_stream_empty_result_usage_falls_back_to_assistant_usage():
    stream = "\n".join([
        json.dumps({"type": "assistant", "message": {
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }}),
        json.dumps({"type": "result", "usage": {}}),
    ])

    parsed = runner._parse_stream(stream)

    assert parsed["input_tokens"] == 7
    assert parsed["tokens_total"] == 10


def test_parse_stream_zero_result_totals_take_precedence_over_assistant():
    stream = "\n".join([
        json.dumps({"type": "assistant", "message": {
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }}),
        json.dumps({"type": "result", "usage": {
            "input_tokens": 0, "output_tokens": 0}}),
    ])

    parsed = runner._parse_stream(stream)

    assert parsed["input_tokens"] == 0
    assert parsed["tokens_total"] == 0
