#!/usr/bin/env python3

"""File history from git into research.db — history-aware search (pattern
Sourcegraph/zoekt: "who changed the file and when" from the index, not from memory).

Measured 13.08.2026: git log over the whole memory — 0.00s, 7.6 MB peak RAM
(negligible for the 8 GB / CPU x0.5 budget).

Examples:
    python3 githist.py refresh                 # re-read history (idempotently)
    python3 githist.py file scripts/doctor/doctor.py  # who changed a file, when, how often
    python3 githist.py hotspots --top 10       # top files by number of edits
    python3 githist.py commits --since 2026-08-01 --limit 10
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import _compat

ROOT = _compat.chulan_root()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110,BLE001 — reconfigure is optional, fine without it
    pass


from findings_db import research_db_path
DB = research_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    hash TEXT NOT NULL,
    date TEXT NOT NULL,
    author TEXT NOT NULL,
    subject TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS file_history (
    file TEXT NOT NULL,
    repo TEXT NOT NULL,
    commits INTEGER NOT NULL DEFAULT 0,
    first TEXT DEFAULT '',
    last TEXT DEFAULT '',
    authors TEXT DEFAULT '',
    PRIMARY KEY (file, repo)
);
CREATE TABLE IF NOT EXISTS commit_files (
    hash TEXT NOT NULL,
    file TEXT NOT NULL,
    repo TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(date);
CREATE INDEX IF NOT EXISTS idx_commit_files ON commit_files(hash, repo);
"""


def connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    con.commit()
    return con


_HEX_DIGITS = set("0123456789abcdef")


def _is_sha(token):
    """40-char hex — the git %H boundary. Anything else (a filename with
    pipes among its characters) is file content, not a commit header."""
    return len(token) == 40 and set(token.lower()) <= _HEX_DIGITS


def _parse_log(text):
    """Parse 'git log --name-only --pretty=format:%H|%ai|%an|%s' output
    into [(hash, date, author, subject, [files])]. Commits without files
    (empty/merge) are kept — 'commits --since' must not undercount."""
    commits = []
    cur = None
    for line in text.splitlines():
        if not line.strip():  # files named commit* are content, not headers
            if cur:
                commits.append(cur)
            cur = None
            continue
        parts = line.split("|", 3)
        if len(parts) == 4 and _is_sha(parts[0]):
            if cur:
                commits.append(cur)
            cur = [parts[0], parts[1].strip(), parts[2].strip(),
                   parts[3].strip(), []]
        elif cur is not None:
            cur[4].append(line.strip())
    if cur:
        commits.append(cur)
    return commits


def _git_log(repo):
    """git log of the whole repository: [(hash, date, author, subject, [files])].

    _compat.run, not bare subprocess: text=True without an explicit
    encoding decodes with the ANSI code page on Windows and turns Cyrillic
    subjects into permanent mojibake in research.db (audit 2026-08-22 M3)."""
    out = _compat.run(
        ["git", "-C", repo, "log", "--name-only",
         "--pretty=format:%H|%ai|%an|%s"], timeout=60)
    if out.returncode != 0:
        return None, out.stderr.strip() or "git unavailable"
    return _parse_log(out.stdout), None


def cmd_refresh(args):
    con = connect()
    repos = [str(ROOT)]
    projects = os.path.join(ROOT, "projects")
    if os.path.isdir(projects):
        repos += [os.path.join(projects, d) for d in sorted(os.listdir(projects))
                  if os.path.isdir(os.path.join(projects, d))]
    for repo in repos:
        commits, err = _git_log(repo)
        if err:
            print(f"[✗] {repo}: {err}", file=sys.stderr)
            continue
        cur = con.cursor()
        cur.execute("DELETE FROM commits WHERE repo=?", (repo,))
        cur.execute("DELETE FROM file_history WHERE repo=?", (repo,))
        cur.execute("DELETE FROM commit_files WHERE repo=?", (repo,))
        per_file = {}
        for h, d, a, s, files in commits:
            cur.execute(
                "INSERT INTO commits (repo, hash, date, author, subject) "
                "VALUES (?,?,?,?,?)", (repo, h, d, a, s))
            for f in files:
                cur.execute(
                    "INSERT INTO commit_files (hash, file, repo) "
                    "VALUES (?,?,?)", (h, f, repo))
                rec = per_file.setdefault(f, {"n": 0, "first": d, "last": d,
                                              "authors": set()})
                rec["n"] += 1
                rec["first"] = min(rec["first"], d)
                rec["last"] = max(rec["last"], d)
                rec["authors"].add(a)
        for f, rec in per_file.items():
            cur.execute(
                "INSERT INTO file_history (file, repo, commits, first, last, "
                "authors) VALUES (?,?,?,?,?,?)",
                (f, repo, rec["n"], rec["first"], rec["last"],
                 ", ".join(sorted(rec["authors"]))))
        con.commit()
        print(f"[✓] {repo}: {len(commits)} commits, "
              f"{len(per_file)} files in history")
    con.close()


def cmd_file(args):
    con = connect()
    cur = con.cursor()
    target = args.file.lstrip("./")
    row = cur.execute(
        "SELECT * FROM file_history WHERE file=? OR file LIKE ?",
        (target, f"%{target}")).fetchone()
    if not row:
        print(f"file '{args.file}' not found in git history")
        con.close()
        return
    print(f"{row['file']}: edits {row['commits']}, "
          f"{row['first'][:10]} -> {row['last'][:10]}, "
          f"authors: {row['authors']}\n")
    rows = cur.execute(
        "SELECT c.date, c.author, c.subject FROM commits c "
        "JOIN commit_files cf ON cf.hash = c.hash "
        "WHERE cf.file=? AND cf.repo=? ORDER BY c.date DESC",
        (row["file"], row["repo"])).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    for r in rows:
        print(f"  {r['date'][:10]}  {r['author']:12}  {r['subject'][:60]}")
    con.close()


def cmd_hotspots(args):
    con = connect()
    cur = con.cursor()
    rows = cur.execute(
        "SELECT file, commits, last FROM file_history "
        "ORDER BY commits DESC LIMIT ?", (args.top,)).fetchall()
    print(f"top-{args.top} files by number of edits:\n")
    for r in rows:
        print(f"  {r['commits']:3}  {r['file']:50}  last: {r['last'][:10]}")
    con.close()


def cmd_commits(args):
    con = connect()
    cur = con.cursor()
    sql = "SELECT date, author, subject, hash FROM commits WHERE 1=1"
    params = []
    if args.since:
        sql += " AND date >= ?"
        params.append(args.since)
    if args.file:
        sql += " AND repo=(SELECT repo FROM file_history WHERE file LIKE ? LIMIT 1)"
        params.append(f"%{args.file.lstrip('./')}%")
    sql += " ORDER BY date DESC LIMIT ?"
    params.append(args.limit)
    rows = cur.execute(sql, params).fetchall()
    for r in rows:
        print(f"{r['date'][:10]}  {r['author']:12}  {r['subject'][:60]}")
    con.close()


def main():
    ap = argparse.ArgumentParser(
        description="File history from git (research.db)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_refresh = sub.add_parser("refresh", help="re-read git history")
    p_refresh.set_defaults(fn=cmd_refresh)

    p_file = sub.add_parser("file", help="history of one file")
    p_file.add_argument("file", help="path to the file")
    p_file.add_argument("--limit", type=int, default=15,
                        help="how many commits to show")
    p_file.set_defaults(fn=cmd_file)

    p_hot = sub.add_parser("hotspots", help="top files by edits")
    p_hot.add_argument("--top", type=int, default=10)
    p_hot.set_defaults(fn=cmd_hotspots)

    p_cm = sub.add_parser("commits", help="list commits")
    p_cm.add_argument("--since", default="", help="since date (YYYY-MM-DD)")
    p_cm.add_argument("--file", default="", help="filter: file (substring)")
    p_cm.add_argument("--limit", type=int, default=20)
    p_cm.set_defaults(fn=cmd_commits)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()


