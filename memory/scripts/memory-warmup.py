#!/usr/bin/env python3
"""memory-warmup.py — cross-chat memory warmup (global + per-project hierarchy).

Schema v2.7 (files + files_fts), search across ALL databases in the db/
directory (global wiki.db + project *.db), findings from research.db.

Usage:
    python scripts/memory-warmup.py              # compact availability summary
    python scripts/memory-warmup.py --full       # full diagnostics warmup
    python scripts/memory-warmup.py --query "X"  # search all databases
    python scripts/memory-warmup.py --stats      # stats only
    python scripts/memory-warmup.py --json       # JSON for the agent

Exit codes for --query follow search_all.py: 0 = searched, 1 = not found,
2 = QUERY error (the query never ran), 3 = STORE error (a store that should
have answered failed; partial results are printed and marked PARTIAL).
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from contextlib import closing
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent


def _engine_dir() -> Path:
    """db-tools/ belonging to THIS script's tree — the kit source tree and the
    ~/.memory install both keep ``scripts/`` and ``db-tools/`` side by side.

    Deliberately NOT derived from MEMORY_ROOT: the root points at the memory
    STORE (data), which need not carry the engine at all, so a script-relative
    engine is what makes source and installed invocations import the SAME
    retrieval code and return the SAME results as search_all.py.
    """
    for candidate in (_SCRIPT_DIR.parent / "db-tools",
                      _SCRIPT_DIR / "db-tools"):
        if (candidate / "search_all.py").is_file():
            return candidate
    return _SCRIPT_DIR.parent / "db-tools"


_ENGINE_DIR = _engine_dir()
# Script dir first so `_compat` resolves to this script's sibling copy (the
# same file install.py ships next to memory-warmup.py); engine dir next so
# search_all/ftsquery/findings_db resolve as top-level modules.
for _dir in (str(_ENGINE_DIR), str(_SCRIPT_DIR)):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

from _compat import chulan_root  # noqa: E402
from ftsquery import sanitize_query as _sanitize  # noqa: E402


def _profile_root() -> Path:
    """Memory ROOT (the STORE): configured MEMORY_ROOT, else ~/.memory when
    that is a real memory root, else this script's tree.

    Same resolver as the engine (_compat.chulan_root), so warmup and
    search_all.py always read the same stores; an unusable root degrades to
    the script tree instead of aborting a session-start diagnostic.
    """
    try:
        return Path(chulan_root())
    except RuntimeError:
        return _SCRIPT_DIR.parent


PROFILE_ROOT = _profile_root()
DB_DIR = PROFILE_ROOT / "db"
WIKI_ROOT = PROFILE_ROOT / "Wiki"
WIKI_DB = DB_DIR / "wiki.db"
# Same single resolver as findings_db.research_db_path(): env override first,
# then the root default (findings.py writes here, so warmup is pinned to it).
RESEARCH_DB = Path(os.environ.get(
    "MEMORY_ROOT_RESEARCH_DB", str(DB_DIR / "research.db"))).expanduser()

_ENGINE_API = None


def _engine():
    """(SearchError, search_all, _json_hits) from the engine's search_all.py.

    Imported lazily: the diagnostic modes (default availability, --stats,
    --full) still run when the engine tree is incomplete or the store root is
    not yet a valid memory root — the engine computes its own DB_DIR at
    import time and raises on an unvalidated root.
    """
    global _ENGINE_API
    if _ENGINE_API is None:
        from search_all import SearchError, _json_hits, search_all
        _ENGINE_API = (SearchError, search_all, _json_hits)
    return _ENGINE_API


def list_dbs() -> list:
    """Databases in db/ with the files_fts table (wiki.db + project ones)."""
    out = []
    if not DB_DIR.exists():
        return out
    for p in sorted(DB_DIR.glob("*.db")):
        con = None
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            has = con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='files_fts'"
            ).fetchone()[0] > 0
        except sqlite3.Error:
            continue
        finally:
            if con is not None:
                con.close()
        if has:
            out.append(p)
    return out


def search_all_dbs(query: str, limit: int = 5, mode: str = "lexical") -> list:
    """Canonical global retrieval adapted to the warmup JSON shape.

    search_all.py owns query and store semantics AND the pinned machine shape
    (``_json_hits``: db/path/snippet plus findings lifecycle metadata), so a
    warmup result list is identical to the `search_all.py --json` CLI for the
    same query and stores. Errors PROPAGATE — an empty list always means the
    query ran everywhere it should have and matched nothing.
    """
    SearchError, search, json_hits = _engine()
    if not _sanitize(query).strip():
        # Same sanitizer module the engine uses: nothing survives that can run
        # as FTS5 MATCH, so this is a QUERY error before any store is opened.
        raise SearchError("empty query: nothing to run as FTS5 MATCH",
                          kind="query")
    return json_hits(search(query, limit=limit, db_dir=DB_DIR,
                           research_db=RESEARCH_DB, mode=mode))


# --- Wiki notes in either real index layout -------------------------------
# build.py stores paths relative to the ROOT it was given, so two layouts
# exist in the wild:
#   root-wide  — the default `build.py` over MEMORY_ROOT: notes carry a
#                `Wiki/` prefix, and unrelated project Markdown (src/, docs/,
#                tests/, db-tools/) is indexed in the same store;
#   wiki-rooted — root = the Wiki directory itself (the existing ~/.memory
#                store): notes sit at the top level, e.g. `notes/x.md`.
# The layout is DETECTED FROM INDEX CONTENT (a root-wide store always carries
# the root markers VERSION/db-tools/build.py/scripts/_compat.py) and never
# assumed, and paths are normalized in SQL so both separators work.
_REL = "replace(rel_path, '\\', '/')"
_ROOT_MARKERS = ("version", "db-tools/build.py", "scripts/_compat.py")
# Service documents of a Wiki (top of the indexed tree) are not notes.
_SERVICE_NOTES = ("wiki/readme.md", "wiki/index.md", "wiki/log.md",
                  "readme.md", "index.md", "log.md")


def _index_layout(con) -> str:
    """'root' for an index built over MEMORY_ROOT, 'wiki' for one built over
    the Wiki directory. Conservative on failure: 'root', so only
    Wiki/-prefixed notes ever count and unrelated Markdown can never be
    reported as a memory note."""
    markers = ",".join(f"'{m}'" for m in _ROOT_MARKERS)
    try:
        found = con.execute(
            f"SELECT 1 FROM files WHERE lower({_REL}) IN ({markers}) LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return "root"
    return "root" if found else "wiki"


def _wiki_where(con) -> str:
    """WHERE selecting Wiki NOTES for the given store connection.

    Service documents and `_templates` are not notes in either layout; a
    root-wide store contributes only its `Wiki/` subtree, so arbitrary project
    source Markdown is excluded rather than counted as memory.
    """
    service = ",".join(f"'{name}'" for name in _SERVICE_NOTES)
    where = (f"lower(ext) IN ('md', '.md') "
             f"AND lower({_REL}) NOT IN ({service}) "
             f"AND lower({_REL}) NOT LIKE '%_templates%'")
    if _index_layout(con) == "wiki":
        return where
    return where + f" AND lower({_REL}) LIKE 'wiki/%'"


def stats() -> dict:
    """Stats: global Wiki + project databases + findings."""
    out = {"wiki_entries": 0, "recent_7d": 0, "project_dbs": [], "findings": 0, "findings_by_project": {}, "high_by_project": {}}
    if WIKI_DB.exists():
        con = None
        try:
            con = sqlite3.connect(f"file:{WIKI_DB.as_posix()}?mode=ro", uri=True)
            where = _wiki_where(con)
            out["wiki_entries"] = con.execute(
                f"SELECT COUNT(*) FROM files WHERE {where}"
            ).fetchone()[0]
            out["recent_7d"] = con.execute(
                f"SELECT COUNT(*) FROM files WHERE {where} "
                "AND mtime >= strftime('%s','now','-7 days')"
            ).fetchone()[0]
        except sqlite3.Error:
            pass
        finally:
            if con is not None:
                con.close()
    for p in list_dbs():
        if p == WIKI_DB:
            continue
        con = None
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            n = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        except sqlite3.Error:
            continue
        finally:
            if con is not None:
                con.close()
        out["project_dbs"].append({"name": p.stem, "files": n})
    if RESEARCH_DB.exists():
        con = None
        try:
            con = sqlite3.connect(f"file:{RESEARCH_DB.as_posix()}?mode=ro",
                                  uri=True)
            out["findings"] = con.execute(
                "SELECT COUNT(*) FROM findings").fetchone()[0]
            has_proj = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='findings'").fetchone()[0] > 0
            if has_proj:
                cols = {c[1] for c in con.execute("PRAGMA table_info(findings)")}
                if "project" in cols:
                    for row in con.execute("SELECT project, COUNT(*) FROM findings GROUP BY project"):
                        p = row[0] or "unknown"
                        out["findings_by_project"][p] = row[1]
                    if "importance" in cols:
                        for row in con.execute("SELECT project, COUNT(*) FROM findings WHERE importance = 'high' GROUP BY project"):
                            p = row[0] or "unknown"
                            out["high_by_project"][p] = row[1]
        except sqlite3.Error:
            pass
        finally:
            if con is not None:
                con.close()
    return out


def recent_entries(limit: int = 5) -> list:
    """Most recent global Wiki entries (by mtime); paths use '/' in both
    layouts so consumers see one separator form."""
    if not WIKI_DB.exists():
        return []
    con = None
    try:
        con = sqlite3.connect(f"file:{WIKI_DB.as_posix()}?mode=ro", uri=True)
        rows = con.execute(
            f"SELECT {_REL} AS rel_path, date(mtime, 'unixepoch') AS d "
            f"FROM files WHERE {_wiki_where(con)} "
            "ORDER BY mtime DESC LIMIT ?", (limit,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if con is not None:
            con.close()
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
    con = None
    try:
        con = sqlite3.connect(f"file:{RESEARCH_DB.as_posix()}?mode=ro",
                              uri=True)
        cols = {c[1] for c in con.execute("PRAGMA table_info(findings)").fetchall()}
        has_imp = "importance" in cols
        has_links = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='links'"
        ).fetchone()[0] > 0
        contra = con.execute(
            "SELECT l.from_id, l.to_id, a.topic, b.topic FROM links l "
            "JOIN findings a ON a.id = l.from_id "
            "JOIN findings b ON b.id = l.to_id "
            "WHERE l.kind = 'contradicts' "
            "AND NOT EXISTS (SELECT 1 FROM links s "
            "               WHERE (s.to_id = l.from_id OR s.to_id = l.to_id) "
            "               AND s.kind = 'supersedes') "
            "ORDER BY l.id DESC LIMIT 2"
        ).fetchall() if has_links else []
        # IFNULL: rows from before the verify_cmd/source ALTERs may hold
        # NULL instead of '' — NULL is exactly "no anchor"
        sup_filter = (
            "AND NOT EXISTS (SELECT 1 FROM links s WHERE s.to_id = f.id AND s.kind = 'supersedes') "
            if has_links else ""
        )
        order_by = (
            "ORDER BY CASE f.importance "
            "  WHEN 'high' THEN 1 "
            "  WHEN 'normal' THEN 2 "
            "  WHEN 'unreviewed' THEN 3 "
            "  ELSE 4 END ASC, f.id DESC"
            if has_imp else "ORDER BY f.id DESC"
        )
        unanch = con.execute(
            f"SELECT f.id, f.topic FROM findings f WHERE f.created >= ? "
            f"AND IFNULL(f.verify_cmd,'') = '' AND IFNULL(f.source,'') = '' "
            f"{sup_filter}"
            f"{order_by} LIMIT 3", (week_ago,)
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if con is not None:
            con.close()
    feed = [f"contradiction: #{f} vs #{t} {_clip(ta)} | {_clip(tb)}"
            for f, t, ta, tb in contra]
    feed += [f"unanchored: #{i} {_clip(t)}" for i, t in unanch]
    # warmup has no session-topic input; a literal query would push a
    # fixed junk pull on every boot — placeholder keeps the hint a
    # template, not a curriculum (advisory 2026-09-03)
    feed.append('pull: search_all.py "<your topic>"')
    return feed


def high_priority_feed() -> list:
    """High-priority architectural invariants / decisions per project."""
    if not RESEARCH_DB.exists():
        return []
    con = None
    rows = []
    try:
        con = sqlite3.connect(f"file:{RESEARCH_DB.as_posix()}?mode=ro",
                              uri=True)
        cols = {c[1] for c in con.execute("PRAGMA table_info(findings)")}
        if "importance" not in cols:
            return []
        has_links = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='links'"
        ).fetchone()[0] > 0
        sup_filter = (
            "AND NOT EXISTS (SELECT 1 FROM links l WHERE l.to_id = f.id AND l.kind = 'supersedes')"
            if has_links else ""
        )
        rows = con.execute(f"""
            SELECT f.id, f.project, f.topic, IFNULL(f.verified_at, '')
            FROM findings f
            WHERE f.importance = 'high'
              {sup_filter}
            ORDER BY f.id DESC LIMIT 4
        """).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if con is not None:
            con.close()
    return [
        f"[{r[1] or 'unknown'}] #{r[0]} {_clip(r[2])}{'' if r[3] else ' [unverified]'}"
        for r in rows
    ]


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


def _availability() -> dict:
    """Probe readable schemas without creating stores or scanning contents."""
    available = {}
    probes = (
        ("wiki", WIKI_DB, (
            "SELECT rel_path, ext, mtime FROM files LIMIT 0",
            "SELECT rel_path, content FROM files_fts LIMIT 0",
        )),
        ("findings", RESEARCH_DB, ("SELECT id, topic FROM findings LIMIT 0",)),
    )
    for name, path, queries in probes:
        if not path.exists():
            available[name] = "absent"
            continue
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as con:
                for query in queries:
                    con.execute(query)
            available[name] = "ok"
        except (sqlite3.Error, OSError):
            available[name] = "unreadable"
    if not DB_DIR.exists():
        available["db_dir"] = "absent"
    return available


def _emit_search(query: str, hits: list, as_json: bool) -> None:
    """--query output: the pinned warmup JSON envelope, or one line per hit."""
    if as_json:
        print(json.dumps({"search": {"query": query, "results": hits}},
                         ensure_ascii=False, indent=2))
        return
    print(f"\nSearch: '{query}' → {len(hits)} results")
    for r in hits[:10]:
        print(f"  [{r['db']}] {r['path']}")
        print(f"    {r['snippet']}")


def _search_mode(args) -> int:
    """--query: canonical retrieval with search_all.py's exit-code contract.

    2 = QUERY error, the query never ran (nothing is emitted to stdout, so a
    "0 results" success is impossible); 3 = STORE error — a store that should
    have answered failed, so whatever the other stores returned is printed and
    marked PARTIAL; 0 = the query ran everywhere it should have.
    """
    try:
        SearchError, _, json_hits = _engine()
    except (ImportError, RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"search error: retrieval engine unavailable ({exc})",
              file=sys.stderr)
        return 3
    try:
        hits = search_all_dbs(args.query)
    except SearchError as exc:
        if exc.kind == "query":
            print(f"query error (query did not run): {exc}", file=sys.stderr)
            return 2
        partial = json_hits(list(exc.partial or []))
        print(f"search error: {exc}", file=sys.stderr)
        if partial:
            print("PARTIAL — not every database was searched; results "
                  "below are incomplete", file=sys.stderr)
            _emit_search(args.query, partial, args.json)
        return 3
    _emit_search(args.query, hits, args.json)
    return 0


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Cross-chat memory warmup")
    p.add_argument("--query", "-q", help="Search query (all dbs)")
    p.add_argument("--stats", "-s", action="store_true", help="Stats only")
    p.add_argument("--full", action="store_true",
                   help="Full diagnostics: recent entries, unsure feed, "
                        "high-priority findings, integrity, git staleness")
    p.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = p.parse_args()

    if args.query:
        return _search_mode(args)

    output = {}
    if args.stats or args.full:
        # --stats keeps its existing shape (stats-only, both formats);
        # --full is the diagnostic warmup that used to be the default
        output["stats"] = stats()
        if args.full:
            output["recent"] = recent_entries()
            output["findings"] = unsure_feed()
            output["integrity"] = integrity_check()
            output["git_stale_days"] = git_stale_days()
            output["high_priority"] = high_priority_feed()
    else:
        output["available"] = _availability()

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    if "available" in output:
        # compact default mode: one line per store, explicit when
        # something is missing or unreadable — never "healthy" silence
        a = output["available"]
        if a["wiki"] == "ok":
            print("memory: available (Wiki index)")
        else:
            print(f"memory: wiki index {'missing' if a['wiki'] == 'absent' else 'unreadable'}"
                  f" ({WIKI_DB}) — rebuild with db-tools/build.py")
        if a.get("db_dir") == "absent":
            print(f"memory: db directory missing ({DB_DIR})")
        if a["findings"] == "ok":
            print("findings: available")
        elif a["findings"] == "absent":
            print("findings: not present (no research.db)")
        else:
            print(f"findings: unreadable ({RESEARCH_DB})")
        print("full diagnostics: python memory-warmup.py --full")
    elif "stats" in output:
        s = output["stats"]
        print(f"Wiki: {s['wiki_entries']} entries ({s['recent_7d']} this week)")
        for pd in s["project_dbs"]:
            print(f"  project [{pd['name']}]: {pd['files']} files")
        f_summary = f"  findings: {s['findings']}"
        if s.get("findings_by_project"):
            bp = s["findings_by_project"]
            top_p = [f"{k}: {bp[k]}" for k in sorted(bp.keys(), key=lambda x: -bp[x])[:4]]
            f_summary += f" ({', '.join(top_p)})"
        print(f_summary)
    if "recent" in output:
        print("\nRecent:")
        for r in output["recent"]:
            print(f"  {r['path']} ({r['date']})")
    if "findings" in output and output["findings"]:
        print("\nUnsure (what memory is NOT sure about):")
        for line in output["findings"]:
            print(f"  {line}")
    if "high_priority" in output and output["high_priority"]:
        print("\nKey Invariants & High-Priority Findings:")
        for line in output["high_priority"]:
            print(f"  {line}")
    if "integrity" in output:
        ic = output["integrity"]
        print(f"\nIntegrity: {'OK' if ic['ok'] else str(len(ic['errors'])) + ' issue(s)'}")
        for e in ic["errors"][:10]:
            print(f"  ! {e}")
        d = output["git_stale_days"]
        if d >= 7:
            print(f"  ! git stale: {d}d since last commit — run "
                  f"`git -C {PROFILE_ROOT} add -A && git commit` (human ritual)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())