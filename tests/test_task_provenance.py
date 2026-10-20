"""Producer-owned phase provenance for task_runner attempts.

Split out of test_task_runner.py (file-size gate): task_runner stamps
every FAIL attempt with the stage that ruled (`executor` / `verifier` /
`verdict`); trend trusts only `phase == "verdict"` (or a PASS) as a
measured oracle signal and never inspects trace text. These tests
exercise the real producer paths (monkeypatched container.run_confined,
real _run_attempt) and the real consumer (_row_verdicts_measured /
update_baselines over the saved row), not mocks of each other.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))

import task_runner
import trend
import results_io
from task_runner import resolve_cmd, run_task_suite
# The same module instance task_runner uses (eval/ on sys.path), so
# monkeypatching here patches what the runner actually calls.
from rigor import container

# Parsed but never launched (every attempt is faked at the container
# boundary, not at the task_runner boundary).
FAKE_EXEC = "docker:kit-task-fake python"


def _confined_run_factory(executor_run, verifier_run):
    """Sequence container.run_confined stubs: one executor call, then
    verifier calls (or exceptions) per attempt."""
    calls = {"n": 0}

    def fake_run_confined(argv, workdir, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            result = executor_run
            if isinstance(result, Exception):
                raise result
            return result
        result = verifier_run
        if isinstance(result, Exception):
            raise result
        return result

    return fake_run_confined


def _attempt_row(monkeypatch, executor_run, verifier_run,
                 task="001-fix-div-zero"):
    """Run one real _run_attempt against stubbed container calls and
    wrap the produced attempt in the row shape run_task_suite saves."""
    monkeypatch.setattr(
        task_runner.container, "run_confined",
        _confined_run_factory(executor_run, verifier_run))
    record = resolve_cmd(FAKE_EXEC)
    attempt = task_runner._run_attempt(task, record, timeout=10)
    return {"name": task, "verdict": attempt["verdict"],
            "attempts": [attempt]}


_EXECUTOR_OK = {"rc": 0, "stdout": "done", "stderr": "",
                "timed_out": False}


def test_verifier_verdict_fail_long_trace_is_measured(monkeypatch):
    """A real oracle rejection (clean rc 1, no kill) whose output exceeds
    the 2000-char trace_tail bound stays a measured FAIL: provenance
    comes from `phase == "verdict"`, never from a `FAIL:` prefix
    surviving in the truncated tail."""
    long_rejection = ("FAIL: no regression test: missing def "
                      "test_divide_by_zero with divide(..., 0) inside "
                      "pytest.raises(ValueError)\n" + "x" * 5000)
    row = _attempt_row(
        monkeypatch, executor_run=_EXECUTOR_OK,
        verifier_run={"rc": 1, "stdout": long_rejection, "stderr": "",
                      "timed_out": False})
    att = row["attempts"][0]
    assert att["verdict"] == "FAIL"
    assert att["phase"] == "verdict"
    assert not att["trace_tail"].startswith("FAIL:")
    assert len(att["trace_tail"]) <= task_runner._TRACE_TAIL_CHARS
    assert trend._row_verdicts_measured(row, "tasks") is True


def test_executor_fail_with_forged_fail_trace_is_not_measured(monkeypatch):
    """An executor that crashes while echoing the oracle's `FAIL:`
    prefix must not be counted as a measured oracle rejection: the
    attempt carries phase "executor" and the consumer rejects it on
    provenance alone."""
    row = _attempt_row(
        monkeypatch,
        executor_run={"rc": 3, "stdout": "FAIL: forged rejection",
                      "stderr": "", "timed_out": False},
        verifier_run={"rc": 0, "stdout": "", "stderr": "",
                      "timed_out": False})
    att = row["attempts"][0]
    assert att["verdict"] == "FAIL"
    assert att["phase"] == "executor"
    assert att["trace_tail"].startswith("FAIL:")
    assert trend._row_verdicts_measured(row, "tasks") is False


def test_verifier_timeout_is_verifier_phase_not_measured(monkeypatch):
    """A verifier killed past its deadline never ruled: the attempt is
    phase "verifier" (infrastructure), not a measured FAIL, even though
    classify_error labels it test_timeout."""
    row = _attempt_row(
        monkeypatch, executor_run=_EXECUTOR_OK,
        verifier_run={"rc": None, "stdout": "", "stderr": "",
                      "timed_out": True})
    att = row["attempts"][0]
    assert att["verdict"] == "FAIL"
    assert att["phase"] == "verifier"
    assert att["error_class"] == "test_timeout"
    assert trend._row_verdicts_measured(row, "tasks") is False


def test_verifier_timeout_with_rc0_is_not_a_pass(monkeypatch):
    """A deadline kill that reports rc 0 is not a PASS: the oracle never
    completed, so the attempt is a verifier-phase FAIL (rc 0 + timed_out
    fails the PASS gate)."""
    row = _attempt_row(
        monkeypatch, executor_run=_EXECUTOR_OK,
        verifier_run={"rc": 0, "stdout": "PASS", "stderr": "",
                      "timed_out": True})
    att = row["attempts"][0]
    assert att["verdict"] == "FAIL"
    assert att["phase"] == "verifier"
    assert trend._row_verdicts_measured(row, "tasks") is False


def test_verifier_unexpected_rc_is_verifier_phase_not_measured(monkeypatch):
    """The oracle's contract is exactly rc 0/1: docker launcher errors
    (rc 125/126/127), signals, or any other nonzero exit mean the oracle
    crashed instead of ruling — infrastructure, never a measured FAIL,
    even when its trace happens to start with the oracle's FAIL: line."""
    for rc in (125, 126, 127, 2, 137):
        row = _attempt_row(
            monkeypatch, executor_run=_EXECUTOR_OK,
            verifier_run={"rc": rc, "stdout": "FAIL: looks like a verdict",
                          "stderr": "", "timed_out": False})
        att = row["attempts"][0]
        assert att["verdict"] == "FAIL", rc
        assert att["phase"] == "verifier", rc
        assert trend._row_verdicts_measured(row, "tasks") is False, rc


def test_verifier_unavailable_is_verifier_phase_not_measured(monkeypatch):
    """The oracle failing to launch (no runtime, bad image) is an
    infrastructure FAIL: phase "verifier", unmeasured."""
    row = _attempt_row(
        monkeypatch, executor_run=_EXECUTOR_OK,
        verifier_run=container.IsolationUnavailable("no container runtime"))
    att = row["attempts"][0]
    assert att["verdict"] == "FAIL"
    assert att["phase"] == "verifier"
    assert trend._row_verdicts_measured(row, "tasks") is False


def test_pass_attempt_carries_verdict_phase(monkeypatch):
    """A passing oracle verdict (clean rc 0, no kill) is stamped phase
    "verdict" and stays measured in the consumer."""
    row = _attempt_row(
        monkeypatch, executor_run=_EXECUTOR_OK,
        verifier_run={"rc": 0, "stdout": "PASS", "stderr": "",
                      "timed_out": False})
    att = row["attempts"][0]
    assert att["verdict"] == "PASS"
    assert att["phase"] == "verdict"
    assert trend._row_verdicts_measured(row, "tasks") is True


def test_fail_attempt_rejects_unknown_phase():
    """The producer validates its own vocabulary: an off-contract phase
    is a programming error, not silent provenance."""
    with pytest.raises(ValueError):
        task_runner._fail_attempt(0.1, "other", "", "", "bogus")


def test_measured_fail_then_pass_retry_seeds_baseline(tmp_path,
                                                       monkeypatch):
    """Producer->consumer end-to-end: a suite whose row holds one real
    measured oracle FAIL attempt (phase "verdict") and one oracle PASS
    attempt (retry succeeded) produces a saved document that
    update_baselines accepts as a measured population."""
    attempts = [
        {"verdict": "FAIL", "duration_s": 12.5, "error_class": "other",
         "phase": "verdict",
         "trace_tail": "FAIL: no regression test: missing def "
                       "test_divide_by_zero with divide(..., 0) inside "
                       "pytest.raises(ValueError)"},
        {"verdict": "PASS", "duration_s": 9.0, "phase": "verdict"},
    ]

    def fake_attempt(name, record, *, timeout, verifier_image=None):
        return attempts.pop(0)

    monkeypatch.setattr(task_runner, "_run_attempt", fake_attempt)
    out = tmp_path / "measured_retry.json"
    rc = run_task_suite(["001-fix-div-zero"], FAKE_EXEC, tries=2,
                        json_out=out, model="measured-model")
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    row = doc["rows"][0]
    assert row["verdict"] == "PASS"
    assert row["attempts"][0]["phase"] == "verdict"

    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"
    results_io.save_result("tasks", "measured-model", {
        "mode": "live", "rows": doc["rows"],
        "passed": doc["passed"], "total": doc["total"],
    }, results_dir=res_dir)
    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir,
                           n=5)
    data = json.loads((base_dir / "tasks.json").read_text(
        encoding="utf-8"))
    assert data == {"measured-model": 1.0}


def test_all_infra_suite_documents_seed_nothing(tmp_path, monkeypatch):
    """Producer->consumer end-to-end: a suite whose every attempt is
    infrastructure (executor launch failure on every try) still runs and
    persists, but the saved document is not a measured population and
    update_baselines writes no tasks baseline."""
    def fake_attempt(name, record, *, timeout, verifier_image=None):
        return {"verdict": "FAIL", "duration_s": 0.1,
                "error_class": "other", "phase": "executor",
                "trace_tail": "IsolationUnavailable: no container runtime"}

    monkeypatch.setattr(task_runner, "_run_attempt", fake_attempt)
    out = tmp_path / "all_infra.json"
    rc = run_task_suite(["001-fix-div-zero"], FAKE_EXEC, tries=2,
                        json_out=out, model="infra-model")
    assert rc == 1
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["rows"][0]["verdict"] == "FAIL"

    res_dir = tmp_path / "results"
    base_dir = tmp_path / "baselines"
    results_io.save_result("tasks", "infra-model", {
        "mode": "live", "rows": doc["rows"],
        "passed": doc["passed"], "total": doc["total"],
    }, results_dir=res_dir)
    trend.update_baselines(results_dir=res_dir, baselines_dir=base_dir,
                           n=5)
    assert not (base_dir / "tasks.json").exists()


def test_legacy_phaseless_fail_attempt_is_not_measured():
    """A FAIL attempt with no `phase` (legacy artifact) is never
    treated as measured, even when its trace carries the oracle's
    `FAIL:` rejection — provenance cannot be inferred from text."""
    row = {"name": "001-fix-div-zero", "verdict": "FAIL", "attempts": [
        {"verdict": "FAIL", "duration_s": 12.5, "error_class": "other",
         "trace_tail": "FAIL: no regression test: missing def"}]}
    assert trend._task_attempt_measured(row["attempts"][0]) is False
    assert trend._row_verdicts_measured(row, "tasks") is False


@pytest.mark.parametrize("phase", [None, "unknown"])
def test_unknown_or_null_task_phase_is_not_measured(phase):
    row = {"verdict": "FAIL", "attempts": [
        {"verdict": "FAIL", "phase": phase, "trace_tail": "FAIL: forged"}]}
    assert not trend._row_verdicts_measured(row, "tasks")
