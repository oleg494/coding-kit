"""Task 18 (wave6 v4.0.0): OTel GenAI semconv key names as aliases.

Naming-only adoption (semconv Development status — no OTel runtime).
Round-trip contract: the schema-v1 store WRITE emits both the legacy keys
and the `gen_ai.*` alias keys with identical values; READ accepts documents
carrying either key set (legacy pre-v4 docs stay loadable); trend.py
prefers the new keys. Legacy keys are kept one release.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import results_io
import task_runner
import telemetry
import trend


def _save(tmp_path, payload, model="m1", kind="tasks"):
    results_dir = tmp_path / "results"
    results_io.save_result(kind, model, payload, results_dir=results_dir)
    return results_io.load_runs(results_dir=results_dir)[0]


def test_round_trip_emits_both_key_sets_with_identical_values(tmp_path):
    payload = {
        "mode": "live",
        "rows": [],
        "passed": 1,
        "total": 1,
        "pass_rate": 1.0,
        "duration_s_total": 2.0,
        "duration_s_mean": 2.0,
        "reported_usage": {
            "tokens_total": 12345,
            "input_tokens": 9000,
            "output_tokens": 3345,
            "cost_usd": 0.42,
        },
    }
    doc = _save(tmp_path, payload)
    # legacy keys kept
    assert doc["model"] == "m1"
    assert doc["duration_s_mean"] == 2.0
    assert doc["reported_usage"]["tokens_total"] == 12345
    # OTel aliases emitted with identical values
    assert doc["gen_ai.response.model"] == "m1"
    assert doc["gen_ai.conversation.id"] == doc["run_id"]
    assert doc["gen_ai.invoke_agent.duration"] == 2.0
    assert doc["gen_ai.usage.tokens_total"] == 12345
    assert doc["gen_ai.usage.input_tokens"] == 9000
    assert doc["gen_ai.usage.output_tokens"] == 3345
    # cost_usd has no alias in this wave's key map
    assert "gen_ai.usage.cost_usd" not in doc


def test_omitted_metrics_omit_aliases_without_fabrication(tmp_path):
    doc = _save(tmp_path, {"rows": [], "passed": 0, "total": 0})
    assert doc["gen_ai.response.model"] == "m1"
    assert doc["gen_ai.conversation.id"] == doc["run_id"]
    assert "gen_ai.invoke_agent.duration" not in doc
    assert "gen_ai.usage.tokens_total" not in doc
    assert "gen_ai.usage.input_tokens" not in doc
    assert "gen_ai.usage.output_tokens" not in doc


def test_alias_keys_are_not_payload_overridable(tmp_path):
    try:
        results_io.save_result("tasks", "m1", {"gen_ai.response.model": "evil"},
                               results_dir=tmp_path / "r")
    except ValueError:
        pass
    else:
        raise AssertionError("gen_ai alias keys must be reserved on write")


def test_store_reads_legacy_and_new_documents(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True)
    legacy = {
        "schema_version": 1,
        "run_id": "tasks-legacy",
        "kind": "tasks",
        "model": "old-model",
        "utc": "2026-08-01T00:00:00+00:00",
        "duration_s_mean": 9.0,
        "rows": [],
    }
    (results_dir / "tasks-legacy.json").write_text(
        json.dumps(legacy), encoding="utf-8")
    runs = results_io.load_runs(results_dir=results_dir)
    assert [r["run_id"] for r in runs] == ["tasks-legacy"]
    assert runs[0]["duration_s_mean"] == 9.0


def test_trend_prefers_new_duration_key_with_legacy_fallback():
    assert trend._duration_str({"gen_ai.invoke_agent.duration": 4.0,
                                "duration_s_mean": 9.0}) == "4.000s"
    assert trend._duration_str({"duration_s_mean": 9.0}) == "9.000s"
    assert trend._duration_str({"gen_ai.invoke_agent.duration": 4.0}) == "4.000s"


def test_task_rows_carry_prompt_name_without_fabricated_version(tmp_path):
    out_file = tmp_path / "dry.json"
    rc = task_runner.run_task_suite(
        ["001-fix-div-zero"], "dummy-executor", json_out=out_file,
        model="m1", dry_run=True)
    assert rc == 0
    doc = json.loads(out_file.read_text(encoding="utf-8"))
    row = doc["rows"][0]
    # the TASK.md frontmatter `name:` is the prompt identity
    assert row["gen_ai.prompt.name"] == "fix-div-zero"
    assert "gen_ai.prompt.version" not in row


def test_load_reported_usage_accepts_known_split(tmp_path):
    f = tmp_path / "u.json"
    f.write_text(json.dumps(
        {"tokens_total": 100, "input_tokens": 70, "output_tokens": 30}),
        encoding="utf-8")
    assert telemetry.load_reported_usage(str(f)) == {
        "tokens_total": 100, "input_tokens": 70, "output_tokens": 30}


def test_load_reported_usage_rejects_bad_split(tmp_path):
    for bad in ({"input_tokens": -1}, {"output_tokens": True},
                {"input_tokens": float("nan")}):
        f = tmp_path / "bad.json"
        f.write_text(json.dumps(bad), encoding="utf-8")
        assert telemetry.load_reported_usage(str(f)) is None, bad
