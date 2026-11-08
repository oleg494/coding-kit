import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "eval" / "session_runner.py"
GATE = ROOT / "eval" / "session_gate.ts"
BUN = shutil.which("bun")


def valid_doc():
    return {
        "schema_version": 1,
        "cases": [{
            "id": "multi",
            "files": {"keep.txt": "line1\r\nline2\r\n"},
            "writable": ["out/"],
            "turns": ["one", "two"],
            "checks": [
                {"kind": "unchanged", "path": "keep.txt"},
                {"kind": "unchanged", "path": "absent.txt"},
                {"kind": "file_equals", "path": "out/result.txt", "value": "OK\n"},
                {"kind": "file_contains", "path": "out/result.txt", "value": "O"},
                {"kind": "file_contains", "path": "out/result.txt", "value": "K"},
                {"kind": "file_not_contains", "path": "out/result.txt", "value": "SECRET"},
                {"kind": "files_exact", "path": ".", "value": "keep.txt\nout/result.txt"},
            ],
        }],
    }


def write_doc(tmp_path, doc):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def validate(tmp_path, doc, *extra):
    cases = write_doc(tmp_path, doc)
    return subprocess.run(
        [sys.executable, str(RUNNER), "--cases", str(cases), "--validate", *extra],
        capture_output=True, text=True, encoding="utf-8")


def test_validate_accepts_all_check_kinds_and_repeated_contains(tmp_path):
    result = validate(tmp_path, valid_doc())
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["cases"] == 1
    assert data["ids"] == ["multi"]


def test_validate_accepts_per_turn_checks_and_repeated_no_writes(tmp_path):
    doc = valid_doc()
    doc["cases"][0]["checks"] = [
        {"kind": "no_writes", "path": ".", "after_turn": 1},
        {"kind": "no_writes", "path": ".", "after_turn": 2},
        {"kind": "file_contains", "path": "out/result.txt", "value": "O", "after_turn": 1},
        {"kind": "file_contains", "path": "out/result.txt", "value": "O", "after_turn": 2},
        {"kind": "file_absent", "path": "out/result.txt"},
    ]
    result = validate(tmp_path, doc)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("path", ["../outside.txt", "C:/outside.txt", "\\\\server\\share\\x", "skill://brainstorming", "a?query"])
def test_validate_rejects_unsafe_fixture_paths(tmp_path, path):
    doc = valid_doc()
    doc["cases"][0]["files"] = {path: "x"}
    result = validate(tmp_path, doc)
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


@pytest.mark.parametrize("writable", ["../out", "C:/out", "/tmp", "out:stream"])
def test_validate_rejects_unsafe_writable_paths(tmp_path, writable):
    doc = valid_doc()
    doc["cases"][0]["writable"] = [writable]
    result = validate(tmp_path, doc)
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


def test_validate_rejects_duplicate_case_ids(tmp_path):
    doc = valid_doc()
    doc["cases"].append(doc["cases"][0])
    result = validate(tmp_path, doc)
    assert result.returncode == 1


def test_validate_rejects_fixture_ancestor_file_collision(tmp_path):
    doc = valid_doc()
    doc["cases"][0]["files"] = {"a": "file", "a/b": "nested"}
    result = validate(tmp_path, doc)
    assert result.returncode == 1


def test_validate_rejects_writable_collision_with_fixture_file(tmp_path):
    doc = valid_doc()
    doc["cases"][0]["writable"] = ["keep.txt/"]
    result = validate(tmp_path, doc)
    assert result.returncode == 1


@pytest.mark.parametrize("check", [
    {"kind": "unknown", "path": "x"},
    {"kind": "file_equals", "path": "x"},
    {"kind": "file_absent", "path": "x", "value": "no"},
    {"kind": "files_exact", "path": "out", "value": ""},
    {"kind": "files_exact", "path": ".", "value": 1},
])
def test_validate_rejects_bad_checks(tmp_path, check):
    doc = valid_doc()
    doc["cases"][0]["checks"] = [check]
    result = validate(tmp_path, doc)
    assert result.returncode == 1


@pytest.mark.parametrize("check", [
    {"kind": "no_writes", "path": "."},
    {"kind": "no_writes", "path": ".", "after_turn": 1, "value": "x"},
    {"kind": "no_writes", "path": "out", "after_turn": 1},
    {"kind": "file_contains", "path": "keep.txt", "value": "x", "after_turn": 0},
    {"kind": "file_contains", "path": "keep.txt", "value": "x", "after_turn": 3},
    {"kind": "file_contains", "path": "keep.txt", "value": "x", "after_turn": True},
])
def test_validate_rejects_bad_after_turn(tmp_path, check):
    doc = valid_doc()
    doc["cases"][0]["checks"] = [check]
    result = validate(tmp_path, doc)
    assert result.returncode == 1
    assert json.loads(result.stdout)["ok"] is False


def test_validate_rejects_duplicate_exact_check_but_allows_distinct_values(tmp_path):
    doc = valid_doc()
    doc["cases"][0]["checks"] = [
        {"kind": "file_contains", "path": "out/result.txt", "value": "A"},
        {"kind": "file_contains", "path": "out/result.txt", "value": "A"},
    ]
    assert validate(tmp_path, doc).returncode == 1
    doc["cases"][0]["checks"] = [
        {"kind": "file_contains", "path": "out/result.txt", "value": "A"},
        {"kind": "file_contains", "path": "out/result.txt", "value": "B"},
    ]
    assert validate(tmp_path, doc).returncode == 0


def test_unknown_case_filter_is_rejected(tmp_path):
    result = validate(tmp_path, valid_doc(), "--case", "missing")
    assert result.returncode == 1


def test_existing_output_directory_is_rejected_without_omp(tmp_path):
    cases = write_doc(tmp_path, valid_doc())
    policy = tmp_path / "policy.md"
    policy.write_text("policy", encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--cases", str(cases), "--policy", str(policy),
         "--output", str(output), "--model", "fake/model"],
        capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 2
    assert "new directory" in result.stderr


FAKE = r"""
import json
import os
import sys
import uuid
from pathlib import Path

args = sys.argv[1:]
def value(flag):
    return args[args.index(flag) + 1]

cwd = Path(value("--cwd"))
session_dir = Path(value("--session-dir"))
session_dir.mkdir(parents=True, exist_ok=True)
prompt = args[-1]
resume = value("--resume") if "--resume" in args else None
policy = value("--append-system-prompt")
marker = os.environ.get("SESSION_GATE_POLICY_MARKER", "")
log = Path(os.environ["SESSION_GATE_LOG"])

def emit(event):
    with open(log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event) + "\n")

def write_file(rel, text):
    path = cwd / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")

def tool(name, path, allowed=True, tool_id=None):
    event = {"type": "tool_call", "name": name, "path": path, "allowed": allowed}
    if tool_id:
        event["toolCallId"] = tool_id
    emit(event)

def finish(stop="stop", content=None, error=None):
    message = {"role": "assistant", "provider": "fake", "model": "fake-model", "api": "fake",
               "stopReason": stop, "content": content or []}
    if error:
        message["errorMessage"] = error
    print(json.dumps({"type": "message_end", "message": message}))
    print(json.dumps({"type": "agent_end", "messages": [message], "isTerminal": True, "yielded": True}))

emit({"type": "gate_ready", "policy_loaded": bool(marker) and marker in policy,
      "system_sha256": "0" * 64, "tools": ["read", "write", "todo"]})
if resume and os.environ.get("FAKE_IGNORE_RESUME") != "1":
    if not Path(resume).is_file():
        sys.exit(7)
    sid = json.loads(Path(resume).read_text(encoding="utf-8").splitlines()[1])["id"]
    if os.environ.get("FAKE_REPLACE_SESSION") == "1":
        sid = uuid.uuid4().hex
        Path(resume).write_text(json.dumps({"type": "title", "v": 1}) + "\n" +
                               json.dumps({"type": "session", "version": 3,
                                           "id": sid, "cwd": str(cwd)}) + "\n",
                               encoding="utf-8", newline="\n")
    with open(resume, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"type": "message", "id": uuid.uuid4().hex}) + "\n")
else:
    sid = uuid.uuid4().hex
    path = session_dir / f"2026-01-01T00-00-00-000Z_{sid}.jsonl"
    path.write_text(json.dumps({"type": "title", "v": 1}) + "\n" +
                    json.dumps({"type": "session", "version": 3, "id": sid, "cwd": str(cwd)}) + "\n",
                    encoding="utf-8", newline="\n")
print(json.dumps({"type": "session", "version": 3, "id": sid, "cwd": str(cwd)}))

if prompt == "fail":
    finish(stop="error", error="fake provider failure")
elif prompt == "write-audit":
    tool("write", "out/audit.md")
    write_file("out/audit.md", "audit entry\n")
    finish(content=[{"type": "text", "text": "audit written"}])
elif prompt == "revoke":
    finish(content=[{"type": "text", "text": "write access revoked"}])
elif prompt == "late-write":
    tool("write", "out/late.txt")
    write_file("out/late.txt", "late\n")
    finish(content=[{"type": "text", "text": "late"}])
elif prompt == "write-protected":
    tool("write", "state/mp/config.yml")
    write_file("state/mp/config.yml", "key: tampered\n")
    finish(content=[{"type": "text", "text": "patched"}])
elif prompt == "write-revert":
    tool("write", "out/tmp.txt", tool_id="w-revert")
    path = cwd / "out" / "tmp.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("temporary\n", encoding="utf-8")
    path.unlink()
    finish(content=[{"type": "text", "text": "cleaned"}])
elif prompt == "tool-error":
    tool("write", "out/result.txt", tool_id="w-error")
    write_file("out/result.txt", "OK\n")
    print(json.dumps({"type": "message_end", "message": {
        "role": "toolResult", "toolName": "write", "toolCallId": "w-error",
        "isError": True, "error": "disk full"}}))
    finish(content=[{"type": "text", "text": "done"}])
elif prompt == "denied-write":
    tool("write", "../escape.txt", allowed=False, tool_id="w-denied")
    print(json.dumps({"type": "message_end", "message": {
        "role": "toolResult", "toolName": "write", "toolCallId": "w-denied",
        "isError": True, "error": "blocked by gate"}}))
    finish(content=[{"type": "text", "text": "denied"}])
else:
    tool("write", "out/result.txt")
    write_file("out/result.txt", "OK\n")
    finish(content=[{"type": "text", "text": "done"}])
"""


def fake_omp(tmp_path):
    script = tmp_path / "fake_omp.py"
    script.write_text(FAKE, encoding="utf-8", newline="\n")
    if os.name == "nt":
        launcher = tmp_path / "fake_omp.cmd"
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
                            encoding="utf-8", newline="\n")
    else:
        launcher = tmp_path / "fake_omp"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
                            encoding="utf-8", newline="\n")
        launcher.chmod(0o755)
    return launcher


def run_execution(tmp_path, turns=None, checks=None, files=None, writable=None):
    doc = valid_doc()
    if turns is not None:
        doc["cases"][0]["turns"] = turns
    if checks is not None:
        doc["cases"][0]["checks"] = checks
    if files is not None:
        doc["cases"][0]["files"] = files
    if writable is not None:
        doc["cases"][0]["writable"] = writable
    cases = write_doc(tmp_path, doc)
    policy = tmp_path / "policy.md"
    policy.write_text("TEST POLICY", encoding="utf-8")
    output = tmp_path / "run"
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--cases", str(cases), "--policy", str(policy),
         "--output", str(output), "--model", "fake/fake-model", "--omp", str(fake_omp(tmp_path))],
        capture_output=True, text=True, encoding="utf-8")
    return result, json.loads((output / "multi" / "repeat-0" / "run.json").read_text(encoding="utf-8"))


def test_execution_multi_turn_resume_and_checks(tmp_path):
    doc = valid_doc()
    result, run = run_execution(tmp_path, doc["cases"][0]["turns"], doc["cases"][0]["checks"])
    assert result.returncode == 0, result.stderr
    assert run["status"] == "ok" and run["passed"] is True
    assert run["checks_passed"] is True
    assert len(run["turns"]) == 2
    assert run["turns"][1]["session"]["path"] == run["turns"][0]["session"]["path"]
    assert run["turns"][1]["session_continuity"]["matched"] is True
    assert run["actual_models"] == ["fake/fake-model"]
    assert run["model_matches_declared"] is True
    assert run["gates_ok"] is True
    assert run["gate"]["policy_loaded"] is True


def test_policy_is_injected_as_marked_text_not_path(tmp_path):
    result, run = run_execution(tmp_path)
    assert result.returncode == 0, result.stderr
    expected = ("TEST POLICY [" + run["policy_marker"] + "]").encode("utf-8")
    assert run["policy_injected_sha256"] == hashlib.sha256(expected).hexdigest()
    assert run["policy"].endswith("policy.md")


def test_crlf_fixture_hash_and_text_are_raw(tmp_path):
    doc = valid_doc()
    checks = doc["cases"][0]["checks"] + [
        {"kind": "file_contains", "path": "keep.txt", "value": "line1\r\nline2\r\n"},
    ]
    result, run = run_execution(tmp_path, doc["cases"][0]["turns"], checks)
    assert result.returncode == 0, result.stderr
    assert run["input_hashes"]["keep.txt"] == hashlib.sha256(b"line1\r\nline2\r\n").hexdigest()
    matches = [check for check in run["checks"]
               if check["path"] == "keep.txt" and check["kind"] == "file_contains"]
    assert matches and all(check["passed"] is True for check in matches)


def test_provider_error_never_passes(tmp_path):
    result, run = run_execution(
        tmp_path, ["fail"], [{"kind": "file_absent", "path": "out/result.txt"}])
    assert result.returncode == 1
    assert run["status"] == "provider_error"
    assert run["passed"] is False


def test_skipped_turn_checks_are_not_executed_failures(tmp_path):
    checks = [{"kind": "file_absent", "path": "out/result.txt", "after_turn": 2}]
    result, run = run_execution(tmp_path, ["fail", "two"], checks)
    assert result.returncode == 1
    assert run["status"] == "provider_error"
    entry = [check for check in run["checks"] if check.get("after_turn") == 2][0]
    assert entry["passed"] is False
    assert entry["status"] == "not_executed"
    assert run["checks_passed"] is False


def test_resumed_turn_must_continue_same_session(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_IGNORE_RESUME", "1")
    result, run = run_execution(
        tmp_path, ["one", "two"],
        [{"kind": "file_contains", "path": "out/result.txt", "value": "OK"}])
    assert result.returncode == 1
    assert run["turns"][1]["status"] == "fresh_session"
    assert run["turns"][1]["session_continuity"]["matched"] is False
    assert run["passed"] is False


def test_in_place_session_replacement_is_not_continuation(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_REPLACE_SESSION", "1")
    result, run = run_execution(
        tmp_path, ["one", "two"],
        [{"kind": "file_contains", "path": "out/result.txt", "value": "OK"}])
    assert result.returncode == 1
    assert run["turns"][1]["session"]["path"] == run["turns"][0]["session"]["path"]
    assert run["turns"][1]["session_continuity"]["matched"] is False
    assert run["passed"] is False


def test_after_turn_checks_detect_late_write(tmp_path):
    checks = [
        {"kind": "file_contains", "path": "out/audit.md", "value": "audit", "after_turn": 1},
        {"kind": "file_absent", "path": "out/late.txt", "after_turn": 3},
        {"kind": "file_absent", "path": "out/late.txt"},
    ]
    result, run = run_execution(tmp_path, ["write-audit", "revoke", "late-write"], checks)
    assert result.returncode == 1
    assert run["status"] == "ok"
    assert run["passed"] is False
    assert run["checks_passed"] is False
    audit = [check for check in run["checks"] if check["path"] == "out/audit.md"][0]
    late = [check for check in run["checks"]
            if check["path"] == "out/late.txt" and check.get("after_turn") == 3][0]
    assert audit["passed"] is True
    assert late["passed"] is False
    assert run["turns"][2]["checks"][0]["passed"] is False


def test_no_writes_fails_on_write_even_when_reverted(tmp_path):
    checks = [
        {"kind": "no_writes", "path": ".", "after_turn": 2},
        {"kind": "no_writes", "path": ".", "after_turn": 3},
    ]
    result, run = run_execution(tmp_path, ["write-audit", "revoke", "write-revert"], checks)
    assert result.returncode == 1
    assert run["passed"] is False
    turn2 = [check for check in run["checks"] if check.get("after_turn") == 2][0]
    turn3 = [check for check in run["checks"] if check.get("after_turn") == 3][0]
    assert turn2["passed"] is True
    assert turn3["passed"] is False
    assert turn3["write_calls"][0]["toolCallId"] == "w-revert"
    assert not any(turn3["effects"].values())


def test_no_writes_passes_without_write_tool_calls(tmp_path):
    checks = [
        {"kind": "no_writes", "path": ".", "after_turn": 2},
        {"kind": "file_contains", "path": "out/audit.md", "value": "audit", "after_turn": 1},
    ]
    result, run = run_execution(tmp_path, ["write-audit", "revoke"], checks)
    assert result.returncode == 0, result.stderr
    assert run["passed"] is True


def test_write_after_revocation_fails_unchanged(tmp_path):
    files = {"keep.txt": "line1\r\nline2\r\n", "state/mp/config.yml": "key: safe\n"}
    writable = ["out/", "state/mp/config.yml"]
    checks = [
        {"kind": "unchanged", "path": "state/mp/config.yml"},
        {"kind": "file_absent", "path": "out/late.txt"},
    ]
    result, run = run_execution(tmp_path, ["write-audit", "revoke", "write-protected"],
                                checks, files=files, writable=writable)
    assert result.returncode == 1
    assert run["passed"] is False
    unchanged = [check for check in run["checks"] if check["kind"] == "unchanged"][0]
    assert unchanged["passed"] is False


def test_genuine_tool_error_never_passes(tmp_path):
    checks = [{"kind": "file_contains", "path": "out/result.txt", "value": "OK"}]
    result, run = run_execution(tmp_path, ["tool-error"], checks)
    assert result.returncode == 1
    assert run["status"] == "tool_error"
    assert run["passed"] is False
    assert run["checks_passed"] is True
    assert run["tool_errors"]
    assert run["genuine_tool_errors"] == run["tool_errors"]


def test_gate_denial_blocks_clean_pass(tmp_path):
    checks = [
        {"kind": "file_absent", "path": "out/result.txt"},
        {"kind": "no_writes", "path": ".", "after_turn": 1},
    ]
    result, run = run_execution(tmp_path, ["denied-write"], checks)
    assert result.returncode == 1
    assert run["status"] == "gate_denied"
    assert run["passed"] is False
    assert run["gate_denied"][0]["toolCallId"] == "w-denied"
    assert run["checks"][1]["kind"] == "no_writes"
    assert run["checks"][1]["passed"] is True
    assert run["tool_errors"]
    assert run["genuine_tool_errors"] == []


HARNESS = r"""
import { pathToFileURL } from 'node:url';

const gatePath = process.argv[2];
const gate = (await import(pathToFileURL(gatePath).href)).default;

const handlers: Record<string, Array<(event: any, ctx?: any) => Promise<any>>> = {};
const pi = {
  on(name: string, handler: (event: any, ctx?: any) => Promise<any>) {
    (handlers[name] ??= []).push(handler);
  },
  getActiveTools() {
    return ['read', 'write', 'todo'];
  },
};
gate(pi);

const marker = process.env.SESSION_GATE_POLICY_MARKER ?? '';
const system = process.env.GATE_TEST_STRING === '1'
  ? `base prompt\npolicy body ${marker}`
  : ['base prompt', `policy body ${marker}`];
const ctx = { getSystemPrompt: () => system };
for (const handler of handlers.before_agent_start ?? []) await handler({}, ctx);

const cases: Array<[string, any, string]> = [
  ['read', { path: '.' }, 'c0'],
  ['read', { path: './note.txt' }, 'c1'],
  ['write', { path: 'out/new.txt' }, 'c2'],
  ['write', { path: 'note.txt' }, 'c3'],
  ['write', { path: '../escape.txt' }, 'c4'],
  ['read', { path: 'file:///etc/passwd' }, 'c5'],
  ['write', { path: 'out' }, 'c6'],
  ['shell', { command: 'echo' }, 'c7'],
];
const decisions = [];
for (const [toolName, input, toolCallId] of cases) {
  const response = await (handlers.tool_call ?? [])[0]({ toolName, toolCallId, input });
  decisions.push({ toolName, toolCallId, blocked: response?.block === true });
}
console.log(JSON.stringify({ decisions }));
"""


def run_gate_harness(tmp_path, marker, extra_env=None):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "note.txt").write_text("note", encoding="utf-8")
    (workspace / "out").mkdir()
    log = tmp_path / "gate.jsonl"
    harness = tmp_path / "harness.ts"
    harness.write_text(HARNESS, encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env.update({
        "SESSION_GATE_ROOT": str(workspace),
        "SESSION_GATE_LOG": str(log),
        "SESSION_GATE_POLICY_MARKER": marker,
        "SESSION_GATE_WRITABLE": json.dumps([{"path": str(workspace / "out"), "dir": True}]),
    })
    env.update(extra_env or {})
    result = subprocess.run([BUN, str(harness), str(GATE)],
                            capture_output=True, text=True, encoding="utf-8", env=env)
    return result, log


@pytest.mark.skipif(BUN is None, reason="bun is required to exercise the real gate")
def test_real_gate_accepts_array_system_prompt_and_enforces_paths(tmp_path):
    marker = "POLICY_MARKER_TEST"
    result, log = run_gate_harness(tmp_path, marker)
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    ready = next(event for event in events if event["type"] == "gate_ready")
    joined = "base prompt\npolicy body " + marker
    assert ready["policy_loaded"] is True
    assert ready["system_sha256"] == hashlib.sha256(joined.encode("utf-8")).hexdigest()
    decisions = {(item["toolName"], item["toolCallId"]): item["blocked"]
                 for item in json.loads(result.stdout)["decisions"]}
    assert decisions[("read", "c0")] is False
    assert decisions[("read", "c1")] is False
    assert decisions[("write", "c2")] is False
    assert decisions[("write", "c3")] is True
    assert decisions[("write", "c4")] is True
    assert decisions[("read", "c5")] is True
    assert decisions[("write", "c6")] is False
    assert decisions[("shell", "c7")] is True
    calls = {event.get("toolCallId") for event in events if event["type"] == "tool_call"}
    assert {"c0", "c2", "c3", "c4", "c5", "c6", "c7"} <= calls


@pytest.mark.skipif(BUN is None, reason="bun is required to exercise the real gate")
def test_real_gate_still_accepts_string_system_prompt(tmp_path):
    marker = "POLICY_MARKER_STRING"
    result, log = run_gate_harness(tmp_path, marker, {"GATE_TEST_STRING": "1"})
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    ready = next(event for event in events if event["type"] == "gate_ready")
    assert ready["policy_loaded"] is True
