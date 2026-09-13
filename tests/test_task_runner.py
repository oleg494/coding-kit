import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))

import task_runner
from task_runner import (
    ERROR_CLASSES,
    classify_error,
    resolve_cmd,
    run_task_suite,
)
# The same module instance task_runner uses (eval/ on sys.path), so
# monkeypatching here patches what the runner actually calls.
from rigor import container

# --- confinement fixtures ---------------------------------------------------
# Every live attempt runs inside a container. Executor-only tests use the
# backend's base image; the real oracles of tasks 001-006 run pytest INSIDE
# the boundary, so the end-to-end PASS/verifier tests additionally need an
# image carrying pytest. Provision it once, then name it:
#
#   docker build -t kit-task-verifier:py312 - <<EOF
#   FROM python:3.12-alpine
#   RUN pip install --no-cache-dir pytest
#   EOF
#
# Override the name with KIT_TEST_TASK_IMAGE. Without a runtime or without
# the image, only the pytest-free real-container tests run.
EXEC_IMAGE = container.DEFAULT_IMAGE
TASK_IMAGE = os.environ.get("KIT_TEST_TASK_IMAGE", "kit-task-verifier:py312")
_RUNTIME = container.docker_status()
_HAS_TASK_IMAGE = bool(_RUNTIME["available"]) and container._docker(
    "image", "inspect", TASK_IMAGE).returncode == 0

requires_runtime = pytest.mark.skipif(
    not _RUNTIME["available"],
    reason=f"no container runtime: {_RUNTIME.get('reason', 'unavailable')}")
requires_task_image = pytest.mark.skipif(
    not _HAS_TASK_IMAGE,
    reason=f"task image {TASK_IMAGE!r} carrying pytest is unavailable")

# Parsed but never launched (every attempt is faked in suite-level tests).
FAKE_EXEC = "docker:kit-task-fake python"

# Deterministic honest 001 fix, executed by the in-container executor with
# cwd=/work (the sandbox, its only writable mount).
FIX_001_PY = """\
import pathlib, sys
calc = pathlib.Path("calc.py")
calc.write_text(calc.read_text(encoding="utf-8").replace(
    "    return a / b",
    '    if b == 0:\\n        raise ValueError("division by zero")\\n'
    "    return a / b"), encoding="utf-8", newline="\\n")
tests = pathlib.Path("test_calc.py")
tests.write_text(tests.read_text(encoding="utf-8") + (
    "\\n\\ndef test_divide_by_zero():\\n"
    "    import pytest\\n"
    "    with pytest.raises(ValueError):\\n"
    "        divide(1, 0)\\n"), encoding="utf-8", newline="\\n")
sys.exit(0)
"""


def _mounted_spec(tmp_path: Path, scripts: dict, entry: str) -> dict:
    """Confined record whose executor is a host script mounted read-only."""
    host = tmp_path / "exec"
    host.mkdir(exist_ok=True)
    for name, code in scripts.items():
        (host / name).write_text(code, encoding="utf-8")
    return resolve_cmd(
        f"docker:{EXEC_IMAGE} @ro:{host.as_posix()}:/exec "
        f"python /exec/{entry}")


def test_task_runner_discovers_tasks():
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "task_runner.py"), "--dry-run"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    assert "6 tasks discovered" in r.stdout or "6 tasks" in r.stdout


def test_verify_rejects_pristine_fixture(tmp_path):
    # pristine fixture fails for all 4 tasks
    for task in ("001-fix-div-zero", "002-add-validation", "003-regression-guard",
                 "004-regression-test-first"):
        sandbox = tmp_path / task
        shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sandbox)
        v = ROOT / "eval" / "tasks" / task / "verify.py"
        r = subprocess.run(
            [sys.executable, str(v), str(sandbox)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 1, f"{task} verify must reject pristine fixture: {r.stdout} {r.stderr}"


def test_verify_accepts_fixed_fixture(tmp_path):
    # Task 001 reference fix
    sandbox_001 = tmp_path / "fixed_001"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sandbox_001)
    (sandbox_001 / "calc.py").write_text(
        (sandbox_001 / "calc.py").read_text(encoding="utf-8").replace(
            "    return a / b",
            '    if b == 0:\n        raise ValueError("division by zero")\n    return a / b',
        ),
        encoding="utf-8",
        newline="\n",
    )
    tests_001 = (sandbox_001 / "test_calc.py").read_text(encoding="utf-8")
    tests_001 += "\n\ndef test_divide_by_zero():\n    import pytest\n    with pytest.raises(ValueError):\n        divide(1, 0)\n"
    (sandbox_001 / "test_calc.py").write_text(tests_001, encoding="utf-8", newline="\n")
    v1 = ROOT / "eval" / "tasks" / "001-fix-div-zero" / "verify.py"
    r1 = subprocess.run(
        [sys.executable, str(v1), str(sandbox_001)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r1.returncode == 0, r1.stdout + r1.stderr

    # Task 002 reference fix
    sandbox_002 = tmp_path / "fixed_002"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sandbox_002)
    (sandbox_002 / "calc.py").write_text(
        (sandbox_002 / "calc.py").read_text(encoding="utf-8").replace(
            "def parse_int(s):\n    return int(s)",
            'def parse_int(s):\n    s = str(s).strip()\n    try:\n        return int(s)\n    except ValueError:\n        raise ValueError(f"not an integer: {s}")',
        ),
        encoding="utf-8",
        newline="\n",
    )
    tests_002 = (sandbox_002 / "test_calc.py").read_text(encoding="utf-8")
    tests_002 += '\n\ndef test_parse_int_whitespace():\n    assert parse_int(" 42 ") == 42\n    assert parse_int("\\t7\\n") == 7\n\ndef test_parse_int_non_numeric():\n    import pytest\n    with pytest.raises(ValueError, match="not an integer"):\n        parse_int("abc")\n'
    (sandbox_002 / "test_calc.py").write_text(tests_002, encoding="utf-8", newline="\n")
    v2 = ROOT / "eval" / "tasks" / "002-add-validation" / "verify.py"
    r2 = subprocess.run(
        [sys.executable, str(v2), str(sandbox_002)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr

    # Task 003 reference fix
    sandbox_003 = tmp_path / "fixed_003"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sandbox_003)
    (sandbox_003 / "calc.py").write_text(
        (sandbox_003 / "calc.py").read_text(encoding="utf-8").replace(
            "def clamp(v, lo, hi):\n    if lo > v < hi:\n        return hi\n    return v",
            "def clamp(v, lo, hi):\n    if v < lo:\n        return lo\n    if v > hi:\n        return hi\n    return v",
        ),
        encoding="utf-8",
        newline="\n",
    )
    tests_003 = (sandbox_003 / "test_calc.py").read_text(encoding="utf-8")
    tests_003 += "\n\ndef test_clamp_bounds():\n    assert clamp(-5, 0, 10) == 0\n    assert clamp(15, 0, 10) == 10\n"
    (sandbox_003 / "test_calc.py").write_text(tests_003, encoding="utf-8", newline="\n")
    v3 = ROOT / "eval" / "tasks" / "003-regression-guard" / "verify.py"
    r3 = subprocess.run(
        [sys.executable, str(v3), str(sandbox_003)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r3.returncode == 0, r3.stdout + r3.stderr


def test_verify_rejects_pass_stubs_and_missing_tests(tmp_path):
    # Fix calc.py for all 3 tasks, but test_calc.py has either pass stub or no new tests
    # 1. Pass stub on 001
    sb1 = tmp_path / "stub_001"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb1)
    (sb1 / "calc.py").write_text(
        (sb1 / "calc.py").read_text(encoding="utf-8").replace(
            "    return a / b",
            '    if b == 0:\n        raise ValueError("division by zero")\n    return a / b',
        ),
        encoding="utf-8",
    )
    (sb1 / "test_calc.py").write_text(
        (sb1 / "test_calc.py").read_text(encoding="utf-8") + "\n\ndef test_stub():\n    pass\n",
        encoding="utf-8",
    )
    r = subprocess.run([sys.executable, str(ROOT / "eval" / "tasks" / "001-fix-div-zero" / "verify.py"), str(sb1)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 1, "Pass stub on 001 must fail verify"

    # 2. Fix without test on 002
    sb2 = tmp_path / "fix_only_002"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb2)
    (sb2 / "calc.py").write_text(
        (sb2 / "calc.py").read_text(encoding="utf-8").replace(
            "def parse_int(s):\n    return int(s)",
            'def parse_int(s):\n    s = str(s).strip()\n    try:\n        return int(s)\n    except ValueError:\n        raise ValueError(f"not an integer: {s}")',
        ),
        encoding="utf-8",
    )
    r = subprocess.run([sys.executable, str(ROOT / "eval" / "tasks" / "002-add-validation" / "verify.py"), str(sb2)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 1, "Fix without test on 002 must fail verify"

    # 3. Unrelated extra test on 003
    sb3 = tmp_path / "unrelated_003"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb3)
    (sb3 / "calc.py").write_text(
        (sb3 / "calc.py").read_text(encoding="utf-8").replace(
            "def clamp(v, lo, hi):\n    if lo > v < hi:\n        return hi\n    return v",
            "def clamp(v, lo, hi):\n    if v < lo:\n        return lo\n    if v > hi:\n        return hi\n    return v",
        ),
        encoding="utf-8",
    )
    (sb3 / "test_calc.py").write_text(
        (sb3 / "test_calc.py").read_text(encoding="utf-8") + "\n\ndef test_unrelated():\n    assert 1 == 1\n",
        encoding="utf-8",
    )
    r = subprocess.run([sys.executable, str(ROOT / "eval" / "tasks" / "003-regression-guard" / "verify.py"), str(sb3)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 1, "Unrelated extra test on 003 must fail verify"


def test_verify_rejects_wrong_regression_target(tmp_path):
    # In task 001, candidate fixes divide and also fixes clamp, but adds regression test for clamp only
    sb = tmp_path / "wrong_target_001"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb)
    cand_calc = (
        'def divide(a, b):\n'
        '    if b == 0:\n'
        '        raise ValueError("division by zero")\n'
        '    return a / b\n\n'
        'def parse_int(s):\n'
        '    return int(s)\n\n'
        'def clamp(v, lo, hi):\n'
        '    if v < lo:\n'
        '        return lo\n'
        '    if v > hi:\n'
        '        return hi\n'
        '    return v\n'
    )
    (sb / "calc.py").write_text(cand_calc, encoding="utf-8")
    tests = (sb / "test_calc.py").read_text(encoding="utf-8")
    tests += "\n\ndef test_clamp_fixed():\n    assert clamp(-5, 0, 10) == 0\n"
    (sb / "test_calc.py").write_text(tests, encoding="utf-8")

    r = subprocess.run([sys.executable, str(ROOT / "eval" / "tasks" / "001-fix-div-zero" / "verify.py"), str(sb)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 1, "Testing wrong function must fail verify (caught by revert step)"

def test_zero_tasks_returns_1_and_no_zero_division(tmp_path):
    # rc 1 on zero tasks in dry-run and live
    rc_dry = run_task_suite([], None, dry_run=True)
    assert rc_dry == 1

    rc_live = run_task_suite([], "dummy-executor")
    assert rc_live == 1

    # with json_out, saves payload with 0 metrics and no division by zero
    out_file = tmp_path / "zero.json"
    rc_json = run_task_suite([], "dummy-executor", json_out=out_file, model="zero-model")
    assert rc_json == 1
    assert out_file.is_file()

    doc = json.loads(out_file.read_text(encoding="utf-8"))
    assert doc["total"] == 0
    assert doc["passed"] == 0
    assert doc["pass_rate"] == 0.0
    assert doc["pass@1"] == 0.0
    assert doc["pass@2"] == 0.0
    assert doc["rows"] == []
    assert doc["duration_s_total"] == 0.0
    assert doc["duration_s_mean"] == 0.0
    assert "reported_usage" not in doc


def test_dry_run_no_subprocess_and_persistence(tmp_path):
    # dry run without json persists nothing
    out_dir = tmp_path / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    rc = run_task_suite(["001-fix-div-zero"], None, dry_run=True)
    assert rc == 0
    assert list(out_dir.glob("*.json")) == []

    # dry run with explicit json_out creates result doc
    explicit_json = tmp_path / "dry_out.json"
    rc_json = run_task_suite(
        ["001-fix-div-zero"],
        None,
        dry_run=True,
        json_out=explicit_json,
    )
    assert rc == 0
    assert explicit_json.is_file()
    doc = json.loads(explicit_json.read_text(encoding="utf-8"))
    assert doc["mode"] == "dry-run"
    assert doc["kind"] == "tasks"
    assert doc["total"] == 1
    assert doc["passed"] == 0
    assert doc["rows"][0]["verdict"] == "DRY_RUN"
    assert doc["duration_s_total"] == 0.0
    assert doc["duration_s_mean"] == 0.0
    assert "reported_usage" not in doc


def test_live_persists_duration_and_reported_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        task_runner, "_run_attempt",
        lambda name, record, *, timeout, verifier_image=None:
            {"verdict": "PASS", "duration_s": 1.5},
    )
    out_file = tmp_path / "live_usage.json"
    rc = run_task_suite(
        ["001-fix-div-zero"],
        FAKE_EXEC,
        json_out=out_file,
        model="usage-model",
        reported_usage={"tokens_total": 100, "cost_usd": 0.05},
    )
    assert rc == 0
    doc = json.loads(out_file.read_text(encoding="utf-8"))
    assert doc["duration_s_total"] == 1.5
    assert doc["duration_s_mean"] == 1.5
    assert doc["reported_usage"] == {"tokens_total": 100, "cost_usd": 0.05}

def test_suite_retries_a_fail_then_pass(tmp_path, monkeypatch):
    # Suite-level retry accounting: FAIL then PASS on the second attempt
    # yields pass@1 0.0 / pass@2 1.0 with both attempts recorded. Real
    # per-attempt sandbox freshness against the live backend is proven by
    # test_retry_gets_a_fresh_sandbox_confined.
    seen = {"n": 0}

    def fake_attempt(name, record, *, timeout, verifier_image=None):
        seen["n"] += 1
        if seen["n"] == 1:
            return {"verdict": "FAIL", "duration_s": 0.5,
                    "error_class": "other", "trace_tail": "exit 1"}
        return {"verdict": "PASS", "duration_s": 1.0}

    monkeypatch.setattr(task_runner, "_run_attempt", fake_attempt)
    json_path = tmp_path / "retry_result.json"
    rc = run_task_suite(["001-fix-div-zero"], FAKE_EXEC, tries=2,
                        json_out=json_path, model="retry-model")
    assert rc == 0
    assert seen["n"] == 2

    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["passed"] == 1
    assert doc["total"] == 1
    assert doc["pass@1"] == 0.0
    assert doc["pass@2"] == 1.0
    row = doc["rows"][0]
    assert row["verdict"] == "PASS"
    assert len(row["attempts"]) == 2
    assert row["attempts"][0]["verdict"] == "FAIL"
    assert row["attempts"][1]["verdict"] == "PASS"


def test_early_stop_on_first_pass(tmp_path, monkeypatch):
    seen = {"n": 0}

    def fake_attempt(name, record, *, timeout, verifier_image=None):
        seen["n"] += 1
        return {"verdict": "PASS", "duration_s": 0.5}

    monkeypatch.setattr(task_runner, "_run_attempt", fake_attempt)
    json_path = tmp_path / "early_stop.json"
    rc = run_task_suite(["001-fix-div-zero"], FAKE_EXEC, tries=5,
                        json_out=json_path, model="early-model")
    assert rc == 0
    assert seen["n"] == 1, "no attempt may run after the first PASS"

    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["pass@1"] == 1.0
    assert doc["pass@2"] == 1.0
    assert len(doc["rows"][0]["attempts"]) == 1


def test_error_classes_are_the_shared_six():
    # Verify the 6 error classes
    assert classify_error(timed_out=True) == "test_timeout"
    assert classify_error(error_text="Subprocess timed out") == "test_timeout"
    assert classify_error(stderr="context_length_exceeded: maximum context length is 8192") == "exhausted_context"
    assert classify_error(stdout="Could you please clarify what tests are needed?") == "user_asks"
    assert classify_error(stderr="SyntaxError: invalid syntax in calc.py line 3") == "syntax_error"
    assert classify_error(returncode=1, stdout="", stderr="") == "malformed_response"
    assert classify_error(stderr="AssertionError: assert 1 == 2") == "other"

    for cls_name in (
        "syntax_error",
        "test_timeout",
        "malformed_response",
        "exhausted_context",
        "user_asks",
        "other",
    ):
        assert cls_name in ERROR_CLASSES


@requires_runtime
def test_nonzero_executor_records_error_and_skips_verifier(tmp_path,
                                                           monkeypatch):
    # A failing executor INSIDE the boundary: the error class comes from its
    # own streams, and the trusted oracle is never launched against the
    # unfixed sandbox.
    calls = []
    real_run = container.run_confined

    def spy(argv, workdir, **kwargs):
        calls.append(list(argv))
        return real_run(argv, workdir, **kwargs)

    monkeypatch.setattr(task_runner.container, "run_confined", spy)
    record = _mounted_spec(tmp_path, {
        "fail.py": 'import sys\n'
                   'sys.stderr.write("context limit exceeded")\n'
                   'sys.exit(3)\n',
    }, "fail.py")
    attempt = task_runner._run_attempt("001-fix-div-zero", record, timeout=300)
    assert attempt["verdict"] == "FAIL"
    assert attempt["error_class"] == "exhausted_context"
    assert "context limit exceeded" in attempt["trace_tail"]
    assert len(calls) == 1, "verifier must not run after a failed executor"


def test_model_and_executor_separation(tmp_path):
    dry_json = tmp_path / "model_sep.json"
    run_task_suite(
        ["001-fix-div-zero"],
        executor_cmd="python -m custom_exec --arg 1",
        tries=1,
        model="claude-3-7-sonnet",
        dry_run=True,
        json_out=dry_json,
    )
    doc = json.loads(dry_json.read_text(encoding="utf-8"))
    assert doc["model"] == "claude-3-7-sonnet"
    assert doc["executor_name"] == "python"

    # When model is omitted / None -> unspecified
    unspec_json = tmp_path / "model_unspec.json"
    run_task_suite(
        ["001-fix-div-zero"],
        executor_cmd="claude -p -",
        tries=1,
        model=None,
        dry_run=True,
        json_out=unspec_json,
    )
    doc_unspec = json.loads(unspec_json.read_text(encoding="utf-8"))
    assert doc_unspec["model"] == "unspecified"
    assert doc_unspec["executor_name"] == "claude"


def test_resolve_cmd_is_the_shared_confined_contract():
    # The task runner reuses the harness-wide parser: blank -> None, a
    # declared docker spec -> the confinement record, any host CLI ->
    # refused before anything can launch.
    assert resolve_cmd("") is None
    assert resolve_cmd("   ") is None
    record = resolve_cmd("docker:img:tag @ro:/host:/mount @net python -c pass")
    assert record["mode"] == "container"
    assert record["image"] == "img:tag"
    assert record["argv"] == ["python", "-c", "pass"]
    assert record["mounts"] == (("/host", "/mount"),)
    assert record["network"] is True
    with pytest.raises(container.IsolationUnavailable):
        resolve_cmd("claude -p")
    with pytest.raises(container.IsolationUnavailable):
        resolve_cmd(r"C:\tools\agent.exe --flag")


def test_host_executor_spec_is_refused_before_any_attempt(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("no attempt may run for a host executor")

    monkeypatch.setattr(task_runner, "_run_attempt", boom)
    with pytest.raises(container.IsolationUnavailable):
        run_task_suite(["001-fix-div-zero"], executor_cmd="claude -p",
                       tries=1, model="host-model")


def test_live_run_requires_an_executor_spec():
    with pytest.raises(ValueError):
        run_task_suite(["001-fix-div-zero"], None, tries=1, model="m")


def test_cli_refuses_host_executor_with_exit_2(tmp_path):
    out_json = tmp_path / "cli.json"
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "task_runner.py"),
         "--executor", "claude -p", "--model", "m", "--json", str(out_json)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 2
    assert "host prompt execution refused" in r.stderr
    assert not out_json.exists()


@requires_runtime
def test_confined_timeout_output_is_classified(tmp_path, monkeypatch):
    # A killed run's streams arrive as bytes from TimeoutExpired; they must
    # be normalized to text before classification, not raise TypeError.
    monkeypatch.setattr(
        task_runner.container, "run_confined",
        lambda argv, workdir, **kwargs: {
            "rc": None, "stdout": b"partial ", "stderr": b"bytes tail",
            "timed_out": True})
    record = resolve_cmd(FAKE_EXEC)
    attempt = task_runner._run_attempt("001-fix-div-zero", record, timeout=1)
    assert attempt["verdict"] == "FAIL"
    assert attempt["error_class"] == "test_timeout"
    assert attempt["trace_tail"] == "partial \nbytes tail"


@requires_task_image
def test_confined_attempt_passes_end_to_end(tmp_path):
    """A deterministic honest executor and the real trusted oracle, both
    inside the boundary: the candidate is fixed at /work and judged from the
    read-only /verifier mount."""
    record = _mounted_spec(tmp_path, {"fix.py": FIX_001_PY}, "fix.py")
    attempt = task_runner._run_attempt("001-fix-div-zero", record,
                                       timeout=600, verifier_image=TASK_IMAGE)
    assert attempt["verdict"] == "PASS", attempt


@requires_task_image
def test_retry_gets_a_fresh_sandbox_confined(tmp_path):
    """Attempt 1 pollutes its sandbox and fails; attempt 2 refuses to run
    when the pollution survived and otherwise fixes honestly. Its PASS
    proves the second attempt really started from a pristine fixture copy."""
    scripts = {
        "poison.py":
            "import pathlib, sys\n"
            "pathlib.Path('poison.marker').write_text('polluted',\n"
            "                                         encoding='utf-8')\n"
            "sys.exit(1)\n",
        "honest.py":
            "import pathlib, sys\n"
            "if pathlib.Path('poison.marker').exists():\n"
            "    sys.exit(2)\n"
            + FIX_001_PY,
    }
    first = task_runner._run_attempt(
        "001-fix-div-zero", _mounted_spec(tmp_path, scripts, "poison.py"),
        timeout=300, verifier_image=TASK_IMAGE)
    assert first["verdict"] == "FAIL"
    second = task_runner._run_attempt(
        "001-fix-div-zero", _mounted_spec(tmp_path, scripts, "honest.py"),
        timeout=600, verifier_image=TASK_IMAGE)
    assert second["verdict"] == "PASS", second


@requires_task_image
def test_candidate_cannot_rewrite_the_oracle(tmp_path):
    """The executor runs before its judge and tries to overwrite verify.py
    through the read-only /verifier mount. The unwritable mount keeps the
    oracle pristine: the unfixed sandbox is still rejected and the host copy
    is byte-identical afterwards."""
    verify_path = task_runner.TASKS / "001-fix-div-zero" / "verify.py"
    before = verify_path.read_bytes()
    hack = (
        "import pathlib, sys\n"
        "always_pass = 'import sys\\nprint(\"PASS\")\\nsys.exit(0)\\n'\n"
        "for target in (\n"
        "        pathlib.Path('/verifier/001-fix-div-zero/verify.py'),\n"
        "        pathlib.Path('/work/../verifier/001-fix-div-zero/verify.py')):\n"
        "    try:\n"
        "        target.write_text(always_pass, encoding='utf-8')\n"
        "    except OSError:\n"
        "        pass\n"
        "sys.exit(0)\n")
    record = _mounted_spec(tmp_path, {"hack.py": hack}, "hack.py")
    attempt = task_runner._run_attempt("001-fix-div-zero", record,
                                       timeout=600, verifier_image=TASK_IMAGE)
    assert attempt["verdict"] == "FAIL", attempt
    assert verify_path.read_bytes() == before


@requires_runtime
def test_executor_launch_error_records_truthful_fail(tmp_path):
    # A nonexistent executable inside the image fails at launch (rc != 0).
    # The runner must record a truthful FAIL (error_class=other, bounded
    # trace), honor tries, continue across tasks, and persist the requested
    # result — nothing ever runs on the host.
    json_path = tmp_path / "oserror.json"
    rc = run_task_suite(
        ["001-fix-div-zero", "002-add-validation"],
        executor_cmd=f"docker:{EXEC_IMAGE} definitely-not-a-real-executable-xyz",
        tries=2,
        json_out=json_path,
        model="failing-model",
    )
    assert rc == 1
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["kind"] == "tasks"
    assert doc["total"] == 2
    assert doc["passed"] == 0
    assert len(doc["rows"]) == 2
    for row in doc["rows"]:
        assert row["verdict"] == "FAIL"
        assert len(row["attempts"]) == 2
        for attempt in row["attempts"]:
            assert attempt["verdict"] == "FAIL"
            assert attempt["error_class"] == "other"
            assert "trace_tail" in attempt


def test_run_task_suite_rejects_live_persistence_without_model(tmp_path):
    json_path = tmp_path / "nomodel.json"
    try:
        run_task_suite(
            ["001-fix-div-zero"],
            executor_cmd="python -m custom_exec",
            json_out=json_path,
            model=None,
        )
    except ValueError as exc:
        assert "model" in str(exc)
    else:
        raise AssertionError("live persistence without --model must raise ValueError")
    assert not json_path.exists()

    # dry-run with json and no model remains permitted (unspecified)
    dry_json = tmp_path / "dry.json"
    rc = run_task_suite(["001-fix-div-zero"], None, dry_run=True, json_out=dry_json)
    assert rc == 0
    assert json.loads(dry_json.read_text(encoding="utf-8"))["model"] == "unspecified"


def test_cli_rejects_live_json_without_model(tmp_path):
    out_json = tmp_path / "cli.json"
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "task_runner.py"),
         "--executor", "claude -p", "--json", str(out_json)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r.returncode == 2
    assert "--model" in r.stderr
    assert not out_json.exists()


def test_verify_rejects_malicious_conftest_bypass(tmp_path):
    # A candidate that fixes calc.py but adds no regression test can, if the
    # oracle copies the whole sandbox and honors plugin autoload, plant a
    # conftest.py that manufactures "tests fail on pristine/reverted" via a
    # pytest startup hook. The hardened oracles copy only test_calc.py and
    # run --noconftest, so every task must reject this bypass with rc 1.
    fixed_calc = {
        "001-fix-div-zero": (
            'def divide(a, b):\n'
            '    if b == 0:\n'
            '        raise ValueError("division by zero")\n'
            '    return a / b\n\n'
            'def parse_int(s):\n'
            '    return int(s)\n\n'
            'def clamp(v, lo, hi):\n'
            '    if lo > v < hi:\n'
            '        return hi\n'
            '    return v\n'
        ),
        "002-add-validation": (
            'def divide(a, b):\n'
            '    return a / b\n\n'
            'def parse_int(s):\n'
            '    s = str(s).strip()\n'
            '    try:\n'
            '        return int(s)\n'
            '    except ValueError:\n'
            '        raise ValueError(f"not an integer: {s}")\n\n'
            'def clamp(v, lo, hi):\n'
            '    if lo > v < hi:\n'
            '        return hi\n'
            '    return v\n'
        ),
        "003-regression-guard": (
            'def divide(a, b):\n'
            '    return a / b\n\n'
            'def parse_int(s):\n'
            '    return int(s)\n\n'
            'def clamp(v, lo, hi):\n'
            '    if v < lo:\n'
            '        return lo\n'
            '    if v > hi:\n'
            '        return hi\n'
            '    return v\n'
        ),
    }
    evil_conftest = {
        "001-fix-div-zero": (
            'import importlib.util\n'
            'from pathlib import Path\n\n\n'
            'def pytest_configure(config):\n'
            '    calc = Path(__file__).resolve().parent / "calc.py"\n'
            '    spec = importlib.util.spec_from_file_location("calc", str(calc))\n'
            '    mod = importlib.util.module_from_spec(spec)\n'
            '    spec.loader.exec_module(mod)\n'
            '    try:\n'
            '        mod.divide(1, 0)\n'
            '    except ZeroDivisionError:\n'
            '        raise RuntimeError("manufactured failure: divide not fixed")\n'
            '    except ValueError:\n'
            '        pass\n'
        ),
        "002-add-validation": (
            'import importlib.util\n'
            'from pathlib import Path\n\n\n'
            'def pytest_configure(config):\n'
            '    calc = Path(__file__).resolve().parent / "calc.py"\n'
            '    spec = importlib.util.spec_from_file_location("calc", str(calc))\n'
            '    mod = importlib.util.module_from_spec(spec)\n'
            '    spec.loader.exec_module(mod)\n'
            '    try:\n'
            '        mod.parse_int("abc")\n'
            '    except ValueError as e:\n'
            '        if "not an integer" not in str(e):\n'
            '            raise RuntimeError("manufactured failure: parse_int not fixed")\n'
        ),
        "003-regression-guard": (
            'import importlib.util\n'
            'from pathlib import Path\n\n\n'
            'def pytest_configure(config):\n'
            '    calc = Path(__file__).resolve().parent / "calc.py"\n'
            '    spec = importlib.util.spec_from_file_location("calc", str(calc))\n'
            '    mod = importlib.util.module_from_spec(spec)\n'
            '    spec.loader.exec_module(mod)\n'
            '    if mod.clamp(-5, 0, 10) != 0:\n'
            '        raise RuntimeError("manufactured failure: clamp not fixed")\n'
        ),
    }

    for task, code in fixed_calc.items():
        sb = tmp_path / ("evil_" + task)
        shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb)
        (sb / "calc.py").write_text(code, encoding="utf-8", newline="\n")
        (sb / "conftest.py").write_text(evil_conftest[task], encoding="utf-8", newline="\n")
        v = ROOT / "eval" / "tasks" / task / "verify.py"
        r = subprocess.run(
            [sys.executable, str(v), str(sb)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert r.returncode == 1, f"{task} must reject malicious conftest bypass: {r.stdout} {r.stderr}"


def test_verify_rejects_source_introspection_bypass(tmp_path):
    # A candidate that fixes calc.py but "verifies" the fix by reading
    # implementation source, files, or bytecode metadata instead of asserting
    # observable behavior must be rejected by the AST audit before any
    # behavior or mutation check runs. Three distinct vectors, one per oracle.
    fixed_calc = {
        "001-fix-div-zero": (
            'def divide(a, b):\n'
            '    if b == 0:\n'
            '        raise ValueError("division by zero")\n'
            '    return a / b\n\n'
            'def parse_int(s):\n'
            '    return int(s)\n\n'
            'def clamp(v, lo, hi):\n'
            '    if lo > v < hi:\n'
            '        return hi\n'
            '    return v\n'
        ),
        "002-add-validation": (
            'def divide(a, b):\n'
            '    return a / b\n\n'
            'def parse_int(s):\n'
            '    s = str(s).strip()\n'
            '    try:\n'
            '        return int(s)\n'
            '    except ValueError:\n'
            '        raise ValueError(f"not an integer: {s}")\n\n'
            'def clamp(v, lo, hi):\n'
            '    if lo > v < hi:\n'
            '        return hi\n'
            '    return v\n'
        ),
        "003-regression-guard": (
            'def divide(a, b):\n'
            '    return a / b\n\n'
            'def parse_int(s):\n'
            '    return int(s)\n\n'
            'def clamp(v, lo, hi):\n'
            '    if v < lo:\n'
            '        return lo\n'
            '    if v > hi:\n'
            '        return hi\n'
            '    return v\n'
        ),
    }
    introspecting_tests = {
        # source text via inspect alias
        "001-fix-div-zero": (
            'from calc import divide\n'
            'import inspect as insp\n\n\n'
            'def test_divide_by_zero():\n'
            '    assert "division by zero" in insp.getsource(divide)\n'
        ),
        # file read via read_text
        "002-add-validation": (
            'from calc import parse_int\n'
            'from pathlib import Path\n\n\n'
            'def test_parse_int_whitespace():\n'
            '    assert "strip" in Path("calc.py").read_text()\n'
        ),
        # bytecode metadata via __code__
        "003-regression-guard": (
            'from calc import clamp\n\n\n'
            'def test_clamp_bounds():\n'
            '    assert len(clamp.__code__.co_code) > 10\n'
        ),
    }
    for task, calc_code in fixed_calc.items():
        sb = tmp_path / ("introspect_" + task)
        shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb)
        (sb / "calc.py").write_text(calc_code, encoding="utf-8", newline="\n")
        (sb / "test_calc.py").write_text(
            introspecting_tests[task], encoding="utf-8", newline="\n"
        )
        v = ROOT / "eval" / "tasks" / task / "verify.py"
        r = subprocess.run(
            [sys.executable, str(v), str(sb)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert r.returncode == 1, f"{task} must reject source-introspection bypass: {r.stdout} {r.stderr}"

    # New vectors the shared guard must also reject: pathlib.Path.open() with
    # a chained .read(), io.open().read(), and a chained stream read, plus a
    # required regression test hidden under `if False` (never collectable).
    read_bypass_tests = {
        "001-fix-div-zero": (
            'from calc import divide\n'
            'from pathlib import Path\n\n\n'
            'if False:\n'
            '    def test_divide_by_zero():\n'
            '        import pytest\n'
            '        with pytest.raises(ValueError):\n'
            '            divide(1, 0)\n\n\n'
            'def test_source_branch():\n'
            '    if "division by zero" in Path("calc.py").open().read():\n'
            '        assert True\n'
            '    else:\n'
            '        assert False\n'
        ),
        "002-add-validation": (
            'from calc import parse_int\n'
            'import io\n\n\n'
            'def test_parse_int_whitespace():\n'
            '    if "strip" in io.open("calc.py").read():\n'
            '        assert parse_int(" 42 ") == 42\n'
            '    else:\n'
            '        assert False\n'
        ),
        "003-regression-guard": (
            'from calc import clamp\n\n\n'
            'def test_clamp_bounds():\n'
            '    if "return lo" in open("calc.py").readlines()[0]:\n'
            '        assert clamp(-5, 0, 10) == 0\n'
            '    else:\n'
            '        assert False\n'
        ),
    }
    nested_expected = {"001-fix-div-zero": "missing def test_divide_by_zero"}
    for task, calc_code in fixed_calc.items():
        sb = tmp_path / ("fileread_" + task)
        shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb)
        (sb / "calc.py").write_text(calc_code, encoding="utf-8", newline="\n")
        (sb / "test_calc.py").write_text(
            read_bypass_tests[task], encoding="utf-8", newline="\n"
        )
        v = ROOT / "eval" / "tasks" / task / "verify.py"
        r = subprocess.run(
            [sys.executable, str(v), str(sb)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        out = r.stdout + r.stderr
        assert r.returncode == 1, f"{task} must reject file-read/nested bypass: {out}"
        assert "forbidden" in out, f"{task} audit must flag the file read: {out}"
        if task in nested_expected:
            assert nested_expected[task] in out, f"{task} audit must reject nested test: {out}"


def test_verify_rejects_partial_behavior_coverage(tmp_path):
    # Task 002 requires BOTH whitespace-success and non-numeric ValueError;
    # task 003 requires BOTH a v<lo->lo and a v>hi->hi boundary. A single
    # covered branch (which would satisfy the mutation checks) must still be
    # rejected by the structural AST audit.
    sb2 = tmp_path / "partial_002"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb2)
    (sb2 / "calc.py").write_text(
        (sb2 / "calc.py").read_text(encoding="utf-8").replace(
            "def parse_int(s):\n    return int(s)",
            'def parse_int(s):\n    s = str(s).strip()\n'
            '    try:\n        return int(s)\n'
            '    except ValueError:\n'
            '        raise ValueError(f"not an integer: {s}")',
        ),
        encoding="utf-8",
        newline="\n",
    )
    (sb2 / "test_calc.py").write_text(
        (sb2 / "test_calc.py").read_text(encoding="utf-8")
        + '\n\ndef test_parse_int_whitespace():\n    assert parse_int(" 42 ") == 42\n',
        encoding="utf-8",
        newline="\n",
    )
    r2 = subprocess.run(
        [
            sys.executable,
            str(ROOT / "eval" / "tasks" / "002-add-validation" / "verify.py"),
            str(sb2),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r2.returncode == 1, f"002 whitespace-only must fail verify: {r2.stdout} {r2.stderr}"

    sb3 = tmp_path / "partial_003"
    shutil.copytree(ROOT / "eval" / "tasks" / "repo-fixture", sb3)
    (sb3 / "calc.py").write_text(
        (sb3 / "calc.py").read_text(encoding="utf-8").replace(
            "def clamp(v, lo, hi):\n    if lo > v < hi:\n        return hi\n    return v",
            "def clamp(v, lo, hi):\n    if v < lo:\n        return lo\n"
            "    if v > hi:\n        return hi\n    return v",
        ),
        encoding="utf-8",
        newline="\n",
    )
    (sb3 / "test_calc.py").write_text(
        (sb3 / "test_calc.py").read_text(encoding="utf-8")
        + '\n\ndef test_clamp_low():\n    assert clamp(-5, 0, 10) == 0\n',
        encoding="utf-8",
        newline="\n",
    )
    r3 = subprocess.run(
        [
            sys.executable,
            str(ROOT / "eval" / "tasks" / "003-regression-guard" / "verify.py"),
            str(sb3),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert r3.returncode == 1, f"003 lo-only must fail verify: {r3.stdout} {r3.stderr}"
