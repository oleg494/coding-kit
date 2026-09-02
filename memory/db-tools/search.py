#!/usr/bin/env python3

"""Full-text search over the project content (database from build.py).

Examples:
    python3 search.py windows
    python3 search.py -b ../db/myproject.db model
    python3 search.py "pattern AND agent"
    python3 search.py --substring "str"             # substring (trigram, >= 3)
    python3 search.py -p skills "agent"             # only in skills/
    python3 search.py --json "agent"                # machine-readable output (JSON)
    python3 search.py --limit 5 fts
"""
import argparse
import json
import os
import sqlite3
import sys

# Windows console defaults to cp1251 — Cyrillic output fails with
# UnicodeEncodeError. Switch to UTF-8 (Python 3.7+).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110,BLE001 — reconfigure is optional; fine without it
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import _compat

ROOT = _compat.chulan_root()

DEFAULT_DB = os.path.join(ROOT, "db", "wiki.db")
from ftsquery import sanitize_query
from log import empty_queries, log_search, search_stats


def _connect(db_path):
    """Opens the project database (row_factory — Row for name access)."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _same_path(a, b):
    """Case-insensitive path equality (on Windows 'C:\\Memory' == 'c:\\memory')."""
    return os.path.normcase(os.path.abspath(a)) == \
        os.path.normcase(os.path.abspath(b))


def _default_db_for(root):
    """The db build.py itself derives for this root (wiki.db for the memory
    root, db/<name>.db for a project). --refresh accepts only this pair —
    a mismatched pair would rebuild one root into another root's index
    (audit 2026-08-22 M1, the v2.6 wiki.db-destruction bug class)."""
    if _same_path(root, str(ROOT)):
        return os.path.join(ROOT, "db", "wiki.db")
    return os.path.join(ROOT, "db", os.path.basename(root) + ".db")


def _out(args, data):
    """JSON output under the --json flag (otherwise silent: the text branches print themselves)."""
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_stats(args):
    """--stats: search usage metrics (research.db search_log)."""
    s = search_stats()
    print(f"searches total: {s['total']}  (empty: {s['empty']}, "
          f"{round(100 * s['empty'] / s['total'], 1) if s['total'] else 0}%)")
    if s["by_db"]:
        print("by database: " + ", ".join(
            f"{r['db_name']} — {r['n']}" for r in s["by_db"]))
    print("\ntop queries (query | count | found | empty):")
    for r in s["top"]:
        print(f"  {r['query'][:60]:60} | {r['n']:3} | {r['found']:4} | {r['miss']}")
    print("\nrecent:")
    for r in s["last"][:10]:
        print(f"  {r['ts']} [{r['tool']}] {r['db_name']}: "
              f"{r['query'][:60]} -> {r['hits']}")


def cmd_empty(args):
    """--empty: mine empty queries — topics people search for and do not find.
    Candidates for docs/wiki (knowledge missing from the databases;
    audit 14.08.2026 — original finding id lost in a research.db reset)."""
    rows = empty_queries(limit=args.limit)
    if not rows:
        print("no stably empty queries — topics are covered")
        return
    print(f"topics searched but not found (>=2 empty runs): {len(rows)}\n")
    for r in rows:
        print(f"  {r['n']:2}× {r['query'][:70]:70} [{r['db_name']}]")
    print("\nwhat to do: topic genuinely needed → write it up in docs/ or Wiki/"
          "(wiki-karpathy skill); fragment/language mismatch → do nothing.")


def cmd_symbol(con, args):
    """--symbol NAME: where a symbol is defined (function/class/section)."""
    rows = con.execute(
        "SELECT rel_path, name, kind, line, signature FROM symbols "
        "WHERE name LIKE ? ORDER BY rel_path, line",
        (f"%{args.symbol}%",)).fetchall()
    data = [dict(r) for r in rows]
    if args.json:
        _out(args, data)
    elif not rows:
        print(f"symbol '{args.symbol}' not found in the project map")
    else:
        print(f"found: {len(rows)}\n")
        for r in rows:
            sig = f"  {r['signature']}" if r["signature"] else ""
            print(f"{r['rel_path']}:{r['line']}  [{r['kind']}] "
                  f"{r['name']}{sig}")


def cmd_imports(con, args):
    """--imports MODULE: who imports the module (file + line)."""
    rows = con.execute(
        "SELECT rel_path, line FROM imports WHERE module = ? "
        "ORDER BY rel_path, line", (args.imports,)).fetchall()
    data = [dict(r) for r in rows]
    if args.json:
        _out(args, data)
    elif not rows:
        print(f"module '{args.imports}' is imported by nobody")
    else:
        print(f"who imports '{args.imports}': {len(rows)}\n")
        for r in rows:
            print(f"{r['rel_path']}:{r['line']}")


def cmd_calls(con, args):
    """--calls FUNCTION: who calls the function (file + line)."""
    rows = con.execute(
        "SELECT rel_path, line FROM calls WHERE callee = ? "
        "ORDER BY rel_path, line", (args.calls,)).fetchall()
    data = [dict(r) for r in rows]
    if args.json:
        _out(args, data)
    elif not rows:
        print(f"nobody calls '{args.calls}'")
    else:
        print(f"who calls '{args.calls}': {len(rows)}\n")
        for r in rows:
            print(f"{r['rel_path']}:{r['line']}")


def cmd_deps(con, args):
    """--deps FILE: which modules the file imports."""
    rows = con.execute(
        "SELECT module, line FROM imports WHERE rel_path = ? "
        "ORDER BY line", (args.deps,)).fetchall()
    data = [dict(r) for r in rows]
    if args.json:
        _out(args, data)
    elif not rows:
        print(f"file '{args.deps}' imports nothing (or is not in the database)")
    else:
        print(f"dependencies of '{args.deps}': {len(rows)}\n")
        for r in rows:
            print(f"  {r['module']}  (line {r['line']})")


def cmd_inherits(con, args):
    """--inherits CLASS: who inherits from the class; with =X — what X inherits from."""
    if args.inherits.startswith("="):
        child = args.inherits[1:]
        rows = con.execute(
            "SELECT rel_path, base, line FROM inherits "
            "WHERE child = ? ORDER BY rel_path, line",
            (child,)).fetchall()
        data = [{"rel_path": r["rel_path"], "child": child,
                 "base": r["base"], "line": r["line"]} for r in rows]
        if args.json:
            _out(args, data)
        elif not rows:
            print(f"class '{child}' inherits nothing (or is not in the database)")
        else:
            print(f"inherited by '{child}': {len(rows)}\n")
            for r in rows:
                print(f"{r['rel_path']}:{r['line']}  {child} -> {r['base']}")
        return
    rows = con.execute(
        "SELECT rel_path, child, line FROM inherits "
        "WHERE base = ? ORDER BY rel_path, line",
        (args.inherits,)).fetchall()
    data = [{"rel_path": r["rel_path"], "child": r["child"],
             "base": args.inherits, "line": r["line"]} for r in rows]
    if args.json:
        _out(args, data)
    elif not rows:
        print(f"nothing inherits from class '{args.inherits}' "
              f"(or it is not in the database)")
    else:
        print(f"inheritors of '{args.inherits}': {len(rows)}\n")
        for r in rows:
            print(f"{r['rel_path']}:{r['line']}  {r['child']} -> "
                  f"{args.inherits}")


def _search_rows(con, idx, query, path, limit, no_snippet):
    """FTS lookup by index idx (files_fts or files_fts_trigram)."""
    # rel_path is stored with OS separators; users type slashes
    path_cond = "AND REPLACE(f.rel_path, '\\', '/') LIKE ?" if path else ""
    params = [query]
    if path:
        params.append(f"%{path.replace(chr(92), '/')}%")
    cols = "f.rel_path, f.size_bytes"
    if not no_snippet:
        cols += f", snippet({idx}, 1, '<<', '>>', '…', 12) AS snip"
    sql = f"""
    SELECT {cols}
    FROM {idx}
    JOIN files f ON f.id = {idx}.rowid
    WHERE {idx} MATCH ? {path_cond}
    ORDER BY bm25({idx}, 10.0, 1.0)
    LIMIT ?
    """
    params.append(limit)
    # idx/cols are internal constants; values are prepared parameters only.
    return con.execute(sql, params).fetchall()  # nosemgrep: sqlalchemy-execute-raw-query


def cmd_errors(con, args):
    """--errors: files with syntax errors (do not parse)."""
    rows = con.execute(
        "SELECT rel_path, line, message FROM errors "
        "ORDER BY rel_path, line").fetchall()
    data = [dict(r) for r in rows]
    if args.json:
        _out(args, data)
    elif not rows:
        print("no syntax errors — all .py files parse")
    else:
        print(f"syntax errors: {len(rows)}\n")
        for r in rows:
            loc = f":{r['line']}" if r["line"] else ""
            print(f"{r['rel_path']}{loc}  {r['message']}")


def cmd_search(con, args):
    """FTS search over content (or trigram substring with --substring)."""
    if args.substring and len(args.query) < 3:
        print("--substring requires a query of at least 3 characters",
              file=sys.stderr)
        sys.exit(1)

    idx = "files_fts_trigram" if args.substring else "files_fts"
    query = sanitize_query(args.query)

    try:
        rows = _search_rows(con, idx, query, args.path, args.limit,
                            args.no_snippet)
    except sqlite3.OperationalError as e:
        print(f"invalid query: {e}", file=sys.stderr)
        sys.exit(1)

    fallback = False
    if not rows and not args.substring and len(args.query) >= 3:
        # Auto-fallback on empty results: the trigram index (substring).
        # Spike 12.08.2026 (finding lost in a research.db reset): 33% of
        # «delet»/«settin»/«delete file» return 0 in plain FTS but dozens
        # in trigram. Trigram has no boolean operators — use the raw query
        # as a literal substring.
        try:
            rows = _search_rows(con, "files_fts_trigram", args.query,
                                args.path, args.limit, args.no_snippet)
            fallback = bool(rows)
        except sqlite3.OperationalError:
            pass

    if not args.no_log:
        log_search("search.py", os.path.basename(args.db).replace(".db", ""),
                   args.query, len(rows))

    if args.json:
        data = [dict(r) for r in rows]
        _out(args, data)
        return

    wiki_hint = (_wiki_hint(args.query, args.db)
                 if len(rows) == 0 or
                 (os.path.basename(args.db) != "wiki.db"
                  and len(rows) <= 2) else "")

    if not rows:
        print("nothing found")
        print("hint: shorter query (2-3 words, no AND chains) and no inflected"
              " forms — content is indexed as-is without stemming («file»"
              " won't match «files»); another database: -b db/wiki.db;"
              " research.db findings ride along in search_all.py"
              " (findings.py search for the full payload)")
        if wiki_hint:
            print(wiki_hint)
        dym = _did_you_mean(args.query,
                            os.path.basename(args.db).replace(".db", ""))
        if dym:
            print(dym)
        return

    label = "found by substring (auto-fallback)" if fallback else "found"
    print(f"{label}: {len(rows)}\n")
    for r in rows:
        print(f"{r['rel_path']}  ({r['size_bytes']} bytes)")
        if not args.no_snippet:
            print(f"  …{r['snip']}")
        print()
    if wiki_hint:
        print(wiki_hint)


def _did_you_mean(query, db_name):
    """Empty result → similar NON-empty queries from search_log (research.db):
    match by a shared token of >=3 chars, top-2 by hit count. The industry
    "did you mean" pattern (search UX); the data is our own (30.7% empty
    queries, audit 15.08 — finding lost in a research.db reset)."""
    if len(query) < 3:
        return ""
    from findings_db import research_db_path
    rd = research_db_path()
    if not os.path.isfile(rd):
        return ""
    toks = {t.lower() for t in query.split() if len(t) >= 3}
    if not toks:
        return ""
    try:
        con = sqlite3.connect(rd)
        try:
            rows = con.execute(
                "SELECT query, MAX(hits) FROM search_log WHERE hits > 0 "
                "GROUP BY query ORDER BY MAX(hits) DESC LIMIT 200").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return ""
    best = []
    for q, h in rows:
        ql = q.lower()
        if ql == query.lower() or ql == db_name:
            continue
        score = sum(1 for t in toks if t in ql)
        if score:
            best.append((score, h, q))
    best.sort(key=lambda x: (-x[0], -x[1]))
    out = [f"«{q}» ({h} hits)" for _, h, q in best[:2]]
    if out:
        return "did you mean: " + ", ".join(out)
    return ""


def _wiki_hint(query, current_db):
    """Cross-database hint: empty/few results in this database → how many in Wiki.
    The Wiki library is barely searched (302 posts → 22 searches of 563,
    audit 15.08 — finding lost in a research.db reset) — the knowledge sits
    unused. Hint when: empty
    result in ANY database (except wiki itself) or few (<=2) in non-workspace
    databases. No hint for a non-empty wiki.db: Wiki/ is already inside its
    index (duplicate results)."""
    wiki = os.path.join(ROOT, "db", "wiki.db")
    if os.path.abspath(current_db) == os.path.abspath(wiki):
        return ""  # this is wiki itself — no hint
    if not os.path.isfile(wiki):
        return ""
    try:
        wcon = sqlite3.connect(wiki)
        try:
            n = wcon.execute(
                "SELECT COUNT(*) FROM files_fts WHERE files_fts MATCH ?",
                (sanitize_query(query),)).fetchone()[0]
            if n == 0 and len(query) >= 3:
                n = wcon.execute(
                    "SELECT COUNT(*) FROM files_fts_trigram "
                    "WHERE files_fts_trigram MATCH ?", (query,)).fetchone()[0]
        finally:
            wcon.close()
    except (sqlite3.Error, OSError):
        return ""
    if n:
        return (f"💡 in Wiki: {n} posts on the topic — take a look: "
                f"search.py -b db/wiki.db \"{query}\"")
    return ""


def main():
    ap = argparse.ArgumentParser(description="Full-text search over the project database")
    ap.add_argument("query", nargs="?", help="FTS5 query, e.g. 'windows' or 'token AND scale'")
    ap.add_argument("-b", "--db", default=DEFAULT_DB, help="path to the database (default: wiki.db)")
    ap.add_argument("--limit", type=int, default=10, help="how many results (default: 10)")
    ap.add_argument("--no-snippet", action="store_true", help="do not show snippets")
    ap.add_argument("--symbol", metavar="NAME", help="where a symbol is defined (function/class/section): file + line + signature")
    ap.add_argument("--imports", metavar="MODULE", help="graph: who imports the module (file + line)")
    ap.add_argument("--calls", metavar="FUNCTION", help="graph: who calls the function (file + line)")
    ap.add_argument("--deps", metavar="FILE", help="graph: which modules the file imports")
    ap.add_argument("--inherits", metavar="CLASS", help="graph: who inherits from the class (file + line); with =X — what the class inherits from")
    ap.add_argument("--errors", action="store_true", help="files with syntax errors (do not parse)")
    ap.add_argument("--substring", action="store_true",
                    help="substring search via the trigram index (query >= 3 characters)")
    ap.add_argument("-p", "--path", metavar="SUBSTRING",
                    help="search only files whose path contains the substring")
    ap.add_argument("--json", action="store_true", help="output as JSON (machine-readable)")
    ap.add_argument("--stats", action="store_true",
                    help="search usage metrics (research.db search_log): "
                         "top queries, empty, recent")
    ap.add_argument("--empty", action="store_true",
                    help="empty-query mining: topics searched but not found — "
                         "candidates for docs/wiki")
    ap.add_argument("--no-log", action="store_true",
                    help="do not log this search to search_log (default: it is logged)")
    ap.add_argument("--refresh", action="store_true",
                    help="rebuild the database (incrementally) before searching; "
                         "-r/--root and --extra-files are taken from the arguments")
    ap.add_argument("--force-refresh", action="store_true",
                    help="allow --refresh even when (-r, -b) do not match "
                         "build.py's own default pair for that root "
                         "(refused otherwise: a mismatched pair silently "
                         "rebuilds one root into another root's index)")
    ap.add_argument("-r", "--root", default=str(ROOT),
                    help="project root for --refresh (default: memory)")
    ap.add_argument("--extra-files", nargs="*", default=[],
                    help="external files outside root for --refresh (e.g. ~/.cache/session/history.md)")
    args = ap.parse_args()

    db_path = os.path.abspath(args.db)
    if args.stats:
        cmd_stats(args)
        return
    if args.empty:
        cmd_empty(args)
        return
    if args.refresh:
        root_abs = os.path.abspath(args.root)
        default_db = _default_db_for(root_abs)
        if not _same_path(db_path, default_db) and not args.force_refresh:
            print(
                f"refused: --refresh would rebuild {root_abs} into {db_path},\n"
                f"but build.py's own index for that root is {default_db}.\n"
                "A mismatched pair silently replaces the other root's "
                "content. Use the matching -b, or pass --force-refresh.",
                file=sys.stderr)
            sys.exit(2)
        import subprocess
        build_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build.py")
        cmd = [sys.executable, build_py, "-r", os.path.abspath(args.root),
               "-o", db_path]
        if args.extra_files:
            cmd += ["--extra-files"] + args.extra_files
        subprocess.run(cmd, check=True)
    if not os.path.exists(db_path):
        print(f"database not found: {db_path}\nRun first: python3 build.py -o {db_path}", file=sys.stderr)
        sys.exit(1)

    con = _connect(db_path)

    if args.symbol:
        cmd_symbol(con, args)
        return
    if args.imports:
        cmd_imports(con, args)
        return
    if args.calls:
        cmd_calls(con, args)
        return
    if args.deps:
        cmd_deps(con, args)
        return
    if args.inherits:
        cmd_inherits(con, args)
        return
    if args.errors:
        cmd_errors(con, args)
        return

    if not args.query:
        print("provide a query or one of the commands: --symbol, --imports, "
              "--calls, --deps, --inherits, --errors, --substring",
              file=sys.stderr)
        sys.exit(1)

    cmd_search(con, args)


if __name__ == "__main__":
    main()


