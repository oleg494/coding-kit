#!/usr/bin/env python3

"""Findings and conclusions database (research.db) — knowledge already arrived at.

Why: research (web, Camoufox, experiments, teardowns) produces conclusions
that get lost after the conversation. Here they live apart from project files
and are found by search, like everything else.

Examples:
    python3 findings.py add "MCP for LSP" --text "agent-lsp — the most mature bridge..." --tags mcp lsp
    python3 findings.py search mcp
    python3 findings.py list
    python3 findings.py list --tags lsp
    python3 findings.py del 12
    python3 findings.py edit 12 --tags "lsp mcp"
"""
import argparse
import datetime
import json
import os
import sqlite3
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import _compat
from ftsquery import fallback_query, sanitize_query
from log import log_search

ROOT = _compat.chulan_root()

# Windows console defaults to cp1251 — non-ASCII output crashes with
# UnicodeEncodeError. Switch to UTF-8 (Python 3.7+).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110,BLE001 — reconfigure is optional, we live without it
    pass


from findings_db import DB, SCHEMA, connect, connect_read
from findings_links import (
    _print_chain,
    _row_links,
    cmd_link_add,
    cmd_link_list,
    cmd_link_rm,
    cmd_related,
)

OPS = {"AND", "OR", "NOT", "NEAR"}  # noqa: F401 — re-exported for old imports

# --- Secret/PII lint (write choke point) -----------------------------------
# The store feeds verbatim into every future session's context and into every
# backup: a captured credential is a permanent leak. Hard-block unambiguous
# token shapes; block keyword+value only when the value LOOKS like a credential
# (has a digit, or mixed case at >=8 chars) so prose like "token budget" or
# "Bearer tokens" passes. Email/IPv4 warn only (server inventory is legitimate).
_SECRET_RES = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), None),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), None),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), None),
    ("keyword+value", re.compile(
        r"(?i)(?<![A-Za-z])(?:password|passwd|пароль|api[_-]?key|secret"
        r"|access[_-]?key|token)(?![A-Za-z])"
        r"\s*[:=]?\s*(?P<val>\S{6,})"), "val"),
    # AWS secret access key: the identifier carries underscores, so the
    # keyword+value \b-style boundary never fires on 'aws_secret_access_
    # key=…' and the base64-ish value (slash-heavy, digit-poor) is not
    # pathish either (measured 2026-09-02). Dedicated shape.
    ("aws-secret-key", re.compile(
        r"(?i)(?<![A-Za-z])(?:aws_)?secret[_-]?access[_-]?key"
        r"\s*[:=]?\s*(?P<val>\S{6,})"), "val"),
    # curl -u user:pass / DSN scheme://user:pass@host — the canonical
    ("curl-u-cred", re.compile(
        r"(?:^|\s)-u\s+\S+:(?P<val>[^\s:]{6,})(?:\s|$)"), "val"),
    ("url-userinfo", re.compile(
        r"[\w.+-]+:(?P<val>[^\s:@/]{6,})@[\w.-]+"), "val"),
]
_PII_RES = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
]

# Structural shell/code punctuation: a value containing these is a fragment
# (e.g. '-m 1983 ... (9)'), never a credential. Leading '-' is a shell flag.
_STRUCTURAL = "(){}[]<>|;&"


# Path/version/date-shaped values are doc paths, not credentials: the
# documented reflex (--source docs/research/2026-09-02-….md after a text
# ending in a keyword) was a verified hard-refuse FP. Bare '/' is NOT
# pathish though: base64/AWS secrets are slash-heavy and digit-poor
# ('…/bPxRfiCYEXAMPLEKEY' slipped the old bare-slash gate).
_PATHISH = re.compile(r"^\d{4}-\d{2}-\d{2}|^v?\d+\.\d+")


def _pathish(v):
    """Doc/path-shaped value: dated/versioned bare value, or a multi-
    segment path (slash OR backslash — the kit lives on Windows) whose
    LAST segment carries a dot (an extension). 'docs/v2.9-2026',
    '…/plan.md' and 'C:\\Users\\…\\notes.md' are refs; 'abc/def123' and
    'wJal…/bPxRfiCYEXAMPLEKEY' are credential-shaped (base64 has no dot
    in its alphabet)."""
    if _PATHISH.search(v):
        return True
    if "/" in v or "\\" in v:
        seg = re.split(r"[/\\]", v)[-1]
        return "." in seg
    return False


def _looks_secret(val):
    """Credential-shaped value, not prose/code fragment/path.

    Strip wrapping quotes first — password="hunter2x" is THE most common
    capture shape and must not slip through the alnum gate. Then require
    alnum start (leading '-' = shell flag), no structural punctuation
    (){}[]<>|;&, no path/version/date shape (_pathish), then entropy:
    chars, or mixed case at >=8. Known live FPs this gate kills: id=53
    ('Only token -m 1983 … (9)') and dated --source paths.
    """
    v = val.strip("'\"")
    if not v or not v[0].isalnum():
        return False
    if any(c in v for c in _STRUCTURAL):
        return False
    if _pathish(v):
        return False
    if any(c.isdigit() for c in v):
        return len(v) >= 6
    return len(v) >= 8 and any(c.isupper() for c in v) \
        and any(c.islower() for c in v)


def find_secrets(text):
    """(blocking pattern names, pii values) — descriptors are pattern NAMES
    only, never a slice of the match: stderr lands in session transcripts,
    which are exactly the long-lived store this lint protects."""
    secrets, pii = [], []
    for name, rx, val_group in _SECRET_RES:
        for m in rx.finditer(text):
            if val_group and not _looks_secret(m.group(val_group)):
                continue
            secrets.append(name)
    for rx in _PII_RES:
        for m in rx.finditer(text):
            pii.append(m.group(0))
    return secrets, pii


def scrub_text(text):
    """Redaction for telemetry: query strings pass through here before the
    search_log INSERT — a password pasted into a search must not become a
    permanent row (telemetry-vs-scrub consistency)."""
    secrets, _ = find_secrets(text)
    return "***redacted***" if secrets else text

def cmd_add(args):
    con = connect()
    cur = con.cursor()
    if args.stdin_mode and args.text:
        print("[!] --stdin and --text are mutually exclusive", file=sys.stderr)
        sys.exit(2)
    if not args.stdin_mode and not args.text:
        print("[!] either --text or --stdin is required", file=sys.stderr)
        sys.exit(2)
    if args.stdin_mode:
        text = sys.stdin.read()
        # Windows pipes/here-strings send CRLF; store LF like every other entry
        text = text.replace("\r\n", "\n")
        if not text.strip():
            print("[!] --stdin: empty input, nothing to add", file=sys.stderr)
            sys.exit(2)
    else:
        text = args.text
    # verify_cmd is scanned too: cmd_verify prints it verbatim to stdout on
    # every re-verify — a credential there lands in the transcript each time.
    # Each field scans INDEPENDENTLY: joining lets the regex \s* bridge a
    # keyword at one field's END to the next field's START (verified FP:
    # text "...api token" + dated --source path was REFUSED). A credential
    # never legitimately spans a field boundary.
    secrets, pii = [], []
    for part in (args.topic, text, args.source or "",
                 getattr(args, "verify_cmd", "") or ""):
        _s, _p = find_secrets(part)
        secrets += _s
        pii += _p
    if secrets and not getattr(args, "force", False):
        print(f"[!] possible secret in topic/text/source/verify-cmd "
              f"({len(secrets)} hit(s): {', '.join(sorted(set(secrets))[:3])}) — "
              f"REFUSED. Store only WHERE the secret lives, not the secret; "
              f"override: --force", file=sys.stderr)
        con.close()
        sys.exit(2)
    if pii:
        kinds = sorted({"email" if "@" in p else "ip" for p in pii})
        print(f"[~] PII note: {'/'.join(kinds)} in text — this store feeds every "
              f"future session and every backup", file=sys.stderr)
    dup = cur.execute(
        "SELECT id, topic FROM findings "
        "WHERE lower(trim(topic)) = ? LIMIT 1",
        (_norm_topic(args.topic),)).fetchone()
    if dup:
        print(f"[!] a finding with this topic already exists: id={dup['id']} "
              f"\"{dup['topic']}\" — edit id={dup['id']} instead of adding "
              f"a duplicate", file=sys.stderr)
    args.tags = _norm_tags(args.tags)
    for w in _topic_style_warn(args.topic):
        print(f"[~] topic style: {w} — prefer a short noun phrase",
              file=sys.stderr)
    if not args.source:
        # P14: auto-promote the first URL from text into an empty
        # source (verifiability without a second flag). URL-shape only:
        # a bare dotted-token branch promoted prose ("Sec. A") and, by
        # filling source, silently disabled the provenance hint below.
        # rstrip: \S+ swallows sentence-final punctuation.
        m = re.search(r"https?://\S+", text)
        if m:
            args.source = m.group(0).rstrip(".,;:)")
    if not args.source:
        print("[~] hint: --source not set; for web facts give a "
              "URL/path so the conclusion stays verifiable", file=sys.stderr)
    rel = _parse_ids(args.related)
    sup = _parse_ids(getattr(args, "supersedes", ""))
    _check_ids(cur, rel + sup, "--related/--supersedes")
    vcmd = getattr(args, "verify_cmd", "") or ""
    if vcmd and not _quote_balanced(vcmd):
        print("[!] --verify-cmd has unbalanced quotes — the shell line "
              "would mis-parse at verify time; REFUSED", file=sys.stderr)
        con.close()
        sys.exit(2)
    cur.execute(
        "INSERT INTO findings (created, topic, text, tags, source, file, "
        "symbol, verify_cmd) VALUES (?,?,?,?,?,?,?,?)",
        (datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
         args.topic, text, args.tags, args.source or "",
         args.file or "", args.symbol or "", getattr(args, "verify_cmd", "") or ""))
    new_id = cur.lastrowid
    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    for tgt, kind in ([(r, "related") for r in rel if r != new_id]
                      + [(s, "supersedes") for s in sup if s != new_id]):
        cur.execute(
            "INSERT INTO links (from_id, to_id, kind, note, created) "
            "VALUES (?,?,?,?,?)", (new_id, tgt, kind, "", now))
    con.commit()
    print(f"[✓] added: {args.topic} (id={new_id})")
    if args.file:
        loc = args.file + (f":{args.symbol}" if args.symbol else "")
        print(f"    attached to: {loc}")
    if rel:
        print(f"    linked to: {args.related}")
    if sup:
        print(f"    supersedes: {args.supersedes}")
    con.close()


def _parse_ids(s):
    """'1,2, 3' -> [1, 2, 3]; skip junk."""
    out = []
    for part in (s or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _norm_tags(s):
    """P14: one tag format — lowercase, comma→space, whitespace collapse.
    Comma storage made the ' tag ' LIKE filter blind to 32 rows;
    normalizing at write time beats a join-table (DEFER behind a
    usage gate)."""
    return " ".join((s or "").replace(",", " ").split()).lower()


def _norm_topic(s):
    """P14 dedup key: lower(trim). Trailing dates stay significant —
    the corpus is date-stamped by design; exact-normalized collision
    is the warn case."""
    return (s or "").strip().lower()


def _topic_style_warn(topic):
    """P14: junk-topic shapes warn at write time (stderr hint, never a
    CHECK-constraint — hard-fail mid-task loses the finding)."""
    warns = []
    if re.match(r"^\d{4}-\d{2}-\d{2}", topic):
        warns.append("date-prefixed topic")
    if len(topic) > 60:
        warns.append(f"{len(topic)}-char topic")
    return warns


def _check_ids(cur, ids, label):
    """P13: existence-check for --related/--supersedes — a silent orphan
    link is worse than a refused add."""
    for i in ids:
        if not cur.execute(
                "SELECT 1 FROM findings WHERE id = ?", (i,)).fetchone():
            print(f"[!] {label}: no finding with id={i}", file=sys.stderr)
            sys.exit(2)


def _quote_balanced(s):
    """P15: cheap guard on verify_cmd — an unbalanced quote means the
    stored shell line will mis-parse at verify time; refuse at write."""
    return (s or "").count('"') % 2 == 0 and (s or "").count("'") % 2 == 0


def _superseded_by(alias):
    """P13 badge: links kind='supersedes', to_id = the OLD row. A scalar
    subquery, NOT a LEFT JOIN: a second `--supersedes N` would fan row N
    out into duplicate result rows (and duplicate --json ids) with a
    join; MIN(from_id) keeps one row per finding. `alias` is a fixed
    column reference (f.id), never user input."""
    return ("(SELECT MIN(l.from_id) FROM links l "
            f"WHERE l.to_id = {alias} AND l.kind = 'supersedes') "
            "AS superseded_by")


def cmd_del(args):
    con = connect()
    cur = con.cursor()
    row = cur.execute("SELECT topic FROM findings WHERE id = ?",
                      (args.id,)).fetchone()
    if not row:
        print(f"no finding with id={args.id}")
        return
    cur.execute("DELETE FROM findings WHERE id = ?", (args.id,))
    n_links = cur.execute(
        "DELETE FROM links WHERE from_id = ? OR to_id = ?",
        (args.id, args.id)).rowcount
    con.commit()
    print(f"[✓] deleted: id={args.id} \"{row['topic']}\""
          + (f" (links deleted: {n_links})" if n_links else ""))
    con.close()


def cmd_edit(args):
    con = connect()
    cur = con.cursor()
    row = cur.execute("SELECT * FROM findings WHERE id = ?",
                      (args.id,)).fetchone()
    if not row:
        print(f"no finding with id={args.id}")
        return
    sets, params = [], []
    for col, val in (("topic", args.topic), ("text", args.text),
                     ("tags", args.tags), ("source", args.source),
                     ("verify_cmd", args.verify_cmd),
                     ("file", args.file), ("symbol", args.symbol)):
        if val is not None:
            if col == "tags":
                val = _norm_tags(val)
            sets.append(f"{col} = ?")
            params.append(val)
    if not sets:
        print("nothing to change: pass --topic/--text/--tags/--source/"
              "--verify-cmd/--file/--symbol")
        return
    # Scan EVERY whitelisted column INDEPENDENTLY (add/edit choke-point
    # symmetry; joining lets the regex bridge a field boundary — see cmd_add).
    secrets = []
    for v in (args.topic, args.text, args.tags, args.source,
              args.verify_cmd, args.file, args.symbol):
        if v is not None:
            secrets += find_secrets(v)[0]
    if secrets and not getattr(args, "force", False):
        print(f"[!] possible secret in edited fields ({len(secrets)} hit(s)) — "
              f"REFUSED. Store only WHERE the secret lives; override: --force",
              file=sys.stderr)
        con.close()
        sys.exit(2)
    params.append(args.id)
    # Columns are the fixed list above (topic/text/tags/source),
    # values are only parameters: no injection.
    cur.execute(f"UPDATE findings SET {', '.join(sets)} WHERE id = ?", params)  # noqa: S608 — columns whitelist, values params; nosemgrep
    con.commit()
    print(f"[✓] updated: id={args.id} \"{row['topic']}\"")
    con.close()


def cmd_verify(args):
    """Re-run a finding's verify-cmd: memory that proves itself fresh.
    VERIFIED (exit 0, verified_at stamped) or FAILED (exit 1)."""
    con = connect()
    cur = con.cursor()
    r = cur.execute("SELECT topic, verify_cmd, verified_at FROM findings "
                    "WHERE id = ?", (args.id,)).fetchone()
    if not r:
        print(f"no finding with id={args.id}")
        con.close()
        sys.exit(1)
    if not r["verify_cmd"]:
        print(f"finding [{args.id}] has no verify-cmd "
              "(add one: findings.py edit ... / add --verify-cmd)")
        con.close()
        sys.exit(1)
    cmd = r["verify_cmd"]
    print(f"[~] running: {cmd}")
    # P15 (D-F): verify_cmd is a SHELL line by design ('cd … && pytest');
    # shlex.split broke every stored multi-command value. Writers of this
    # store already hold the shell — an exec-allowlist is disproportionate.
    out = _compat.run(cmd, shell=True,
                      timeout=getattr(args, "timeout", None) or 300)
    tail = "\n".join(((out.stdout or "") + (out.stderr or "")).splitlines()[-5:])
    if out.returncode == 0:
        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        cur.execute("UPDATE findings SET verified_at = ? WHERE id = ?",
                    (now, args.id))
        con.commit()
        print(f"[✓] VERIFIED: \"{r['topic']}\" at {now}")
        con.close()
        return
    print(f"[✗] FAILED (rc={out.returncode}): \"{r['topic']}\" — "
          f"last verified: {r['verified_at'] or 'never'}")
    if tail:
        print(tail)
    con.close()
    sys.exit(1)


def cmd_search(args):
    con = connect_read()
    cur = con.cursor()
    base = ("SELECT f.id, f.created, f.topic, f.tags, f.source, f.file, "
            "f.symbol, f.verify_cmd, f.verified_at, "
            + _superseded_by("f.id") + ", "
            "bm25(findings_fts, 10.0, 1.0) AS score, "
            "snippet(findings_fts, 1, '[', ']', '…', 12) AS snip, "
            "highlight(findings_fts, 0, '[', ']') AS htopic "
            "FROM findings_fts JOIN findings f ON f.id = findings_fts.rowid "
            "WHERE findings_fts MATCH ?")
    filters = ""
    params = [sanitize_query(args.query)]
    source = getattr(args, "source", "")
    tag = getattr(args, "tag", "")
    if source:
        filters += " AND f.source LIKE ?"
        params.append(f"%{source}%")
    if tag:
        filters += " AND ' '||f.tags||' ' LIKE ?"
        params.append(f"% {tag} %")
    # P9: relevance first (weights mirror search.py:220), recency only as
    # tiebreak; id-DESC was defect #1 (0/10 overlap with bm25-top-10 on
    # the 10k clone). COUNT separately from LIMIT = honest header.
    order = " ORDER BY score, f.id DESC"
    note = ""
    try:
        rows = cur.execute(base + filters + order + " LIMIT ?",
                           params + [args.limit]).fetchall()
        total = cur.execute(
            "SELECT COUNT(*) FROM findings_fts JOIN findings f "
            "ON f.id = findings_fts.rowid WHERE findings_fts MATCH ?"
            + filters, params).fetchone()[0]
    except sqlite3.OperationalError as e:
        # P8: one retry with the dot-split fallback ('5.3' is an FTS5
        # syntax error bare); a second failure is a genuinely bad query
        retry = fallback_query(args.query)
        try:
            params = [retry] + ([f"%{source}%"] if source else []) \
                + ([f"% {tag} %"] if tag else [])
            rows = cur.execute(base + filters + order + " LIMIT ?",
                               params + [args.limit]).fetchall()
            total = cur.execute(
                "SELECT COUNT(*) FROM findings_fts JOIN findings f "
                "ON f.id = findings_fts.rowid WHERE findings_fts MATCH ?"
                + filters, params).fetchone()[0]
            note = " (query auto-quoted)"
        except sqlite3.OperationalError:
            print(f"invalid query: {e}", file=sys.stderr)
            con.close()
            sys.exit(1)
    # P10: prefix-retry on empty (query-side, mirrors search.py): any
    # token len>=4 becomes a prefix; zero storage cost
    if not rows and not note:
        toks = [t for t in args.query.split() if len(t) >= 4]
        if toks:
            pq = " ".join('"' + t.replace('"', '""') + '"*' for t in toks)
            pparams = [pq] + ([f"%{source}%"] if source else []) \
                + ([f"% {tag} %"] if tag else [])
            prows = cur.execute(base + filters + order + " LIMIT ?",
                                pparams + [args.limit]).fetchall()
            if prows:
                ptotal = cur.execute(
                    "SELECT COUNT(*) FROM findings_fts JOIN findings f "
                    "ON f.id = findings_fts.rowid WHERE findings_fts "
                    "MATCH ?" + filters, pparams).fetchone()[0]
                rows, total = prows, ptotal
                note = " (found by prefix (auto))"
    # Telemetry: the findings surface was invisible to search_log, so every
    # recall decision (did-you-mean, trigram, empty-mining) flew blind here.
    log_search("findings.py", "research", scrub_text(args.query), len(rows))
    if getattr(args, "json_mode", False):
        print(json.dumps([
            {"id": r["id"], "created": r["created"], "topic": r["topic"],
             "tags": r["tags"], "source": r["source"], "file": r["file"],
             "score": round(r["score"], 4),
             "superseded_by": r["superseded_by"],
             "has_verify": bool(r["verify_cmd"]),
             "verified_at": r["verified_at"], "snippet": r["snip"]}
            for r in rows], ensure_ascii=False))
        con.close()
        return
    if not rows:
        print(f"not found for \"{args.query}\""
              + (f" (source ~ \"{source}\")" if source else "")
              + (f" (tag \"{tag}\")" if tag else ""))
        con.close()
        return
    print(f"found: {total}, showing: {len(rows)}{note}\n")
    for r in rows:
        badge = (f"  ⚠ superseded by #{r['superseded_by']}"
                 if r["superseded_by"] else "")
        print(f"[{r['id']}] {r['created']}  {r['htopic']}  "
              f"({r['tags']}){badge}")
        print(f"  …{r['snip']}")
        print()
    con.close()


def cmd_list(args):
    con = connect_read()
    cur = con.cursor()
    sel = ("SELECT f.id, f.created, f.topic, f.tags, f.file, f.symbol, "
           + _superseded_by("f.id") + " FROM findings f ")
    if args.tags:
        rows = cur.execute(
            sel + "WHERE ' '||f.tags||' ' LIKE ? ORDER BY f.id DESC",
            (f"% {args.tags} %",)).fetchall()
    else:
        rows = cur.execute(
            sel + "ORDER BY f.id DESC LIMIT ?", (args.limit,)).fetchall()
    if not rows:
        print("empty so far — add the first finding: findings.py add \"topic\"")
        return
    print(f"total: {len(rows)}\n")
    for r in rows:
        loc = f" [{r['file']}:{r['symbol']}]" if r["file"] else ""
        badge = (f"  ⚠ superseded by #{r['superseded_by']}"
                 if r["superseded_by"] else "")
        print(f"[{r['id']}] {r['created']}  {r['topic']}  "
              f"({r['tags']}){loc}{badge}")
    con.close()


def cmd_show(args):
    con = connect_read()
    cur = con.cursor()
    r = cur.execute("SELECT * FROM findings WHERE id = ?",
                    (args.id,)).fetchone()
    if not r:
        print(f"no finding with id={args.id}")
        con.close()
        return
    print(f"[{r['id']}] {r['created']}  {r['topic']}")
    if r["tags"]:
        print(f"tags: {r['tags']}")
    if r["source"]:
        print(f"source: {r['source']}")
    if r["file"]:
        print(f"at: {r['file']}" + (f":{r['symbol']}" if r["symbol"] else ""))
    if r["verify_cmd"]:
        print(f"verify-cmd: {r['verify_cmd']} "
              f"(last: {r['verified_at'] or 'never'})")
    print()
    print(r["text"])
    links = _row_links(cur, args.id)
    if links:
        print("\nlinks:")
        for _link_id, direction, kind, topic, note in links:
            note_s = f"  ({note})" if note else ""
            print(f"  {direction} {kind:12} {topic}{note_s}")
    con.close()


def cmd_stats(args):
    con = connect_read()
    cur = con.cursor()
    total = cur.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    week_ago = (datetime.datetime.now().astimezone() -
                datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    last7 = cur.execute("SELECT COUNT(*) FROM findings WHERE created >= ?",
                        (week_ago,)).fetchone()[0]
    nlinks = cur.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    print(f"findings: {total}  (last 7 days: {last7})  links: {nlinks}")
    tags = cur.execute(
        "SELECT tags, COUNT(*) n FROM findings GROUP BY tags "
        "ORDER BY n DESC LIMIT 10").fetchall()
    if tags and any(r["tags"] for r in tags):
        print("\ntop tags (set | count):")
        for r in tags:
            if r["tags"]:
                print(f"  {r['tags']:40} | {r['n']}")
    con.close()


def cmd_doctor(args):
    """Findings-store integrity: table vs FTS agreement + FTS5 self-check.

    External-content FTS5 fails SILENTLY — PRAGMA integrity_check validates
    page structure, not index↔table correspondence, so a desynced store
    reports green everywhere while search quietly loses rows. Detect, heal
    with 'rebuild', re-verify; exit non-zero only if healing fails.
    The FTS5 self-check MUST pass rank=1: the bare form (rank=0) only
    validates shadow-internal structure; per SQLite docs §6.7 the index
    is compared against the content table ONLY when rank=1 — measured
    2026-09-02: rank=0 PASSES an empty index over 2 rows and stale
    content with equal counts, rank=1 raises on both.
    """
    con = connect()
    cur = con.cursor()
    problems = []

    n_tab = cur.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    try:
        n_fts = cur.execute(
            "SELECT COUNT(*) FROM findings_fts_docsize").fetchone()[0]
        shadow = True
    except sqlite3.OperationalError:
        n_fts, shadow = None, False
    if shadow and n_fts != n_tab:
        problems.append(
            f"FTS desync: findings={n_tab} indexed={n_fts} — rebuilding")

    try:
        cur.execute("INSERT INTO findings_fts(findings_fts, rank) "
                    "VALUES('integrity-check', 1)")
    except sqlite3.DatabaseError as e:
        problems.append(f"FTS5 integrity-check failed: {e} — rebuilding")

    healed = False
    if problems:
        try:
            cur.execute(
                "INSERT INTO findings_fts(findings_fts) VALUES('rebuild')")
            con.commit()
            n_fts2 = cur.execute(
                "SELECT COUNT(*) FROM findings_fts_docsize").fetchone()[0]
            cur.execute("INSERT INTO findings_fts(findings_fts, rank) "
                        "VALUES('integrity-check', 1)")
            if n_fts2 != n_tab:
                problems.append(
                    f"rebuild did NOT heal: findings={n_tab} indexed={n_fts2}")
            else:
                healed = True
        except sqlite3.DatabaseError as e:
            problems.append(f"rebuild failed: {e}")

    if not problems:
        print(f"doctor: OK — findings={n_tab}, FTS in sync, "
              f"integrity-check passed")
        con.close()
        return
    for p in problems:
        print(f"  ! {p}")
    fatal = any(("did NOT" in p) or ("rebuild failed" in p) or
                ("integrity-check failed" in p and not healed)
                for p in problems)
    if fatal or not healed:
        print("doctor: FAILED", file=sys.stderr)
        con.close()
        sys.exit(1)
    print("doctor: OK after rebuild")
    con.close()


def main():
    ap = argparse.ArgumentParser(description="Findings and conclusions database")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add", help="add a finding")
    p_add.add_argument("topic", help="topic in one line")
    p_add.add_argument("--text", help="conclusion/fact (or use --stdin)")
    p_add.add_argument("--stdin", dest="stdin_mode", action="store_true",
                       help="read conclusion text from stdin (no shell quoting)")
    p_add.add_argument("--tags", default="", help="space-separated tags")
    p_add.add_argument("--source", default="", help="where it came from (path/URL)")
    p_add.add_argument("--file", default="",
                       help="project file where the problem lives (rel_path)")
    p_add.add_argument("--symbol", default="",
                       help="symbol (fn/class) where the problem lives")
    p_add.add_argument("--related", default="",
                       help="ids of linked findings, comma-separated")
    p_add.add_argument("--supersedes", default="",
                       help="ids this finding replaces (link kind="
                            "'supersedes'; old rows get a badge)")
    p_add.add_argument("--verify-cmd", default="",
                       help="command that re-verifies this conclusion "
                            "(findings.py verify <id> runs it)")
    p_add.add_argument("--force", action="store_true",
                       help="insert even if the secret lint fires "
                            "(default: refuse credential-shaped text)")
    p_add.set_defaults(fn=cmd_add)

    p_verify = sub.add_parser("verify", help="re-run a finding's verify-cmd")
    p_verify.add_argument("id", type=int)
    p_verify.add_argument("--timeout", type=int, default=300,
                          help="verify-cmd timeout seconds (default 300)")
    p_verify.set_defaults(fn=cmd_verify)

    p_search = sub.add_parser("search", help="search findings")
    p_search.add_argument("query", help="FTS5 query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--source", default="",
                          help="filter: source (path/URL) contains substring")
    p_search.add_argument("--tag", default="",
                          help="filter: exact finding tag")
    p_search.add_argument("--json", dest="json_mode", action="store_true",
                          help="machine output: JSON list")
    p_search.set_defaults(fn=cmd_search)

    p_list = sub.add_parser("list", help="list findings")
    p_list.add_argument("--tags", default="", help="filter by tag (exact word)")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(fn=cmd_list)

    p_del = sub.add_parser("del", help="delete finding by id")
    p_del.add_argument("id", type=int)
    p_del.set_defaults(fn=cmd_del)

    p_edit = sub.add_parser("edit", help="edit finding by id")
    p_edit.add_argument("id", type=int)
    p_edit.add_argument("--topic")
    p_edit.add_argument("--text")
    p_edit.add_argument("--tags")
    p_edit.add_argument("--source")
    p_edit.add_argument("--verify-cmd", dest="verify_cmd")
    p_edit.add_argument("--file")
    p_edit.add_argument("--symbol")
    p_edit.add_argument("--force", action="store_true",
                        help="save even if the secret lint fires")
    p_edit.set_defaults(fn=cmd_edit)

    p_show = sub.add_parser("show", help="full finding record + links")
    p_show.add_argument("id", type=int)
    p_show.set_defaults(fn=cmd_show)

    p_related = sub.add_parser("related", help="what is linked to a finding")
    p_related.add_argument("id", type=int)
    p_related.add_argument("--depth", type=int, default=0,
                           help="link graph depth (0 — neighbors only)")
    p_related.set_defaults(fn=cmd_related)

    p_link = sub.add_parser("link", help="finding links (link add/list/rm)")
    link_sub = p_link.add_subparsers(dest="link_cmd", required=True)
    p_la = link_sub.add_parser("add", help="add a link")
    p_la.add_argument("from_id", type=int)
    p_la.add_argument("to_id", type=int)
    p_la.add_argument("--kind", default="related",
                      help="type: related/extends/contradicts/source (default related)")
    p_la.add_argument("--note", default="", help="note for the link")
    p_la.set_defaults(fn=cmd_link_add)
    p_ll = link_sub.add_parser("list", help="finding links (both directions)")
    p_ll.add_argument("id", type=int)
    p_ll.set_defaults(fn=cmd_link_list)
    p_lr = link_sub.add_parser("rm", help="delete link by id")
    p_lr.add_argument("id", type=int)
    p_lr.set_defaults(fn=cmd_link_rm)

    p_stats = sub.add_parser("stats", help="metrics: total findings, last 7 days, links, top tags")
    p_stats.set_defaults(fn=cmd_stats)

    p_doctor = sub.add_parser(
        "doctor", help="integrity: findings vs FTS agreement, integrity-check, "
                       "auto-rebuild on desync")
    p_doctor.set_defaults(fn=cmd_doctor)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()


