"""OS-enforced confinement backend for live evaluations (CK-03).

Prompt-level controls (`--safe-mode`, empty tool list, canary strings) shape a
model's behavior; they are not a boundary — a child process can still read host
credentials and write outside the workspace. The only boundary this module
accepts is a disposable OS boundary: a container with no writable host mounts,
no network, a read-only root filesystem and a dropped capability set.

`require_backend()` fails closed: a live run raises `IsolationUnavailable`
instead of silently executing unconfined. The escape battery
(`escape_probes`) is deterministic and model-free — it proves or disproves the
boundary on this machine, and its result is what a live evaluation records.

A live executor is declared explicitly, as an `--executor` spec:

    docker:<image> [@ro:<host-path>:<container-path>]... [@net] <argv...>

`<argv...>` is resolved INSIDE the image (the image carries the CLI, the
interpreter and its dependencies); the task directory is the only writable
mount (`/work`), the policy bundle is read-only (`/policy`), the trusted
verifier is read-only (`/verifier`), stdin carries the prompt and stdout/
stderr carry the result — the same contract the host CLI had. `@net` is the
only transport opt-in, for model endpoints. Anything else — a bare host CLI
above all — is refused.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_IMAGE = "python:3.12-alpine"
HERE = Path(__file__).resolve().parent
EXECUTOR_PREFIX = "docker:"
WORK_MOUNT = "/work"
POLICY_MOUNT = "/policy"
VERIFIER_MOUNT = "/verifier"
VERIFIER_PYTHON = "python"
# Host-side sentinels that a confined child must never create: the offline
# executor and an escaping candidate both attempt `<workdir>/../<name>`
# (inside the container: `/work/../<name>`, i.e. the read-only rootfs).
ESCAPE_MARKER_NAMES = ("rigor-executor-escape.txt", "rigor-verifier-escape.txt")
# Host variables whose values must never appear inside the boundary.
HOST_ENV_NAMES = ("USERPROFILE", "HOME", "MEMORY_ROOT", "ANTHROPIC_API_KEY",
                  "OPENAI_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY",
                  "DOCKER_HOST")


class IsolationUnavailable(RuntimeError):
    """No OS-enforced confinement backend is available on this host."""


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          check=False)


def _unquote(token: str) -> str:
    if len(token) >= 2 and ((token.startswith('"') and token.endswith('"'))
                            or (token.startswith("'") and token.endswith("'"))):
        return token[1:-1]
    return token


def container_name() -> str:
    return f"kit-eval-{secrets.token_hex(6)}"


def _docker_argv(image: str, argv: list, *, name: str, network: bool,
                 workdir: Path | None = None, ro_mounts: tuple = (),
                 env: dict | None = None) -> list[str]:
    """The one `docker run` shape: read-only rootfs, no capabilities, no host
    environment, `workdir` (when given) as the only writable mount."""
    cmd = ["docker", "run", "--rm", "--name", name,
           # `-i` is what forwards stdin (the prompt) into the boundary; the
           # prompt never touches the host filesystem.
           "-i",
           "--network", "bridge" if network else "none",
           "--read-only", "--tmpfs", "/tmp:rw,size=64m",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--pids-limit", "256", "--memory", "1g"]
    if workdir is not None:
        cmd += ["-v", f"{Path(workdir).resolve().as_posix()}:{WORK_MOUNT}:rw",
                "-w", WORK_MOUNT]
    for src, dst in ro_mounts:
        cmd += ["-v", f"{Path(src).resolve().as_posix()}:{dst}:ro"]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd += [image, *argv]
    return cmd


def parse_executor_spec(executor_spec: str | None) -> dict:
    """`--executor` string -> confinement record (pure; no backend probing).

    Confined form: `docker:<image> [@ro:<host>:<container>]... [@net] <argv...>`
    — the argv is resolved inside the image. An empty spec is a dry-run; any
    other spec is a host CLI (`mode="host"`) and never qualifies as confined.
    Mount paths carrying spaces are not supported in the spec string.
    """
    blank = {"mode": "dry-run", "spec": None, "image": None, "argv": [],
             "mounts": (), "network": False}
    if not executor_spec or not executor_spec.strip():
        return blank
    parts = shlex.split(executor_spec, posix=(sys.platform != "win32"))
    if sys.platform == "win32":
        parts = [_unquote(p) for p in parts]
    if not parts or not parts[0].startswith(EXECUTOR_PREFIX):
        return {"mode": "host", "spec": executor_spec, "image": None,
                "argv": parts, "mounts": (), "network": False}
    image = parts[0][len(EXECUTOR_PREFIX):]
    mounts, network, argv = [], False, []
    for token in parts[1:]:
        if argv:
            argv.append(token)
        elif token == "@net":
            network = True
        elif token.startswith("@ro:"):
            host, sep, container = token[len("@ro:"):].rpartition(":")
            if not sep or not host or not container:
                raise ValueError(f"invalid read-only mount token: {token!r}")
            mounts.append((_unquote(host), container))
        else:
            argv.append(token)
    if not image or not argv:
        raise ValueError(
            f"confined executor needs `{EXECUTOR_PREFIX}<image> <argv...>`: "
            f"{executor_spec!r}")
    return {"mode": "container", "spec": executor_spec, "image": image,
            "argv": argv, "mounts": tuple(mounts), "network": network}


def confined_argv(record: dict, argv: list, *, workdir: Path | None = None,
                  ro_mounts: tuple = (),
                  name: str | None = None) -> list[str]:
    """Full `docker run` argv for a parsed executor record.

    The caller-supplied `argv` runs inside the image; `record["mounts"]` are
    always read-only. `name` lets a caller address the container for cleanup
    when it launches without `run_confined` (e.g. through a shared CLI helper).
    """
    return _docker_argv(record["image"], list(argv),
                        name=name or container_name(),
                        network=record["network"], workdir=workdir,
                        ro_mounts=tuple(record["mounts"]) + tuple(ro_mounts))


def remove_container(name: str) -> None:
    """Stop and delete a container by name; safe when it is already gone."""
    _docker("kill", name, timeout=60)
    _docker("rm", "-f", name, timeout=60)


def docker_status(timeout: int = 30) -> dict:
    """Is a container runtime usable right now (CLI present AND daemon up)?"""
    if shutil.which("docker") is None:
        return {"available": False, "reason": "docker CLI not found"}
    try:
        version = _docker("version", "--format", "{{.Server.Version}}",
                          timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "docker daemon timed out"}
    except OSError as exc:
        return {"available": False, "reason": f"docker CLI failed: {exc}"}
    if version.returncode != 0:
        return {"available": False,
                "reason": (version.stderr or version.stdout).strip()[:200]
                or "docker daemon unreachable"}
    return {"available": True, "runtime": "docker",
            "version": version.stdout.strip()}


def require_backend(timeout: int = 30) -> dict:
    """Fail closed: raise unless a container runtime answers a live ping."""
    status = docker_status(timeout=timeout)
    if not status["available"]:
        raise IsolationUnavailable(
            "live evaluation refused: no OS-enforced confinement backend "
            f"({status['reason']}). Prompt-level controls are not a sandbox; "
            "start a container runtime or keep the live path blocked.")
    return status


def run_confined(argv: list, workdir: Path, *, image: str = DEFAULT_IMAGE,
                 timeout: int = 300, network: bool = False,
                 ro_mounts: tuple = (), env: dict | None = None,
                 stdin: str | None = None) -> dict:
    """Run argv in a disposable container: only `workdir` is writable.

    argv is resolved inside the container (use the image's own binaries, not
    host paths). No host environment is forwarded (only the explicit `env`
    entries), the root filesystem is read-only, capabilities are dropped and the
    container is removed on completion. A timeout kills the container across the
    whole tree, so descendants cannot outlive the run. `stdin` carries the
    prompt to the in-container process without touching the host filesystem.
    """
    require_backend()
    name = container_name()
    cmd = _docker_argv(image, argv, name=name, network=network, workdir=workdir,
                       ro_mounts=ro_mounts, env=env)
    try:
        if stdin is None:
            # `-i` keeps the container's stdin open, so give it EOF instead of
            # this process's terminal.
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=timeout, check=False)
        else:
            proc = subprocess.run(cmd, input=stdin, capture_output=True,
                                  text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout, check=False)
        out = {"rc": proc.returncode, "stdout": proc.stdout,
               "stderr": proc.stderr, "timed_out": False,
               "argv": cmd[:3] + ["..."] + cmd[-len(argv):]}
    except subprocess.TimeoutExpired as exc:
        remove_container(name)
        out = {"rc": None, "stdout": exc.stdout or "", "stderr": exc.stderr or "",
               "timed_out": True,
               "argv": cmd[:3] + ["..."] + cmd[-len(argv):]}
    out["name"] = name
    return out


def run_verifier(verify: Path, workdir: Path, *, task_dir: Path,
                 image: str = DEFAULT_IMAGE, timeout: int = 120) -> dict:
    """Run the trusted verifier inside the boundary against `workdir`.

    Only `workdir` (the candidate) is writable, mounted at `/work`; the task
    directory holding the verifier and its pristine fixture is mounted
    read-only at `/verifier`, so candidate code executed by the verifier cannot
    rewrite the oracle it is judged by. The image must provide `python`; the
    pytest-based oracles additionally need pytest in the image.
    """
    argv = [VERIFIER_PYTHON, f"{VERIFIER_MOUNT}/{verify.name}", WORK_MOUNT]
    return run_confined(argv, workdir, image=image, timeout=timeout,
                        ro_mounts=((Path(task_dir), VERIFIER_MOUNT),))


def escape_markers(workdir: Path) -> dict:
    """Host-side sentinels a confined child must never be able to create.

    The child attempts `<workdir>/../<name>`; inside the container that is
    `/work/../<name>` — the read-only rootfs. The host, not the container,
    decides: it checks the real host paths afterwards.
    """
    parent = Path(workdir).resolve().parent
    return {name: (parent / name).exists() for name in ESCAPE_MARKER_NAMES}


def container_exists(name: str) -> bool:
    res = _docker("ps", "-a", "--filter", f"name=^/{name}$",
                  "--format", "{{.Names}}", timeout=60)
    return bool(res.stdout.strip())


def host_path_candidates(host_path: Path) -> dict:
    """Places a host path could be reached from inside a container — none of
    them may be reachable, and each is attempted separately so the evidence
    names the exact vector that failed."""
    posix = Path(host_path).as_posix()
    rest = posix.lstrip("/")
    drive = Path(host_path).drive.rstrip(":")
    candidates = {"host_style": f"/{rest}", "wsl_style": f"/mnt/{drive.lower()}/{rest[2:] if drive else rest}",
                  "bind_style": f"/host/{rest}"}
    return candidates


def escape_probes(image: str = DEFAULT_IMAGE, timeout: int = 300) -> dict:
    """Deterministic, model-free escape battery inside the real backend.

    A fixture secret lives OUTSIDE every mount; sentinel paths sit on the host
    root mount, beside the mount, and behind a symlink. Every attempt is made
    in-process and from a child process. The host — not the container — decides
    pass/fail: the secret must never be read, no sentinel may exist, the network
    and the docker socket must be unreachable, and the mount itself must still
    be writable (otherwise the "blocks" prove nothing).
    """
    require_backend()
    with tempfile.TemporaryDirectory(prefix="rigor-confinement-") as td:
        base = Path(td)
        work, probe, outside = base / "work", base / "probe", base / "outside"
        for path in (work, probe, outside):
            path.mkdir()
        shutil.copy(HERE / "container_probe.py", probe / "container_probe.py")

        token = secrets.token_hex(16)
        secret = outside / "secret.txt"
        secret.write_text(f"SECRET_{token}\n", encoding="utf-8")
        sentinel = outside / "sentinel.txt"

        job = {
            "read_targets": {**host_path_candidates(secret),
                             "traversal": f"/work/../{secret.name}"},
            "write_targets": {**host_path_candidates(sentinel),
                              "absolute": "/sentinel-absolute.txt",
                              "sibling": "/work/../sentinel-sibling.txt",
                              "etsc": "/etc/sentinel-etc.txt",
                              "ro_mount": "/probe/attack.txt"},
            "symlink_target": "/",
            "read_only_mount": "/probe",
            # digests, never values: the container must not receive host
            # credentials even to prove their absence
            "host_env_digests": {
                name: hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()
                for name, value in (
                    (n, os.environ.get(n)) for n in HOST_ENV_NAMES
                    if os.environ.get(n)
                )
            },
        }
        (probe / "job.json").write_text(json.dumps(job), encoding="utf-8")

        # argv is resolved INSIDE the container: `python` is the image's
        # interpreter, never sys.executable (a host path cannot run there).
        run = run_confined(["python", "/probe/container_probe.py"], work,
                           image=image, timeout=timeout,
                           ro_mounts=((probe, "/probe"),))
        probe_out = {}
        for line in reversed((run["stdout"] or "").splitlines()):
            try:
                probe_out = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        if not probe_out:
            raise IsolationUnavailable(
                f"escape probe produced no result: rc={run['rc']} "
                f"stderr={(run['stderr'] or '')[:200]}")

        def blocked(section: str) -> dict:
            return {label: value for label, value in probe_out[section].items()
                    if value.get("result") != "blocked"}

        reachable_reads = blocked("reads")
        reachable_writes = blocked("writes")
        probe_files = (probe / "attack.txt", probe / "attack-symlink.txt")
        checks = {
            "host_mount_writable": probe_out["workdir_writable"].get("result") == "wrote",
            "secret_never_read": not reachable_reads and f"SECRET_{token}" not in (run["stdout"] or ""),
            "outside_writes_blocked": not reachable_writes,
            "no_host_sentinel": not sentinel.exists() and not (base / "sentinel-sibling.txt").exists(),
            "read_only_mount_blocked": (
                probe_out["writes"]["ro_mount"].get("result") == "blocked"
                and probe_out["symlink_ro"].get("result") == "blocked"
                and not any(path.exists() for path in probe_files)),
            "symlink_escape_blocked": probe_out["symlink"].get("result") == "blocked",
            "subprocess_escape_blocked": probe_out["subprocess"].get("result") == "blocked",
            "network_blocked": probe_out["network"].get("result") == "blocked",
            "no_docker_socket": probe_out["docker_socket"].get("present") is False,
            "host_env_absent": not any(probe_out["host_env_matches"].values()),
        }
        return {"ok": all(checks.values()), "checks": checks,
                "reachable_reads": reachable_reads,
                "reachable_writes": reachable_writes,
                "probe": probe_out, "run": {"rc": run["rc"],
                                            "timed_out": run["timed_out"]},
                "child_escape": probe_out["subprocess"],
                "secret_fixture": str(secret)}


def require_confined_executor(executor_spec: str | None) -> dict:
    """Gate every live model run: the executor must execute INSIDE a boundary.

    A host CLI (spawned with cwd = the policy bundle) is not confined by
    anything — a model-driven child process can read host credentials and write
    outside the workspace, so prompt-level controls (`--safe-mode`, empty tool
    list, canaries) do not qualify. A confined executor declares the image that
    carries the CLI:

        docker:<image> [@ro:<host-path>:<container-path>]... [@net] <argv...>

    Only the task directory is mounted writable, the policy bundle and the
    verifier are read-only, stdout/stderr carry the result, and `@net` is the
    only transport opt-in (model endpoints). A bare host CLI is refused, and
    with no container runtime every live spec is refused — fail closed. Dry-run
    (no executor) runs nothing and is unaffected.
    """
    record = parse_executor_spec(executor_spec)
    if record["mode"] == "dry-run":
        record["backend"] = docker_status()
        return record
    if record["mode"] == "host":
        require_backend()  # fails closed with the no-backend message
        raise IsolationUnavailable(
            "live run refused: the executor command runs on the host, outside "
            "the container boundary. Declare a confined executor "
            f"(`{EXECUTOR_PREFIX}<image> [@ro:<host>:<container>]... [@net] "
            "<argv...>`) to run it inside the OS boundary; prompt-level "
            "controls are not a sandbox.")
    record["backend"] = require_backend()
    return record


def timeout_kills_descendants(image: str = DEFAULT_IMAGE, timeout: int = 6) -> dict:
    """A confined run that outlives its deadline must leave nothing behind:
    the container (and every process in it) is gone afterwards."""
    with tempfile.TemporaryDirectory(prefix="rigor-timeout-") as td:
        run = run_confined(["sh", "-c", "sleep 300 & sleep 300"], Path(td),
                           image=image, timeout=timeout)
    return {"timed_out": run["timed_out"], "container_gone": not container_exists(run["name"]),
            "name": run["name"], "rc": run["rc"]}
