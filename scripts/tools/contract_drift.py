#!/usr/bin/env python3
"""contract_drift.py — AGENTS.md contract materiality gate (wave5 Task 17).

Review-time check, NOT a doctor row: it needs the diff context (changed
paths) that the doctor, which audits the tree as-is, does not have.
fable-judge's "contract drift?" step runs it; CONTRIBUTING.md
names it.

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

needs_contract_update(paths) -> True iff the diff touches high
files WITHOUT any contract document (AGENTS.md, OPS.md,
CONTRIBUTING.md, README.md, docs/SECURITY-MAP.md,
docs/CHANGELOG.md) in the same diff — i.e. the contract silently
drifted from the tree it describes.

Stdlib only; Windows-safe (backslash paths normalized).
"""
from __future__ import annotations

import sys

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# Contract documents: their presence in the same diff proves the change
# carried its contract update. Kept lowercase; compare against _norm().
_CONTRACT_FILES = frozenset(p.lower() for p in (
    "AGENTS.md", "OPS.md", "CONTRIBUTING.md", "README.md",
    "docs/SECURITY-MAP.md", "docs/CHANGELOG.md",
))
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


def needs_contract_update(changed_paths: list[str]) -> bool:
    """True iff high-materiality files changed and no contract doc did."""
    paths = [_norm(p) for p in changed_paths]
    has_high = any(_is_high(p) for p in paths)
    has_contract = any(p in _CONTRACT_FILES for p in paths)
    return has_high and not has_contract


def summarize(changed_paths: list[str]) -> str:
    """Human-readable one-liner for a review report."""
    tier = materiality(changed_paths)
    if tier != HIGH:
        return f"contract drift? materiality {tier} — no gate"
    paths = [_norm(p) for p in changed_paths]
    high_files = sorted(p for p in paths if _is_high(p))
    if needs_contract_update(changed_paths):
        return ("contract drift? materiality HIGH (" +
                ", ".join(high_files) +
                ") without a contract doc — update AGENTS.md/OPS.md "
                "or justify in the report")
    return ("contract drift? materiality HIGH (" +
            ", ".join(high_files) + ") — contract doc present, OK")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import json
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        raise SystemExit(0)
    paths = json.loads(argv[0]) if argv else []
    print(summarize(paths))
    raise SystemExit(1 if needs_contract_update(paths) else 0)
