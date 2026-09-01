#!/usr/bin/env python3


"""Build a file database from a project folder.

By default — INCREMENTAL: compares file mtime/size against the database
and updates only changed/added/deleted. The FTS index is synchronized
by triggers itself. Full rebuild — only on a schema change or with the
--full flag.

Run:
    python3 build.py                                    # memory -> wiki.db
    python3 build.py -r ../projects/myproject -o ../db/myproject.db
    python3 build.py --full                             # full rebuild
"""
import argparse
import datetime
import fnmatch
import hashlib
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import _compat

ROOT = _compat.chulan_root()

# Windows console defaults to cp1251 — Russian output crashes with
# UnicodeEncodeError. Switching to UTF-8 (Python 3.7+).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110,BLE001 — reconfigure is optional, fine without it
    pass

from file_scanner import (
    DEFAULT_SKIP_DIRS,
    DEFAULT_SKIP_FILES,
    collect_extra,
    is_artifact,
    load_gitignore,
    load_local_skip,
    read_hashed,
    scan_files,
)
# --- JS/TS via tree-sitter (parsers.py; optional dependency). ---
import os
import sys

import _compat
from parsers import (  # noqa: F401 — the contract (tests: build.extract_*)
    extract_calls,
    extract_errors,
    extract_imports,
    extract_inherits,
    extract_symbols,
)



SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path TEXT NOT NULL UNIQUE,
    ext TEXT,
    size_bytes INTEGER,
    mtime REAL,
    lines INTEGER,
    symbols_count INTEGER,
    content_hash TEXT,
    content TEXT
);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER,
    signature TEXT
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(rel_path);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path TEXT NOT NULL,
    module TEXT NOT NULL,
    line INTEGER
);
CREATE INDEX IF NOT EXISTS idx_imports_module ON imports(module);
CREATE INDEX IF NOT EXISTS idx_imports_path ON imports(rel_path);

CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path TEXT NOT NULL,
    callee TEXT NOT NULL,
    line INTEGER
);
CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee);
CREATE INDEX IF NOT EXISTS idx_calls_path ON calls(rel_path);

CREATE TABLE IF NOT EXISTS inherits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path TEXT NOT NULL,
    child TEXT NOT NULL,
    base TEXT NOT NULL,
    line INTEGER
);
CREATE INDEX IF NOT EXISTS idx_inherits_base ON inherits(base);
CREATE INDEX IF NOT EXISTS idx_inherits_child ON inherits(child);
CREATE INDEX IF NOT EXISTS idx_inherits_path ON inherits(rel_path);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path TEXT NOT NULL,
    line INTEGER,
    message TEXT
);
CREATE INDEX IF NOT EXISTS idx_errors_path ON errors(rel_path);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    rel_path, content,
    content='files', content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts_trigram USING fts5(
    rel_path, content,
    content='files', content_rowid='id', tokenize='trigram'
);

-- WHEN: triggers don't fire on touch-updates (mtime/size) when content
-- has not changed — otherwise every reindexing would rewrite the FTS.

CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, rel_path, content)
    VALUES (new.id, new.rel_path, new.content);
END;

CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, rel_path, content)
    VALUES ('delete', old.id, old.rel_path, old.content);
END;

CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files
WHEN old.content IS NOT new.content BEGIN
    INSERT INTO files_fts(files_fts, rowid, rel_path, content)
    VALUES ('delete', old.id, old.rel_path, old.content);
    INSERT INTO files_fts(rowid, rel_path, content)
    VALUES (new.id, new.rel_path, new.content);
END;

CREATE TRIGGER IF NOT EXISTS files_ai_t AFTER INSERT ON files BEGIN
    INSERT INTO files_fts_trigram(rowid, rel_path, content)
    VALUES (new.id, new.rel_path, new.content);
END;

CREATE TRIGGER IF NOT EXISTS files_ad_t AFTER DELETE ON files BEGIN
    INSERT INTO files_fts_trigram(files_fts_trigram, rowid, rel_path, content)
    VALUES ('delete', old.id, old.rel_path, old.content);
END;

CREATE TRIGGER IF NOT EXISTS files_au_t AFTER UPDATE ON files
WHEN old.content IS NOT new.content BEGIN
    INSERT INTO files_fts_trigram(files_fts_trigram, rowid, rel_path, content)
    VALUES ('delete', old.id, old.rel_path, old.content);
    INSERT INTO files_fts_trigram(rowid, rel_path, content)
    VALUES (new.id, new.rel_path, new.content);
END;
"""




def stamp_wiki_frontmatter(rel: str, content: str, content_hash: str):
    """wave4 Task 14: wiki notes get the writer-maintained frontmatter
    stamps in the INDEXED COPY only — the file on disk is never rewritten
    (no history rewrite; wave1 origin-stamp pattern, now generic):
    - `origin: manual` when the note lacks any origin (ASI06, wave1);
    - `modified: <ISO-8601>` when the note lacks the freshness stamp.
    Returns (stamped_content, recomputed_hash_or_None)."""
    if "/Wiki/" not in f"/{rel}" or not rel.endswith(".md"):
        return content, None
    head_end = content.find("\n---", 3) if content.startswith("---") else -1
    if head_end == -1:
        return content, None
    head = content[3:head_end]
    stamped = content
    if "origin:" not in head:
        stamped = stamped[:head_end] + "\norigin: manual" + stamped[head_end:]
        head_end = stamped.find("\n---", 3)
        head = stamped[3:head_end]
    if not re.search(r"^modified:", head, re.MULTILINE):
        stamped = stamped[:head_end] + \
            f"\nmodified: {datetime.date.today().isoformat()}" + stamped[head_end:]  # noqa: DTZ011 — local day is the contract
    else:
        return content, None  # nothing to stamp
    return stamped, hashlib.sha256(stamped.encode("utf-8")).hexdigest()


def upsert_file(cur, rel, full, mtime, size, stats, action, content_hash=None,
                content=None):
    """Read the file and insert/update it (content + symbols + edges).
    Hash and content can be passed in advance (already read during
    comparison) to avoid reading the file twice."""
    if content is None:
        content_hash, content = read_hashed(full)
    # wave4 Task 14 (generalizes wave1's origin stamp): wiki notes get
    # `origin: manual` + `modified: <ISO>` stamps in the indexed copy
    # only — the file on disk is never rewritten, the hash is recomputed
    # so the index stays self-consistent.
    stamped, new_hash = stamp_wiki_frontmatter(rel, content, content_hash)
    if new_hash is not None:
        content, content_hash = stamped, new_hash
    cur.execute("DELETE FROM symbols WHERE rel_path = ?", (rel,))
    cur.execute("DELETE FROM imports WHERE rel_path = ?", (rel,))
    cur.execute("DELETE FROM calls WHERE rel_path = ?", (rel,))
    cur.execute("DELETE FROM inherits WHERE rel_path = ?", (rel,))
    cur.execute("DELETE FROM errors WHERE rel_path = ?", (rel,))
    if "\x00" in content:
        # binary (no extension match): drop any stale row left by a
        # text->binary flip, never index — a 50MB .exe of U+FFFD made
        # snippet()/bm25() crawl for minutes
        cur.execute("DELETE FROM files WHERE rel_path = ?", (rel,))
        stats["del"] += 1
        return
    lines = content.count("\n") + 1
    syms = extract_symbols(rel, content)
    imports = extract_imports(rel, content)
    calls = extract_calls(rel, content)
    inherits = extract_inherits(rel, content)
    errors = extract_errors(rel, content)
    ext = os.path.splitext(rel)[1].lower() or "none"
    if action == "new":
        cur.execute(
            "INSERT INTO files (rel_path, ext, size_bytes, mtime, lines, "
            "symbols_count, content_hash, content) VALUES (?,?,?,?,?,?,?,?)",
            (rel, ext, size, mtime, lines, len(syms), content_hash, content),
        )
    else:
        cur.execute(
            "UPDATE files SET ext=?, size_bytes=?, mtime=?, lines=?, "
            "symbols_count=?, content_hash=?, content=? WHERE rel_path=?",
            (ext, size, mtime, lines, len(syms), content_hash, content, rel),
        )
    cur.executemany(
        "INSERT INTO symbols (rel_path, name, kind, line, signature) "
        "VALUES (?,?,?,?,?)",
        [(rel, s[0], s[1], s[2], s[3]) for s in syms],
    )
    cur.executemany(
        "INSERT INTO imports (rel_path, module, line) VALUES (?,?,?)",
        [(rel, m, ln) for m, ln in imports],
    )
    cur.executemany(
        "INSERT INTO calls (rel_path, callee, line) VALUES (?,?,?)",
        [(rel, c, ln) for c, ln in calls],
    )
    cur.executemany(
        "INSERT INTO inherits (rel_path, child, base, line) VALUES (?,?,?,?)",
        [(rel, c, b, ln) for c, b, ln in inherits],
    )
    cur.executemany(
        "INSERT INTO errors (rel_path, line, message) VALUES (?,?,?)",
        [(rel, ln, msg) for ln, msg in errors],
    )
    stats[action] += 1


def full_build(con, root, skip_dirs, skip_files, extra=None,
               use_gitignore=False):
    """Full rebuild: DROP + CREATE + all files."""
    cur = con.cursor()
    cur.executescript(
        "DROP TABLE IF EXISTS files_fts_trigram; "
        "DROP TABLE IF EXISTS files_fts; DROP TABLE IF EXISTS errors; "
        "DROP TABLE IF EXISTS inherits; DROP TABLE IF EXISTS calls; "
        "DROP TABLE IF EXISTS imports; DROP TABLE IF EXISTS symbols; "
        "DROP TABLE IF EXISTS files;")
    cur.executescript(SCHEMA)
    stats = {"new": 0, "changed": 0, "del": 0, "same": 0}
    for rel, (mtime, size) in scan_files(root, skip_dirs, skip_files,
                                         use_gitignore).items():
        upsert_file(cur, rel, os.path.join(root, rel), mtime, size, stats, "new")
    for full, (mtime, size) in (extra or {}).items():
        upsert_file(cur, full, full, mtime, size, stats, "new")
    return stats


def incremental_build(con, root, skip_dirs, skip_files, extra=None,
                      use_gitignore=False):
    """mtime-then-hash: mtime/size — cheap gate, sha256 — authority.

    mtime matches -> leave the file alone (fast path, no reading).
    mtime/size differ -> read and hash; hash matches the stored one
    (cp -p, restore, LiveSync rewrote bytes identically) -> update only
    mtime/size, content and FTS untouched. Hash differs -> full upsert.
    Triggers keep both FTS indexes in sync."""
    cur = con.cursor()
    cur.execute("SELECT rel_path, mtime, size_bytes, content_hash FROM files")
    db_files = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    disk = scan_files(root, skip_dirs, skip_files, use_gitignore)
    stats = {"new": 0, "changed": 0, "del": 0, "same": 0, "touch": 0}

    for rel, (mtime, size) in disk.items():
        rec = db_files.get(rel)
        if rec is None:
            upsert_file(cur, rel, os.path.join(root, rel), mtime, size,
                        stats, "new")
        elif rec[0] == mtime and rec[1] == size:
            stats["same"] += 1
        else:
            full = os.path.join(root, rel)
            content_hash, content = read_hashed(full)
            if rec[2] == content_hash:
                cur.execute(
                    "UPDATE files SET mtime=?, size_bytes=? WHERE rel_path=?",
                    (mtime, size, rel))
                stats["touch"] += 1
            else:
                upsert_file(cur, rel, full, mtime, size, stats, "changed",
                            content_hash, content)

    for full, (mtime, size) in (extra or {}).items():
        rec = db_files.get(full)
        if rec is None:
            upsert_file(cur, full, full, mtime, size, stats, "new")
        elif rec[0] == mtime and rec[1] == size:
            stats["same"] += 1
        else:
            content_hash, content = read_hashed(full)
            if rec[2] == content_hash:
                cur.execute(
                    "UPDATE files SET mtime=?, size_bytes=? WHERE rel_path=?",
                    (mtime, size, full))
                stats["touch"] += 1
            else:
                upsert_file(cur, full, full, mtime, size, stats, "changed",
                            content_hash, content)

    for rel in set(db_files) - set(disk) - set(extra or {}):
        cur.execute("DELETE FROM files WHERE rel_path = ?", (rel,))
        cur.execute("DELETE FROM symbols WHERE rel_path = ?", (rel,))
        cur.execute("DELETE FROM imports WHERE rel_path = ?", (rel,))
        cur.execute("DELETE FROM calls WHERE rel_path = ?", (rel,))
        cur.execute("DELETE FROM inherits WHERE rel_path = ?", (rel,))
        cur.execute("DELETE FROM errors WHERE rel_path = ?", (rel,))
        stats["del"] += 1
    if stats["del"]:
        # DELETE triggers leave FTS tombstones; merge them so the index
        # does not bloat (372MB agent.db incident, 2026-08-19)
        cur.execute("INSERT INTO files_fts(files_fts) VALUES('optimize')")
        cur.execute(
            "INSERT INTO files_fts_trigram(files_fts_trigram) VALUES('optimize')")
    return stats


def schema_ok(con):
    """Database is suitable for incremental updates (current schema)."""
    try:
        cur = con.cursor()
        for t in ("files", "symbols", "imports", "calls", "inherits",
                  "errors"):
            # t — only from the fixed tuple above, not user input
            cur.execute(f"SELECT 1 FROM {t} LIMIT 1")  # noqa: S608 — t from the fixed tuple above; nosemgrep
        file_cols = [r[1] for r in cur.execute("PRAGMA table_info(files)")]
        sym_cols = [r[1] for r in cur.execute("PRAGMA table_info(symbols)")]
        return "lines" in file_cols and "content_hash" in file_cols and \
            "signature" in sym_cols
    except sqlite3.Error:
        return False


def atomic_full_build(db_path, root, skip_dirs, skip_files, extra=None,
                      use_gitignore=False):
    """Full rebuild into a temp db + atomic rename over db_path. A crash
    mid-build leaves the previous index intact (audit 2026-08-22 m3: the
    old code DROPped+CREATEd in place and a failed rebuild left the db
    empty)."""
    tmp = db_path + ".tmp-full"
    for side in (tmp, tmp + "-wal", tmp + "-shm", tmp + "-journal"):
        if os.path.exists(side):
            os.remove(side)
    con = sqlite3.connect(tmp)
    try:
        stats = full_build(con, root, skip_dirs, skip_files, extra,
                           use_gitignore)
        con.commit()
        con.close()
    except BaseException:
        con.close()
        for side in (tmp, tmp + "-wal", tmp + "-shm", tmp + "-journal"):
            if os.path.exists(side):
                os.remove(side)
        raise
    try:
        # a stale -wal/-shm from the previous index would corrupt the
        # replaced file; they are checkpoints-by-close, safe to drop
        for side in (db_path + "-wal", db_path + "-shm"):
            if os.path.exists(side):
                os.remove(side)
        os.replace(tmp, db_path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return stats


def main():
    ap = argparse.ArgumentParser(description="Build a file database in sqlite")
    ap.add_argument("-r", "--root", default=str(ROOT))
    ap.add_argument("-o", "--out", help="path to the database (default <root>/<folder-name>.db)")
    ap.add_argument("--full", action="store_true", help="full rebuild instead of incremental")
    ap.add_argument("--skip-dirs", nargs="*", default=[], help="additional folders to exclude")
    ap.add_argument("--skip-files", nargs="*", default=[], help="additional files to exclude")
    ap.add_argument("--gitignore", action="store_true",
                    help="respect the root .gitignore (default off: the database indexes everything, "
                         "including nested projects)")
    ap.add_argument("--extra-files", nargs="*", default=[],
                    help="external files outside root (e.g. ~/.cache/session/history.md)")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"no such folder: {root}", file=sys.stderr)
        sys.exit(1)
    if args.out:
        db_path = os.path.abspath(args.out)
    elif os.path.normcase(os.path.abspath(root)) == \
            os.path.normcase(os.path.abspath(str(ROOT))):
        db_path = os.path.join(ROOT, "db", "wiki.db")
    else:
        # project build: its own db, never the wiki (a documented
        # invocation used to destroy wiki.db: '-r X' without '-o')
        db_path = os.path.join(ROOT, "db", os.path.basename(root) + ".db")
        if os.path.basename(root) == "research":
            # would collide with the findings store (research.db): a
            # schema check would then CREATE index tables inside it
            # (audit 2026-08-22 m-adjacent). Explicit -o only.
            print("refused: a project named 'research' defaults to "
                  "db/research.db — the findings store. Pass -o "
                  "with another path.", file=sys.stderr)
            sys.exit(2)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    local_dirs, local_files = load_local_skip(root)
    skip_dirs = DEFAULT_SKIP_DIRS | set(args.skip_dirs) | local_dirs
    skip_files = DEFAULT_SKIP_FILES | set(args.skip_files) | local_files
    extra = collect_extra(args.extra_files)

    existed = os.path.exists(db_path)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    if args.full or not existed or not schema_ok(con):
        con.close()
        stats = atomic_full_build(db_path, root, skip_dirs, skip_files,
                                  extra, args.gitignore)
        mode = "full"
        con = sqlite3.connect(db_path)
        con.execute("PRAGMA journal_mode=WAL")
    else:
        stats = incremental_build(con, root, skip_dirs, skip_files, extra,
                                  args.gitignore)
        mode = "incremental"

    con.commit()
    cur = con.cursor()
    n = cur.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    total = cur.execute("SELECT SUM(LENGTH(content)) FROM files").fetchone()[0]
    nsym = cur.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    print(f"ok [{mode}]: {n} files, {nsym} symbols, {total} chars of text "
          f"-> {db_path}")
    print(f"    processed: +{stats['new']} / ~{stats['changed']} / "
          f"-{stats['del']}, unchanged: {stats['same']}, "
          f"touch (mtime, content identical): {stats.get('touch', 0)}")
    con.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — CLI wrapper: surface any error with exit code 1
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
