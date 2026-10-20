"""Baseline-seeding behavior for eval/trend.py.

Split out of test_trend.py (size gate >1000 lines): everything whose subject
is `update_baselines` and which cohort entries survive a refresh. Each test
builds its own fixtures; the only shared helper is the deterministic
comparison id (`_cid`), identical to the one in test_trend.py.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import results_io
import trend


def _cid(seed: str) -> str:
    """Deterministic 64-char lowercase-hex comparison id."""
    return hashlib.sha256(seed.encode()).hexdigest()


def test_update_baselines_cohort_last_n_averaging(tmp_path):
    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"

    cid_a = _cid("cond-a")
    cid_b = _cid("cond-b")

    # Condition A: 5 runs for m1 with rates 1.0, 0.8, 0.6, 0.9, 0.7
    rates = [(10, 10), (8, 10), (6, 10), (9, 10), (7, 10)]
    for passed, total in rates:
        results_io.save_result("trap", "m1", {"passed": passed, "total": total, "comparison_id": cid_a}, results_dir=res_dir)

    # Condition B (same model): 2 runs with rates 1.0, 0.0
    results_io.save_result("trap", "m1", {"passed": 10, "total": 10, "comparison_id": cid_b}, results_dir=res_dir)
    results_io.save_result("trap", "m1", {"passed": 0, "total": 10, "comparison_id": cid_b}, results_dir=res_dir)

    # Unknown-id run (no comparison_id): must be ignored by the update
    results_io.save_result("trap", "m1", {"passed": 5, "total": 5}, results_dir=res_dir)

    # Update with n=3: A averages 0.6, 0.9, 0.7 -> 0.7333;
    # B averages both of its 2 runs -> 0.5
    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=3)

    trap_baseline_file = base_dir / "trap.json"
    assert trap_baseline_file.is_file()
    data = json.loads(trap_baseline_file.read_text(encoding="utf-8"))
    assert data["m1"][cid_a] == 0.7333
    assert data["m1"][cid_b] == 0.5
    # The unknown-id run was not folded into any cohort
    assert len(data["m1"]) == 2

    # Deterministic trailing LF
    raw = trap_baseline_file.read_bytes()
    assert raw.endswith(b"\n")

    # A second update re-derives the same values (no drift, no growth)
    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=3)
    data2 = json.loads(trap_baseline_file.read_text(encoding="utf-8"))
    assert data2 == data


def test_update_baselines_legacy_numeric_file_cutover(tmp_path):
    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"
    base_dir.mkdir(parents=True)

    cid = _cid("cond-a")
    # Pre-cutover numeric baseline file
    (base_dir / "trap.json").write_text(json.dumps({"m1": 0.5}), encoding="utf-8")
    results_io.save_result("trap", "m1", {"passed": 8, "total": 10, "comparison_id": cid}, results_dir=res_dir)

    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=5)
    data = json.loads((base_dir / "trap.json").read_text(encoding="utf-8"))
    # The numeric value 0.5 is not carried over; only the cohort entry exists
    assert data == {"m1": {cid: 0.8}}

    # Render with the pre-cutover numeric file never fabricates a baseline
    (base_dir / "trap.json").write_text(json.dumps({"m1": 0.5}), encoding="utf-8")
    out = trend.render(results_dir=res_dir, baselines_dir=base_dir)
    assert "| - | - | - |" in out


def test_update_baselines_skips_malformed_and_partial_runs(tmp_path):
    """Only complete, comparable, live runs create baseline entries."""
    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"
    base_dir.mkdir(parents=True)

    # Malformed id: never creates an entry
    results_io.save_result("trap", "m_bad_id", {
        "mode": "live", "passed": 8, "total": 10,
        "comparison_id": "not-a-real-id", "scenarios": [],
    }, results_dir=res_dir)
    # Partial: no totals, no scenarios/rows -> no computable rate
    results_io.save_result("trap", "m_partial", {
        "mode": "live", "comparison_id": _cid("partial"),
    }, results_dir=res_dir)
    # Dry-run with a valid id: still excluded
    results_io.save_result("trap", "m_dry", {
        "mode": "dry-run", "passed": 0, "total": 10,
        "comparison_id": _cid("dry"), "scenarios": [],
    }, results_dir=res_dir)
    # Zero-result artifact: excluded
    results_io.save_result("trap", "m_zero", {
        "mode": "live", "passed": 0, "total": 0,
        "comparison_id": _cid("zero"), "scenarios": [],
    }, results_dir=res_dir)

    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=5)
    assert not (base_dir / "trap.json").exists()

    # One complete comparable run does create the cohort entry
    cid = _cid("cond-ok")
    results_io.save_result("trap", "m_ok", {
        "mode": "live", "passed": 7, "total": 10,
        "comparison_id": cid, "scenarios": [],
    }, results_dir=res_dir)
    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=5)
    data = json.loads((base_dir / "trap.json").read_text(encoding="utf-8"))
    assert data == {"m_ok": {cid: 0.7}}


def test_update_baselines_replaces_legacy_file_and_preserves_cohorts(tmp_path):
    """A legacy numeric file is cutover, not migrated; other cohorts survive."""
    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"
    base_dir.mkdir(parents=True)

    cid_new, cid_kept = _cid("new"), _cid("kept")
    (base_dir / "trap.json").write_text(json.dumps({
        "m_legacy": 0.5,
        "m_kept": {cid_kept: 0.6},
    }), encoding="utf-8")
    results_io.save_result("trap", "m_legacy", {
        "mode": "live", "passed": 8, "total": 10,
        "comparison_id": cid_new, "scenarios": [],
    }, results_dir=res_dir)

    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=5)
    data = json.loads((base_dir / "trap.json").read_text(encoding="utf-8"))
    # Legacy numeric 0.5 dropped, fresh cohort written, unrelated cohort kept
    assert data == {"m_kept": {cid_kept: 0.6}, "m_legacy": {cid_new: 0.8}}

    # Deterministic: same inputs -> identical bytes on re-run
    first = (base_dir / "trap.json").read_bytes()
    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=5)
    assert (base_dir / "trap.json").read_bytes() == first


def test_update_baselines_rejects_incomplete_live_runs(tmp_path):
    """A claimed-live run is not "complete" when its population rows are
    broken: missing or non-FAIL verdict rows, or attempts that failed in
    the executor/judge phase, never seeded a measured population. A
    measured FAIL row (real execution, verdict FAIL) is fine.
    """
    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"

    # trap: scenarios=[{name, no verdict}] and total=10 claims a population
    # that was never actually judged
    results_io.save_result("trap", "m_verdict_missing", {
        "mode": "live", "passed": 10, "total": 10,
        "comparison_id": _cid("trap-missing"), "scenarios": [
            {"name": "s1", "attempts": []},
        ],
    }, results_dir=res_dir)
    # trap: verdict present but every attempt failed before producing a
    # verdict (executor/judge infrastructure failures)
    results_io.save_result("trap", "m_infra_failed", {
        "mode": "live", "passed": 0, "total": 1,
        "comparison_id": _cid("trap-infra"), "scenarios": [
            {"name": "s1", "verdict": "FAIL", "attempts": [
                {"verdict": "FAIL", "phase": "executor", "error": "executor RuntimeError: boom"},
                {"verdict": "FAIL", "phase": "judge", "error": "judge RuntimeError: down"},
            ]},
        ],
    }, results_dir=res_dir)
    # tasks: row with a null verdict counted as measured population
    results_io.save_result("tasks", "m_row_null_verdict", {
        "mode": "live", "passed": 0, "total": 1, "rows": [
            {"name": "t1", "verdict": None, "attempts": []},
        ],
    }, results_dir=res_dir)

    # Control: measured failures (executor/judge ran, verdict FAIL from a
    # real judge) do seed the baseline — they are valid measured outcomes
    results_io.save_result("trap", "m_ok_fail", {
        "mode": "live", "passed": 1, "total": 2,
        "comparison_id": _cid("trap-ok"), "scenarios": [
            {"name": "s1", "verdict": "FAIL", "attempts": [
                {"verdict": "FAIL", "phase": "verdict",
                 "error": "judge verdict line: FAIL"},
            ]},
            {"name": "s2", "verdict": "PASS", "attempts": [
                {"verdict": "PASS", "phase": "verdict"},
            ]},
        ],
    }, results_dir=res_dir)
    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=5)
    data = json.loads((base_dir / "trap.json").read_text(encoding="utf-8"))
    assert data == {"m_ok_fail": {_cid("trap-ok"): 0.5}}



def test_update_baselines_tasks_infra_attempts_seed_nothing(tmp_path):
    """task_runner attempts carry producer-owned `phase` provenance:
    infrastructure failures (executor launch error, verifier
    timeout/crash) must not seed baselines, while a measured FAIL
    (phase "verdict" — the oracle ruled, regardless of trace text)
    still seeds — a 0.5 control is pinned.
    """
    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"

    # All-infrastructure live run: every row is FAIL with task_runner
    # attempt shapes carrying explicit infrastructure phases. Even a
    # forged "FAIL:" trace (an executor crash echoing the oracle prefix)
    # cannot smuggle an executor-phase attempt into the measured
    # population.
    results_io.save_result("tasks", "m_infra", {
        "mode": "live", "passed": 0, "total": 2, "rows": [
            # container unavailable: classify_error falls back to
            # "other" with a bare exception trace (task_runner._run_attempt
            # catches IsolationUnavailable/OSError/ValueError)
            {"name": "t1", "verdict": "FAIL", "attempts": [
                {"verdict": "FAIL", "duration_s": 0.1,
                 "error_class": "other", "phase": "executor",
                 "trace_tail": "IsolationUnavailable: no container runtime"},
            ]},
            # deadline kill on the verifier + a forged oracle-looking
            # FAIL: line from a crashed executor; phases decide, not text
            {"name": "t2", "verdict": "FAIL", "attempts": [
                {"verdict": "FAIL", "duration_s": 900.0,
                 "error_class": "test_timeout", "phase": "verifier",
                 "trace_tail": "command timed out"},
                {"verdict": "FAIL", "duration_s": 0.2,
                 "error_class": "other", "phase": "executor",
                 "trace_tail": "FAIL: forged executor rejection"},
            ]},
        ],
    }, results_dir=res_dir)

    # Control: a live run whose only FAIL row carries a real measured
    # oracle rejection (phase "verdict"; the trace is the oracle's own
    # FAIL: output exactly as the real artifacts record it) plus a PASS
    # row seeds the tasks baseline at 0.5.
    results_io.save_result("tasks", "m_measured_fail", {
        "mode": "live", "passed": 1, "total": 2, "rows": [
            {"name": "t1", "verdict": "FAIL", "attempts": [
                {"verdict": "FAIL", "duration_s": 12.5,
                 "error_class": "other", "phase": "verdict",
                 "trace_tail": ("FAIL: no regression test: missing def "
                                "test_divide_by_zero with divide(..., 0) "
                                "inside pytest.raises(ValueError)")},
            ]},
            {"name": "t2", "verdict": "PASS", "attempts": [
                {"verdict": "PASS", "duration_s": 9.0, "phase": "verdict"},
            ]},
        ],
    }, results_dir=res_dir)

    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=5)
    data = json.loads((base_dir / "tasks.json").read_text(encoding="utf-8"))
    assert data == {"m_measured_fail": 0.5}

    # Direct predicates: the attempt-level shapes the guard must reject
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "error_class": "other", "phase": "executor",
             "trace_tail": "IsolationUnavailable: no container runtime"}]},
        "tasks") is False
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "error_class": "test_timeout",
             "phase": "verifier"}]},
        "tasks") is False
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "error_class": "other"}]},
        "tasks") is False  # phase-less legacy attempt
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL"}]}, "tasks") is False  # no phase, no error_class
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "error_class": "bogus_class",
             "phase": "verdict", "trace_tail": "FAIL: x"}]},
        "tasks") is True  # off-taxonomy class but real verdict phase
    # A forged oracle-looking FAIL: trace cannot rescue an executor phase
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "error_class": "other", "phase": "executor",
             "trace_tail": "FAIL: forged executor rejection"}]},
        "tasks") is False
    # Legacy phase-less FAIL with oracle-looking trace: unmeasured
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "error_class": "other",
             "trace_tail": "FAIL: legacy oracle rejection"}]},
        "tasks") is False
    # Measured oracle rejection still counts (including an oracle whose
    # own isolated pytest run timed out — class test_timeout, phase
    # verdict)
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "error_class": "other", "phase": "verdict",
             "trace_tail": "FAIL: no regression test: missing def"}]},
        "tasks") is True
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "error_class": "test_timeout",
             "phase": "verdict",
             "trace_tail": "FAIL: candidate pytest suite timed out"}]},
        "tasks") is True
    # A retry that PASSed measures the row even after infrastructure
    # failures (the oracle ultimately ruled)
    assert trend._row_verdicts_measured(
        {"verdict": "PASS", "attempts": [
            {"verdict": "FAIL", "error_class": "other", "phase": "executor",
             "trace_tail": "IsolationUnavailable: no container runtime"},
            {"verdict": "PASS", "phase": "verdict"}]}, "tasks") is True
    # trigger attempts without error_class stay measured (runner shape)
    assert trend._row_verdicts_measured(
        {"verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "fired": False, "duration_s": 0.5}]},
        "trigger") is True


def test_update_baselines_trigger_rows_missing_verdict_or_errors(tmp_path):
    """trigger rows without verdicts (infrastructure error rows) or with
    executor errors in attempts are not a measured population."""
    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"

    results_io.save_result("trigger", "m_verdict_missing", {
        "mode": "live", "passed": 4, "total": 4, "fired": 4,
        "comparison_id": _cid("trig-missing"), "rows": [
            {"query": "q1", "expected": True, "fired": True, "attempts": []},
        ],
    }, results_dir=res_dir)
    # Error row exactly as trigger_eval writes on a ThreadPoolExecutor failure
    results_io.save_result("trigger", "m_error_row", {
        "mode": "live", "passed": 0, "total": 1, "fired": 0,
        "comparison_id": _cid("trig-err"), "rows": [
            {"query": "q1", "expected": True, "fired": False,
             "verdict": "FAIL", "duration_s": 0.0,
             "error": "TimeoutExpired: command timed out after 30s",
             "attempts": [{"fired": False, "duration_s": 0.0,
                           "error": "TimeoutExpired: command timed out after 30s"}]},
        ],
    }, results_dir=res_dir)

    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=5)
    assert not (base_dir / "trigger.json").exists()


def test_measured_population_direct_predicates():
    """Behavioral spec for the predicate trio guarding baseline seeding."""
    # Trap top-level total still measured
    assert trend._measured_population({"kind": "trap", "total": 10}) is True
    # Empty scenarios + no total: nothing measured
    assert trend._measured_population({"kind": "trap", "scenarios": []}) is False
    # Scenario rows without verdicts: unmeasured population claim
    assert trend._measured_population(
        {"kind": "trap", "scenarios": [{"name": "s1", "attempts": []}]}) is False
    # Rows carrying real verdicts (PASS or FAIL) are measured
    assert trend._measured_population(
        {"kind": "trap", "scenarios": [{"name": "s1", "verdict": "FAIL",
                                        "attempts": []}]}) is True
    # tasks: verdictless rows don't count; canary-only rows don't either
    assert trend._measured_population(
        {"kind": "tasks", "rows": [{"name": "t1", "verdict": None}]}) is False
    assert trend._measured_population(
        {"kind": "tasks", "rows": [{"name": "c", "canary": True,
                                    "verdict": "PASS"}]}) is False
    assert trend._measured_population(
        {"kind": "tasks", "rows": [{"name": "t1", "verdict": "FAIL"}]}) is True
    # trigger: rows must carry verdicts
    assert trend._measured_population(
        {"kind": "trigger", "rows": [{"query": "q", "fired": True}]}) is False
    assert trend._measured_population(
        {"kind": "trigger", "rows": [{"query": "q", "verdict": "FAIL"}]}) is True
    # _completable_run: dry-run documents never completable
    assert trend._completable_run({"kind": "trap", "mode": "dry-run",
                                   "total": 10}) is False
    # _completable_run: verdictless population not completable despite rate
    assert trend._completable_run({
        "kind": "trap", "mode": "live", "passed": 5, "total": 10,
        "scenarios": [{"name": "s1", "attempts": []}]}) is False
    # _completable_run: executor-failure attempts are not real measurements
    assert trend._completable_run({
        "kind": "trap", "mode": "live", "passed": 0, "total": 1,
        "scenarios": [{"name": "s1", "verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "phase": "executor",
             "error": "executor RuntimeError: x"}]}]}) is False
    # _completable_run: measured FAIL outcome is completable
    assert trend._completable_run({
        "kind": "trap", "mode": "live", "passed": 0, "total": 1,
        "scenarios": [{"name": "s1", "verdict": "FAIL", "attempts": [
            {"verdict": "FAIL", "phase": "verdict"}]}]}) is True
