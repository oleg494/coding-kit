"""Consumer-visible handoff boundaries; all data stays inside tmp_path."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

CLI = Path(__file__).resolve().parents[1] / "scripts/tools/handoff.py"


def invoke(*args):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)


def seed(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (workspace / "policy.txt").write_text("Keep public API stable.\n", encoding="utf-8")
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({
        "goal": "Finish actual implementation", "acceptance": ["CLI preserves data"],
        "constraints": ["Do not deploy"], "pending": ["Exercise changed behavior"],
        "observations": [
            {"claim": "Current value is one", "paths": ["module.py"]},
            {"claim": "Public API must stay stable", "paths": ["policy.txt"]},
        ]}), encoding="utf-8")
    output = tmp_path / "handoff.json"
    return workspace, brief, output


def capture(workspace, brief, output):
    return invoke("capture", "--workspace", workspace, "--brief", brief, "--output", output)


def resume(workspace, output):
    return invoke("resume", "--workspace", workspace, "--handoff", output, "--json")


def test_resume_marks_changed_evidence_without_losing_mission(tmp_path):
    workspace, brief, output = seed(tmp_path)
    result = capture(workspace, brief, output)
    assert result.returncode == 0, result.stdout + result.stderr
    original = output.read_bytes()
    (workspace / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    result = resume(workspace, output)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["goal"] == "Finish actual implementation"
    assert report["acceptance"] == ["CLI preserves data"]
    assert report["constraints"] == ["Do not deploy"]
    assert report["pending"] == ["Exercise changed behavior"]
    observations = {row["claim"]: row for row in report["observations"]}
    assert observations["Current value is one"]["status"] == "stale"
    assert observations["Current value is one"]["changed_paths"] == ["module.py"]
    assert observations["Public API must stay stable"]["status"] == "unchanged"
    assert output.read_bytes() == original


def test_missing_evidence_is_drift_not_current(tmp_path):
    workspace, brief, output = seed(tmp_path)
    assert capture(workspace, brief, output).returncode == 0
    (workspace / "module.py").unlink()
    result = resume(workspace, output)
    assert result.returncode == 1, result.stdout + result.stderr
    files = {row["path"]: row["status"] for row in json.loads(result.stdout)["files"]}
    assert files == {"module.py": "missing", "policy.txt": "unchanged"}


def test_capture_never_overwrites_prior_handoff(tmp_path):
    workspace, brief, output = seed(tmp_path)
    assert capture(workspace, brief, output).returncode == 0
    original = output.read_bytes()
    (workspace / "module.py").write_text("CHANGED\n", encoding="utf-8")
    assert capture(workspace, brief, output).returncode == 2
    assert output.read_bytes() == original


@pytest.mark.parametrize("path", ["../outside.txt", "C:/outside.txt", "//host/share/file", "module.py:stream", ".git/config", ".autonomous/state.json"])
def test_capture_rejects_unsafe_references(tmp_path, path):
    workspace, brief, output = seed(tmp_path)
    data = json.loads(brief.read_text(encoding="utf-8"))
    data["observations"][0]["paths"] = [path]
    brief.write_text(json.dumps(data), encoding="utf-8")
    result = capture(workspace, brief, output)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not output.exists()
    assert "Traceback" not in result.stderr


def test_wrong_workspace_and_corrupt_manifest_never_resume(tmp_path):
    workspace, brief, output = seed(tmp_path)
    assert capture(workspace, brief, output).returncode == 0
    elsewhere = tmp_path / "other"
    elsewhere.mkdir()
    assert resume(elsewhere, output).returncode == 2
    output.write_text('{"version": true}', encoding="utf-8")
    result = resume(workspace, output)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_symlink_swap_cannot_read_outside_workspace(tmp_path):
    workspace, brief, output = seed(tmp_path)
    assert capture(workspace, brief, output).returncode == 0
    outside = tmp_path / "private.txt"
    outside.write_text("PRIVATE SENTINEL", encoding="utf-8")
    target = workspace / "module.py"
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = resume(workspace, output)
    assert result.returncode == 1, result.stdout + result.stderr
    files = {row["path"]: row["status"] for row in json.loads(result.stdout)["files"]}
    assert files["module.py"] == "unsafe"
    assert "PRIVATE SENTINEL" not in result.stdout


def test_relative_workspace_cannot_rebind_manifest(tmp_path):
    workspace, brief, output = seed(tmp_path)
    assert capture(workspace, brief, output).returncode == 0
    manifest = json.loads(output.read_text(encoding="utf-8"))
    manifest["workspace"] = "."
    output.write_text(json.dumps(manifest), encoding="utf-8")
    result = subprocess.run([sys.executable, str(CLI), "resume", "--workspace", ".",
                             "--handoff", str(output)], cwd=workspace,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_nested_json_is_cleanly_rejected(tmp_path):
    workspace, brief, output = seed(tmp_path)
    output.write_text('{"goal":' + '[' * 2000 + '0' + ']' * 2000 + '}', encoding="utf-8")
    result = resume(workspace, output)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_report_cannot_emit_terminal_escape_sequences(tmp_path):
    workspace, brief, output = seed(tmp_path)
    data = json.loads(brief.read_text(encoding="utf-8"))
    data["goal"] = "Keep evidence visible\u001b[2J"
    brief.write_text(json.dumps(data), encoding="utf-8")
    assert capture(workspace, brief, output).returncode == 0
    result = invoke("resume", "--workspace", workspace, "--handoff", output)
    assert result.returncode == 0
    assert "\u001b" not in result.stdout
    assert "Keep evidence visible" in result.stdout
