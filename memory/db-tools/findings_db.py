"""memory/db-tools/findings_db.py — database connection and schema for findings."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import _compat

ROOT = _compat.chulan_root()

# The DB can be overridden for tests/sandbox (isolation from the prod store):
# MEMORY_ROOT_RESEARCH_DB=/tmp/test.db python3 db-tools/findings.py ...
# Single resolver for EVERY module that touches research.db (findings, log,
# tasks, githist, repomap, search): before this, 5 of 6 hardcoded the prod
# path, so "sandboxed" writes silently mutated real memory.
def research_db_path():
    """research.db path: $MEMORY_ROOT_RESEARCH_DB override or the root default."""
    return os.environ.get(
        "MEMORY_ROOT_RESEARCH_DB", os.path.join(ROOT, "db", "research.db"))


DB = research_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    topic TEXT NOT NULL,
    text TEXT NOT NULL,
    tags TEXT DEFAULT '',
    source TEXT DEFAULT '',
    file TEXT DEFAULT '',
    symbol TEXT DEFAULT '',
    verify_cmd TEXT DEFAULT '',
    verified_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL,
    to_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'related',
    note TEXT DEFAULT '',
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_id);
CREATE INDEX IF NOT EXISTS idx_links_to ON links(to_id);
CREATE VIRTUAL TABLE IF NOT EXISTS findings_fts USING fts5(
    topic, text, content='findings', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS findings_ai AFTER INSERT ON findings BEGIN
    INSERT INTO findings_fts(rowid, topic, text)
    VALUES (new.id, new.topic, new.text);
END;
CREATE TRIGGER IF NOT EXISTS findings_ad AFTER DELETE ON findings BEGIN
    INSERT INTO findings_fts(findings_fts, rowid, topic, text)
    VALUES ('delete', old.id, old.topic, old.text);
END;
CREATE TRIGGER IF NOT EXISTS findings_au AFTER UPDATE ON findings BEGIN
    INSERT INTO findings_fts(findings_fts, rowid, topic, text)
    VALUES ('delete', old.id, old.topic, old.text);
    INSERT INTO findings_fts(rowid, topic, text)
    VALUES (new.id, new.topic, new.text);
END;
CREATE INDEX IF NOT EXISTS idx_findings_topic ON findings(topic);
"""


def connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        if con.execute(
                "PRAGMA journal_mode").fetchone()[0].lower() != "wal":
            con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # header write blocked by a concurrent writer: keep mode
    has = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table',"
        "'virtual table') AND name IN ('findings', 'findings_fts')"
        " UNION SELECT name FROM sqlite_master WHERE type = 'trigger'"
        " AND name IN ('findings_ai', 'findings_ad', 'findings_au')")}
    if has != {"findings", "findings_fts",
               "findings_ai", "findings_ad", "findings_au"}:
        # DDL only when the schema is absent or PARTIAL (pre-FTS stores
        # have findings but no findings_fts; a dropped sync trigger
        # would otherwise drift the index silently on every UPDATE —
        # the IF NOT EXISTS clauses make the script idempotent). A
        # complete schema must not take the write lock on every
        # connect (D-K).
        con.executescript(SCHEMA)
    # Soft migration of old databases: columns that did not exist before
    cols = [r[1] for r in con.execute("PRAGMA table_info(findings)")]
    if "source" not in cols:
        con.execute("ALTER TABLE findings ADD COLUMN source TEXT DEFAULT ''")
    if "file" not in cols:
        con.execute("ALTER TABLE findings ADD COLUMN file TEXT DEFAULT ''")
    if "symbol" not in cols:
        con.execute("ALTER TABLE findings ADD COLUMN symbol TEXT DEFAULT ''")
    if "verify_cmd" not in cols:
        con.execute("ALTER TABLE findings ADD COLUMN verify_cmd TEXT DEFAULT ''")
    if "verified_at" not in cols:
        con.execute("ALTER TABLE findings ADD COLUMN verified_at TEXT DEFAULT ''")
    # FTS backfill (D-C, the restore bomb): the triggers keep NEW writes in
    # sync, but rows predating the virtual table are never indexed — a
    # restored pre-FTS backup searches as empty while stats/list look
    # healthy and PRAGMA integrity_check passes. Detect "index freshly
    # created over a non-empty table" and rebuild from the content table.
    # Scoped to the empty-index case on purpose: reads stay cheap, and a
    # partial desync is `findings.py doctor`'s job (it runs integrity-check).
    try:
        n_tab = con.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        if n_tab:
            n_fts = con.execute(
                "SELECT COUNT(*) FROM findings_fts_docsize").fetchone()[0]
            if n_fts == 0:
                con.execute(
                    "INSERT INTO findings_fts(findings_fts) VALUES('rebuild')")
    except sqlite3.OperationalError:
        pass  # shadow table absent (columnsize=0 variant) — doctor's domain
    con.commit()
    return con


def connect_read():
    """Read-only connection for search/list/show/stats (D-K: reads must
    not take the write lock that serializes parallel agents). No DDL and
    no backfill here — both are writes. A store that needs healing
    (pre-FTS restore, missing schema) is routed to the rw connect(): a
    ro open SUCCEEDS on a desynced db, so the empty-index check below is
    what keeps the D-C bomb from going silent on the read path."""
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return connect()  # db absent: first-run creation is a write
    con.row_factory = sqlite3.Row
    try:
        n_tab = con.execute(
            "SELECT COUNT(*) FROM findings").fetchone()[0]
        n_fts = con.execute(
            "SELECT COUNT(*) FROM findings_fts_docsize").fetchone()[0]
    except sqlite3.Error:
        con.close()
        return connect()  # schema absent/partial: rw migrates
    if n_tab and not n_fts:
        con.close()
        return connect()  # D-C: rw backfill heals, then read
    return con
