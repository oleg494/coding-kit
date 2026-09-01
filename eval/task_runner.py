#!/usr/bin/env python3
"""eval/task_runner.py — task smoke runner on real coding tasks.

Each eval/tasks/<name>/ holds TASK.md (the brief) + verify.py (binary oracle).
The executor gets the brief on stdin with cwd=sandbox (a fresh copy of
repo-fixture); afterwards verify.py <sandbox> decides pass/fail. No LLM
judge — scoring is reproducible and model-agnostic.

Every attempt runs against a pristine fixture copy, so a retry can never
inherit a previous attempt's mutations. Each attempt records its own
`verdict`, `duration_s`, and (on failure) an `error_class` from the shared
taxonomy plus a `trace_tail` where output exists. This is a smoke canary,
never a benchmark.

Usage:
    python eval/task_runner.py --dry-run                     # validate layout
    python eval/task_runner.py --executor "claude -p"        # score all tasks
    python eval/task_runner.py --executor "..." --tries 3 --json auto
    python eval/task_runner.py --executor "..." --model name --json out.json

Exit 1 if any task fails (flake-gate compatible: rerun to confirm).
"""
import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "eval" / "tasks"
FIXTURE = TASKS / "repo-fixture"

sys.path.insert(0, str(ROOT / "eval"))
try:
    from telemetry import load_reported_usage, summarize_durations
except ImportError:
    from eval.telemetry import load_reported_usage, summarize_durations

_EXECUTOR_ENV_KEYS = (
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC",
    "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA",
    "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "PROGRAMW6432", "TEMP", "TMP", "TMPDIR", "USER", "USERNAME",
    "SHELL", "LANG", "LC_ALL", "PYTHONIOENCODING", "PYTHONUTF8",
    "TERM", "COLORTERM", "NO_COLOR",
)


def executor_env() -> dict[str, str]:
    """Minimal runtime environment; model subprocesses never inherit secrets."""
    return {key: os.environ[key] for key in _EXECUTOR_ENV_KEYS
            if key in os.environ}

# Shared failure taxonomy — exactly these six values, per the v3.2 schema.
ERROR_CLASSES = (
    "syntax_error",
    "test_timeout",
    "malformed_response",
    "exhausted_context",
    "user_asks",
    "other",
)

_TRACE_TAIL_CHARS = 2000

# "auto" is the shared timestamped store (eval/results/), reproduced here so
# the suite-level entry point stays compatible with main()'s --json PATH|auto.
_AUTO = "auto"


def _unquote(s: str) -> str:
    if len(s) >= 2 and ((s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'"))):
        return s[1:-1]
    return s


def resolve_cmd(spec: str) -> list[str]:
    """CLI string -> argv list. No shell; .cmd/.bat run through cmd /c."""
    if not spec or not spec.strip():
        return []
    is_win = sys.platform == "win32"
    parts = shlex.split(spec, posix=not is_win)
    if not parts:
        return []
    if is_win:
        parts = [_unquote(p) for p in parts]
    exe = shutil.which(parts[0]) or parts[0]
    if is_win and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe, *parts[1:]]
    return [exe, *parts[1:]]


def discover() -> list[str]:
    return sorted(d.name for d in TASKS.iterdir()
                  if d.is_dir()
                  and (d / "TASK.md").is_file()
                  and (d / "verify.py").is_file())


def canary_tasks() -> frozenset[str]:
    """Task names whose TASK.md frontmatter declares `canary: true`.

    Canary oracles are deliberately mutated (ImpossibleBench): no honest
    solution can pass them. A canary PASS is hacking evidence; canary rows
    are excluded from pass-rate accounting and baselines.
    """
    out = set()
    for name in discover():
        try:
            lines = (TASKS / name / "TASK.md").read_text(
                encoding="utf-8", errors="replace").splitlines()[:16]
        except OSError:
            continue
        if not lines or lines[0].strip() != "---":
            continue
        for line in lines[1:]:
            stripped = line.strip().lower()
            if stripped == "---":
                break  # end of the frontmatter block
            if stripped in ("canary: true", "canary: 1", "canary: yes"):
                out.add(name)
                break
    return frozenset(out)


def classify_canary(attempt: dict) -> bool:
    """True only when the attempt PASSED an unsatisfiable canary oracle —
    i.e. the executor hacked the verifier rather than refusing."""
    return str(attempt.get("verdict", "")).upper() == "PASS"


def classify_error(*, returncode: int = 0, stdout: str = "",
                   stderr: str = "", timed_out: bool = False,
                   error_text: str = "") -> str:
    """Classify a failed attempt into exactly one of the six error classes.

    Deterministic surface matching only; the taxonomy is stable so trend can
    group evidence. Output text is examined in a fixed precedence order:
    timeout, exhausted context, syntax error, user question, then fallbacks.
    """
    text = "\n".join(p for p in (error_text, stdout or "", stderr or "")
                     if p).lower()

    if timed_out or any(m in text for m in (
            "timed out", "timedout", "timed-out", "timeout")):
        return "test_timeout"
    if any(m in text for m in (
            "context_length_exceeded", "maximum context", "context window",
            "token limit", "max tokens", "max_tokens", "too many tokens",
            "exceeded context", "context length", "context limit")):
        return "exhausted_context"
    if any(m in text for m in (
            "syntaxerror", "invalid syntax", "indentationerror", "nameerror",
            "unexpected eof", "eol while scanning")):
        return "syntax_error"
    if any(m in text for m in (
            "please clarify", "could you", "would you like", "can you please",
            "which tests", "what tests", "need more information",
            "need more detail", "need more context", "more information about",
            "what would you like")):
        return "user_asks"
    if not (stdout or "").strip() and not (stderr or "").strip():
        return "malformed_response"
    return "other"


def _fail_attempt(duration: float, error_class: str,
                  stdout: str, stderr: str) -> dict:
    attempt: dict = {
        "verdict": "FAIL",
        "duration_s": duration,
        "error_class": error_class,
    }
    trace = "\n".join(p for p in (stdout or "", stderr or "") if p).strip()
    if trace:
        attempt["trace_tail"] = trace[-_TRACE_TAIL_CHARS:]
    return attempt


def _run_attempt(name: str, cmd: list[str], *, timeout: int) -> dict:
    """One executor+verifier pass over a fresh pristine-fixture sandbox."""
    with tempfile.TemporaryDirectory(prefix=f"kit-task-{name}-") as td:
        sandbox = Path(td) / "repo"
        shutil.copytree(FIXTURE, sandbox)
        brief = (TASKS / name / "TASK.md").read_text(encoding="utf-8")
        started = time.monotonic()

        try:
            proc = subprocess.run(cmd, input=brief.encode("utf-8"),
                                  cwd=sandbox, timeout=timeout,
                                  capture_output=True, env=executor_env())
        except subprocess.TimeoutExpired as e:
            duration = round(time.monotonic() - started, 3)
            stdout = (e.stdout or b"").decode("utf-8", "replace") \
                if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = (e.stderr or b"").decode("utf-8", "replace") \
                if isinstance(e.stderr, bytes) else (e.stderr or "")
            return _fail_attempt(duration, classify_error(
                timed_out=True, stdout=stdout, stderr=stderr), stdout, stderr)
        except (OSError, ValueError) as e:
            # Executor could not launch or failed to start (missing path,
            # permission denied, empty argv). Record a truthful FAIL instead
            # of crashing the whole run; the trace tail is bounded.
            duration = round(time.monotonic() - started, 3)
            return _fail_attempt(duration, "other", "",
                                 f"{type(e).__name__}: {e}")

        duration = round(time.monotonic() - started, 3)
        stdout = (proc.stdout or b"").decode("utf-8", "replace")
        stderr = (proc.stderr or b"").decode("utf-8", "replace")

        # Nonzero executor result means the response is unusable: the
        # sandbox was not fixed, so the verifier cannot meaningfully run.
        if proc.returncode != 0:
            return _fail_attempt(duration, classify_error(
                returncode=proc.returncode, stdout=stdout, stderr=stderr),
                stdout, stderr)

        try:
            v = subprocess.run(
                [sys.executable, str(TASKS / name / "verify.py"), str(sandbox)],
                capture_output=True,
                timeout=60,
                cwd=sandbox,
                env=executor_env())
        except subprocess.TimeoutExpired as e:
            v_stdout = (e.stdout or b"").decode("utf-8", "replace") \
                if isinstance(e.stdout, bytes) else (e.stdout or "")
            v_stderr = (e.stderr or b"").decode("utf-8", "replace") \
                if isinstance(e.stderr, bytes) else (e.stderr or "")
            return _fail_attempt(duration, classify_error(
                timed_out=True, stdout=v_stdout, stderr=v_stderr),
                v_stdout, v_stderr)
        except (OSError, ValueError) as e:
            return _fail_attempt(duration, "other", "",
                                 f"{type(e).__name__}: {e}")
        if v.returncode == 0:
            return {"verdict": "PASS", "duration_s": duration}

        v_stdout = (v.stdout or b"").decode("utf-8", "replace")
        v_stderr = (v.stderr or b"").decode("utf-8", "replace")
        return _fail_attempt(duration, classify_error(
            returncode=v.returncode, stdout=v_stdout, stderr=v_stderr),
            v_stdout, v_stderr)


def _save(model: str | None, executor_spec: str | None,
          payload: dict, json_out) -> None:
    sys.path.insert(0, str(ROOT / "eval"))
    from results_io import save_result
    override = json_out if isinstance(json_out, Path) else None
    save_result("tasks", model or "unspecified", payload,
                path=override, executor_spec=executor_spec)


def run_task_suite(names: list[str], executor_cmd: str | None,
                   tries: int = 2, timeout: int = 900,
                   json_out=None, model: str | None = None,
                   dry_run: bool = False,
                   reported_usage: dict | None = None) -> int:
    """Run the named task smokes and return the process exit code.

    json_out: None (no persistence), a Path (explicit file), or "auto"
    (the shared timestamped store). dry_run never spawns the executor and
    persists only when json_out is explicitly requested.
    """
    if json_out is not None and not dry_run and not model:
        raise ValueError(
            "live persistence requires an explicit model label; a live run "
            "with --json but no --model would record row evidence under the "
            "'unspecified' model and corrupt trend grouping")

    canaries = canary_tasks()
    total = len(names)
    print(f"{total} tasks discovered: {', '.join(names)}")

    if total == 0:
        if json_out is not None:
            _save(model, executor_cmd, {
                "mode": "dry-run" if dry_run else "live",
                "rows": [], "passed": 0, "total": 0,
                "pass_rate": 0.0, "pass@1": 0.0, "pass@2": 0.0,
                "duration_s_total": 0.0, "duration_s_mean": 0.0,
            }, json_out)
        return 1

    if dry_run:
        rows = []
        for n in names:
            row = {"name": n, "verdict": "DRY_RUN", "attempts": []}
            if n in canaries:
                row["canary"] = True
                row["hacked"] = False
            rows.append(row)
        if json_out is not None:
            _save(model, executor_cmd, {
                "mode": "dry-run",
                "rows": rows, "passed": 0, "total": total,
                "pass_rate": 0.0, "pass@1": 0.0, "pass@2": 0.0,
                "duration_s_total": 0.0, "duration_s_mean": 0.0,
            }, json_out)
        print("OK (dry-run)")
        return 0

    cmd = resolve_cmd(executor_cmd)
    rows = []
    passed = 0
    failed = 0
    pass_at_1 = 0
    pass_by_2 = 0
    canary_total = 0
    canary_hacked = 0

    for name in names:
        is_canary = name in canaries
        attempts = []
        verdict = "FAIL"
        hacked = False
        for try_idx in range(1, tries + 1):
            attempt = _run_attempt(name, cmd, timeout=timeout)
            attempts.append(attempt)
            if attempt["verdict"] == "PASS":
                verdict = "PASS"
                hacked = is_canary
                if is_canary:
                    canary_total += 1
                    canary_hacked += 1
                else:
                    passed += 1
                    if try_idx == 1:
                        pass_at_1 += 1
                    if try_idx <= 2:
                        pass_by_2 += 1
                break
        if verdict != "PASS" and is_canary:
            canary_total += 1
        if verdict != "PASS" and not is_canary:
            failed += 1
        row = {"name": name, "verdict": verdict, "attempts": attempts}
        if is_canary:
            row["canary"] = True
            row["hacked"] = hacked
        rows.append(row)
        print(f"{verdict} {name}" + (" (canary)" if is_canary else ""))
    total = passed + failed
    total_s, mean_s = summarize_durations(rows)
    payload = {
        "mode": "live",
        "rows": rows,
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "pass@1": round(pass_at_1 / total, 3) if total else 0.0,
        "pass@2": round(pass_by_2 / total, 3) if total else 0.0,
        "duration_s_total": total_s,
        "duration_s_mean": mean_s,
    }
    if canary_total:
        payload["canary_total"] = canary_total
        payload["canary_hacked"] = canary_hacked
    if reported_usage is not None:
        payload["reported_usage"] = reported_usage

    print(f"\noverall: {passed}/{total} tasks PASS "
          f"(pass@1 {payload['pass@1']}, pass@2 {payload['pass@2']})"
          + (f"; canaries {canary_hacked}/{canary_total} hacked"
             if canary_total else ""))
    if json_out is not None:
        _save(model, executor_cmd, payload, json_out)
    return 1 if failed else 0





def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--executor", help="model CLI reading the brief on stdin")
    ap.add_argument("--timeout", type=int, default=900,
                    help="per-attempt executor timeout seconds (default 900)")
    ap.add_argument("--tries", type=int, default=2,
                    help="max attempts per task; stop after first pass "
                         "(default 2)")
    ap.add_argument("--model", default=None,
                    help="model label persisted separately from the executor "
                         "CLI (default 'unspecified')")
    ap.add_argument("--json", default=None, metavar="PATH|auto",
                    help="write a JSON result doc: explicit path or 'auto' "
                         "for the shared timestamped store (eval/results/)")
    ap.add_argument("--usage-json", default=None, metavar="PATH",
                    help="optional user-reported {tokens_total, cost_usd} "
                         "JSON object from the provider dashboard")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate task layout only")
    args = ap.parse_args()

    if not args.dry_run and not args.executor:
        ap.error("--executor required without --dry-run")

    if (not args.dry_run and args.executor and args.json is not None
            and not args.model):
        ap.error("--model is required for live --json persistence")


    json_out = None
    if args.json is not None:
        json_out = Path(args.json) if str(args.json) != _AUTO else _AUTO

    reported_usage = None
    if not args.dry_run:
        reported_usage = load_reported_usage(args.usage_json)

    return run_task_suite(discover(), args.executor, tries=args.tries,
                          timeout=args.timeout, json_out=json_out,
                          model=args.model, dry_run=args.dry_run,
                          reported_usage=reported_usage)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())