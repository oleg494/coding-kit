#!/usr/bin/env python3
"""backup_memory.py — backup/DR for the memory pillar (~/.memory).

Why: the Wiki + SQLite databases are the kit's cross-chat memory — the one
asset that cannot be rebuilt from the repo (db/*.db are gitignored by
design; everything else in ~/.memory is rebuildable via install.py).
SQLite warns against raw file copies of live databases (WAL corruption,
https://www.sqlite.org/howtocorrupt.html §2.2) — so .db files go through
sqlite3's online backup API, everything else through copytree.

Usage:
    python scripts/tools/backup_memory.py                     # backup
    python scripts/tools/backup_memory.py --restore-drill DIR  # restore+verify drill
    python scripts/tools/backup_memory.py --list
"""
import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110,BLE001 — optional console nicety
    pass

DEFAULT_ROOT = Path.home() / ".memory"
# Files that are rebuilt by install.py / build.py — excluded from backups.
REBUILDABLE = {"_compat.pyc", "__pycache__"}


def memory_root() -> Path:
    import os
    return Path(os.environ.get("MEMORY_ROOT") or DEFAULT_ROOT)


def _backup_db(src: Path, dst: Path) -> None:
    """One database via sqlite3 online backup API (WAL-safe)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_con = sqlite3.connect(str(src))
    dst_con = sqlite3.connect(str(dst))
    try:
        src_con.backup(dst_con)
        dst_con.commit()
    finally:
        src_con.close()
        dst_con.close()


def backup(dest: Path | None = None, root: Path | None = None) -> dict:
    """Create a timestamped backup under dest (default <root>/backups).

    Returns {"name", "path", "files", "dbs"}; raises on missing root."""
    root = root or memory_root()
    if not root.is_dir():
        raise FileNotFoundError(f"memory root missing: {root}")
    stamp = time.strftime("%Y%m%dT%H%M%S")
    target = (dest or root / "backups") / stamp
    if target.exists():  # same-second rerun
        target = target.with_name(target.name + "_1")
    target.mkdir(parents=True)

    copied, dbs = 0, 0
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root)
        # Never back up the backups, caches, or rebuildable engine state.
        if "backups" in rel.parts or any(p in REBUILDABLE for p in rel.parts):
            continue
        if item.is_dir():
            (target / rel).mkdir(parents=True, exist_ok=True)
            continue
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if item.suffix in (".db", ".sqlite", ".sqlite3", ".db3"):
            _backup_db(item, out)
            dbs += 1
        else:
            shutil.copy2(item, out)
            copied += 1
    return {"name": target.name, "path": str(target),
            "files": copied, "dbs": dbs}


def restore_drill(backup_dir: Path, root: Path | None = None) -> dict:
    """Restore a backup into a temp MEMORY_ROOT and verify search works.

    Returns {"restored_root", "files", "dbs", "probe"}; probe is the
    search_all.py output (exit code + first hits) proving the restore is
    usable, not just present."""
    root = root or memory_root()
    if not backup_dir.is_dir():
        raise FileNotFoundError(f"backup dir missing: {backup_dir}")
    with tempfile.TemporaryDirectory(prefix="memory-drill-") as tmp:
        restored = Path(tmp) / "memory"
        shutil.copytree(backup_dir, restored)

        # Probe: run search_all.py against the restored root.
        tool = root / "db-tools" / "search_all.py"
        probe = {"tool": str(tool), "exists": tool.is_file()}
        if tool.is_file():
            import subprocess
            r = subprocess.run(
                [sys.executable, str(tool), "test"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60,
                env={**__import__("os").environ,
                     "MEMORY_ROOT": str(restored)})
            probe["returncode"] = r.returncode
            probe["first_lines"] = (r.stdout or r.stderr).strip().splitlines()[:3]
        files = sum(1 for p in restored.rglob("*") if p.is_file())
        dbs = sum(1 for p in restored.rglob("*.db"))
        return {"restored_root": str(restored), "files": files,
                "dbs": dbs, "probe": probe}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, default=None,
                    help="backup destination dir (default <root>/backups)")
    ap.add_argument("--restore-drill", type=Path, default=None,
                    metavar="BACKUP_DIR",
                    help="restore BACKUP_DIR into a temp root, run search probe")
    ap.add_argument("--list", action="store_true",
                    help="list existing backups")
    args = ap.parse_args(argv)

    if args.list:
        backups = memory_root() / "backups"
        if backups.is_dir():
            for e in sorted(backups.iterdir()):
                if e.is_dir():
                    print(e.name)
        return 0
    if args.restore_drill:
        result = restore_drill(args.restore_drill)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0 if result["probe"].get("returncode") == 0 else 1
    result = backup(args.dest)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
