#!/usr/bin/env python3

"""Search ALL workspace databases at once (srclight multi-repo pattern:
ATTACH + UNION). "Where does this live" in a single query — across all
agent, wiki and project databases db/*.db (databases without files_fts
are skipped, e.g. research.db — it has its own findings/tasks schema).

Usage:
    python3 db-tools/search_all.py "firmware"
    python3 db-tools/search_all.py "load_mix" --limit 15
    python3 db-tools/search_all.py "legacy" --substring
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from _compat import chulan_root, fix_encoding  # noqa: E402
from ftsquery import sanitize_query  # noqa: E402

fix_encoding()

DB_DIR = chulan_root() / "db"


def list_searchable_dbs(db_dir=None) -> list:
    """Databases in the db/ directory that have a files_fts (or files_fts_trigram) table."""
    ddir = Path(db_dir) if db_dir else DB_DIR
    out = []
    for p in sorted(ddir.glob("*.db")):
        con = None
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            has = con.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE name IN ('files_fts','files_fts_trigram')"
            ).fetchone()[0] > 0
        except sqlite3.Error:
            continue
        finally:
            if con is not None:
                con.close()
        if has:
            out.append(p)
    return out


def search_all(query: str, limit: int = 5, substring: bool = False,
               db_dir=None) -> list:
    """[(db, rel_path, snippet), ...] across all databases."""
    results = []
    idx = "files_fts_trigram" if substring else "files_fts"
    for p in list_searchable_dbs(db_dir):
        name = p.stem
        con = None
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            rows = con.execute(
                f"SELECT rel_path, snippet({idx}, 1, '<b>', '</b>', "
                f"'…', 12) FROM {idx} WHERE {idx} MATCH ? LIMIT ?",
                (sanitize_query(query), limit)).fetchall()
        except sqlite3.OperationalError:
            continue
        finally:
            if con is not None:
                con.close()
        for rel_path, snip in rows:
            results.append((name, rel_path, snip))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", help="query (>= 3 characters)")
    ap.add_argument("--limit", type=int, default=5,
                    help="results per database")
    ap.add_argument("--substring", action="store_true",
                    help="trigram substring instead of words (declensions)")
    ap.add_argument("--json", dest="json_mode", action="store_true",
                    help="machine output: JSON list")
    args = ap.parse_args()
    if args.substring and len(args.query) < 3:
        print("--substring requires a query of at least 3 characters",
              file=sys.stderr)
        return 1
    results = search_all(args.query, limit=args.limit,
                         substring=args.substring)
    if getattr(args, "json_mode", False):
        print(json.dumps(
            [{"db": n, "path": rp, "snippet": snip} for n, rp, snip in results],
            ensure_ascii=False))
        return 0
    if not results:
        print("not found in any database")
        return 1
    for name, rel_path, snip in results:
        print(f"[{name}] {rel_path}")
        print(f"  {snip}")
    print(f"\ntotal: {len(results)} in {len({n for n, _, _ in results})} databases")
    return 0


if __name__ == "__main__":
    sys.exit(main())