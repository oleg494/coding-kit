#!/usr/bin/env python3

"""Search ALL workspace databases at once (srclight multi-repo pattern:
ATTACH + UNION). "Where does this live" in a single query — across all
agent, wiki and project databases db/*.db PLUS the findings store
research.db (P11/D-G: AGENTS.md §4 routes "what do we know about X"
here, so findings_fts must answer too — before this the store was
structurally invisible because it has no files_fts).

Results print as ONE global bm25 merge-sort (best first) instead of
alphabetical db order: a strong wiki.db hit must not rank below a weak
hit from a clone db just because of its name.

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
from findings_db import research_db_path  # noqa: E402
from ftsquery import sanitize_query  # noqa: E402

fix_encoding()

DB_DIR = chulan_root() / "db"

# Column weights for the two-column FTS indexes — files_fts(rel_path,
# content) and findings_fts(topic, text). SAME weights as search.py:220
# and findings.py cmd_search (P9/P11 contract) so every surface ranks a
# given query identically; the global merge below compares these scores
# across databases.
BM25_WEIGHTS = "10.0, 1.0"


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


def search_files(query: str, limit: int = 5, substring: bool = False,
                 db_dir=None) -> list:
    """[(score, db, rel_path, snippet), ...] from every files_fts database.

    score is bm25(idx, 10.0, 1.0) — SQLite FTS5 convention: MORE NEGATIVE
    is MORE relevant (ORDER BY bm25 ASC = best first). The trigram index
    supports bm25 too (SQLite >= 3.34), so --substring ranks by score as
    well; no fallback ordering is needed.
    """
    results = []
    idx = "files_fts_trigram" if substring else "files_fts"
    for p in list_searchable_dbs(db_dir):
        name = p.stem
        con = None
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            rows = con.execute(
                f"SELECT rel_path, snippet({idx}, 1, '<b>', '</b>', "
                f"'…', 12), bm25({idx}, {BM25_WEIGHTS}) "
                f"FROM {idx} WHERE {idx} MATCH ? "
                f"ORDER BY bm25({idx}, {BM25_WEIGHTS}) LIMIT ?",
                (sanitize_query(query), limit)).fetchall()
        except sqlite3.OperationalError:
            continue
        finally:
            if con is not None:
                con.close()
        for rel_path, snip, score in rows:
            results.append((score, name, rel_path, snip))
    return results


def search_findings(query: str, limit: int = 5, research_db=None) -> list:
    """[(score, id, topic, snippet), ...] from the research.db findings union.

    Path via findings_db.research_db_path() (honors MEMORY_ROOT_RESEARCH_DB
    — never hardcoded). Read-only and best-effort like the files loop: an
    absent/corrupt/schemaless store skips the section instead of failing
    the whole union. findings_fts has no trigram twin, so --substring
    degrades to a word match here — still strictly better than the pre-P11
    structural blindness (D-G).
    """
    db = Path(research_db) if research_db else Path(research_db_path())
    if not db.is_file():
        return []
    con = None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT f.id, f.topic, snippet(findings_fts, 1, '[', ']', "
            f"'…', 12), bm25(findings_fts, {BM25_WEIGHTS}) "
            "FROM findings_fts JOIN findings f ON f.id = findings_fts.rowid "
            "WHERE findings_fts MATCH ? "
            f"ORDER BY bm25(findings_fts, {BM25_WEIGHTS}) LIMIT ?",
            (sanitize_query(query), limit)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if con is not None:
            con.close()
    return [(score, fid, topic, snip) for fid, topic, snip, score in rows]


def search_all(query: str, limit: int = 5, substring: bool = False,
               db_dir=None, research_db=None) -> list:
    """[(score, db, label, snippet, finding_id), ...] — files dbs + findings
    union in ONE global bm25 order (ascending score = descending relevance;
    bm25 is negative, more negative = better).

    finding_id is None for file hits; for findings the label is
    'finding#<id> <topic>' (printed on one line plus a show-hint).
    Ties keep insertion order — stable sort over files dbs (alphabetical)
    then findings (already bm25-ordered by SQL).
    """
    hits = [(score, db, rel_path, snip, None)
            for score, db, rel_path, snip
            in search_files(query, limit, substring, db_dir)]
    hits += [(score, "research", f"finding#{fid} {topic}", snip, fid)
             for score, fid, topic, snip
             in search_findings(query, limit, research_db)]
    hits.sort(key=lambda h: h[0])
    return hits


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
        # db/path/snippet keys are the pinned machine contract (v4.0.2);
        # a findings row carries path='finding#<id> <topic>'.
        print(json.dumps(
            [{"db": db, "path": label, "snippet": snip}
             for _score, db, label, snip, _fid in results],
            ensure_ascii=False))
        return 0
    if not results:
        print("not found in any database")
        return 1
    for _score, db, label, snip, fid in results:
        if fid is not None:
            # P11 contract: one line + the drill-down hint
            print(f"[{db}] {label} …{snip}")
            print(f"  findings.py show {fid}")
        else:
            print(f"[{db}] {label}")
            print(f"  {snip}")
    print(f"\ntotal: {len(results)} in "
          f"{len({db for _s, db, _l, _sn, _f in results})} databases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
