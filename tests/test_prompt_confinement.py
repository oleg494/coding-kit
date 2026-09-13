"""Execution boundaries must reject host commands before they run."""
import sys

import pytest

from eval import runner


def test_prompt_rejects_host_write(tmp_path):
    marker = tmp_path / "outside.txt"
    command = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('escaped')"]
    with pytest.raises(RuntimeError):
        runner.run_prompt(command, "fixture", timeout=10)
    assert not marker.exists()


def test_confined_prompt_cannot_read_host_secret(tmp_path, monkeypatch):
    from rigor import container

    status = container.docker_status()
    if not status["available"]:
        pytest.skip(status["reason"])
    secret = tmp_path / "secret.txt"
    secret.write_text("private-fixture", encoding="utf-8")
    monkeypatch.setenv("KIT_PRIVATE_FIXTURE", "private-fixture")
    code = (
        "import os,sys; from pathlib import Path; "
        f"assert not Path({str(secret)!r}).exists(); "
        "assert 'KIT_PRIVATE_FIXTURE' not in os.environ; "
        "print(sys.stdin.read().upper())"
    )
    record = runner.resolve_cmd("docker:python:3.12-alpine python")
    record["argv"] = ["python", "-c", code]
    assert runner.run_prompt(record, "container evidence", timeout=30) == "CONTAINER EVIDENCE"


def test_prompt_backend_unavailable_never_launches(monkeypatch):
    from rigor import container

    monkeypatch.setattr(container, "docker_status", lambda **kwargs: {
        "available": False, "reason": "fixture offline"})
    record = runner.resolve_cmd("docker:python:3.12-alpine python")
    with pytest.raises(RuntimeError, match="fixture offline"):
        runner.run_prompt(record, "fixture")
