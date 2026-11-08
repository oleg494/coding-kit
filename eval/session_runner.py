#!/usr/bin/env python3
"""Isolated multi-turn OMP session eval runner (cases schema v1).

One case is a frozen workspace, an ordered list of prompts, and file checks.
Every turn is a separate ``omp --print`` process; later turns resume the exact
session file produced by the previous turn and are rejected when the process
starts a fresh session instead. The extension gate is a tool-level boundary, not
an OS sandbox: it denies shell/network/URI access, reads outside the workspace,
writes outside the workspace, and writes to undeclared paths.

Checks are evaluated on final state unless they carry an ``after_turn`` (1-based)
index, in which case the runner evaluates them right after that turn and carries
the result into the final report. ``no_writes`` proves a turn performed no write
tool call and caused no file effects; it requires ``after_turn``. A genuine tool
error or gate-denied attempt never turns a run into a pass.

Validation is offline. Model execution is never part of ``--validate``.

Usage:
    python eval/session_runner.py --cases eval/session_cases.json --validate
    python eval/session_runner.py --cases cases.json --policy policy.md \
        --output eval/runs/2026-11-08-review --model provider/model
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCHEMA_VERSION = 1
GATE = Path(__file__).resolve().with_name("session_gate.ts")
TURN_LIMIT = 240
PROCESS_LIMIT = 270
CHECK_KINDS = {"file_equals", "file_absent", "file_contains", "file_not_contains",
               "files_exact", "unchanged", "no_writes"}
CASE_KEYS = {"id", "files", "writable", "turns", "checks"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
RUNTIME = "memory:\n  backend: off\nrecap:\n  enabled: false\nttsr:\n  enabled: false\nretry:\n  fallbackChains: {}\n"


class InputError(ValueError):
    """Invalid cases, policy, or runner input."""


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside(root, target):
    try:
        rel = os.path.relpath(target, root)
    except ValueError:
        return False
    return rel == "." or (rel != ".." and not rel.startswith(".." + os.sep)
                          and not os.path.isabs(rel))


def _nearest_real(path):
    current = Path(path)
    while not current.exists():
        if current.parent == current:
            break
        current = current.parent
    return current.resolve(strict=True)


def _assert_contained(root, target, label):
    root = Path(root).resolve(strict=True)
    target = Path(target).resolve(strict=False)
    if not _inside(root, target):
        raise InputError(f"{label}: path escapes workspace: {target}")
    real = _nearest_real(target)
    if not _inside(root, real):
        raise InputError(f"{label}: real path escapes workspace: {target}")


def _rel_entry(value, label, allow_root=False):
    if not isinstance(value, str) or not value:
        raise InputError(f"{label}: expected non-empty relative path string")
    if "\0" in value or "://" in value or "?" in value or "#" in value:
        raise InputError(f"{label}: URI/query/control syntax is not allowed: {value!r}")
    raw = value
    if raw.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", raw):
        raise InputError(f"{label}: absolute, drive, or UNC path is not allowed: {value!r}")
    is_dir = raw.endswith(("/", "\\"))
    body = raw.rstrip("/\\")
    if body in ("", "."):
        if allow_root and not raw.startswith(("~",)):
            return "", True
        raise InputError(f"{label}: workspace root is only allowed as a writable directory")
    if ":" in body:
        raise InputError(f"{label}: drive or alternate-stream syntax is not allowed: {value!r}")
    parts = body.replace("\\", "/").split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise InputError(f"{label}: empty or traversal segment: {value!r}")
        if part.endswith((" ", ".")):
            raise InputError(f"{label}: Windows-hostile trailing dot/space: {value!r}")
    return "/".join(parts), is_dir


def _case_path(value, label):
    rel, is_dir = _rel_entry(value, label)
    if is_dir:
        raise InputError(f"{label}: file path must not end with a separator")
    return rel


def _prefixes(rel):
    parts = rel.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def _check_path_conflicts(files, writable, label):
    file_keys = {os.path.normcase(rel) for rel in files}
    for rel in files:
        for parent in _prefixes(rel):
            if os.path.normcase(parent) in file_keys:
                raise InputError(f"{label}: file path is nested under another file: {rel}")
    for rel, is_dir in writable:
        if not rel:
            continue
        key = os.path.normcase(rel)
        if is_dir:
            if key in file_keys:
                raise InputError(f"{label}: writable directory collides with a file: {rel}")
        else:
            marker = os.path.normcase(rel + "/")
            if any(key.startswith(marker) for key in file_keys):
                raise InputError(f"{label}: writable file is a parent of a fixture file: {rel}")
        for parent in _prefixes(rel):
            if os.path.normcase(parent) in file_keys:
                raise InputError(f"{label}: writable path is nested under a fixture file: {rel}")
    for rel, is_dir in writable:
        for other, other_dir in writable:
            if other == rel:
                if is_dir != other_dir:
                    raise InputError(f"{label}: writable file and directory share a path: {rel}")
            elif not is_dir and os.path.normcase(other).startswith(os.path.normcase(rel + "/")):
                raise InputError(f"{label}: writable file is a parent of another writable path: {rel}")


def _validate_case(raw, index):
    prefix = f"cases[{index}]"
    if not isinstance(raw, dict):
        raise InputError(f"{prefix}: expected object")
    unknown = set(raw) - CASE_KEYS
    missing = CASE_KEYS - set(raw)
    if unknown:
        raise InputError(f"{prefix}: unknown keys: {sorted(unknown)}")
    if missing:
        raise InputError(f"{prefix}: missing keys: {sorted(missing)}")
    case_id = raw["id"]
    if not isinstance(case_id, str) or not ID_RE.match(case_id):
        raise InputError(f"{prefix}.id: expected [A-Za-z0-9][A-Za-z0-9_.-]{{0,63}}")
    files = raw["files"]
    if not isinstance(files, dict):
        raise InputError(f"{prefix}.files: expected object of relative path -> utf8 text")
    normalized_files = {}
    seen_files = set()
    for key, text in files.items():
        rel = _case_path(key, f"{prefix}.files")
        if not isinstance(text, str):
            raise InputError(f"{prefix}.files[{key!r}]: expected string")
        marker = os.path.normcase(rel)
        if marker in seen_files:
            raise InputError(f"{prefix}.files: duplicate path: {rel}")
        seen_files.add(marker)
        normalized_files[rel] = text
    writable = raw["writable"]
    if not isinstance(writable, list):
        raise InputError(f"{prefix}.writable: expected list of relative files/directories")
    normalized_writable = []
    seen_writable = set()
    for item in writable:
        rel, is_dir = _rel_entry(item, f"{prefix}.writable", allow_root=True)
        marker = (os.path.normcase(rel), is_dir)
        if marker in seen_writable:
            raise InputError(f"{prefix}.writable: duplicate path: {item!r}")
        seen_writable.add(marker)
        normalized_writable.append((rel, is_dir))
    turns = raw["turns"]
    if not isinstance(turns, list) or not turns:
        raise InputError(f"{prefix}.turns: expected non-empty list of prompt strings")
    for i, turn in enumerate(turns):
        if not isinstance(turn, str) or not turn.strip():
            raise InputError(f"{prefix}.turns[{i}]: expected non-empty string")
        if "\0" in turn:
            raise InputError(f"{prefix}.turns[{i}]: NUL byte is not allowed")
    checks = raw["checks"]
    if not isinstance(checks, list) or not checks:
        raise InputError(f"{prefix}.checks: expected non-empty list")
    normalized_checks = []
    seen_checks = set()
    for i, check in enumerate(checks):
        label = f"{prefix}.checks[{i}]"
        if not isinstance(check, dict):
            raise InputError(f"{label}: expected object")
        unknown = set(check) - {"kind", "path", "value", "after_turn"}
        if unknown:
            raise InputError(f"{label}: unknown keys: {sorted(unknown)}")
        kind = check.get("kind")
        if kind not in CHECK_KINDS:
            raise InputError(f"{label}.kind: expected one of {sorted(CHECK_KINDS)}")
        has_value = "value" in check
        after_turn = check.get("after_turn")
        if "after_turn" in check:
            if (not isinstance(after_turn, int) or isinstance(after_turn, bool)
                    or not 1 <= after_turn <= len(turns)):
                raise InputError(f"{label}.after_turn: expected integer 1..{len(turns)}")
        if kind == "no_writes":
            if check.get("path") != ".":
                raise InputError(f"{label}.path: no_writes requires '.'")
            rel = "."
            if has_value:
                raise InputError(f"{label}.value: not allowed for no_writes")
            if "after_turn" not in check:
                raise InputError(f"{label}.after_turn: required for no_writes")
        elif kind == "files_exact":
            if check.get("path") != ".":
                raise InputError(f"{label}.path: files_exact requires '.'")
            rel = "."
        else:
            rel = _case_path(check.get("path"), f"{label}.path")
        if kind in ("file_equals", "file_contains", "file_not_contains", "files_exact"):
            if not has_value or not isinstance(check["value"], str):
                raise InputError(f"{label}.value: required string for {kind}")
        elif has_value:
            raise InputError(f"{label}.value: not allowed for {kind}")
        value_marker = (check.get("value")
                        if kind in ("file_equals", "file_contains", "file_not_contains", "files_exact")
                        else None)
        marker = (kind, os.path.normcase(rel), check.get("after_turn"), value_marker)
        if marker in seen_checks:
            raise InputError(f"{label}: duplicate check {kind} {rel}")
        seen_checks.add(marker)
        entry = {"kind": kind, "path": rel}
        if has_value:
            entry["value"] = check["value"]
        if "after_turn" in check:
            entry["after_turn"] = after_turn
        normalized_checks.append(entry)
    _check_path_conflicts(normalized_files, normalized_writable, prefix)
    return {"id": case_id, "files": normalized_files, "writable": normalized_writable,
            "turns": turns, "checks": normalized_checks}


def _load_doc(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError(f"cannot read cases file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"cases file is not valid JSON: {exc}") from exc


def _validate_doc(doc):
    if not isinstance(doc, dict):
        raise InputError("top level: expected object")
    unknown = set(doc) - {"schema_version", "cases"}
    missing = {"schema_version", "cases"} - set(doc)
    if unknown:
        raise InputError(f"top level: unknown keys: {sorted(unknown)}")
    if missing:
        raise InputError(f"top level: missing keys: {sorted(missing)}")
    if (not isinstance(doc["schema_version"], int) or isinstance(doc["schema_version"], bool)
            or doc["schema_version"] != SCHEMA_VERSION):
        raise InputError(f"schema_version: expected integer {SCHEMA_VERSION}")
    cases = doc["cases"]
    if not isinstance(cases, list) or not cases:
        raise InputError("cases: expected non-empty list")
    normalized = []
    seen = set()
    for i, raw in enumerate(cases):
        case = _validate_case(raw, i)
        marker = os.path.normcase(case["id"])
        if marker in seen:
            raise InputError(f"cases[{i}].id: duplicate id: {case['id']}")
        seen.add(marker)
        normalized.append(case)
    return normalized


def _snapshot(root):
    result = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in list(dirnames):
            path = Path(dirpath) / name
            if path.is_symlink():
                rel = path.relative_to(root).as_posix()
                result[rel] = "symlink:" + os.readlink(path)
                dirnames.remove(name)
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[rel] = "symlink:" + os.readlink(path)
            elif path.is_file():
                result[rel] = _sha_file(path)
    return result


def _effects(before, after):
    return {
        "created": sorted(set(after) - set(before)),
        "modified": sorted(path for path in set(before) & set(after) if before[path] != after[path]),
        "deleted": sorted(set(before) - set(after)),
    }


def _session_header(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for _ in range(32):
                line = handle.readline()
                if not line:
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("type") == "session":
                    return event
    except OSError:
        return None
    return None


def _same_path(left, right):
    try:
        return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))
    except (OSError, ValueError):
        return False


def _session_size(path):
    try:
        return os.stat(path).st_size
    except OSError:
        return None


def _same_session(discovery, expected):
    """True only when a resumed turn continued the exact original session file."""
    path, expected_path = discovery.get("path"), (expected or {}).get("path")
    if not path or not expected_path:
        return False
    header = _session_header(expected_path)
    if (not header or not header.get("id")
            or header.get("id") != (expected or {}).get("id")
            or header.get("id") != discovery.get("id")):
        return False
    return _same_path(path, expected_path)


def _discover_session(session_dir, workspace, before_paths, stdout_events, previous):
    records = []
    if session_dir.is_dir():
        for path in sorted(session_dir.rglob("*.jsonl")):
            header = _session_header(path)
            if header and _same_path(header.get("cwd", ""), workspace):
                records.append((path, header))
    wanted = [event.get("id") for event in stdout_events
              if event.get("type") == "session" and event.get("id")]
    for session_id in reversed(wanted):
        for path, header in records:
            if header.get("id") == session_id:
                return {"path": str(path), "id": session_id, "candidates": [str(p) for p, _ in records]}
    fresh = [(path, header) for path, header in records
             if str(path.resolve()) not in before_paths]
    if len(fresh) == 1:
        path, header = fresh[0]
        return {"path": str(path), "id": header.get("id"), "candidates": [str(path)]}
    if len(fresh) > 1:
        return {"path": None, "error": "multiple new OMP session files; cannot choose truthfully",
                "candidates": [str(path) for path, _ in fresh]}
    if previous and Path(previous).is_file():
        header = _session_header(previous)
        if header and _same_path(header.get("cwd", ""), workspace):
            return {"path": str(previous), "id": header.get("id"), "candidates": [str(previous)]}
    if len(records) == 1:
        path, header = records[0]
        return {"path": str(path), "id": header.get("id"), "candidates": [str(path)]}
    return {"path": None, "error": f"no OMP session file found under {session_dir}",
            "candidates": [str(path) for path, _ in records]}


def _parse_events(stdout):
    events, malformed = [], 0
    for line in stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            events.append(json.loads(text))
        except json.JSONDecodeError:
            malformed += 1
    return events, malformed


def _summarize(events):
    assistant, errors, tool_errors, agent_end = [], [], [], None
    for event in events:
        kind = event.get("type") if isinstance(event, dict) else None
        if kind == "message_end" and isinstance(event.get("message"), dict):
            message = event["message"]
            if message.get("role") == "assistant":
                assistant.append(message)
            elif message.get("role") == "toolResult" and message.get("isError") is True:
                tool_errors.append({"toolName": message.get("toolName"),
                                    "toolCallId": message.get("toolCallId"),
                                    "error": message.get("error")})
        if kind == "agent_end":
            agent_end = event
        if isinstance(kind, str) and "error" in kind.lower():
            errors.append({"type": kind, "error": event.get("error") or event.get("message")})
    tool_calls = []
    for message in assistant:
        content = message.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "toolCall":
                    args = item.get("arguments")
                    path = args.get("path") if isinstance(args, dict) else None
                    tool_calls.append({"id": item.get("id"), "name": item.get("name"), "path": path})
        if message.get("errorMessage"):
            errors.append({"type": "provider_error", "error": message["errorMessage"],
                           "stopReason": message.get("stopReason")})
        if message.get("stopReason") in ("error", "aborted"):
            errors.append({"type": "stop_reason", "error": None,
                           "stopReason": message.get("stopReason")})
    models, seen = [], set()
    for message in assistant:
        if not message.get("model"):
            continue
        item = {"provider": message.get("provider"), "model": message.get("model"),
                "api": message.get("api"), "stopReason": message.get("stopReason")}
        marker = (item["provider"], item["model"], item["api"], item["stopReason"])
        if marker not in seen:
            seen.add(marker)
            models.append(item)
    final_text = ""
    sources = []
    if agent_end and isinstance(agent_end.get("messages"), list):
        sources.extend(agent_end["messages"])
    sources.extend(assistant)
    for message in sources:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        text = "\n".join(item.get("text", "") for item in content
                         if isinstance(item, dict) and item.get("type") == "text")
        if text.strip():
            final_text = text
    terminal = agent_end is not None and agent_end.get("isTerminal") is not False
    return {
        "assistant_messages": len(assistant),
        "models": models,
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "provider_errors": errors,
        "agent_end_present": agent_end is not None,
        "agent_end_terminal": terminal,
        "yielded": agent_end.get("yielded") if agent_end else None,
        "final_text": final_text,
    }


def _command(args, workspace, session_dir, runtime, policy_injected, prompt, resume):
    cmd = [args.omp, "--print", "--mode", "json", "--no-title",
           "--no-context-files", "--no-skills", "--no-rules", "--no-extensions",
           "--no-lsp", "--no-prewalk", "--tools", "read,write,todo",
           "--extension", str(GATE), "--config", str(runtime), "--model", args.model,
           "--append-system-prompt", policy_injected, "--session-dir", str(session_dir),
           "--cwd", str(workspace), "--max-time", str(TURN_LIMIT),
           "--approval-mode", "yolo"]
    if resume:
        cmd.extend(["--resume", str(resume)])
    cmd.append(prompt)
    return cmd


def _gate_env(workspace, gate_log, writable, policy_marker):
    specs = [{"path": str((workspace / Path(*rel.split("/"))).resolve()) if rel else str(workspace),
              "dir": is_dir} for rel, is_dir in writable]
    return {"SESSION_GATE_ROOT": str(workspace), "SESSION_GATE_LOG": str(gate_log),
            "SESSION_GATE_WRITABLE": json.dumps(specs),
            "SESSION_GATE_POLICY_MARKER": policy_marker}


def _gate_slice(gate_log, offset):
    if not gate_log.is_file():
        return [], 0, offset
    with open(gate_log, "rb") as handle:
        handle.seek(offset)
        data = handle.read()
    events, malformed = [], 0
    for line in data.decode("utf-8", "replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            malformed += 1
    return events, malformed, offset + len(data)


def _gate_summary(events, malformed):
    actions = [event for event in events if event.get("type") == "tool_call"]
    ready = [event for event in events if event.get("type") == "gate_ready"]
    return {
        "ready": bool(ready),
        "policy_loaded": any(event.get("policy_loaded") is True for event in ready),
        "system_sha256": ready[-1].get("system_sha256") if ready else None,
        "events": len(events),
        "malformed": malformed,
        "actions": actions,
        "denied": [event for event in actions if event.get("allowed") is not True],
    }


def _file_list(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in list(dirnames):
            path = Path(dirpath) / name
            if path.is_symlink():
                dirnames.remove(name)
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_file() or path.is_symlink():
                files.append(path.relative_to(root).as_posix())
    return sorted(files)


def _evaluate_check(root, workspace, initial, check, turn):
    rel, kind = check["path"], check["kind"]
    result = {"kind": kind, "path": rel}
    if "after_turn" in check:
        result["after_turn"] = check["after_turn"]
    if kind == "no_writes":
        if turn is None:
            result.update(passed=False, error="no_writes requires an executed turn")
            return result
        effects = turn.get("effects") or {}
        changed = {name: list(effects.get(name) or [])
                   for name in ("created", "modified", "deleted")}
        writes = [{"toolCallId": action.get("toolCallId"), "path": action.get("path"),
                   "normalized": action.get("normalized")}
                  for action in (turn.get("gate") or {}).get("actions", [])
                  if action.get("name") == "write" and action.get("allowed") is True]
        result.update(passed=not any(changed.values()) and not writes,
                      effects=changed, write_calls=writes)
        return result
    if kind == "files_exact":
        actual_files = _file_list(root)
        actual = "\n".join(actual_files)
        result.update(passed=actual == check["value"], actual=actual,
                      actual_files=actual_files)
        return result
    path = workspace / Path(*rel.split("/"))
    try:
        _assert_contained(root, path, f"check {kind} {rel}")
    except InputError as exc:
        result.update(passed=False, error=str(exc))
        return result
    if kind == "file_absent":
        result["passed"] = not os.path.lexists(path)
        return result
    if kind == "unchanged" and rel not in initial:
        result["passed"] = not os.path.lexists(path)
        return result
    if path.is_symlink() or not path.is_file():
        result.update(passed=False, error="expected a regular file")
        return result
    result["actual_sha256"] = _sha_file(path)
    if kind == "unchanged":
        expected = initial.get(rel)
        result["passed"] = expected is not None and expected == result["actual_sha256"]
        return result
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            data = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        result.update(passed=False, error=f"cannot read utf8 file: {exc}")
        return result
    if kind == "file_equals":
        result["passed"] = data == check["value"]
    elif kind == "file_contains":
        result["passed"] = check["value"] in data
    else:
        result["passed"] = check["value"] not in data
    if not result["passed"]:
        result["actual_preview"] = data[:500]
    return result


def _check_case(case, workspace, initial, after_turn=None, turn=None):
    root = workspace.resolve(strict=True)
    return [(index, _evaluate_check(root, workspace, initial, check, turn))
            for index, check in enumerate(case["checks"])
            if check.get("after_turn") == after_turn]


def _read_text(path, label):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"{label}: cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"{label}: not UTF-8: {path}: {exc}") from exc
    if not text.strip():
        raise InputError(f"{label}: empty file: {path}")
    if "\0" in text:
        raise InputError(f"{label}: NUL byte is not allowed: {path}")
    return text


def _run_case(case, repeat, args, output_root, policy, policy_text, policy_sha, gate_sha, cases_sha):
    run_dir = output_root / case["id"] / f"repeat-{repeat}"
    run_dir.mkdir(parents=True)
    workspace = run_dir / "workspace"
    workspace.mkdir()
    session_dir = run_dir / "session"
    session_dir.mkdir()
    gate_log = run_dir / "gate.jsonl"
    runtime = run_dir / "runtime.yml"
    runtime.write_text(RUNTIME, encoding="utf-8", newline="\n")
    result = {
        "schema_version": SCHEMA_VERSION, "case": case["id"], "repeat": repeat,
        "declared_model": args.model, "omp": args.omp,
        "policy": str(policy), "policy_sha256": policy_sha,
        "cases_sha256": cases_sha, "gate_sha256": gate_sha,
        "runtime_sha256": _sha_file(runtime),
        "isolation": {"tool_boundary": "session_gate.ts", "os_sandbox": False,
                      "tools": ["read", "write", "todo"], "shell": False,
                      "network": False, "uri_paths": False},
        "workspace": str(workspace), "session_dir": str(session_dir),
        "turns": [], "checks": [], "status": "setup_error", "passed": False,
        "errors": [],
    }
    try:
        for rel, text in case["files"].items():
            path = workspace / Path(*rel.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        for rel, is_dir in case["writable"]:
            path = workspace if not rel else workspace / Path(*rel.split("/"))
            if is_dir:
                path.mkdir(parents=True, exist_ok=True)
                if not path.is_dir():
                    raise InputError(f"writable directory collides with a file: {rel or '.'}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists() and path.is_dir():
                    raise InputError(f"writable file collides with a directory: {rel}")
        initial = _snapshot(workspace)
        result["input_hashes"] = initial
        policy_marker = "SESSION_RUNNER_POLICY_" + os.urandom(8).hex()
        policy_injected = policy_text + " [" + policy_marker + "]"
        result["policy_marker"] = policy_marker
        result["policy_injected_sha256"] = _sha(policy_injected.encode("utf-8"))
        env = dict(os.environ, **_gate_env(workspace, gate_log, case["writable"], policy_marker))
        session_path = None
        per_turn_checks = {}
        gate_offset = gate_log.stat().st_size if gate_log.is_file() else 0
        for index, prompt in enumerate(case["turns"]):
            if index and not session_path:
                result["turns"].append({"index": index, "prompt": prompt, "status": "skipped",
                                        "error": "no resumable session from previous turn"})
                continue
            expected_session = None
            resume_size = None
            if index:
                previous_header = _session_header(session_path) if Path(session_path).is_file() else None
                if not previous_header:
                    result["turns"].append({"index": index, "prompt": prompt, "status": "session_missing",
                                            "error": f"saved session is missing: {session_path}"})
                    for later in range(index + 1, len(case["turns"])):
                        result["turns"].append({"index": later, "prompt": case["turns"][later],
                                                "status": "skipped", "error": "session_missing"})
                    break
                expected_session = {"id": previous_header.get("id"), "path": session_path}
                resume_size = _session_size(session_path)
            before = _snapshot(workspace)
            before_sessions = {str(path.resolve()) for path in session_dir.rglob("*.jsonl")}
            turn_gate_offset = gate_offset
            cmd = _command(args, workspace, session_dir, runtime, policy_injected,
                           prompt, session_path if index else None)
            started = time.monotonic()
            timeout_error = None
            try:
                proc = subprocess.run(cmd, cwd=str(workspace), env=env, capture_output=True,
                                      encoding="utf-8", errors="replace", timeout=PROCESS_LIMIT)
                stdout, stderr, code = proc.stdout or "", proc.stderr or "", proc.returncode
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                code, timeout_error = None, f"turn exceeded {PROCESS_LIMIT}s"
            except OSError as exc:
                stdout, stderr, code = "", str(exc), None
                result["errors"].append(f"cannot execute omp: {exc}")
            turn = {"index": index, "prompt": prompt, "exit": code,
                    "seconds": round(time.monotonic() - started, 3)}
            if timeout_error:
                turn.update(status="timeout", error=timeout_error)
            events, malformed = _parse_events(stdout)
            summary = _summarize(events)
            turn.update({key: value for key, value in summary.items()
                         if key not in ("final_text", "assistant_messages", "tool_calls")})
            turn["assistant_messages"] = summary["assistant_messages"]
            turn["tool_calls"] = summary["tool_calls"]
            turn["final_text"] = summary["final_text"]
            turn["malformed_lines"] = malformed
            turn["effects"] = _effects(before, _snapshot(workspace))
            gate_events, gate_malformed, gate_offset = _gate_slice(gate_log, turn_gate_offset)
            turn["gate"] = _gate_summary(gate_events, gate_malformed)
            transcript_dir = run_dir / "transcripts"
            transcript_dir.mkdir(exist_ok=True)
            stdout_path = transcript_dir / f"turn-{index}.stdout.jsonl"
            stderr_path = transcript_dir / f"turn-{index}.stderr.txt"
            stdout_path.write_text(stdout, encoding="utf-8", newline="\n")
            stderr_path.write_text(stderr, encoding="utf-8", newline="\n")
            turn["stdout"] = str(stdout_path)
            turn["stderr"] = str(stderr_path)
            if "status" not in turn:
                if code is None:
                    status = "execution_error"
                elif code != 0:
                    status = f"exit_{code}"
                elif summary["provider_errors"]:
                    status = "provider_error"
                elif malformed:
                    status = "malformed_transcript"
                elif not summary["agent_end_present"]:
                    status = "malformed_result"
                elif not summary["agent_end_terminal"]:
                    status = "incomplete_result"
                elif not summary["assistant_messages"] or not summary["models"]:
                    status = "malformed_result"
                elif not turn["gate"]["ready"]:
                    status = "gate_missing"
                elif turn["gate"]["malformed"]:
                    status = "gate_malformed"
                elif not turn["gate"]["policy_loaded"]:
                    status = "policy_not_loaded"
                else:
                    status = "ok"
                turn["status"] = status
            discovery = _discover_session(session_dir, workspace, before_sessions, events, session_path)
            turn["session"] = discovery
            if expected_session:
                matched = _same_session(discovery, expected_session)
                grew = resume_size is not None and _session_size(session_path) not in (None, resume_size)
                turn["session_continuity"] = {"expected_id": expected_session["id"],
                                              "expected_path": expected_session["path"],
                                              "matched": matched, "transcript_grew": grew}
                if not matched or not grew:
                    if turn["status"] == "ok":
                        turn["status"] = "fresh_session" if not matched and discovery.get("path") else "session_missing"
                elif discovery.get("path"):
                    session_path = discovery["path"]
            elif discovery.get("path"):
                session_path = discovery["path"]
            elif turn["status"] == "ok":
                turn["status"] = "session_missing"
            result["turns"].append(turn)
            turn_checks = _check_case(case, workspace, initial, index + 1, turn)
            turn["checks"] = [entry for _, entry in turn_checks]
            per_turn_checks.update(dict(turn_checks))
            if turn["status"] != "ok":
                for later in range(index + 1, len(case["turns"])):
                    result["turns"].append({"index": later, "prompt": case["turns"][later],
                                            "status": "skipped", "error": f"previous turn: {turn['status']}"})
                break
        result["session_path"] = session_path
        all_gate_events, all_gate_malformed, _ = _gate_slice(gate_log, 0)
        gate = _gate_summary(all_gate_events, all_gate_malformed)
        result["gate"] = gate
        executed = [turn for turn in result["turns"] if "gate" in turn]
        gates_ok = bool(executed) and all(turn["gate"]["ready"] and turn["gate"]["policy_loaded"]
                                          and not turn["gate"]["malformed"] for turn in executed)
        result["gates_ok"] = gates_ok
        final_checks = dict(_check_case(case, workspace, initial))
        compiled_checks = []
        for check_index, check in enumerate(case["checks"]):
            if check.get("after_turn") is None:
                compiled_checks.append(final_checks[check_index])
            elif check_index in per_turn_checks:
                compiled_checks.append(per_turn_checks[check_index])
            else:
                compiled_checks.append({"kind": check["kind"], "path": check["path"],
                                        "after_turn": check["after_turn"], "passed": False,
                                        "status": "not_executed",
                                        "error": "the turn this check observes did not execute"})
        result["checks"] = compiled_checks
        checks_passed = all(check.get("passed") is True for check in compiled_checks)
        result["checks_passed"] = checks_passed
        result["effects"] = {
            "created": sorted({path for turn in result["turns"]
                               for path in (turn.get("effects") or {}).get("created", [])}),
            "modified": sorted({path for turn in result["turns"]
                                for path in (turn.get("effects") or {}).get("modified", [])}),
            "deleted": sorted({path for turn in result["turns"]
                               for path in (turn.get("effects") or {}).get("deleted", [])}),
        }
        result["tool_errors"] = [{"turn": turn["index"], **error}
                                 for turn in result["turns"] for error in turn.get("tool_errors", [])]
        denied = [{"turn": turn["index"], **{key: event.get(key) for key in
                                             ("name", "toolCallId", "path", "normalized", "reason")}}
                  for turn in result["turns"]
                  for event in (turn.get("gate") or {}).get("denied", [])]
        denied_ids = {item.get("toolCallId") for item in denied if item.get("toolCallId")}
        result["gate_denied"] = denied
        result["genuine_tool_errors"] = [error for error in result["tool_errors"]
                                         if not (error.get("toolCallId")
                                                 and error["toolCallId"] in denied_ids)]
        actual_models = sorted({(m["model"] if "/" in m["model"] else
                                 f"{m.get('provider')}/{m['model']}")
                                for turn in result["turns"] for m in turn.get("models", [])
                                if m.get("model")})
        result["actual_models"] = actual_models
        declared = args.model.lower()
        result["model_matches_declared"] = bool(actual_models) and all(
            model.lower() == declared
            or ("/" not in declared and model.lower().split("/")[-1] == declared)
            for model in actual_models)
        statuses = [turn["status"] for turn in result["turns"]]
        failure = next((status for status in statuses if status != "ok"), None)
        if failure is None and len(statuses) != len(case["turns"]):
            failure = "task_incomplete"
        if failure is None and not result["model_matches_declared"]:
            failure = "model_mismatch"
        if failure is None and not gates_ok:
            if not any(turn["gate"]["ready"] for turn in executed):
                failure = "gate_missing"
            elif any(turn["gate"]["malformed"] for turn in executed):
                failure = "gate_malformed"
            else:
                failure = "policy_not_loaded"
        if failure is None and result["genuine_tool_errors"]:
            failure = "tool_error"
        if failure is None and denied:
            failure = "gate_denied"
        result["status"] = failure or "ok"
        result["passed"] = result["status"] == "ok" and checks_passed and gates_ok
    except Exception as exc:  # noqa: BLE001 - keep one truthful failed result
        result["status"] = "runner_error"
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        result["passed"] = False
    (run_dir / "run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _resolve_omp(value):
    candidate = Path(value)
    if candidate.is_file():
        return str(candidate.resolve())
    found = shutil.which(value)
    if not found:
        raise InputError(f"OMP executable not found: {value}")
    return str(Path(found).resolve())


def _positive(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("expected integer >= 1")
    return number


def _parser():
    parser = argparse.ArgumentParser(description="Isolated multi-turn OMP session eval runner")
    parser.add_argument("--cases", required=True, help="cases JSON file (schema version 1)")
    parser.add_argument("--policy", help="frozen policy file appended to the system prompt")
    parser.add_argument("--output", help="new output directory")
    parser.add_argument("--model", help="explicit OMP model id")
    parser.add_argument("--omp", default="omp", help="OMP executable (default: omp)")
    parser.add_argument("--case", dest="case_ids", action="append", help="run only this case id")
    parser.add_argument("--repeat", type=_positive, default=1, help="repetitions per case (default: 1)")
    parser.add_argument("--validate", action="store_true", help="validate cases/input only; no model process")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        cases = _validate_doc(_load_doc(args.cases))
        if args.case_ids:
            wanted = list(dict.fromkeys(args.case_ids))
            known = {case["id"] for case in cases}
            unknown = [case_id for case_id in wanted if case_id not in known]
            if unknown:
                raise InputError(f"unknown --case ids: {unknown}")
            cases = [case for case in cases if case["id"] in set(wanted)]
        if not GATE.is_file():
            raise InputError(f"gate extension is missing: {GATE}")
        policy_text = _read_text(args.policy, "policy") if args.policy else None
        if args.validate:
            print(json.dumps({"ok": True, "schema_version": SCHEMA_VERSION,
                              "cases": len(cases), "ids": [case["id"] for case in cases],
                              "policy": bool(policy_text), "gate": str(GATE)}))
            return 0
        if not args.model:
            raise InputError("--model is required for execution")
        if not args.policy:
            raise InputError("--policy is required for execution")
        if not args.output:
            raise InputError("--output is required for execution")
        output_root = Path(args.output).resolve()
        if output_root.exists():
            raise InputError(f"--output must be a new directory: {output_root}")
        args.omp = _resolve_omp(args.omp)
        output_root.mkdir(parents=True)
        policy = Path(args.policy).resolve()
        policy_sha = _sha_file(policy)
        gate_sha = _sha_file(GATE)
        cases_sha = _sha_file(Path(args.cases))
        runs = []
        for case in cases:
            for repeat in range(args.repeat):
                run = _run_case(case, repeat, args, output_root, policy, policy_text,
                                policy_sha, gate_sha, cases_sha)
                runs.append(run)
                print(json.dumps({"case": run["case"], "repeat": repeat, "status": run["status"],
                                  "passed": run["passed"], "checks_passed": run.get("checks_passed"),
                                  "effects": run.get("effects"), "run": str(output_root / run["case"] / f"repeat-{repeat}" / "run.json")},
                                 ensure_ascii=False), flush=True)
        summary = {"schema_version": SCHEMA_VERSION, "cases": str(Path(args.cases).resolve()),
                   "model": args.model, "policy": str(Path(args.policy).resolve()),
                   "runs": [{"case": run["case"], "repeat": run["repeat"], "status": run["status"],
                             "passed": run["passed"], "checks_passed": run.get("checks_passed")}
                            for run in runs]}
        (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
        return 0 if all(run["passed"] for run in runs) else 1
    except InputError as exc:
        if args.validate:
            print(json.dumps({"ok": False, "errors": [str(exc)]}))
            return 1
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
