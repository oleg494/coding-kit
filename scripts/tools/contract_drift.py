#!/usr/bin/env python3
"""contract_drift.py — contract-review pointer for high-materiality diffs.

Review-time advisory, NOT a gate and NOT a doctor row: it needs the diff
context (changed paths) that the doctor, which audits the tree as-is,
does not have. fable-judge's contract-review step uses it;
CONTRIBUTING.md names it.

materiality(changed_paths) -> "high" | "medium" | "low"

    high   — files that execute or steer automatically, or define the
             contract itself: .github/workflows/*, scripts/install.py,
             pyproject/dep definitions (pyproject.toml, setup.py,
             requirements*.txt, Pipfile*, poetry.lock,
             environment.yml/yaml), test-framework infrastructure
             (conftest.py, pytest.ini, tests/_util*,
             eval/task_runner.py, eval/runner.py, eval/results_io.py,
             eval/prompt_assembly.py, eval/scenarios/*), and major
             restructures (VERSION, profile.yml, OPS.md, AGENTS.md,
             adapters/*, integrity-manifest.json, skills/*/SKILL.md).
    medium — process config that shifts behavior without steering:
             lint/test-runner rules (ruff.toml, .ruff.toml, .flake8,
             setup.cfg, tox.ini).
    low    — everything else.

needs_contract_review(paths) -> True iff the diff touches high-
materiality files. This is a path heuristic: it points at a diff worth
a contract review, it cannot prove coverage. A contract document
(AGENTS.md, OPS.md, CONTRIBUTING.md, README.md, docs/SECURITY-MAP.md,
docs/CHANGELOG.md) in the same diff does NOT clear the pointer — its
presence says nothing about whether it describes the change. The
reviewer decides: update the contract, or explain why no change is
needed.

CLI: `contract_drift.py '["<paths>"]'` prints summarize() and exits 0
(advisory, even for HIGH). No argument means an empty diff. Invalid JSON,
non-array/non-string values or extra arguments exit 2 with a stderr diagnostic.

Stdlib only; Windows-safe (backslash paths normalized).
"""
from __future__ import annotations

import sys

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

_HIGH_EXACT = frozenset({
    "version", "profile.yml", "ops.md", "agents.md",
    "integrity-manifest.json", "pyproject.toml", "setup.py",
    "scripts/install.py", "pytest.ini", "conftest.py",
    "eval/task_runner.py", "eval/runner.py", "eval/results_io.py",
    "eval/prompt_assembly.py",
})
_HIGH_PREFIXES = (
    ".github/workflows/", "adapters/", "eval/scenarios/",
)
_HIGH_SUFFIXES = (
    "requirements.txt", "pipfile", "pipfile.lock", "poetry.lock",
    "environment.yml", "environment.yaml",
)

_MEDIUM_EXACT = frozenset({
    "ruff.toml", ".ruff.toml", ".flake8", "setup.cfg", "tox.ini",
})


def _norm(path: str) -> str:
    """Lowercase, unify separators; strip only the relative './' marker
    (leading dots are meaningful: .github/, .ruff.toml)."""
    p = path.replace("\\", "/").strip().lower()
    while p.startswith("./"):
        p = p[2:]
    return p


def _is_high(p: str) -> bool:
    if p in _HIGH_EXACT:
        return True
    if p.endswith(("conftest.py", "pytest.ini")):
        return True
    if p.startswith(_HIGH_PREFIXES):
        return True
    if p.endswith(_HIGH_SUFFIXES):
        return True
    if p.startswith("requirements") and p.endswith(".txt"):
        return True
    if p.startswith("tests/_util"):
        return True
    return p.startswith("skills/") and p.endswith("/skill.md")


def materiality(changed_paths: list[str]) -> str:
    """Highest materiality tier across the changed paths."""
    tiers = {LOW}
    for raw in changed_paths:
        p = _norm(raw)
        if not p:
            continue
        if _is_high(p):
            tiers.add(HIGH)
        elif p in _MEDIUM_EXACT:
            tiers.add(MEDIUM)
    for tier in (HIGH, MEDIUM):
        if tier in tiers:
            return tier
    return LOW


def needs_contract_review(changed_paths: list[str]) -> bool:
    """True iff any changed path is high-materiality.

    Advisory side only: paths are a heuristic for "worth a contract
    review", never proof that the contract covers (or misses) the
    change. A contract document in the same diff does not clear it.
    """
    return materiality(changed_paths) == HIGH


def summarize(changed_paths: list[str]) -> str:
    """Human-readable neutral one-liner for a review report."""
    tier = materiality(changed_paths)
    if tier != HIGH:
        return f"contract review? materiality {tier} — no review pointer"
    paths = [_norm(p) for p in changed_paths]
    high_files = sorted(p for p in paths if _is_high(p))
    return ("contract review? materiality HIGH (" +
            ", ".join(high_files) +
            ") — review the relevant contract (AGENTS.md/OPS.md); update it "
            "if affected or explain why no change")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import json
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        raise SystemExit(0)
    if len(argv) > 1:
        print("error: expected one JSON array of path strings", file=sys.stderr)
        raise SystemExit(2)
    try:
        paths = json.loads(argv[0]) if argv else []
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc.msg}", file=sys.stderr)
        raise SystemExit(2)
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        print("error: expected a JSON array of path strings", file=sys.stderr)
        raise SystemExit(2)
    print(summarize(paths))
