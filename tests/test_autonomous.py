"""Real subprocess checks; all executor/verifier writes stay in tmp_path."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "scripts/tools/autonomous.py"


def command(path):
    return f'"{sys.executable}" "{path}"'


def setup_run(tmp_path, body, verify="assert Path('result').read_text() == 'correct'\n"):
    executor = tmp_path / "executor.py"
    executor.write_text(
        "import json, os, sys, time\nfrom pathlib import Path\n"
        "prompt = sys.stdin.read()\n"
        "counter = Path('calls')\n"
        "n = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(n))\n"
        "def checkpoint(status='complete', summary='worked', next_action=''):\n"
        "    Path(os.environ['AUTONOMOUS_CHECKPOINT']).write_text(json.dumps({\n"
        "        'status': status, 'summary': summary, 'next_action': next_action,\n"
        "        'evidence': ['executor observation']}), encoding='utf-8')\n" + body,
        encoding="utf-8",
    )
    verifier = tmp_path / "verifier.py"
    verifier.write_text("from pathlib import Path\n" + verify, encoding="utf-8")
    return [sys.executable, str(RUNNER), "--workspace", str(tmp_path),
            "--mission", "Produce correct result", "--executor", command(executor),
            "--verify", command(verifier), "--max-iterations", "4", "--timeout", "10"]


def run(args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=30)


def state_of(tmp_path):
    return json.loads((tmp_path / ".autonomous/state.json").read_text(encoding="utf-8"))


def test_false_completion_retries_with_verifier_feedback(tmp_path):
    args = setup_run(tmp_path, "if n == 2:\n    assert 'AssertionError' in prompt\n"
                     "Path('result').write_text('wrong' if n == 1 else 'correct')\ncheckpoint()\n")
    result = run(args)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "calls").read_text() == "2"
    assert (tmp_path / "result").read_text() == "correct"


def test_iteration_limit_resumes_progress_and_rechecks_completed_state(tmp_path):
    args = setup_run(tmp_path, "if n == 1:\n    checkpoint('continue', 'first part', 'finish result')\n"
                     "else:\n    Path('result').write_text('correct')\n    checkpoint()\n")
    args[args.index("--max-iterations") + 1] = "1"
    first = run(args)
    assert first.returncode == 1, first.stdout + first.stderr
    assert (tmp_path / ".autonomous/state.json").exists()
    second = run(args)
    assert second.returncode == 0, second.stdout + second.stderr
    (tmp_path / "result").write_text("regression")
    third = run(args)
    assert third.returncode == 0, third.stdout + third.stderr
    assert (tmp_path / "result").read_text() == "correct"
    assert (tmp_path / "calls").read_text() == "3"


@pytest.mark.parametrize("body", [
    "checkpoint()\nsys.exit(9)\n",
    "pass\n",
    "Path(os.environ['AUTONOMOUS_CHECKPOINT']).write_text('{broken')\n",
    "checkpoint('continue', next_action='')\n",
    "checkpoint('blocked', 'missing authorization')\n",
])
def test_failed_or_invalid_executor_stops_without_retry(tmp_path, body):
    result = run(setup_run(tmp_path, body))
    assert result.returncode == 1, result.stdout + result.stderr
    assert (tmp_path / "calls").read_text() == "1"


def test_unchanged_checkpoint_stalls_instead_of_looping(tmp_path):
    result = run(setup_run(tmp_path, "checkpoint('continue', 'same', 'same action')\n"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert (tmp_path / "calls").read_text() == "3"


def test_resume_configuration_mismatch_never_launches_executor(tmp_path):
    args = setup_run(tmp_path, "checkpoint('blocked', 'missing input')\n")
    assert run(args).returncode == 1
    args[args.index("--mission") + 1] = "Different authority"
    result = run(args)
    assert result.returncode == 1, result.stdout + result.stderr
    assert (tmp_path / "calls").read_text() == "1"


def test_stop_before_spawn_has_no_executor_side_effect(tmp_path):
    args = setup_run(tmp_path, "checkpoint()\n")
    state = tmp_path / ".autonomous"
    state.mkdir()
    (state / "STOP").touch()
    result = run(args)
    assert result.returncode == 130, result.stdout + result.stderr
    assert not (tmp_path / "calls").exists()


@pytest.mark.parametrize("phase", ["executor", "verifier"])
def test_stop_interrupts_active_child(tmp_path, phase):
    sleeping = "Path('ready').touch()\ntime.sleep(20)\nPath('escaped').touch()\n"
    body = sleeping if phase == "executor" else "checkpoint()\n"
    verify = "import time\n" + sleeping if phase == "verifier" else "assert False\n"
    args = setup_run(tmp_path, body, verify)
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        deadline = time.monotonic() + 10
        while not (tmp_path / "ready").exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        try:
            assert (tmp_path / "ready").exists(), "child never reached ready marker"
            (tmp_path / ".autonomous/STOP").touch()
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 130, (stdout, stderr)
            assert not (tmp_path / "escaped").exists()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_timeout_is_failure_not_completion(tmp_path):
    args = setup_run(tmp_path, "time.sleep(20)\ncheckpoint()\n")
    args[args.index("--timeout") + 1] = "1"
    result = run(args)
    assert result.returncode == 1, result.stdout + result.stderr
    assert (tmp_path / "calls").read_text() == "1"


def test_stop_interrupts_child_that_never_reads_large_prompt(tmp_path):
    args = setup_run(tmp_path, "checkpoint()\n")
    args[args.index("--mission") + 1] = "x" * 20000
    (tmp_path / "executor.py").write_text(
        "import time\nfrom pathlib import Path\n"
        "Path('ready').touch()\ntime.sleep(20)\nPath('escaped').touch()\n",
        encoding="utf-8")
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        deadline = time.monotonic() + 10
        while not (tmp_path / "ready").exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        try:
            assert (tmp_path / "ready").exists(), "child never reached ready marker"
            (tmp_path / ".autonomous/STOP").touch()
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == 130, (stdout, stderr)
            assert not (tmp_path / "escaped").exists()
        finally:
            if process.poll() is None:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                               capture_output=True) if os.name == "nt" else process.kill()
                process.wait()


def test_state_is_durable_before_every_executor_spawn(tmp_path):
    args = setup_run(
        tmp_path,
        "state = json.loads(Path(os.environ['AUTONOMOUS_STATE_DIR'] + '/state.json').read_text())\n"
        "assert state['version'] == 1\n"
        "assert state['status'] == 'running'\n"
        "assert state['iterations'] == int(os.environ['AUTONOMOUS_ITERATION'])\n"
        "assert state['config']['mission'] == 'Produce correct result'\n"
        "assert state['last_checkpoint'] is None\n"
        "assert state['verification']['passed'] is None\n"
        "Path('result').write_text('correct')\n"
        "checkpoint()\n")
    result = run(args)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "calls").read_text() == "1"


def test_state_records_incremented_iteration_and_progress_before_spawn(tmp_path):
    args = setup_run(
        tmp_path,
        "state = json.loads(Path(os.environ['AUTONOMOUS_STATE_DIR'] + '/state.json').read_text())\n"
        "assert state['version'] == 1\n"
        "assert state['status'] == 'running'\n"
        "assert state['iterations'] == 1\n"
        "assert state['last_checkpoint'] is None\n"
        "checkpoint('continue', 'first part', 'finish result')\n")
    args[args.index("--max-iterations") + 1] = "1"
    result = run(args)
    assert result.returncode == 1, result.stdout + result.stderr
    state = state_of(tmp_path)
    assert state["iterations"] == 1
    assert state["last_checkpoint"]["status"] == "continue"
    assert state["recent_signatures"], "normalized checkpoint signature is durable"
    assert state["status"] == "exhausted"


def test_resume_persists_incremented_iteration_before_second_spawn(tmp_path):
    args = setup_run(
        tmp_path,
        "state = json.loads(Path(os.environ['AUTONOMOUS_STATE_DIR'] + '/state.json').read_text())\n"
        "if n == 1:\n"
        "    checkpoint('continue', 'first part', 'finish result')\n"
        "else:\n"
        "    assert state['iterations'] == 2, state\n"
        "    assert state['last_checkpoint']['status'] == 'continue', state\n"
        "    Path('result').write_text('correct')\n"
        "    checkpoint()\n")
    args[args.index("--max-iterations") + 1] = "1"
    assert run(args).returncode == 1
    second = run(args)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (tmp_path / "calls").read_text() == "2"


@pytest.mark.parametrize("name,mutate", [
    ("wrong version", lambda s: s.update(version=2)),
    ("missing version", lambda s: s.pop("version")),
    ("iterations bool", lambda s: s.update(iterations=True)),
    ("iterations negative", lambda s: s.update(iterations=-1)),
    ("iterations string", lambda s: s.update(iterations="3")),
    ("unsupported status", lambda s: s.update(status="paused")),
    ("missing status", lambda s: s.pop("status")),
    ("config not object", lambda s: s.update(config=[])),
    ("config missing identity key", lambda s: s["config"].pop("verify")),
    ("config identity not string", lambda s: s["config"].update(mission=17)),
    ("verification missing key", lambda s: s["verification"].pop("exit_code")),
    ("verification passed not bool", lambda s: s["verification"].update(passed="yes")),
    ("verification exit_code string", lambda s: s["verification"].update(exit_code="0")),
    ("last_checkpoint bad status", lambda s: s.update(
        last_checkpoint={"status": "nope", "summary": "x", "next_action": "", "evidence": []})),
    ("last_checkpoint not object", lambda s: s.update(last_checkpoint="summary")),
    ("recent_signatures not list", lambda s: s.update(recent_signatures={})),
    ("recent_signatures non string item", lambda s: s.update(recent_signatures=[1])),
    ("state_dir not string", lambda s: s.update(state_dir=1)),
    ("not a json object", lambda s: None),
])
def test_corrupt_saved_state_is_rejected_cleanly_and_left_unchanged(tmp_path, name, mutate):
    args = setup_run(tmp_path, "checkpoint('blocked', 'missing input')\n")
    assert run(args).returncode == 1
    state_path = tmp_path / ".autonomous/state.json"
    doc = json.loads(state_path.read_text(encoding="utf-8"))
    mutate(doc)
    payload = "[]" if name == "not a json object" else json.dumps(doc, indent=2) + "\n"
    state_path.write_text(payload, encoding="utf-8")
    before = state_path.read_bytes()

    result = run(args)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "autonomous:" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert state_path.read_bytes() == before, "rejected state must not be rewritten"
    assert (tmp_path / "calls").read_text() == "1", "no executor launch on rejected state"


def test_valid_version_one_state_with_progress_resumes(tmp_path):
    args = setup_run(tmp_path, "Path('result').write_text('correct')\ncheckpoint()\n")
    assert run(args).returncode == 0
    state_path = tmp_path / ".autonomous/state.json"
    doc = json.loads(state_path.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    doc.update(status="running", iterations=7, updated_at="2026-09-08T00:00:00")
    doc["last_checkpoint"] = {"status": "continue", "summary": "prior progress",
                              "next_action": "finish", "evidence": ["prior"]}
    doc["recent_signatures"] = ['{"status": "continue"}']
    state_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    result = run(args)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "calls").read_text() == "2"
    assert state_of(tmp_path)["iterations"] == 8
