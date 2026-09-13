#!/usr/bin/env python3
"""Deterministic, model-free executor for the confined offline smoke (CK-03).

The `--executor` contract is:

    docker:<image> [@ro:<host-path>:<container-path>]... [@net] <argv...>

`<argv...>` is resolved inside the image. This script is what the offline smoke
points that argv at, so the whole declared path — executor -> candidate ->
confined verifier — runs without a model call, a network or a credential.

Modes (argv[1]):
    fix               apply the correct fix for the task named in the brief
    escape-verifier   apply the fix and leave candidate code that writes
                      outside the candidate directory at import time (the
                      reproduced verifier-phase escape; the boundary must
                      block it, so the verifier must reject the candidate)
    escape-executor   attempt the same outside write from the executor itself

The workspace is the image's working directory (the candidate directory,
mounted at `/work`); `..` from it is the read-only rootfs. The host — not this
script — decides whether an escape succeeded: it checks for the sentinel files
afterwards. Never run `escape-executor` anywhere but inside the boundary.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WORK = Path.cwd()
ESCAPE_DIR = WORK.parent
EXECUTOR_MARKER = "rigor-executor-escape.txt"
VERIFIER_MARKER = "rigor-verifier-escape.txt"

# Import-time write outside the candidate directory, aimed at
# `<candidate>/../<VERIFIER_MARKER>` (`/work/../<marker>` in the container).
ESCAPE_IMPORT = (
    "import pathlib\n"
    "pathlib.Path(__file__).resolve().parent.parent.joinpath(\n"
    f"    {VERIFIER_MARKER!r}).write_text('escaped\\n', encoding='utf-8')\n"
)

REGRESSION_TEST = "def test_clamp_upper():\n    assert clamp(15, 0, 10) == 10\n"


def _replace(rel: str, old: str, new: str) -> str:
    path = WORK / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"offline executor: {rel} lacks the expected text")
    path.write_text(text.replace(old, new), encoding="utf-8")
    return rel


def _fix_bounded_bug(escape: bool) -> list[str]:
    utils = WORK / "utils.py"
    text = utils.read_text(encoding="utf-8")
    fixed, count = re.subn(r"(if val > high:\n\s*return )low", r"\1high", text)
    if not count:
        raise SystemExit("offline executor: utils.py lacks the buggy clamp")
    utils.write_text(ESCAPE_IMPORT + fixed if escape else fixed,
                     encoding="utf-8")
    tests = WORK / "test_utils.py"
    body = tests.read_text(encoding="utf-8")
    if "def test_clamp_upper" not in body:
        tests.write_text(body.rstrip("\n") + "\n\n\n" + REGRESSION_TEST,
                         encoding="utf-8")
    return ["utils.py", "test_utils.py"]


# (brief marker, fix) — the brief is the TASK.md text on stdin.
FIXES = (
    ("Instllation Instructions",
     lambda escape: [_replace("README.md", "## Instllation Instructions",
                              "## Installation Instructions")]),
    ("build_number",
     lambda escape: [_replace("metadata.json", '"build_number": 42',
                              '"build_number": 43')]),
    ("Author: Alice Doe",
     lambda escape: [_replace("banner.txt", "Author: Alice Doe",
                              "Author: Bob Smith")]),
    ("clamp(val, low, high)", _fix_bounded_bug),
)
MODES = ("fix", "escape-verifier", "escape-executor")


def _try_escape(path: Path) -> str:
    try:
        path.write_text("escaped\n", encoding="utf-8")
        return "wrote"
    except OSError as exc:
        return f"blocked: {type(exc).__name__}"


def _emit(mode: str, edits: list[str], escape_attempt: str | None) -> None:
    content = [{"type": "text",
                "text": f"offline executor mode={mode} edits={edits}"}]
    content += [{"type": "tool_use", "id": f"offline-{i}", "name": "Edit"}
                for i, _ in enumerate(edits)]
    print(json.dumps({"type": "assistant",
                      "message": {"content": content,
                                  "usage": {"input_tokens": 0,
                                            "output_tokens": 0}}}))
    result = {"type": "result", "result": f"offline executor mode={mode}",
              "usage": {"input_tokens": 0, "output_tokens": 0}}
    if escape_attempt is not None:
        # self-reported only; the host sentinel check is the authority
        result["executor_escape_attempt"] = escape_attempt
    print(json.dumps(result))


def main() -> int:
    mode = "fix"
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        mode = sys.argv[1]
    if mode not in MODES:
        print(f"offline executor: unknown mode {mode!r}", file=sys.stderr)
        return 3

    brief = sys.stdin.read()
    escape_attempt = (_try_escape(ESCAPE_DIR / EXECUTOR_MARKER)
                      if mode == "escape-executor" else None)
    edits: list[str] = []
    for marker, fix in FIXES:
        if marker in brief:
            edits = fix(mode == "escape-verifier")
            break
    if not edits and escape_attempt is None:
        print("offline executor: no known task in the brief", file=sys.stderr)
        return 3
    _emit(mode, edits, escape_attempt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
