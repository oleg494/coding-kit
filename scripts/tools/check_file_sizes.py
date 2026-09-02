#!/usr/bin/env python3

"""Unified file-size gate for coding-kit (god-files prohibited).

ONE source of truth for the limits. Consumers:
- doctor.py — file-size check (import collect);
- CI (.github/workflows/test.yml) — `--ci` (exit 1 on violations);
- OPS.md rule — constant mirror
  (the hook is autonomous, runs from ~/.claude/hooks/ etc. — does not import
  scripts/); when editing limits, change BOTH places.

Limits (industry practice; original finding id lost in a research.db reset):
- code: soft 500 / hard 1000 (SonarQube python:S104 = 1000, ESLint = 300 —
  we sit between: the agent's context budget);
- docs: soft 300 / hard 500 (canon MD/SKILL.md are read by the agent whole).

Grandfathering (baseline, SonarQube new-code quality gate pattern):
files already above hard when the rule was introduced are pinned in
scripts/file_size_baseline.json at their CURRENT line count (as measured
by this script). They may only SHRINK (cutting); growth = error. New
files above hard — always error. After cutting a file — remove it from
the baseline.

Run:
    python3 scripts/tools/check_file_sizes.py            # report (exit 0)
    python3 scripts/tools/check_file_sizes.py --ci       # gate: exit 1 on error
"""
import argparse
import json
import os
import subprocess
import sys

from pathlib import Path

# stdlib-only: no scripts/_compat.py dependency (memory/ moved out of the kit)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110 — optional, lives without it
    pass

ROOT = Path(__file__).resolve().parents[2]

# Limits: (soft, hard). soft = nudge/warning, hard = block/gate.
LIMITS = {
    "code": {"soft": 500, "hard": 1000, "ext": (
        ".py", ".js", ".ts", ".sh", ".go", ".rs", ".java", ".c", ".cpp",
        ".css", ".html", ".toml")},
    "docs": {"soft": 300, "hard": 500, "ext": (".md",)},
}

# Directories out of the tree (by name, any level).
EXCLUDE_DIRS = {".git", "db", "node_modules", "__pycache__", ".cache",
                "dist", "build", "vendor"}

# Names not counted (append-only logs, generated, backups).
EXCLUDE_NAMES = {"CHANGELOG.md", "index.md"}

BASELINE_PATH = Path(__file__).resolve().parent.parent / "file_size_baseline.json"


def _tier_for(rel_path: str):
    ext = os.path.splitext(rel_path)[1].lower()
    for tier, conf in LIMITS.items():
        if ext in conf["ext"]:
            return tier
    return None


def _count_lines(path: Path) -> int:
    """Lines like wc -l: count of \n (binary, fast). A file without a
    trailing newline loses its last line by one — same as wc -l and the
    base (db/files.lines) we cross-check against."""
    with open(path, "rb") as fh:
        return sum(1 for _ in fh)


def _load_baseline():
    if not BASELINE_PATH.is_file():
        return {}
    with open(BASELINE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _level(rel: str, lines: int, tier: str, baseline: dict):
    """(level, cap) for one file: level (hard/baseline-grown/soft/
    baseline-done/baseline-ok) or None (within limits); cap — baseline pin."""
    conf = LIMITS[tier]
    if rel in baseline:
        cap = baseline[rel].get("lines", conf["hard"])
        if lines > cap:
            return "baseline-grown", cap
        if lines <= conf["hard"]:
            return "baseline-done", cap
        return "baseline-ok", cap
    if lines > conf["hard"]:
        return "hard", None
    if lines > conf["soft"]:
        return "soft", None
    return None, None


def collect(root: Path) -> list:
    """All tree files with line counts and verdicts. Only violations
    (soft/hard/baseline-grown) + baseline-done — clean ones are not returned."""
    baseline = _load_baseline()
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS
                             and not d.startswith("venv"))
        for name in sorted(filenames):
            if name in EXCLUDE_NAMES or name.endswith((".bak", ".orig")):
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            tier = _tier_for(rel)
            if tier is None:
                continue
            try:
                lines = _count_lines(full)
            except OSError:
                continue
            level, cap = _level(rel, lines, tier, baseline)
            if level in (None, "baseline-ok"):
                continue
            rows.append({"rel_path": rel, "lines": lines, "tier": tier,
                         "level": level, "cap": cap})
    return rows


def staged_rows(root: Path) -> list:
    """Verdicts for files in the git index (staged): count lines of their
    TO-BE-COMMITTED content (git show :path), not the working tree.
    Skip deleted/binary/out-of-tier. Empty result — not a gate."""
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            cwd=str(root), capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    baseline = _load_baseline()
    rows = []
    for rel in r.stdout.decode("utf-8", "replace").split("\0"):
        rel = rel.strip()
        if not rel:
            continue
        tier = _tier_for(rel)
        if tier is None or os.path.basename(rel) in EXCLUDE_NAMES:
            continue
        try:
            g = subprocess.run(["git", "show", f":{rel}"],
                               cwd=str(root), capture_output=True,
                               timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if g.returncode != 0:
            continue  # removed from the index / not staged content
        lines = g.stdout.count(b"\n")
        level, cap = _level(rel, lines, tier, baseline)
        if level in (None, "baseline-ok"):
            continue
        rows.append({"rel_path": rel, "lines": lines, "tier": tier,
                     "level": level, "cap": cap})
    return rows


def gate(rows: list) -> tuple:
    """(errors, warnings, info). error = hard/baseline-grown; warning = soft;
    info = baseline-done (already under hard — the pin can be lifted)."""
    errors = [r for r in rows if r["level"] in ("hard", "baseline-grown")]
    warnings = [r for r in rows if r["level"] == "soft"]
    info = [r for r in rows if r["level"] == "baseline-done"]
    return errors, warnings, info


def _fmt(r: dict) -> str:
    lim = LIMITS[r["tier"]]
    if r["level"] == "baseline-grown":
        return (f"{r['rel_path']}: {r['lines']} lines (> baseline "
                f"{r.get('cap')}) — GROWTH FORBIDDEN, only cutting")
    if r["level"] == "baseline-done":
        return (f"{r['rel_path']}: {r['lines']} lines (already <= hard "
                f"{lim['hard']}) — remove the file from the baseline: the "
                f"hard limit takes over")
    if r["level"] == "hard":
        return (f"{r['rel_path']}: {r['lines']} lines (> hard {lim['hard']}) "
                f"— god-file: cut it or pin it in the baseline with a reason")
    return (f"{r['rel_path']}: {r['lines']} lines (> soft {lim['soft']}, "
            f"hard {lim['hard']})")


def main():
    ap = argparse.ArgumentParser(description="File-size gate (god-files)")
    ap.add_argument("--ci", action="store_true",
                    help="CI gate: exit 1 on error violations")
    ap.add_argument("--quiet", action="store_true",
                    help="errors only, no warnings")
    ap.add_argument("--root", default=None,
                    help="root to scan (default: the coding-kit root; "
                         "for a pre-commit hook — git rev-parse "
                         "--show-toplevel)")
    ap.add_argument("--staged", action="store_true",
                    help="staged-files gate (git diff --cached): counts "
                         "lines of THEIR indexed content, exit 1 on error. "
                         "For a git pre-commit hook")
    ap.add_argument("--reviewdog", action="store_true",
                    help="print hard violations in reviewdog errorformat: "
                         "path:1:1: message")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else ROOT

    if args.staged:
        rows = staged_rows(root)
        errors, warnings, info = gate(rows)
        for r in errors:
            print(f"[✗] {_fmt(r)}")
        for r in info:
            print(f"[i] {_fmt(r)}")
        if errors:
            print(f"total: {len(errors)} staged violations — commit blocked")
            sys.exit(1)
        print(f"[v] staged files within limits ({len(rows)} warnings)" if warnings
              else "[v] staged files within limits")
        sys.exit(0)

    rows = collect(root)
    errors, warnings, info = gate(rows)

    if args.reviewdog:
        # errorformat %f:%l:%c: %m — reviewdog posts it into the PR/check.
        for r in errors:
            print(f"{r['rel_path']}:1:1: god-file: {_fmt(r)}")
        sys.exit(0)

    if errors:
        print(f"[x] hard violations ({len(errors)}):")
        for r in errors:
            print(f"  {_fmt(r)}")
    if warnings and not args.quiet:
        print(f"[!] above the soft limit ({len(warnings)}):")
        for r in warnings:
            print(f"  {_fmt(r)}")
    if info and not args.quiet:
        print(f"[i] baseline pins can be lifted ({len(info)}):")
        for r in info:
            print(f"  {_fmt(r)}")
    if not errors and not warnings and not info:
        print("[v] all files within limits (soft/hard)")
    elif not errors:
        print(f"total: hard 0, soft {len(warnings)} — gate green")
    sys.exit(1 if (args.ci and errors) else 0)


if __name__ == "__main__":
    main()
