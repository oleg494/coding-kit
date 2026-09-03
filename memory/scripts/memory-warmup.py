#!/usr/bin/env python3
"""memory-warmup.py — cross-chat memory warmup (global + per-project hierarchy).

Schema v2.7 (files + files_fts), search across ALL databases in the db/
directory (global wiki.db + project *.db), findings from research.db.

Usage:
    python scripts/memory-warmup.py              # full warmup
    python scripts/memory-warmup.py --query "X"  # search all databases
    python scripts/memory-warmup.py --stats      # stats only
    python scripts/memory-warmup.py --json       # JSON for the agent
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# MEMORY_ROOT overrides the install location (OPS §5 contract; the kit
# copy and ~/.memory/scripts copy both resolve correctly via __file__).
PROFILE_ROOT = Path(os.environ.get(
    "MEMORY_ROOT", str(Path(__file__).resolve().parent.parent))).expanduser()
DB_DIR = PROFILE_ROOT / "db"
WIKI_ROOT = PROFILE_ROOT / "Wiki"
WIKI_DB = DB_DIR / "wiki.db"
RESEARCH_DB = DB_DIR / "research.db"

# one sanitizer for the whole kit (ftsquery.py); the sibling db-tools dir
# exists in both layouts (kit source and the ~/.memory junction)
sys.path.insert(0, str(PROFILE_ROOT / "db-tools"))
from ftsquery import sanitize_query as _sanitize


def list_dbs() -> list:
    """Databases in db/ with the files_fts table (wiki.db + project ones)."""
    out = []
    if not DB_DIR.exists():
        return out
    for p in sorted(DB_DIR.glob("*.db")):
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            has = con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='files_fts'"
            ).fetchone()[0] > 0
            con.close()
        except sqlite3.Error:
            continue
        if has:
            out.append(p)
    return out


def search_all_dbs(query: str, limit: int = 5) -> list:
    """FTS search across all databases: [{db, path, snippet}]."""
    results = []
    for p in list_dbs():
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            rows = con.execute(
                "SELECT rel_path, snippet(files_fts, 1, '<mark>', '</mark>', '...', 40) "
                "FROM files_fts WHERE files_fts MATCH ? LIMIT ?",
                (_sanitize(query), limit),
            ).fetchall()
            con.close()
        except sqlite3.OperationalError:
            continue
        for path, snip in rows:
            results.append({"db": p.stem, "path": path, "snippet": snip})
    return results


def _wiki_where() -> str:
    """WHERE for global Wiki files (separator-independent: GLOB)."""
    return "(rel_path GLOB 'Wiki*') AND ext IN ('md','.md') AND rel_path NOT GLOB '*_templates*'"


def stats() -> dict:
    """Stats: global Wiki + project databases + findings."""
    out = {"wiki_entries": 0, "recent_7d": 0, "project_dbs": [], "findings": 0}
    if WIKI_DB.exists():
        con = sqlite3.connect(f"file:{WIKI_DB}?mode=ro", uri=True)
        try:
            out["wiki_entries"] = con.execute(
                f"SELECT COUNT(*) FROM files WHERE {_wiki_where()}"
            ).fetchone()[0]
            out["recent_7d"] = con.execute(
                f"SELECT COUNT(*) FROM files WHERE {_wiki_where()} "
                "AND mtime >= strftime('%s','now','-7 days')"
            ).fetchone()[0]
        except sqlite3.Error:
            pass
        con.close()
    for p in list_dbs():
        if p == WIKI_DB:
            continue
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            n = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            con.close()
            out["project_dbs"].append({"name": p.stem, "files": n})
        except sqlite3.Error:
            continue
    if RESEARCH_DB.exists():
        try:
            con = sqlite3.connect(f"file:{RESEARCH_DB}?mode=ro", uri=True)
            out["findings"] = con.execute(
                "SELECT COUNT(*) FROM findings").fetchone()[0]
            con.close()
        except sqlite3.Error:
            pass
    return out


def recent_entries(limit: int = 5) -> list:
    """Most recent global Wiki entries (by mtime)."""
    if not WIKI_DB.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{WIKI_DB}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT rel_path, date(mtime, 'unixepoch') AS d FROM files "
            f"WHERE {_wiki_where()} "
            "ORDER BY mtime DESC LIMIT ?", (limit,),
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return []
    return [{"path": r[0], "date": r[1]} for r in rows]


def _clip(text: str, width: int = 60) -> str:
    """Clip a topic: the unsure feed carries a ~200-token budget (P12)
    and prod topics run long."""
    return text if len(text) <= width else text[:width - 1] + "…"


def unsure_feed() -> list:
    """What memory is NOT sure about (P12) — replaces the raw
    `ORDER BY id DESC LIMIT 3` topic feed: junk newest-topics acted as a
    hidden curriculum teaching new agents to imitate junk. Push cannot
    know relevance, but it CAN know uncertainty — and uncertainty grows
    with scale: open contradicts links (both endpoints joined, dangling
    links drop out) + last-7d rows anchored to neither verify_cmd nor
    source, then a literal pull hint toward the documented search reflex.

    ro bare-SELECT on purpose: warmup runs at session start and MUST NOT
    run migrations (findings_db.connect may write); any sqlite3 error
    degrades to an empty feed, never a crash."""
    if not RESEARCH_DB.exists():
        return []
    # same local-wall-clock string format findings.py writes into created
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    try:
        con = sqlite3.connect(f"file:{RESEARCH_DB}?mode=ro", uri=True)
        contra = con.execute(
            "SELECT l.from_id, l.to_id, a.topic, b.topic FROM links l "
            "JOIN findings a ON a.id = l.from_id "
            "JOIN findings b ON b.id = l.to_id "
            "WHERE l.kind = 'contradicts' "
            "AND NOT EXISTS (SELECT 1 FROM links s "
            "               WHERE (s.to_id = l.from_id OR s.to_id = l.to_id) "
            "               AND s.kind = 'supersedes') "
            "ORDER BY l.id DESC LIMIT 2"
        ).fetchall()
        # IFNULL: rows from before the verify_cmd/source ALTERs may hold
        # NULL instead of '' — NULL is exactly "no anchor"
        unanch = con.execute(
            "SELECT id, topic FROM findings WHERE created >= ? "
            "AND IFNULL(verify_cmd,'') = '' AND IFNULL(source,'') = '' "
            "ORDER BY id DESC LIMIT 3", (week_ago,)
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return []
    feed = [f"contradiction: #{f} vs #{t} {_clip(ta)} | {_clip(tb)}"
            for f, t, ta, tb in contra]
    feed += [f"unanchored: #{i} {_clip(t)}" for i, t in unanch]
    # warmup has no session-topic input; a literal query would push a
    # fixed junk pull on every boot — placeholder keeps the hint a
    # template, not a curriculum (advisory 2026-09-03)
    feed.append('pull: search_all.py "<your topic>"')
    return feed


def integrity_check() -> dict:
    """Quick integrity check of the global Wiki."""
    errors = []
    if not WIKI_ROOT.exists():
        return {"ok": False, "errors": ["Wiki/ directory missing"]}
    for name in ("index.md", "log.md"):
        if not (WIKI_ROOT / name).exists():
            errors.append(f"Wiki/{name} missing")
    for md in WIKI_ROOT.rglob("*.md"):
        if md.name in ("index.md", "log.md", "README.md"):
            continue
        try:
            if not md.read_text(encoding="utf-8").startswith("---"):
                errors.append(f"{md.relative_to(WIKI_ROOT)}: missing frontmatter")
        except Exception:
            errors.append(f"{md.relative_to(WIKI_ROOT)}: unreadable")
    return {"ok": len(errors) == 0, "errors": errors}

def git_stale_days(root: Path = None) -> int:
    """Days since the memory repo's last commit, or -1 if not a git repo /
    no git / no commits. Variant A of the git-hygiene decision (plan §Q3):
    warmup only WARNS; a human commits. Agents never auto-commit — a wrong
    finding committed by an agent would be enshrined as canon in history.
    """
    import subprocess
    root = root or PROFILE_ROOT
    if not (root / ".git").exists():
        return -1
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        if r.returncode != 0 or not r.stdout.strip():
            return -1
        last = int(r.stdout.strip())
        return max(0, (datetime.now().timestamp() - last) // 86400)
    except (OSError, ValueError, subprocess.SubprocessError):
        return -1


def main():
    import argparse

    p = argparse.ArgumentParser(description="Cross-chat memory warmup")
    p.add_argument("--query", "-q", help="Search query (all dbs)")
    p.add_argument("--stats", "-s", action="store_true", help="Stats only")
    p.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = p.parse_args()

    output = {}
    if args.query:
        output["search"] = {"query": args.query,
                            "results": search_all_dbs(args.query)}
    elif args.stats:
        output["stats"] = stats()
    else:
        output["stats"] = stats()
        output["recent"] = recent_entries()
        output["findings"] = unsure_feed()
        output["integrity"] = integrity_check()
        output["git_stale_days"] = git_stale_days()

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if "stats" in output:
        s = output["stats"]
        print(f"Wiki: {s['wiki_entries']} entries ({s['recent_7d']} this week)")
        for pd in s["project_dbs"]:
            print(f"  project [{pd['name']}]: {pd['files']} files")
        print(f"  findings: {s['findings']}")
    if "recent" in output:
        print("\nRecent:")
        for r in output["recent"]:
            print(f"  {r['path']} ({r['date']})")
    if "findings" in output and output["findings"]:
        print("\nUnsure (what memory is NOT sure about):")
        for line in output["findings"]:
            print(f"  {line}")
    if "integrity" in output:
        ic = output["integrity"]
        print(f"\nIntegrity: {'OK' if ic['ok'] else str(len(ic['errors'])) + ' issue(s)'}")
        for e in ic["errors"][:10]:
            print(f"  ! {e}")
    if output.get("git_stale_days", -1) >= 0:
        d = output["git_stale_days"]
        if d >= 7:
            print(f"  ! git stale: {d}d since last commit — run "
                  f"`git -C {PROFILE_ROOT} add -A && git commit` (human ritual)")
    if "search" in output:
        q = output["search"]
        print(f"\nSearch: '{q['query']}' → {len(q['results'])} results")
        for r in q["results"][:10]:
            print(f"  [{r['db']}] {r['path']}")
            print(f"    {r['snippet']}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()