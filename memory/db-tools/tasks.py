#!/usr/bin/env python3

"""Task journal (research.db, tasks table) — event-sourced work history.

Why: findings answer "what do we know", the journal answers "what we did,
when, and how it ended". Survives session restarts and harness switches
(industry pattern: file-based/event-sourced memory, understandingdata.com).

Rules:
- entries are append-only: never deleted (it is a journal, time-travel);
- a task in progress has status=active; at the end — close (done) or
  abort/block (aborted/blocked);
- "how it ended" goes into --result in one or two lines (not a retelling).

Examples:
    python3 tasks.py add "Rewrite the firmware for 7 harnesses" --tags proshivka
    python3 tasks.py list
    python3 tasks.py list --status active
    python3 tasks.py close 3 --result "PreToolUse guard in 6/7 harnesses"
    python3 tasks.py block 3 --reason "owner access required"
    python3 tasks.py search firmware
    python3 tasks.py stats
"""
import argparse
import datetime
import os
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


from findings_db import research_db_path
DB = research_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    result TEXT DEFAULT '',
    closed TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    source TEXT DEFAULT ''
);
CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
    task, result, content='tasks', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS tasks_ai AFTER INSERT ON tasks BEGIN
    INSERT INTO tasks_fts(rowid, task, result)
    VALUES (new.id, new.task, new.result);
END;
CREATE TRIGGER IF NOT EXISTS tasks_au AFTER UPDATE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, task, result)
    VALUES ('delete', old.id, old.task, old.result);
    INSERT INTO tasks_fts(rowid, task, result)
    VALUES (new.id, new.task, new.result);
END;
"""

STATUSES = {"active", "done", "aborted", "blocked"}


def connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    con.commit()
    return con


def _now():
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def _warn_active(con, cur):
    act = cur.execute("SELECT COUNT(*) FROM tasks WHERE status='active'") \
        .fetchone()[0]
    if act:
        print(f"[~] open tasks: {act} — remember to close them when done",
              file=sys.stderr)


def cmd_add(args):
    con = connect()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO tasks (created, task, status, tags, source) "
        "VALUES (?,?, 'active', ?, ?)",
        (_now(), args.task, args.tags, args.source or ""))
    new_id = cur.lastrowid
    con.commit()
    print(f"[✓] task: {args.task} (id={new_id})")
    _warn_active(con, cur)
    con.close()


def cmd_close(args):
    con = connect()
    cur = con.cursor()
    row = cur.execute("SELECT * FROM tasks WHERE id = ?",
                      (args.id,)).fetchone()
    if not row:
        print(f"no task with id={args.id}")
        return
    if not args.result:
        print("provide --result 'how it ended' (one or two lines)")
        return
    cur.execute(
        "UPDATE tasks SET status='done', result=?, closed=? WHERE id=?",
        (args.result, _now(), args.id))
    con.commit()
    print(f"[✓] closed: [{args.id}] {row['task']}")
    print(f"    result: {args.result}")
    con.close()


def cmd_abort(args):
    con = connect()
    cur = con.cursor()
    row = cur.execute("SELECT * FROM tasks WHERE id = ?",
                      (args.id,)).fetchone()
    if not row:
        print(f"no task with id={args.id}")
        return
    cur.execute(
        "UPDATE tasks SET status='aborted', result=?, closed=? WHERE id=?",
        (args.reason or "aborted", _now(), args.id))
    con.commit()
    print(f"[✗] aborted: [{args.id}] {row['task']} ({args.reason or 'no reason'})")
    con.close()


def cmd_block(args):
    con = connect()
    cur = con.cursor()
    row = cur.execute("SELECT * FROM tasks WHERE id = ?",
                      (args.id,)).fetchone()
    if not row:
        print(f"no task with id={args.id}")
        return
    cur.execute(
        "UPDATE tasks SET status='blocked', result=?, closed=? WHERE id=?",
        (args.reason or "blocked", _now(), args.id))
    con.commit()
    print(f"[■] blocked: [{args.id}] {row['task']} ({args.reason or 'no reason'})")
    con.close()


def cmd_list(args):
    con = connect()
    cur = con.cursor()
    if args.status == "all":
        rows = cur.execute(
            "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
            (args.limit,)).fetchall()
    else:
        rows = cur.execute(
            "SELECT * FROM tasks WHERE status=? ORDER BY id DESC LIMIT ?",
            (args.status, args.limit)).fetchall()
    if not rows:
        print(f"no tasks with status {args.status}")
        return
    print(f"tasks: {len(rows)} (status: {args.status})\n")
    marks = {"active": "▸", "done": "✓", "aborted": "✗", "blocked": "■"}
    for r in rows:
        tail = ""
        if r["status"] == "done":
            tail = f" — {r['result'][:60]}"
        elif r["result"]:
            tail = f" ({r['result'][:60]})"
        print(f"{marks.get(r['status'], '?')} [{r['id']}] {r['created']}  "
              f"{r['task']}{tail}")
    con.close()


def cmd_search(args):
    con = connect()
    cur = con.cursor()
    from findings import sanitize_query
    try:
        rows = cur.execute(
            "SELECT t.id, t.created, t.status, t.task, t.result, "
            "snippet(tasks_fts, 1, '[', ']', '…', 12) AS snip "
            "FROM tasks_fts JOIN tasks t ON t.id = tasks_fts.rowid "
            "WHERE tasks_fts MATCH ? ORDER BY t.id DESC LIMIT ?",
            (sanitize_query(args.query), args.limit)).fetchall()
    except sqlite3.OperationalError as e:
        print(f"invalid query: {e}", file=sys.stderr)
        sys.exit(1)
    if not rows:
        print(f"nothing found for '{args.query}'")
        return
    print(f"found: {len(rows)}\n")
    for r in rows:
        print(f"[{r['id']}] {r['status']:8} {r['created']}  {r['task']}")
        print(f"  …{r['snip']}")
        print()
    con.close()


def cmd_stats(args):
    con = connect()
    cur = con.cursor()
    total = cur.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    by_status = {r["status"]: r["n"] for r in cur.execute(
        "SELECT status, COUNT(*) n FROM tasks GROUP BY status").fetchall()}
    print(f"tasks in the journal: {total}")
    for s in ("active", "blocked", "done", "aborted"):
        n = by_status.get(s, 0)
        if n or s in ("active", "done"):
            print(f"  {s:8} | {n}")
    con.close()


def main():
    ap = argparse.ArgumentParser(description="Task journal (append-only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="create a task")
    p_add.add_argument("task", help="what to do, in one line")
    p_add.add_argument("--tags", default="", help="tags, space-separated")
    p_add.add_argument("--source", default="", help="where the task came from (path/URL)")
    p_add.set_defaults(fn=cmd_add)

    p_list = sub.add_parser("list", help="list tasks")
    p_list.add_argument("--status", default="active",
                        choices=["active", "done", "aborted", "blocked", "all"],
                        help="filter by status (default active)")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(fn=cmd_list)

    p_close = sub.add_parser("close", help="close a task when done")
    p_close.add_argument("id", type=int)
    p_close.add_argument("--result", required=True,
                         help="how it ended (one or two lines)")
    p_close.set_defaults(fn=cmd_close)

    p_abort = sub.add_parser("abort", help="abort a task")
    p_abort.add_argument("id", type=int)
    p_abort.add_argument("--reason", default="", help="why it was aborted")
    p_abort.set_defaults(fn=cmd_abort)

    p_block = sub.add_parser("block", help="block a task")
    p_block.add_argument("id", type=int)
    p_block.add_argument("--reason", default="", help="what is blocking")
    p_block.set_defaults(fn=cmd_block)

    p_search = sub.add_parser("search", help="search the journal (FTS5)")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.set_defaults(fn=cmd_search)

    p_stats = sub.add_parser("stats", help="journal metrics")
    p_stats.set_defaults(fn=cmd_stats)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()


