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
import re
import sys
from pathlib import Path

from _compat import chulan_root, fix_encoding  # noqa: E402
from findings_db import research_db_path  # noqa: E402
from ftsquery import sanitize_query  # noqa: E402
from memory_corpus import inventory, selected
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


def scan_searchable_dbs(db_dir=None, project=""):
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
        if project and p.stem != project:
            continue
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


def _search_files(query, limit, substring, db_dir, project=""):
    """(rows, failures, attempted) for every files_fts database.

    rows: [(score, db, rel_path, snippet), ...] from stores that
    answered; failures: ["<file>: <error>", ...] for corrupt or
    unreadable stores (scan problems + query-time failures); attempted:
    how many db/*.db files were search candidates (healthy + broken).
    Raises SearchError(kind="query") before touching any store when the
    sanitized query cannot run (see _validated_match)."""
    idx = "files_fts_trigram" if substring else "files_fts"
    q = _validated_match(query, idx)
    dbs, problems = scan_searchable_dbs(db_dir, project) if project else scan_searchable_dbs(db_dir)
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


def _search_findings(query, limit, research_db, project, importance,
                     state="all", verification="all", source="", tag=""):
    q = _validated_match(query, "findings_fts")
    db = Path(research_db) if research_db else Path(research_db_path())
    if not db.is_file():
        return [], [], "absent"
    con = None
    try:
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        replacements = dict(con.execute(
            "SELECT to_id, MIN(from_id) FROM links WHERE kind='supersedes' GROUP BY to_id")) if "links" in names else {}
        rows = con.execute(
            "SELECT f.*, bm25(findings_fts, 10.0, 1.0) AS score, "
            "snippet(findings_fts, 1, '[', ']', '…', 12) AS snip "
            "FROM findings_fts JOIN findings f ON f.id=findings_fts.rowid "
            "WHERE findings_fts MATCH ? ORDER BY score, f.id DESC", (q,))
        out = []
        for raw in rows:
            row = dict(raw)
            fid = row["id"]
            row.update(kind="finding", finding_id=fid,
                       project=row.get("project") or "unknown",
                       importance=row.get("importance") or "unreviewed",
                       superseded_by=replacements.get(fid))
            row["verified"] = bool(row.get("verified_at"))
            row["superseded"] = bool(row["superseded_by"] or "[superseded:" in row["text"])
            if not selected(row, project, importance, state, verification, source, tag):
                continue
            tup = (row["score"], fid, row["topic"], row["snip"], row["superseded_by"],
                   row["verified"], row.get("verified_at", ""), row.get("source", ""))
            out.append(HitTuple(tup, row))
            if len(out) >= limit:
                break
        return out, [], "searched"
    except sqlite3.Error as exc:
        return [], [f"{db.name}: {exc}"], "failed"
    finally:
        if con is not None:
            con.close()


def search_findings(query, limit=5, research_db=None, project="", importance=""):
    rows, failures, _ = _search_findings(query, limit, research_db, project, importance)
    if failures:
        raise SearchError("; ".join(failures), kind="store", partial=rows)
    return rows


def _search_lexical(query, limit, substring, db_dir, research_db, project,
                    importance, state, verification, findings_only, source, tag):
    failures, hits, attempted = [], [], 0
    only_findings = findings_only or importance or state != "all" or verification != "all" or source or tag
    if not only_findings:
        rows, fails, attempted = _search_files(query, limit, substring, db_dir, project)
        failures += fails
        hits += [HitTuple((score, db, path, snip, None)) for score, db, path, snip in rows]
    rows, fails, store_state = _search_findings(query, limit, research_db,
        project, importance, state, verification, source, tag)
    failures += fails
    for row in rows:
        score, fid, topic, snip = row[:4]
        proj = row.meta["project"]
        db = f"research:{proj}" if proj != "unknown" else "research"
        hits.append(HitTuple((score, db, f"finding#{fid} {topic}", snip, fid), row.meta))
    hits.sort(key=lambda hit: hit[0])
    if failures:
        raise SearchError("; ".join(failures), kind="store", partial=hits)
    if store_state != "searched" and not attempted:
        raise SearchError("no searchable databases in selected scope", kind="store")
    return hits


def natural_query(query):
    """Literal OR terms for natural-language recall; FTS operators stay lexical-only."""
    return " OR ".join('"' + word + '"' for word in dict.fromkeys(re.findall(r"\w+", query, re.UNICODE)))


def search_all(query, limit=5, substring=False, db_dir=None, research_db=None,
               project="", importance="", mode="lexical", state="all",
               verification="all", findings_only=False, source="", tag="",
               model_dir=None, index_path=None):
    """Read-only retrieval. Semantic modes require an explicitly built local index.

    Lexical limit remains per store. Vector/hybrid return a global top-k.
    Lifecycle/scope filters precede candidate limits in every mode.
    """
    if mode not in {"lexical", "vector", "hybrid"} or state not in {"all", "current", "superseded"} or verification not in {"all", "verified", "unverified"}:
        raise SearchError("invalid retrieval mode or lifecycle filter", kind="query")
    if not isinstance(limit, int) or limit <= 0 or not query.strip():
        raise SearchError("query must be nonempty and limit positive", kind="query")
    if substring and mode != "lexical":
        raise SearchError("--substring requires lexical mode", kind="query")
    db_dir = Path(db_dir) if db_dir is not None else DB_DIR
    research_db = Path(research_db) if research_db is not None else Path(research_db_path())
    args = (substring, db_dir, research_db, project, importance, state,
            verification, findings_only, source, tag)
    if mode == "lexical":
        return _search_lexical(query, limit, *args)
    from embedding_model import EmbeddingError
    from vector_search import VectorError, search, reciprocal_rank_fusion
    lexical = []
    if mode == "hybrid":
        literal = natural_query(query)
        if literal:
            lexical = _search_lexical(literal, max(20, limit * 4), *args)
    records, failures, attempted = inventory(db_dir, research_db,
        findings_only, project, importance, state, verification, source, tag)
    if failures or not attempted:
        raise SearchError("; ".join(failures) or "no searchable databases in selected scope",
                          kind="store", partial=lexical)
    try:
        ranked = search(query, records, db_dir, research_db, max(20, limit * 4), model_dir, index_path)
    except (EmbeddingError, VectorError, OSError) as exc:
        raise SearchError(str(exc), kind="store", partial=lexical) from exc
    vector = [HitTuple((-score, r['db'], r['path'], ' '.join(r['text'].split())[:240], r['finding_id']),
                       r if r['kind'] == 'finding' else {}) for score, r in ranked]
    if mode == "vector":
        return vector[:limit]
    def key(hit):
        return f"finding:{hit[4]}" if hit[4] is not None else f"file:{hit[1]}:{hit[2]}"
    scores = reciprocal_rank_fusion([key(h) for h in lexical], [key(h) for h in vector])
    # Preserve exact-match snippets when both retrievers found a document.
    records = {key(h): h for h in vector + lexical}
    fused = [HitTuple((-score, *records[k][1:5]), records[k].meta) for k, score in scores.items()]
    fused.sort(key=lambda h: (h[0], key(h)))
    return fused[:limit]

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
            item["superseded"] = bool(meta.get("superseded"))
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
            elif meta.get("superseded"):
                badges.append("[superseded; replacer deleted]")
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
                    help="trigram substring instead of words (lexical mode)")
    ap.add_argument("--mode", choices=("lexical", "vector", "hybrid"),
                    default="lexical",
                    help="retrieval mode (default: lexical)")
    ap.add_argument("--project", default="",
                    help="filter by project slug")
    ap.add_argument("--importance", default="",
                    help="filter by importance (high, normal, low, unreviewed)")
    ap.add_argument("--state", choices=("all", "current", "superseded"), default="all")
    ap.add_argument("--verification", choices=("all", "verified", "unverified"), default="all")
    ap.add_argument("--model-dir", help="local multilingual MiniLM model directory")
    ap.add_argument("--index", dest="index_path", help="disposable semantic index path")
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
                             importance=args.importance,
                             mode=args.mode, state=args.state, verification=args.verification,
                             model_dir=args.model_dir, index_path=args.index_path)
    except SearchError as e:
        if e.kind == "query":
            print(f"query error (query did not run): {e}", file=sys.stderr)
            return 2
        partial = list(e.partial or [])
        if partial:
            if args.json_mode:
                print(json.dumps(_json_hits(partial), ensure_ascii=False))
            else:
                _print_human_hits(partial)
            print(f"search error: {e}", file=sys.stderr)
            print("results above are PARTIAL — not all databases were searched",
                  file=sys.stderr)
        else:
            print(f"search error: {e}", file=sys.stderr)
        return 3
    if args.json_mode:
        print(json.dumps(_json_hits(results), ensure_ascii=False))
        return 0
    if not results:
        print("not found in any database")
        return 1
    _print_human_hits(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
