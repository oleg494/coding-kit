"""CK-03 confinement backend: fail-closed gate and the real escape battery.

The battery runs only when a container runtime answers a live ping (Docker
Desktop on this machine); with no runtime the suite asserts the fail-closed
behavior instead, which is the property the live eval path depends on.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))

from eval.rigor import container
from eval.rigor.runner import run_rigor_suite
# runner.py imports the same file as `rigor.container` (eval/ is on its
# sys.path), so the exception class the live gate raises lives in that module
# instance — `eval.rigor.container` is a distinct object.
from rigor import container as runner_container
from rigor import runner as runner_mod

_RUNTIME = container.docker_status()
_SKIP_REASON = f"no container runtime: {_RUNTIME.get('reason', 'unavailable')}"


def test_confined_executor_spec_is_parsed_explicitly():
    record = container.parse_executor_spec(
        "docker:img @ro:/host/policy:/policy @net python /x.py --flag")
    assert record["mode"] == "container"
    assert record["image"] == "img"
    assert record["argv"] == ["python", "/x.py", "--flag"]
    assert record["mounts"] == (("/host/policy", "/policy"),)
    assert record["network"] is True

    # dry-run runs nothing; a bare host CLI is not a confined executor
    assert container.parse_executor_spec(None)["mode"] == "dry-run"
    assert container.parse_executor_spec("")["mode"] == "dry-run"
    assert container.parse_executor_spec("claude -p")["mode"] == "host"
    with pytest.raises(ValueError):
        container.parse_executor_spec("docker:img")          # no argv
    with pytest.raises(ValueError):
        container.parse_executor_spec("docker:img @ro:/only-host")  # no :container


def test_confined_executor_gate_fails_closed_without_a_backend(monkeypatch):
    monkeypatch.setattr(container, "docker_status",
                        lambda timeout=30: {"available": False,
                                            "reason": "daemon unreachable"})
    with pytest.raises(container.IsolationUnavailable) as excinfo:
        container.require_confined_executor("docker:img python /x.py")
    assert "daemon unreachable" in str(excinfo.value)
    assert "not a sandbox" in str(excinfo.value)


def test_confined_argv_writes_only_the_workdir(tmp_path):
    work = tmp_path / "candidate"
    policy = tmp_path / "policy"
    work.mkdir()
    policy.mkdir()
    record = container.parse_executor_spec(f"docker:img @ro:{policy}:/policy python /x.py")
    cmd = container.confined_argv(record, ["python", "/x.py"], workdir=work)

    assert cmd[0] == "docker"
    assert "-i" in cmd, "stdin must be forwarded for the prompt"
    assert cmd[cmd.index("--network") + 1] == "none"      # offline by default
    assert "--read-only" in cmd
    assert f"{work.resolve().as_posix()}:{container.WORK_MOUNT}:rw" in cmd
    assert f"{policy.resolve().as_posix()}:{container.POLICY_MOUNT}:ro" in cmd
    assert cmd[-3:] == ["img", "python", "/x.py"]

    online = container.confined_argv(
        container.parse_executor_spec("docker:img @net python /x.py"),
        ["python", "/x.py"], workdir=work)
    assert online[online.index("--network") + 1] == "bridge"


def test_offline_executor_escapes_only_without_a_boundary(tmp_path):
    """The escape fixture really writes outside the candidate directory.

    Proven on the host (no boundary): the escaping candidate that the confined
    verifier must reject leaves a sentinel beside the candidate directory while
    the permissive host verifier still accepts it — the reproduced hole this
    path closes.
    """
    tdir = runner_mod.OFFLINE_DIR / "006-import-boundary"
    sandbox = tmp_path / "sandbox"
    shutil.copytree(tdir / "fixture", sandbox)
    brief = (tdir / "TASK.md").read_text(encoding="utf-8")
    spec = runner_mod.offline_executor_spec("escape-verifier")
    argv = container.parse_executor_spec(spec)["argv"]
    marker = tmp_path / "rigor-verifier-escape.txt"
    assert not marker.exists()

    run = subprocess.run([sys.executable, str(runner_mod.OFFLINE_EXECUTOR),
                          *argv[2:]], cwd=sandbox, input=brief, text=True,
                         capture_output=True, timeout=120)
    assert run.returncode == 0, run.stderr

    host_verify = subprocess.run([sys.executable, str(tdir / "verify.py"),
                                  str(sandbox)], capture_output=True, timeout=120)
    assert marker.exists(), \
        "the escaping candidate must write outside the candidate dir at import"
    assert host_verify.returncode == 0, \
        "unconfined, the verifier accepts the escaping candidate (the bug)"


def test_require_backend_fails_closed_without_a_runtime(monkeypatch):
    monkeypatch.setattr(container, "docker_status",
                        lambda timeout=30: {"available": False,
                                            "reason": "daemon unreachable"})
    with pytest.raises(container.IsolationUnavailable) as excinfo:
        container.require_backend()
    assert "daemon unreachable" in str(excinfo.value)
    assert "not a sandbox" in str(excinfo.value)


def test_host_executor_is_refused_even_with_docker_available(monkeypatch):
    monkeypatch.setattr(container, "docker_status",
                        lambda timeout=30: {"available": True, "runtime": "docker",
                                            "version": "test"})
    with pytest.raises(container.IsolationUnavailable) as excinfo:
        container.require_confined_executor("claude -p")
    assert "outside the container boundary" in str(excinfo.value)
    # dry-run (no executor) is unaffected: nothing runs
    record = container.require_confined_executor(None)
    assert record["mode"] == "dry-run"


def test_live_rigor_run_is_refused_before_any_model_call():
    with pytest.raises(runner_container.IsolationUnavailable) as excinfo:
        run_rigor_suite("baseline", "worktree", executor_cmd="claude -p")
    assert "live run refused" in str(excinfo.value)


@pytest.mark.skipif(not _RUNTIME["available"], reason=_SKIP_REASON)
def test_escape_battery_blocks_every_vector():
    result = container.escape_probes()
    assert result["ok"], {"checks": result["checks"],
                          "reachable_reads": result["reachable_reads"],
                          "reachable_writes": result["reachable_writes"]}
    assert result["checks"]["host_mount_writable"], \
        "the mount must stay writable, otherwise the blocked writes prove nothing"
    assert result["checks"]["read_only_mount_blocked"], \
        "a candidate-controlled symlink must not make a read-only mount writable"
    assert not result["reachable_reads"] and not result["reachable_writes"]
    assert result["probe"]["host_env_matches"] == {} or not any(
        result["probe"]["host_env_matches"].values()), \
        "no host credential value may appear inside the boundary"


@pytest.mark.skipif(not _RUNTIME["available"], reason=_SKIP_REASON)
def test_timeout_leaves_no_container_or_descendant():
    result = container.timeout_kills_descendants()
    assert result["timed_out"], result
    assert result["container_gone"], result


@pytest.mark.skipif(not _RUNTIME["available"], reason=_SKIP_REASON)
def test_judge_launch_plumbing_inside_the_boundary(tmp_path):
    """The judge command is a `docker run` argv consumed by the shared helper.

    Stand-in judge, no model: it proves the boundary argv works with
    `judge_one`/`run_prompt` (stdin carries the judge prompt, stdout the
    verdict, the host cwd is irrelevant).
    """
    from eval.runner import judge_one

    code = "import sys; print('PASS' if 'EXPECT:' in sys.stdin.read() else 'FAIL')"
    record = container.parse_executor_spec(
        f"docker:{container.DEFAULT_IMAGE} python")
    jcmd = container.confined_argv(record, ["python", "-c", code],
                                   workdir=tmp_path)
    assert judge_one(jcmd, "the expectation", "the answer").startswith("PASS")


@pytest.mark.skipif(not _RUNTIME["available"], reason=_SKIP_REASON)
def test_executor_cannot_write_outside_its_workdir(tmp_path):
    """The executor itself faces the boundary, not just the verifier."""
    tdir = runner_mod.OFFLINE_DIR / "006-import-boundary"
    sandbox = tmp_path / "sandbox"
    shutil.copytree(tdir / "fixture", sandbox)
    record = container.parse_executor_spec(
        runner_mod.offline_executor_spec("escape-executor"))
    cmd = container.confined_argv(record, record["argv"], workdir=sandbox)

    run = subprocess.run(cmd, input=(tdir / "TASK.md").read_text(encoding="utf-8"),
                         text=True, capture_output=True, timeout=300)
    assert run.returncode == 0, run.stderr
    # self-reported; the host-side sentinel below is the authoritative check
    assert "blocked:" in run.stdout, run.stdout
    assert not (tmp_path / "rigor-executor-escape.txt").exists()
    assert (sandbox / "utils.py").read_text(encoding="utf-8").count("return high") == 1


@pytest.mark.skipif(not _RUNTIME["available"], reason=_SKIP_REASON)
def test_confined_offline_task_end_to_end(tmp_path):
    """The declared path end to end on the local image, without a model.

    A deterministic executor edits the candidate inside the boundary; the
    trusted verifier runs read-only against it. The correct candidate passes;
    the candidate that writes outside the candidate directory at import time
    is rejected, and the host sentinels stay absent.
    """
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for name in runner_mod.POLICY_FILES:
        (bundle / name).write_text(f"# {name}\n", encoding="utf-8")

    good = runner_mod.run_microtask(
        "006-import-boundary", bundle, runner_mod.offline_executor_spec("fix"),
        timeout=300, tasks_dir=runner_mod.OFFLINE_DIR)
    assert good["verdict"] == "PASS", good
    attempt = good["attempts"][0]
    assert attempt["clean_pass"] is True
    assert attempt["verifier"]["rc"] == 0
    assert attempt["verifier"]["timed_out"] is False
    assert attempt["escaped"] == []
    assert not any(attempt["escape_markers"].values()), attempt["escape_markers"]

    escaping = runner_mod.run_microtask(
        "006-import-boundary", bundle,
        runner_mod.offline_executor_spec("escape-verifier"), timeout=300,
        tasks_dir=runner_mod.OFFLINE_DIR)
    bad = escaping["attempts"][0]
    assert escaping["verdict"] == "FAIL", escaping
    assert bad["clean_pass"] is False
    assert bad["verifier"]["rc"] not in (0, None), bad["verifier"]
    assert bad["escaped"] == []
    assert not any(bad["escape_markers"].values()), bad["escape_markers"]
