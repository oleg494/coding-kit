#!/usr/bin/env python3

"""Search ALL workspace databases at once (srclight multi-repo pattern:
ATTACH + UNION). "Where does this live" in a single query — across all
agent, wiki and project databases db/*.db PLUS the findings store
research.db as well. OPS §5 routes "what do we know about X" here, so the
findings store must answer too — before this it was structurally invisible
because it has no files_fts.

Results print as ONE global bm25 merge-sort (best first) instead of
alphabetical db order: a strong wiki.db hit must not rank below a weak
hit from a clone db just because of its name.

In --json mode, results are emitted as a JSON list. File hits retain the
pinned 3-key shape {"db", "path", "snippet"}. Findings hits extend this
additively with lifecycle metadata: "superseded_by" (int|null), "verified"
(bool, kept for compatibility), "verified_at" (exact stamp or null) and
"source" (provenance), keeping file hits simple while providing machine
consumers with lifecycle authority.

Error contract — a query that cannot run is NEVER reported as "not found
in any database" (that phrase stays reserved for a query that ran
everywhere it could and matched nothing). Query errors are detected by
replaying the sanitized MATCH against an in-memory control FTS index
BEFORE any real store is opened, so classification never sniffs a
particular store's error text: 'fts5: syntax error' AND the reported
'{component}' case (FTS5 brace column-filter syntax answering
"no such column: component") are both query errors, not empty results.

  exit 0  search ran, hits printed (JSON payload on stdout)
  exit 1  search ran everywhere it could, valid empty result
  exit 2  query error: unusable FTS5 query — actionable diagnostic on
          stderr, no JSON payload (an empty list would read as
          "searched, found nothing")
  exit 3  store error: a known searchable store failed (corrupt file,
          broken/foreign schema, unreadable) or nothing was searchable
          at all. Partial hits from stores that DID answer still print
          on stdout, but the nonzero status and stderr diagnostic make
          the incompleteness explicit — a corrupt store silently
          disappearing from the union would silently shrink what
          "all databases" means. A missing research.db stays a quiet
          skip while healthy indexed stores answer (it is optional).

Usage:
    python3 db-tools/search_all.py "firmware"
    python3 db-tools/search_all.py "load_mix" --limit 15
    python3 db-tools/search_all.py "legacy" --substring
    python3 db-tools/search_all.py "workflow" --json

    An unusable FTS query, e.g. "term OR" or "{component}", prints an
    actionable "query error (query did not run): ..." to stderr and
    exits 2; a corrupt store prints "search error: ..." to stderr
    (plus any partial hits on stdout) and exits 3.
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


class SearchError(Exception):
    """A search failed for a non-absence reason.

    kind == "query": the sanitized query cannot execute as an FTS5 MATCH
    (malformed syntax, a brace column filter naming an unknown column,
    ...). Detected by replaying the query against an in-memory control
    index, so it never depends on a particular store's error text.

    kind == "store": a store that should have answered (a db/*.db file,
    or the research store whose file exists) failed to open or run the
    query — or nothing was searchable at all. `.partial` carries the
    hits from stores that DID answer (may be empty): callers must not
    report "not found" when the query never ran everywhere it should
    have, and must not treat a partial union as a quiet success.

    A missing research.db is NOT an error (absence, kind stays unset):
    it is an optional store and healthy indexed files stores may answer
    alone.
    """

    def __init__(self, message, kind="query", partial=None):
        super().__init__(message)
        self.kind = kind
        self.partial = list(partial) if partial else []


class HitTuple(tuple):
    """5-element tuple: (score, db, label, snippet, finding_id).
    Findings carry lifecycle attributes: superseded_by, verified, verified_at, source.
    Indexed access h[5], h[6], h[7], h[8] supported for findings hits.
    """
    def __new__(cls, base_tuple, meta=None):
        instance = super().__new__(cls, base_tuple)
        meta = meta or {}
        instance.meta = meta
        instance.superseded_by = meta.get("superseded_by")
        instance.verified = meta.get("verified", False) if meta else None
        instance.verified_at = meta.get("verified_at", "") if meta else None
        instance.source = meta.get("source", "") if meta else None
        instance.project = meta.get("project", "unknown") if meta else None
        instance.importance = meta.get("importance", "unreviewed") if meta else None
        return instance

    def __getitem__(self, item):
        if isinstance(item, int) and item >= 5:
            if item == 5:
                return self.superseded_by
            if item == 6:
                return self.verified
            if item == 7:
                return self.verified_at
            if item == 8:
                return self.source
            raise IndexError("tuple index out of range")
        return super().__getitem__(item)


# Column shape of each real FTS index, used to build the in-memory
# control indexes for query validation. Column names matter: FTS5 brace
# column filters ('{component}') are valid only when the column exists,
# so the control must mirror the real index it stands in for.
_FTS_CONTROL_COLUMNS = {
    "files_fts": "rel_path, content",
    "files_fts_trigram": "rel_path, content, tokenize='trigram'",
    "findings_fts": "topic, text",
}


def _validated_match(query, control):
    """sanitize_query(query), checked against an in-memory FTS5 control
    index shaped like `control`; raises SearchError(kind="query") when
    the query cannot run — BEFORE any real store is opened.

    This replay is what separates a QUERY error from a STORE error
    without sniffing error text: '{component}' parses as a brace column
    filter and fails here with "no such column" (the reported defect:
    the old code matched only the literal 'syntax error' and silently
    returned []), while a store-side failure happens after this check
    and is therefore always classified as a store error."""
    q = sanitize_query(query)
    con = sqlite3.connect(":memory:")
    try:
        con.execute(
            f"CREATE VIRTUAL TABLE ctl_fts USING fts5("
            f"{_FTS_CONTROL_COLUMNS[control]})")
        con.execute("SELECT ctl_fts.rowid FROM ctl_fts WHERE ctl_fts MATCH ?",
                    (q,)).fetchall()
    except sqlite3.OperationalError as e:
        raise SearchError(f"malformed FTS query: {e}", kind="query") from e
    finally:
        con.close()
    return q


def scan_searchable_dbs(db_dir=None):
    """(searchable paths, problems [(file name, error text)]) for db/*.db.

    A file that cannot be opened or read is a PROBLEM (corrupt store),
    not a silent skip — the caller turns problems into a SearchError so
    the CLI never claims "searched everything, found nothing" while a
    database quietly disappeared. A healthy file without files_fts (a
    foreign store, an empty db) is a legitimate non-searchable skip: no
    problem is recorded for it.
    """
    ddir = Path(db_dir) if db_dir else DB_DIR
    out, problems = [], []
    for p in sorted(ddir.glob("*.db")):
        con = None
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            has = con.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE name IN ('files_fts','files_fts_trigram')"
            ).fetchone()[0] > 0
        except sqlite3.Error as e:
            problems.append((p.name, str(e)))
            continue
        finally:
            if con is not None:
                con.close()
        if has:
            out.append(p)
    return out, problems


def list_searchable_dbs(db_dir=None) -> list:
    """Databases in the db/ directory that have a files_fts (or
    files_fts_trigram) table. Legacy single-value view of
    scan_searchable_dbs — corrupt-file problems are dropped here, so
    new code should call scan_searchable_dbs and handle them."""
    return scan_searchable_dbs(db_dir)[0]


def _search_files(query, limit, substring, db_dir):
    """(rows, failures, attempted) for every files_fts database.

    rows: [(score, db, rel_path, snippet), ...] from stores that
    answered; failures: ["<file>: <error>", ...] for corrupt or
    unreadable stores (scan problems + query-time failures); attempted:
    how many db/*.db files were search candidates (healthy + broken).
    Raises SearchError(kind="query") before touching any store when the
    sanitized query cannot run (see _validated_match)."""
    idx = "files_fts_trigram" if substring else "files_fts"
    q = _validated_match(query, idx)
    dbs, problems = scan_searchable_dbs(db_dir)
    failures = [f"{name}: {err}" for name, err in problems]
    results = []
    for p in dbs:
        name = p.stem
        con = None
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            rows = con.execute(
                f"SELECT rel_path, snippet({idx}, 1, '<b>', '</b>', "
                f"'…', 12), bm25({idx}, {BM25_WEIGHTS}) "
                f"FROM {idx} WHERE {idx} MATCH ? "
                f"ORDER BY bm25({idx}, {BM25_WEIGHTS}) LIMIT ?",
                (q, limit)).fetchall()
        except sqlite3.Error as e:
            # The scan admitted this store but the query failed on it:
            # a store failure (disk I/O, mid-read corruption) — recorded,
            # other stores still get to answer.
            failures.append(f"{p.name}: {e}")
            rows = []
        finally:
            if con is not None:
                con.close()
        for rel_path, snip, score in rows:
            results.append((score, name, rel_path, snip))
    return results, failures, len(dbs) + len(problems)


def search_files(query: str, limit: int = 5, substring: bool = False,
                 db_dir=None) -> list:
    """[(score, db, rel_path, snippet), ...] from every files_fts database.

    score is bm25(idx, 10.0, 1.0) — SQLite FTS5 convention: MORE NEGATIVE
    is MORE relevant (ORDER BY bm25 ASC = best first). The trigram index
    supports bm25 too (SQLite >= 3.34), so --substring ranks by score as
    well; no fallback ordering is needed.

    Raises SearchError: kind="query" when the (sanitized) query cannot
    run as FTS5 MATCH, kind="store" when a db/*.db candidate failed
    (corrupt file admitted by neither scan nor query, or a query-time
    failure) — .partial then carries the rows from stores that DID
    answer. Never returns [] to mean "the query did not run"."""
    results, failures, _attempted = _search_files(query, limit, substring,
                                                  db_dir)
    if failures:
        raise SearchError("; ".join(failures), kind="store", partial=results)
    return results


def _search_findings(query, limit, research_db, project, importance):
    """(rows, failures, state) for the research.db findings union.

    state: "absent" (no file — the optional store simply is not there),
    "searched" (the query ran), or "failed" (the file exists but could
    not answer; failures explains why). Raises SearchError(kind="query")
    before the store is even opened when the sanitized query cannot run.

    Path via findings_db.research_db_path() (honors MEMORY_ROOT_RESEARCH_DB
    — never hardcoded). Read-only. findings_fts has no trigram twin, so
    --substring degrades to a word match here — still strictly better
    than the pre-P11 structural blindness (D-G)."""
    q = _validated_match(query, "findings_fts")
    db = Path(research_db) if research_db else Path(research_db_path())
    if not db.is_file():
        return [], [], "absent"
    con = None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        cols = {c[1] for c in con.execute("PRAGMA table_info(findings)").fetchall()}
        has_links = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='links'").fetchone()[0] > 0
        proj_col = "f.project" if "project" in cols else "'unknown' AS project"
        imp_col = "f.importance" if "importance" in cols else "'unreviewed' AS importance"
        if has_links:
            superseded_sql = (
                "(SELECT MIN(l.from_id) FROM links l "
                "WHERE l.to_id = f.id AND l.kind = 'supersedes') "
                "AS superseded_by"
            )
        else:
            superseded_sql = "NULL AS superseded_by"
        where_clause = "WHERE findings_fts MATCH ?"
        params = [q]
        if project:
            where_clause += f" AND ({proj_col}) = ?"
            params.append(project)
        if importance:
            where_clause += f" AND ({imp_col}) = ?"
            params.append(importance)
        rows = con.execute(
            f"SELECT f.id, f.topic, snippet(findings_fts, 1, '[', ']', '…', 12), "
            f"bm25(findings_fts, {BM25_WEIGHTS}), "
            f"{superseded_sql}, f.verified_at, f.source, {proj_col}, {imp_col} "
            f"FROM findings_fts JOIN findings f ON f.id = findings_fts.rowid "
            f"{where_clause} "
            f"ORDER BY bm25(findings_fts, {BM25_WEIGHTS}) LIMIT ?",
            params + [limit]).fetchall()
    except sqlite3.Error as e:
        # The store EXISTS at the documented path but cannot answer
        # (corrupt file, foreign schema without findings/findings_fts):
        # a store failure, not an absence.
        return [], [f"{db.name}: {e}"], "failed"
    finally:
        if con is not None:
            con.close()
    out = []
    for fid, topic, snip, score, sup, v_at, src, proj, imp in rows:
        meta = {
            "finding_id": fid,
            "superseded_by": sup,
            "verified": bool(v_at),
            "verified_at": v_at,
            "source": src,
            "project": proj or "unknown",
            "importance": imp or "unreviewed",
        }
        tup = (score, fid, topic, snip, sup, bool(v_at), v_at, src)
        out.append(HitTuple(tup, meta))
    return out, [], "searched"


def search_findings(query: str, limit: int = 5, research_db=None, project: str = "", importance: str = "") -> list:
    """[(score, id, topic, snippet, superseded_by, verified, verified_at, source), ...]
    from the research.db findings union.

    Raises SearchError: kind="query" for an unusable FTS5 query (checked
    before the store is opened), kind="store" when the research store
    file exists but cannot answer (corrupt file, foreign schema) — with
    .partial carrying whatever the leg collected. An ABSENT store stays
    a quiet skip: it is optional and the files stores may answer alone.
    """
    rows, failures, _state = _search_findings(query, limit, research_db,
                                              project, importance)
    if failures:
        raise SearchError("; ".join(failures), kind="store", partial=rows)
    return rows

def search_all(query: str, limit: int = 5, substring: bool = False,
               db_dir=None, research_db=None, project: str = "", importance: str = "") -> list:
    """[(score, db, label, snippet, finding_id), ...] — files dbs + findings
    union in ONE global bm25 order (ascending score = descending relevance;
    bm25 is negative, more negative = better).

    finding_id is None for file hits; for findings the label is
    'finding#<id> <topic>' (printed on one line plus a show-hint).
    Findings hits also expose lifecycle fields h[5] (superseded_by),
    h[6] (verified), h[7] (verified_at), h[8] (source) and attributes.
    Ties keep insertion order — stable sort over files dbs (alphabetical)
    then findings (already bm25-ordered by SQL).

    Raises SearchError (typed, never a silent [] for a failed run):
      kind="query"  — the sanitized query cannot run as FTS5 MATCH
                      (validated against an in-memory control index
                      before any store is opened);
      kind="store"  — a known searchable store failed (corrupt file,
                      broken schema) or nothing was searchable at all;
                      .partial carries the global-merged hits from the
                      stores that DID answer, so callers can show
                      partial data while failing loudly.
    A search that ran and matched nothing still returns [] (valid
    empty) — including when the optional research.db is absent and
    healthy indexed files stores answered. With an importance filter
    the files stores cannot answer, so a missing research store leaves
    nothing searchable: that raises rather than lie with [].
    """
    failures = []
    hits = []
    if not importance:
        # Files leg: an importance filter scopes the question to the
        # findings store, so the files stores are not searched at all.
        rows, fails, attempted = _search_files(query, limit, substring, db_dir)
        failures += fails
        hits += [HitTuple((score, db, rel_path, snip, None), None)
                 for score, db, rel_path, snip in rows
                 if not project or db == project]
    else:
        attempted = None
    findings_hits, fails, state = _search_findings(query, limit, research_db,
                                                   project, importance)
    failures += fails
    hits += [HitTuple((score, f"research:{h.meta.get('project', 'unknown')}" if h.meta.get('project') and h.meta.get('project') != 'unknown' else "research", f"finding#{fid} {topic}", snip, fid),
                      h.meta)
             for h in findings_hits
             for score, fid, topic, snip, sup, ver, v_at, src in [h]]
    hits.sort(key=lambda h: h[0])
    if failures:
        raise SearchError("; ".join(failures), kind="store", partial=hits)
    if state != "searched" and not (attempted or 0):
        # Nothing ran the query anywhere: returning [] would let the CLI
        # claim "not found in any database" — a lie about a search that
        # never happened.
        ddir = Path(db_dir) if db_dir else DB_DIR
        rpath = Path(research_db) if research_db else Path(research_db_path())
        if attempted == 0:
            detail = (f"no searchable databases in {ddir}; "
                      f"research store absent: {rpath}")
        else:
            detail = (f"importance-filtered search has no store to run "
                      f"(research store absent: {rpath})")
        raise SearchError(detail, kind="store")
    return hits

def _json_hits(results):
    """[{db, path, snippet, ...}, ...] — the pinned machine contract
    (v4.0.2) with additive findings lifecycle metadata."""
    formatted = []
    for hit in results:
        _score, db, label, snip, fid = hit[0], hit[1], hit[2], hit[3], hit[4]
        item = {"db": db, "path": label, "snippet": snip}
        if fid is not None:
            meta = getattr(hit, "meta", {}) or {}
            item["superseded_by"] = meta.get("superseded_by")
            # Provenance/freshness evidence, additively: source
            # (may be '') and the exact verified_at stamp (string or
            # null when the schema sentinel '' means unverified);
            # "verified" bool stays for compatibility.
            item["source"] = meta.get("source", "")
            v_at = meta.get("verified_at")
            item["verified_at"] = v_at if v_at else None
            item["verified"] = bool(meta.get("verified", False))
            if meta.get("project") and meta.get("project") != "unknown":
                item["project"] = meta.get("project")
            if meta.get("importance") and meta.get("importance") != "unreviewed":
                item["importance"] = meta.get("importance")
        formatted.append(item)
    return formatted


def _print_human_hits(results):
    """The human listing: one line per hit (+ drill-down hints) and the
    total line, in the global bm25 order."""
    for hit in results:
        _score, db, label, snip, fid = hit[0], hit[1], hit[2], hit[3], hit[4]
        if fid is not None:
            meta = getattr(hit, "meta", {})
            sup = meta.get("superseded_by")
            ver = meta.get("verified", False)
            badges = []
            if sup:
                badges.append(f"[superseded by #{sup}]")
            if not ver:
                badges.append("[unverified]")
            badge_str = (" " + " ".join(badges)) if badges else ""
            # P11/LR-05 contract: one line + drill-down hint
            print(f"[{db}] {label}{badge_str} …{snip}")
            print(f"  findings.py show {fid}")
        else:
            print(f"[{db}] {label}")
            print(f"  {snip}")
    print(f"\ntotal: {len(results)} in "
          f"{len({h[1] for h in results})} databases")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", help="query (>= 3 characters)")
    ap.add_argument("--limit", type=int, default=5,
                    help="results per database")
    ap.add_argument("--substring", action="store_true",
                    help="trigram substring instead of words (declensions)")
    ap.add_argument("--project", default="",
                    help="filter by project slug")
    ap.add_argument("--importance", default="",
                    help="filter by importance (high, normal, low, unreviewed)")
    ap.add_argument("--json", dest="json_mode", action="store_true",
                    help="machine output: JSON list")
    args = ap.parse_args()
    if args.substring and len(args.query) < 3:
        print("--substring requires a query of at least 3 characters",
              file=sys.stderr)
        return 1
    try:
        results = search_all(args.query, limit=args.limit,
                             substring=args.substring,
                             project=args.project,
                             importance=args.importance)
    except SearchError as e:
        if e.kind == "query":
            # A malformed/unusable query is NOT "not found": print an
            # actionable diagnostic (the message includes the fts5
            # parser detail) and exit 2 (usage/argument-class error,
            # distinct from rc 1). --json emits NO payload — an empty
            # list would read as "searched, found nothing".
            print(f"query error (query did not run): {e}", file=sys.stderr)
            return 2
        # Store failure: the query never ran everywhere it should have.
        # Partial hits (if any) still print on stdout, but the nonzero
        # status and the stderr diagnostic make the incompleteness
        # explicit — a corrupt store must never silently shrink "all
        # databases" into a quiet success or a "not found" lie.
        partial = list(e.partial or [])
        if partial:
            if getattr(args, "json_mode", False):
                print(json.dumps(_json_hits(partial), ensure_ascii=False))
            else:
                _print_human_hits(partial)
            print(f"search error: {e}", file=sys.stderr)
            print("results above are PARTIAL — not all databases were "
                  "searched; repair or re-index the failing stores "
                  "(db-tools/build.py) before trusting this coverage",
                  file=sys.stderr)
        else:
            print(f"search error: {e}", file=sys.stderr)
        return 3
    if getattr(args, "json_mode", False):
        print(json.dumps(_json_hits(results), ensure_ascii=False))
        return 0
    if not results:
        print("not found in any database")
        return 1
    _print_human_hits(results)
    return 0

if __name__ == "__main__":
    sys.exit(main())
