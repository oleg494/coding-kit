#!/usr/bin/env python3
"""autonomous.py — foreground supervisor for opt-in autonomous work.

Usage:
    python scripts/tools/autonomous.py --workspace PATH --mission TEXT
        --executor COMMAND --verify COMMAND
        [--state-dir PATH] [--max-iterations 10] [--timeout 600]

The supervisor launches a user-configured executor CLI in a workspace, feeds it
the mission plus a checkpoint protocol on stdin, and continues to the next
iteration while the model claims useful work remains. A `complete` claim is
never trusted: an independently configured verifier must exit zero. State,
logs and the checkpoint live in the state dir (default `<workspace>/.autonomous`)
so progress survives process restarts.

The workspace is a working directory, NOT a security sandbox. The supervisor
does not confine, sandbox, or approve the executor's actions; the harness that
launches this supervisor remains responsible for permissions. Checkpoints are
untrusted claims and are never executed as commands.

Exit codes: 0 verified complete, 1 failed/blocked/stalled/exhausted/lock or
config mismatch, 130 stop (STOP file or Ctrl+C).
"""
import argparse
import ctypes
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

STATUSES = ("continue", "complete", "blocked")
STATE_STATUSES = ("running", "complete", "blocked", "failed", "stalled",
                  "exhausted", "stopped")
STATE_VERSION = 1
CHECKPOINT_NAME = "checkpoint.json"
STATE_NAME = "state.json"
LOCK_NAME = "invocation.lock"
STOP_NAME = "STOP"
LOG_DIR_NAME = "logs"
CHECKPOINT_MAX_BYTES = 1 << 20
FEEDBACK_MAX_CHARS = 4000
POLL_SECONDS = 0.2
STOP_POLL_SECONDS = 0.5
TERMINAL_MAX_ITERATIONS = 1_000_000
TERMINAL_MAX_TIMEOUT = 86_400


# --------------------------------------------------------------------------
# Reuse the shared CLI-string parser instead of inventing a second dialect.
# --------------------------------------------------------------------------
def _load_resolve_cmd():
    """Load `resolve_cmd` from eval/task_runner.py, robust to direct invocation."""
    root = Path(__file__).resolve().parents[2]
    path = root / "eval" / "task_runner.py"
    if not path.is_file():
        raise SystemExit(f"autonomous: cannot find {path} (resolve_cmd source)")
    spec = importlib.util.spec_from_file_location("_coding_kit_task_runner", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - import-time environment issue
        raise SystemExit(f"autonomous: cannot import resolve_cmd: {exc}")
    return module.resolve_cmd


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {text!r}")
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer (>= 1)")
    if value > TERMINAL_MAX_ITERATIONS:
        raise argparse.ArgumentTypeError(f"must be <= {TERMINAL_MAX_ITERATIONS}")
    return value


def _positive_timeout(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {text!r}")
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer (>= 1)")
    if value > TERMINAL_MAX_TIMEOUT:
        raise argparse.ArgumentTypeError(f"must be <= {TERMINAL_MAX_TIMEOUT}")
    return value


# --------------------------------------------------------------------------
# State, logs, lock.
# --------------------------------------------------------------------------
def _write_json_atomic(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(doc, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_path, "a", encoding="utf-8", errors="replace", newline="\n") as handle:
        handle.write(f"{stamp} {message}\n")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
        if not process:
            return False
        ctypes.windll.kernel32.CloseHandle(process)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class LockError(RuntimeError):
    pass


class ChildSpawnError(RuntimeError):
    """A child CLI could not be started (missing binary, permissions, ...)."""


class InvocationLock:
    """Exclusive per-state-dir lock. A stale lock is reported, never stolen."""

    def __init__(self, path: Path):
        self.path = path
        self.held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"pid": os.getpid(),
                              "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            raise LockError(self._describe_conflict())
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload + "\n")
        except BaseException:
            self.path.unlink(missing_ok=True)
            raise
        self.held = True

    def _describe_conflict(self) -> str:
        try:
            info = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        pid = info.get("pid")
        started = info.get("started_at", "unknown")
        if isinstance(pid, int) and _pid_alive(pid):
            return (f"another supervisor is active (pid {pid}, started {started}); "
                    f"refusing to share {self.path}")
        return (f"stale lock at {self.path} (pid {pid}, started {started}); "
                f"refusing to steal it — confirm no supervisor is running and delete it")

    def release(self) -> None:
        if self.held:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self.held = False


# --------------------------------------------------------------------------
# Child processes.
# --------------------------------------------------------------------------
def _terminate_tree(proc: subprocess.Popen) -> None:
    """Terminate a child and its descendants on Windows and POSIX."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _tail(path: Path, limit: int = FEEDBACK_MAX_CHARS) -> str:
    """Last `limit` characters of a log, reading a bounded tail window only."""
    window = limit * 4
    try:
        size = path.stat().st_size
        with open(path, "rb") as handle:
            handle.seek(max(0, size - window))
            data = handle.read(window)
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")[-limit:].strip()


def _run_child(argv: list[str], *, cwd: Path, env: dict, stdin_text: str | None,
               log_path: Path, timeout: int, stop_path: Path):
    """Run one child with output on disk. Returns (code, timed_out, stopped)."""
    if stop_path.exists():
        return None, False, True
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        creationflags = 0
        kwargs: dict = {}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(
                argv, cwd=str(cwd), env=env,
                stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=creationflags, **kwargs)
        except OSError as exc:
            raise ChildSpawnError(f"cannot start {argv[0]!r}: {exc}") from exc
        writer = _feed_stdin(proc, stdin_text) if stdin_text is not None else None
        deadline = time.monotonic() + timeout
        timed_out = False
        stopped = False
        last_stop_check = 0.0
        try:
            while proc.poll() is None:
                now = time.monotonic()
                if now - last_stop_check >= STOP_POLL_SECONDS:
                    last_stop_check = now
                    if stop_path.exists():
                        stopped = True
                        break
                if now >= deadline:
                    timed_out = True
                    break
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            _terminate_tree(proc)
            raise
        if stopped or timed_out:
            _terminate_tree(proc)
        code = proc.wait()
        if writer is not None:
            # The child is gone, so a blocked writer fails fast; bounded join
            # only to avoid returning with a live thread holding the pipe.
            writer.join(timeout=5)
    return code, timed_out, stopped


def _feed_stdin(proc: subprocess.Popen, text: str) -> threading.Thread:
    """Write the prompt on a daemon thread; the writer owns the pipe.

    The parent never joins or closes stdin: a child that never reads must not
    stall the supervisor's cancellation/STOP/deadline polling.
    """
    payload = text.encode("utf-8")

    def write() -> None:
        try:
            proc.stdin.write(payload)
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                proc.stdin.close()
            except (OSError, ValueError):
                pass

    thread = threading.Thread(target=write, daemon=True)
    thread.start()
    return thread


# --------------------------------------------------------------------------
# Checkpoint contract.
# --------------------------------------------------------------------------
def _read_checkpoint(path: Path):
    """Return (checkpoint, error). Checkpoints are untrusted claims."""
    if not path.is_file():
        return None, f"checkpoint missing at {path}"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"checkpoint unreadable: {exc}"
    if len(raw) > CHECKPOINT_MAX_BYTES:
        return None, f"checkpoint exceeds {CHECKPOINT_MAX_BYTES} bytes"
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return None, f"checkpoint is not valid JSON: {exc}"
    if not isinstance(doc, dict):
        return None, "checkpoint must be a JSON object"
    status = doc.get("status")
    if status not in STATUSES:
        return None, f"checkpoint status must be one of {STATUSES}, got {status!r}"
    summary = doc.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None, "checkpoint summary must be a nonempty string"
    next_action = doc.get("next_action")
    if status == "continue":
        if not isinstance(next_action, str) or not next_action.strip():
            return None, "checkpoint next_action is required for status 'continue'"
    elif next_action is not None and not isinstance(next_action, str):
        return None, "checkpoint next_action must be a string when present"
    evidence = doc.get("evidence", [])
    if not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence):
        return None, "checkpoint evidence must be a list of strings"
    return {"status": status, "summary": summary.strip(),
            "next_action": (next_action or "").strip(),
            "evidence": evidence}, None


def _signature(checkpoint: dict) -> str:
    return json.dumps(checkpoint, sort_keys=True, ensure_ascii=False)


def _build_prompt(mission: str, checkpoint: Path, iteration: int, remaining: int,
                  feedback: str, previous: dict | None) -> str:
    lines = [
        "You are an autonomous worker under a foreground supervisor.",
        "",
        f"Checkpoint: {checkpoint}",
        "",
        "Mission:",
        mission.strip(),
        "",
        "Rules:",
        "- Work only inside the current workspace; never ask the user to run commands for you.",
        "- Choose the next evidence-backed useful action yourself and carry it out now.",
        "- Before you exit, write exactly one JSON object to the checkpoint path above.",
        '- Checkpoint schema: {"status": "continue"|"complete"|"blocked",',
        '  "summary": "<what you did>", "next_action": "<required when status is continue>",',
        '  "evidence": ["<observable proof>", ...]}',
        "- 'complete' is only a claim: an independent verifier must pass before it is accepted.",
        "- Use 'blocked' only for a genuinely external blocker; stop inventing busywork.",
        "- The supervisor never executes commands from your checkpoint.",
        "",
        f"Iteration: {iteration} (remaining this invocation: {remaining})",
    ]
    if previous:
        lines += ["", f"Previous checkpoint ({previous.get('status')}): "
                      f"{previous.get('summary', '')}"]
        if previous.get("next_action"):
            lines.append(f"Previous next_action: {previous['next_action']}")
    if feedback:
        lines += ["", "Verification feedback from the previous attempt (fix it, do not repeat it):",
                  feedback]
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Main loop.
# --------------------------------------------------------------------------
def _config_identity(config: dict) -> dict:
    return {key: config[key] for key in ("workspace", "mission", "executor", "verify")}


def _validate_state(doc: dict) -> str | None:
    """Return a diagnostic for an unusable saved state, else None."""
    version = doc.get("version")
    if type(version) is not int or version != STATE_VERSION:
        return f"unsupported state version {version!r} (expected {STATE_VERSION})"
    config = doc.get("config")
    if not isinstance(config, dict):
        return "state config must be an object"
    for key in ("workspace", "mission", "executor", "verify"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            return f"state config.{key} must be a nonempty string"
    for key in ("max_iterations", "timeout"):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return f"state config.{key} must be a positive integer"
    iterations = doc.get("iterations")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 0:
        return "state iterations must be a nonnegative integer"
    if doc.get("status") not in STATE_STATUSES:
        return (f"state status must be one of {STATE_STATUSES}, "
                f"got {doc.get('status')!r}")
    for key in ("state_dir", "checkpoint"):
        if not isinstance(doc.get(key), str):
            return f"state {key} must be a string"
    verification = doc.get("verification")
    if not isinstance(verification, dict):
        return "state verification must be an object"
    for key in ("passed", "exit_code", "feedback", "checked_at"):
        if key not in verification:
            return f"state verification.{key} is missing"
    passed = verification.get("passed")
    if passed is not True and passed is not False and passed is not None:
        return "state verification.passed must be true, false, or null"
    exit_code = verification.get("exit_code")
    if exit_code is not None and (isinstance(exit_code, bool)
                                  or not isinstance(exit_code, int)):
        return "state verification.exit_code must be an integer or null"
    if not isinstance(verification.get("feedback"), str):
        return "state verification.feedback must be a string"
    checked_at = verification.get("checked_at")
    if checked_at is not None and not isinstance(checked_at, str):
        return "state verification.checked_at must be a string or null"
    last = doc.get("last_checkpoint")
    if last is not None:
        if not isinstance(last, dict):
            return "state last_checkpoint must be an object or null"
        if last.get("status") not in STATUSES:
            return (f"state last_checkpoint.status must be one of {STATUSES}, "
                    f"got {last.get('status')!r}")
        summary = last.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            return "state last_checkpoint.summary must be a nonempty string"
        if not isinstance(last.get("next_action"), str):
            return "state last_checkpoint.next_action must be a string"
        if last["status"] == "continue" and not last["next_action"].strip():
            return "state last_checkpoint.next_action is required for status 'continue'"
        evidence = last.get("evidence")
        if not isinstance(evidence, list) or any(not isinstance(item, str)
                                                 for item in evidence):
            return "state last_checkpoint.evidence must be a list of strings"
    signatures = doc.get("recent_signatures")
    if not isinstance(signatures, list) or any(not isinstance(item, str)
                                               for item in signatures):
        return "state recent_signatures must be a list of strings"
    return None


def _load_state(state_path: Path):
    try:
        doc = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"state file {state_path} is unreadable: {exc}"
    if not isinstance(doc, dict):
        return None, f"state file {state_path} has an unexpected shape"
    error = _validate_state(doc)
    if error:
        return None, f"{error} in {state_path}"
    return doc, None


def _new_state(config: dict, checkpoint: Path, state_dir: Path) -> dict:
    return {
        "version": STATE_VERSION,
        "config": config,
        "state_dir": str(state_dir),
        "checkpoint": str(checkpoint),
        "iterations": 0,
        "status": "running",
        "verification": {"passed": None, "exit_code": None, "feedback": "",
                         "checked_at": None},
        "last_checkpoint": None,
        "recent_signatures": [],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", required=True, help="executor working directory")
    parser.add_argument("--mission", required=True, help="durable mission text")
    parser.add_argument("--executor", required=True,
                        help="executor CLI command string (no shell interpretation)")
    parser.add_argument("--verify", required=True,
                        help="independent verifier CLI command string")
    parser.add_argument("--state-dir", default=None,
                        help="state dir (default <workspace>/.autonomous)")
    parser.add_argument("--max-iterations", type=_positive_int, default=10)
    parser.add_argument("--timeout", type=_positive_timeout, default=600)
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"autonomous: workspace is not a directory: {workspace}", file=sys.stderr)
        return 1
    state_dir = (Path(args.state_dir).expanduser().resolve()
                 if args.state_dir else workspace / ".autonomous")
    state_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = state_dir / CHECKPOINT_NAME
    state_path = state_dir / STATE_NAME
    stop_path = state_dir / STOP_NAME
    log_dir = state_dir / LOG_DIR_NAME
    supervisor_log = log_dir / "supervisor.log"

    resolve_cmd = _load_resolve_cmd()
    executor_argv = resolve_cmd(args.executor)
    verifier_argv = resolve_cmd(args.verify)
    if not executor_argv:
        print("autonomous: --executor resolved to an empty command", file=sys.stderr)
        return 1
    if not verifier_argv:
        print("autonomous: --verify resolved to an empty command", file=sys.stderr)
        return 1

    config = {
        "workspace": str(workspace),
        "mission": args.mission,
        "executor": args.executor,
        "verify": args.verify,
        "max_iterations": args.max_iterations,
        "timeout": args.timeout,
    }

    lock = InvocationLock(state_dir / LOCK_NAME)
    try:
        lock.acquire()
    except LockError as exc:
        print(f"autonomous: {exc}", file=sys.stderr)
        _log(supervisor_log, f"lock refused: {exc}")
        return 1

    try:
        return _run(args, workspace, state_dir, checkpoint, state_path, stop_path,
                    log_dir, supervisor_log, config, executor_argv, verifier_argv)
    finally:
        lock.release()


def _run(args, workspace: Path, state_dir: Path, checkpoint: Path, state_path: Path,
         stop_path: Path, log_dir: Path, supervisor_log: Path, config: dict,
         executor_argv: list[str], verifier_argv: list[str]) -> int:
    _log(supervisor_log, f"start workspace={workspace} executor={args.executor!r} "
                         f"verify={args.verify!r} max={args.max_iterations} "
                         f"timeout={args.timeout}")
    if state_path.exists():
        state, error = _load_state(state_path)
        if error:
            print(f"autonomous: {error}", file=sys.stderr)
            return 1
        saved = state["config"]
        mismatch = [key for key, value in _config_identity(config).items()
                    if saved.get(key) != value]
        if mismatch:
            message = ("configuration mismatch on resume: "
                       + ", ".join(sorted(mismatch))
                       + f" (state dir {state_dir})")
            print(f"autonomous: {message}", file=sys.stderr)
            _log(supervisor_log, message)
            return 1
        # Ceilings are per invocation; only the durable iteration count and
        # progress carry over.
        max_iterations = args.max_iterations
        timeout = args.timeout
        state["config"]["max_iterations"] = max_iterations
        state["config"]["timeout"] = timeout
        state["config"]["mission"] = args.mission
        _log(supervisor_log, f"resume iterations={state.get('iterations', 0)} "
                             f"status={state.get('status')}")
    else:
        max_iterations = args.max_iterations
        timeout = args.timeout
        state = _new_state(config, checkpoint, state_dir)

    verification = state.setdefault("verification", {"passed": None, "exit_code": None,
                                                     "feedback": "", "checked_at": None})
    state.setdefault("recent_signatures", [])
    state.setdefault("last_checkpoint", None)

    def persist() -> None:
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        state["checkpoint"] = str(checkpoint)
        _write_json_atomic(state_path, state)

    def finish(status: str, code: int, message: str) -> int:
        state["status"] = status
        persist()
        _log(supervisor_log, f"finish status={status} exit={code} {message}")
        stream = sys.stdout if code == 0 else sys.stderr
        print(f"autonomous: {message}", file=stream)
        return code

    def verify_completion(iteration: int):
        """Run the independent verifier. Returns (passed, code, feedback)."""
        code, timed_out, stopped = _run_child(
            verifier_argv, cwd=workspace, env=dict(os.environ),
            stdin_text=None, log_path=log_dir / f"verifier-{iteration}.log",
            timeout=timeout, stop_path=stop_path)
        if stopped:
            return None, None, ""
        feedback = _tail(log_dir / f"verifier-{iteration}.log")
        if timed_out:
            feedback = f"verifier timed out after {timeout}s\n{feedback}".strip()
            verification.update({"passed": False, "exit_code": None,
                                 "feedback": feedback,
                                 "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
            _log(supervisor_log, f"verifier iteration={iteration} timed out after {timeout}s")
            return False, None, feedback
        passed = code == 0
        verification.update({"passed": passed, "exit_code": code,
                             "feedback": feedback,
                             "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        _log(supervisor_log, f"verifier iteration={iteration} exit={code} passed={passed}")
        return passed, code, feedback

    try:
        # A previous `complete` is only a claim: re-verify against the live verifier.
        if state.get("status") == "complete":
            _log(supervisor_log, "resume: re-verifying previous complete claim")
            passed, _, _ = verify_completion(int(state.get("iterations", 0)))
            if passed is None:
                return finish("stopped", 130, "stop requested during verification")
            if passed:
                return finish("complete", 0, "previous completion verified on resume")
            state["status"] = "running"
            persist()

        budget = max_iterations
        while budget > 0:
            if stop_path.exists():
                return finish("stopped", 130, f"STOP file present at {stop_path}")
            budget -= 1
            state["iterations"] = int(state.get("iterations", 0)) + 1
            iteration = state["iterations"]
            checkpoint.unlink(missing_ok=True)
            feedback = verification.get("feedback", "") if verification.get("passed") is False else ""
            prompt = _build_prompt(args.mission, checkpoint, iteration, budget,
                                   feedback, state.get("last_checkpoint"))
            env = dict(os.environ)
            env["AUTONOMOUS_CHECKPOINT"] = str(checkpoint)
            env["AUTONOMOUS_STATE_DIR"] = str(state_dir)
            env["AUTONOMOUS_ITERATION"] = str(iteration)
            # Durable before spawn: an executor can read current state on its
            # very first launch, and a crash cannot lose the iteration count.
            state["status"] = "running"
            persist()
            _log(supervisor_log, f"executor iteration={iteration} spawn")
            code, timed_out, stopped = _run_child(
                executor_argv, cwd=workspace, env=env, stdin_text=prompt,
                log_path=log_dir / f"executor-{iteration}.log",
                timeout=timeout, stop_path=stop_path)
            if stopped:
                return finish("stopped", 130, "stop requested during execution")
            if timed_out:
                return finish("failed", 1, f"executor timed out after {timeout}s")
            if code != 0:
                return finish("failed", 1, f"executor exited with code {code}")

            checkpoint_doc, error = _read_checkpoint(checkpoint)
            if error:
                return finish("failed", 1, error)

            signature = _signature(checkpoint_doc)
            recent = state["recent_signatures"]
            recent.append(signature)
            del recent[:-3]
            state["last_checkpoint"] = checkpoint_doc
            status = checkpoint_doc["status"]
            _log(supervisor_log, f"checkpoint iteration={iteration} status={status} "
                                 f"summary={checkpoint_doc['summary'][:120]!r}")

            if status == "blocked":
                return finish("blocked", 1,
                              f"executor reported blocked: {checkpoint_doc['summary']}")

            if status == "continue":
                if len(recent) >= 3 and recent[-1] == recent[-2] == recent[-3]:
                    return finish("stalled", 1,
                                  "three identical consecutive continue checkpoints")
                state["status"] = "running"
                persist()
                continue

            # status == "complete": untrusted until the verifier agrees. An
            # identical summary may reflect newly fixed files, so it is always
            # re-verified rather than treated as a stall.
            state["status"] = "running"
            persist()
            passed, _, _ = verify_completion(iteration)
            if passed is None:
                return finish("stopped", 130, "stop requested during verification")
            if passed:
                return finish("complete", 0,
                              f"completion verified at iteration {iteration}")
            state["status"] = "running"
            persist()

        return finish("exhausted", 1,
                      f"iteration limit reached ({max_iterations} this invocation); "
                      f"state is resumable")
    except ChildSpawnError as exc:
        return finish("failed", 1, str(exc))
    except KeyboardInterrupt:
        state["status"] = "stopped"
        persist()
        _log(supervisor_log, "interrupted by user")
        print("autonomous: interrupted; child process tree terminated", file=sys.stderr)
        return 130


def cli() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("autonomous: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(cli())
