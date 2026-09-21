"""Execute the supervisor across process boundaries with evidence drift."""
import json
from pathlib import Path
import subprocess
import sys

from test_autonomous import run, setup_run, state_of

HANDOFF = Path(__file__).resolve().parents[1] / "scripts/tools/handoff.py"


def make_handoff(tmp_path):
    (tmp_path / "design.txt").write_text("original", encoding="utf-8")
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"goal": "Preserve actual task context",
        "acceptance": ["Result respects current design"],
        "constraints": ["Preserve user changes"], "pending": ["Finish implementation"],
        "observations": [{"claim": "Design was original", "paths": ["design.txt"]}]}), encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    captured = subprocess.run([sys.executable, str(HANDOFF), "capture",
        "--workspace", str(tmp_path), "--brief", str(brief), "--output", str(handoff)],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert captured.returncode == 0, captured.stdout + captured.stderr
    return handoff


def test_new_process_receives_drift_and_preserves_changed_design(tmp_path):
    handoff = make_handoff(tmp_path)
    args = setup_run(tmp_path,
        "assert 'Preserve actual task context' in prompt\n"
        "assert 'Preserve user changes' in prompt\n"
        "if n == 1:\n"
        "    checkpoint('continue', 'inspected design', 'finish implementation')\n"
        "else:\n"
        "    assert 'stale' in prompt.lower()\n"
        "    assert 'design.txt' in prompt\n"
        "    Path('result').write_text(Path('design.txt').read_text())\n"
        "    checkpoint()\n",
        verify="assert Path('result').read_text() == 'changed by user'\n")
    args[args.index("--max-iterations") + 1] = "1"
    args += ["--handoff", str(handoff)]
    first = run(args)
    assert first.returncode == 1, first.stdout + first.stderr
    (tmp_path / "design.txt").write_text("changed by user", encoding="utf-8")
    second = run(args)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (tmp_path / "result").read_text() == "changed by user"
    assert (tmp_path / "design.txt").read_text() == "changed by user"
    assert state_of(tmp_path)["verification"]["passed"] is True


def test_invalid_handoff_never_launches_child(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{broken", encoding="utf-8")
    args = setup_run(tmp_path, "Path('result').write_text('correct')\ncheckpoint()\n")
    result = run(args + ["--handoff", str(bad)])
    assert result.returncode != 0
    assert not (tmp_path / "calls").exists()
    assert "Traceback" not in result.stderr


def test_resume_cannot_drop_handoff_binding(tmp_path):
    handoff = make_handoff(tmp_path)
    args = setup_run(tmp_path, "checkpoint('blocked', 'external prerequisite')\n")
    first = run(args + ["--handoff", str(handoff)])
    assert first.returncode == 1
    prior = (tmp_path / ".autonomous/state.json").read_bytes()
    second = run(args)
    assert second.returncode == 1
    assert (tmp_path / "calls").read_text() == "1"
    assert (tmp_path / ".autonomous/state.json").read_bytes() == prior


def test_adding_handoff_on_resume_is_mismatch(tmp_path):
    handoff = make_handoff(tmp_path)
    args = setup_run(tmp_path, "checkpoint('blocked', 'external prerequisite')\n")
    assert run(args).returncode == 1
    prior = (tmp_path / ".autonomous/state.json").read_bytes()
    result = run(args + ["--handoff", str(handoff)])
    assert result.returncode == 1
    assert (tmp_path / ".autonomous/state.json").read_bytes() == prior
    assert "Traceback" not in result.stderr


def test_swapped_handoff_path_on_resume_is_mismatch(tmp_path):
    handoff = make_handoff(tmp_path)
    other = tmp_path / "other.json"
    other.write_bytes(handoff.read_bytes())
    args = setup_run(tmp_path, "checkpoint('blocked', 'external prerequisite')\n")
    assert run(args + ["--handoff", str(handoff)]).returncode == 1
    prior = (tmp_path / ".autonomous/state.json").read_bytes()
    result = run(args + ["--handoff", str(other)])
    assert result.returncode == 1
    assert (tmp_path / ".autonomous/state.json").read_bytes() == prior


def test_bound_handoff_corrupted_between_runs_never_launches_child(tmp_path):
    handoff = make_handoff(tmp_path)
    args = setup_run(tmp_path, "checkpoint('blocked', 'external prerequisite')\n")
    assert run(args + ["--handoff", str(handoff)]).returncode == 1
    prior = (tmp_path / ".autonomous/state.json").read_bytes()
    handoff.write_text("{broken", encoding="utf-8")
    result = run(args + ["--handoff", str(handoff)])
    assert result.returncode == 1
    assert (tmp_path / "calls").read_text() == "1"
    assert (tmp_path / ".autonomous/state.json").read_bytes() == prior
    assert "Traceback" not in result.stderr


def test_supervisor_rejects_wrong_workspace_handoff(tmp_path):
    other_ws = tmp_path / "other"
    other_ws.mkdir()
    (other_ws / "design.txt").write_text("original", encoding="utf-8")
    brief = tmp_path / "foreign-brief.json"
    brief.write_text(json.dumps({"goal": "Foreign task",
        "acceptance": ["never"], "constraints": [], "pending": ["never"],
        "observations": [{"claim": "foreign evidence", "paths": ["design.txt"]}]}),
        encoding="utf-8")
    foreign = tmp_path / "foreign.json"
    captured = subprocess.run([sys.executable, str(HANDOFF), "capture",
        "--workspace", str(other_ws), "--brief", str(brief), "--output", str(foreign)],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert captured.returncode == 0, captured.stdout + captured.stderr
    args = setup_run(tmp_path, "Path('result').write_text('correct')\ncheckpoint()\n")
    result = run(args + ["--handoff", str(foreign)])
    assert result.returncode == 1
    assert "different workspace" in result.stderr
    assert not (tmp_path / "calls").exists()
    assert "Traceback" not in result.stderr
