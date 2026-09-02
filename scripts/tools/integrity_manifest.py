#!/usr/bin/env python3
"""integrity_manifest.py — SHA-256 manifest over the kit control plane.

Cymulate CBSE (Configuration-Based Sandbox Escape) threat model, 2026-05:
sandbox isolation is bypassed by writing trusted config files from inside
(Claude Code CVE-2026-25725: attacker writes a SessionStart hook that runs
silently on the next session). The writable control plane, not the sandbox,
is the real boundary. This script hashes every kit file that executes or
steers automatically; doctor fails the kit on drift, deploy refuses to
roll out a drifted tree.

Honest limitation (Cymulate's own caveat): this detects drift — it cannot
prevent a harness-level hook compromise.

Scope (exact, wave1 Task 2 — every file that executes or steers;
v4.0.2 adds eval truth: scenario briefs, task briefs, trigger queries,
committed baselines. Mutable eval/results artifacts stay unpinned):
    OPS.md, AGENTS.md, profile.yml, SKILL_RUNTIME.md,
    adapters/*.md, scripts/**/*.py, eval/*.py (incl. tasks/*/verify.py
    and tasks/_verify_common.py), eval/scenarios/*.md,
    eval/tasks/*/TASK.md, eval/trigger_queries.json,
    eval/baselines/*.json,
    memory/db-tools/*.py, memory/scripts/*.py, skills/*/SKILL.md

Hashes are computed over utf-8 text with newlines normalized to \n, so a
CRLF checkout of the same content never flags false drift.

Run:
    python scripts/tools/integrity_manifest.py            # check (exit 1 on drift)
    python scripts/tools/integrity_manifest.py --update   # regenerate baseline
    python scripts/tools/integrity_manifest.py --root DIR # operate on a tree
"""
import argparse
import fnmatch
import hashlib
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110,BLE001 — reconfigure is optional
    pass

KIT = Path(__file__).resolve().parents[2]
MANIFEST_NAME = "integrity-manifest.json"

# (kind, pattern) rows: kind "file" = exact relpath, "glob" = fnmatch over
# the whole tree, "tree" = all *.py under a directory prefix.
_FILE_SCOPE = ("OPS.md", "AGENTS.md", "profile.yml", "SKILL_RUNTIME.md",
               "eval/trigger_queries.json")
_GLOB_SCOPE = ("adapters/*.md", "eval/*.py", "eval/scenarios/*.md",
               "eval/tasks/*/TASK.md", "eval/baselines/*.json")
_TREE_SCOPE = ("scripts", "memory/db-tools", "memory/scripts")


def in_scope(rel: str) -> bool:
    """True when rel (posix) belongs to the control plane."""
    if rel in _FILE_SCOPE:
        return True
    if rel.endswith(".py"):
        top = rel.split("/")[0]
        if top in ("eval",):
            return True
        for prefix in _TREE_SCOPE:
            if rel.startswith(prefix + "/"):
                return True
        if rel.startswith("scripts/"):
            return True
    if rel.startswith("skills/") and rel.endswith("/SKILL.md"):
        return True
    return any(fnmatch.fnmatchcase(rel, pat) for pat in _GLOB_SCOPE)


def scope_files(root: Path) -> list[Path]:
    """Control-plane files present under root, posix-sorted (case-sensitive
    — the same order everywhere; Windows rglob casefolds otherwise)."""
    out = []
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if in_scope(rel):
                out.append(p)
    return [p for _, p in sorted(
        (p.relative_to(root).as_posix(), p) for p in out)]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_file(p: Path) -> str:
    text = p.read_text(encoding="utf-8", errors="replace")
    return _sha256_text(text.replace("\r\n", "\n").replace("\r", "\n"))


def build_manifest(root: Path) -> dict[str, str]:
    """{relpath (posix, sorted): sha256 of \\n-normalized utf-8 content}."""
    return {p.relative_to(root).as_posix(): _hash_file(p)
            for p in scope_files(root)}


def check(root: Path, manifest: dict[str, str]) -> list[str]:
    """Drifted/added/removed relpaths (sorted). `manifest` maps relpath ->
    expected sha256; anything in the tree but not in it is ADDED, anything
    in it but not in the tree is REMOVED, hash mismatch is DRIFTED."""
    problems = []
    current = {p.relative_to(root).as_posix(): _hash_file(p)
               for p in scope_files(root)}
    for rel in sorted(set(manifest) | set(current)):
        if rel not in current:
            problems.append(f"removed: {rel}")
        elif rel not in manifest:
            problems.append(f"added: {rel}")
        elif manifest[rel] != current[rel]:
            problems.append(f"drifted: {rel}")
    return problems


def load_manifest(root: Path) -> dict | None:
    f = root / MANIFEST_NAME
    if not f.is_file():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) and "files" in data else None


def update_or_create(root: Path, version: str | None = None) -> dict[str, str]:
    """Regenerate the baseline (explicit --update only, file_size_baseline
    pattern) and write it with a kit_version stamp. Returns the files map."""
    if version is None:
        vfile = root / "VERSION"
        version = vfile.read_text(encoding="utf-8").strip() if vfile.is_file() \
            else "unknown"
    files = build_manifest(root)
    payload = {"kit_version": version, "files": files}
    (root / MANIFEST_NAME).write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true",
                    help="regenerate the manifest (writes "
                         f"{MANIFEST_NAME}); default mode checks")
    ap.add_argument("--root", default=str(KIT),
                    help="kit root to operate on (default: the coding-kit "
                         "root this script ships in)")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    if args.update:
        files = update_or_create(root)
        print(f"manifest updated: {len(files)} files hashed")
        return 0

    data = load_manifest(root)
    if data is None:
        print(f"FAIL: no readable {MANIFEST_NAME} in {root} — "
              "run with --update to create the baseline", file=sys.stderr)
        return 2
    problems = check(root, data["files"])
    if problems:
        for p in problems:
            print(p)
        print(f"integrity FAIL: {len(problems)} control-plane file(s) "
              "drifted/added/removed")
        return 1
    print(f"integrity OK: {len(data['files'])} control-plane files verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
