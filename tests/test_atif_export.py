"""Task 19 (wave6 v4.0.0): ATIF v1.7 export layer contract.

`to_atif` maps a schema-v1 results payload onto one Harbor ATIF Trajectory:
agent.name="coding-kit", steps[] (source system|user|agent), tool_calls[]
linked to observation.results[] via source_call_id, per-step
metrics{prompt_tokens, completion_tokens, cached_tokens, cost_usd},
final_metrics, llm_call_count. The validator checks structure against the
Harbor RFC tables (token_ids/logprobs deliberately skipped — RL-oriented).
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

from atif_export import to_atif, validate_atif


def _payload(**overrides):
    payload = {
        "mode": "live",
        "rows": [
            {
                "name": "001-fix-div-zero",
                "verdict": "PASS",
                "gen_ai.prompt.name": "fix-div-zero",
                "attempts": [
                    {"verdict": "PASS", "duration_s": 34.2,
                     "metrics": {"prompt_tokens": 520, "completion_tokens": 80,
                                 "cached_tokens": 200, "cost_usd": 0.00045}},
                ],
                "tool_calls": [
                    {"tool_call_id": "call_1", "function_name": "bash",
                     "arguments": {"command": "pytest -q"}},
                ],
                "observation": {
                    "results": [
                        {"source_call_id": "call_1", "content": "1 passed"},
                    ]
                },
            },
        ],
        "passed": 1, "total": 1, "pass_rate": 1.0,
        "duration_s_total": 34.2, "duration_s_mean": 34.2,
        "reported_usage": {"tokens_total": 600,
                           "input_tokens": 520, "output_tokens": 80,
                           "cost_usd": 0.00045},
    }
    payload.update(overrides)
    return payload


def test_to_atif_shape_and_rfc_fields():
    traj = to_atif(_payload(), run_id="tasks-run-1", model="m1",
                   utc="2026-08-29T08:36:43+00:00", agent_version="4.0.0")
    assert traj["schema_version"] == "ATIF-v1.7"
    assert traj["session_id"] == "tasks-run-1"
    assert traj["agent"]["name"] == "coding-kit"
    assert traj["agent"]["version"] == "4.0.0"
    assert traj["agent"]["model_name"] == "m1"
    steps = traj["steps"]
    assert [s["step_id"] for s in steps] == list(range(1, len(steps) + 1))
    sources = [s["source"] for s in steps]
    assert sources[0] == "system"
    assert "user" in sources and "agent" in sources
    agent_steps = [s for s in steps if s["source"] == "agent"]
    calls = [c for s in agent_steps for c in s.get("tool_calls", [])]
    assert calls and calls[0]["tool_call_id"] == "call_1"
    assert calls[0]["function_name"] == "bash"
    assert calls[0]["arguments"] == {"command": "pytest -q"}
    linked = [r for s in agent_steps
              for r in (s.get("observation") or {}).get("results", [])]
    assert any(r["source_call_id"] == "call_1" for r in linked)
    metrics = agent_steps[0]["metrics"]
    assert metrics["prompt_tokens"] == 520
    assert metrics["completion_tokens"] == 80
    assert metrics["cached_tokens"] == 200
    assert metrics["cost_usd"] == 0.00045
    fm = traj["final_metrics"]
    assert fm["total_prompt_tokens"] == 520
    assert fm["total_completion_tokens"] == 80
    assert fm["total_cached_tokens"] == 200
    assert fm["total_cost_usd"] == 0.00045
    assert fm["total_steps"] == len(steps)
    assert traj["extra"]["llm_call_count"] >= 1
    # RL-oriented fields never emitted
    dumped = json.dumps(traj)
    assert "token_ids" not in dumped and "logprobs" not in dumped


def test_exported_trajectory_passes_validator():
    traj = to_atif(_payload(), run_id="r1", model="m1",
                   utc="2026-08-29T08:36:43+00:00", agent_version="4.0.0")
    assert validate_atif(traj) == []


def test_validator_names_the_missing_field():
    traj = to_atif(_payload(), run_id="r1", model="m1",
                   utc="2026-08-29T08:36:43+00:00", agent_version="4.0.0")
    del traj["agent"]["name"]
    errors = validate_atif(traj)
    assert errors and "agent.name" in errors[0]
    del traj["schema_version"]
    errors = validate_atif(traj)
    assert any("schema_version" in e for e in errors)


def test_validator_catches_bad_step_ids_and_orphan_results():
    traj = to_atif(_payload(), run_id="r1", model="m1",
                   utc="2026-08-29T08:36:43+00:00", agent_version="4.0.0")
    traj["steps"][0]["step_id"] = 5
    errors = validate_atif(traj)
    assert any("step_id" in e for e in errors)
    traj2 = to_atif(_payload(), run_id="r1", model="m1",
                    utc="2026-08-29T08:36:43+00:00", agent_version="4.0.0")
    for s in traj2["steps"]:
        if s["source"] == "agent":
            for r in (s.get("observation") or {}).get("results", []):
                r["source_call_id"] = "call_missing"
    errors = validate_atif(traj2)
    assert any("source_call_id" in e for e in errors)


def test_plaintext_payload_without_tools_still_exports():
    payload = {
        "mode": "live",
        "rows": [{"name": "t", "verdict": "FAIL", "attempts": []}],
        "passed": 0, "total": 1,
    }
    traj = to_atif(payload, run_id="r2", model="m2",
                   utc="2026-08-29T09:00:00+00:00", agent_version="4.0.0")
    assert validate_atif(traj) == []
    assert traj["final_metrics"]["total_steps"] == len(traj["steps"])
    assert traj["extra"]["llm_call_count"] == 0


def test_cli_writes_trajectory_json(tmp_path):
    import subprocess
    src = tmp_path / "results.json"
    src.write_text(json.dumps({
        "schema_version": 1, "run_id": "tasks-x", "kind": "tasks",
        "model": "m1", "utc": "2026-08-29T08:36:43+00:00",
        **_payload()}), encoding="utf-8")
    out = tmp_path / "traj.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "atif_export.py"),
         "--from", str(src), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr
    traj = json.loads(out.read_text(encoding="utf-8"))
    assert traj["schema_version"] == "ATIF-v1.7"
    assert traj["session_id"] == "tasks-x"


def test_cli_rejects_malformed_results(tmp_path):
    src = tmp_path / "bad.json"
    src.write_text('{"kind": "tasks"}', encoding="utf-8")
    out = tmp_path / "traj.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "atif_export.py"),
         "--from", str(src), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", check=False)
    assert proc.returncode != 0
    text = proc.stderr + proc.stdout
    # the error names the first missing required envelope field
    assert ("utc" in text) or ("run_id" in text)
