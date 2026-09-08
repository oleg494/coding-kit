"""memory/db-tools/findings_classify.py — finding classification, projects and batch classify."""
import datetime
import json
import os
import re
import sqlite3
import sys
import findings_db
from findings_db import ROOT, connect, connect_read
RESERVED_PROJECTS = {"portable", "unknown"}
IMPORTANCE_LEVELS = {"high", "normal", "low", "unreviewed"}
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def list_known_projects(root=None):
    """Discover projects dynamically: reserved constants + db/*.db + optional projects.json."""
    r = root or ROOT
    projects = set(RESERVED_PROJECTS)
    db_dir = os.path.join(r, "db")
    if os.path.isdir(db_dir):
        for f in os.listdir(db_dir):
            if f.endswith(".db"):
                stem = f[:-3]
                if stem not in ("wiki", "research") and _SLUG_RE.match(stem):
                    projects.add(stem)
    pj = os.path.join(r, "projects.json")
    if os.path.isfile(pj):
        try:
            with open(pj, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    for p in data:
                        if isinstance(p, str) and _SLUG_RE.match(p):
                            projects.add(p)
                elif isinstance(data, dict):
                    for p in data.keys():
                        if isinstance(p, str) and _SLUG_RE.match(p):
                            projects.add(p)
        except Exception:
            pass
    return sorted(projects)


def validate_project_slug(slug):
    """Validate project slug: lower(trim), must match alphanumeric with dash/underscore."""
    if not slug:
        return "unknown"
    s = slug.strip().lower()
    if not _SLUG_RE.match(s):
        raise ValueError(f"Invalid project slug '{slug}': must match [a-z0-9][a-z0-9_-]{{0,63}}")
    return s


def cmd_projects(args):
    """Summary table of findings counts grouped by project and importance."""
    con = connect_read()
    cur = con.cursor()
    cols = {c[1] for c in cur.execute("PRAGMA table_info(findings)").fetchall()}
    if "project" not in cols or "importance" not in cols:
        print("no findings recorded yet")
        con.close()
        return
    rows = cur.execute("""
        SELECT project, importance, COUNT(*) AS cnt
        FROM findings
        GROUP BY project, importance
        ORDER BY project, cnt DESC
    """).fetchall()
    con.close()
    if not rows:
        print("no findings recorded yet")
        return
    by_proj = {}
    for r in rows:
        p = r["project"] or "unknown"
        imp = r["importance"] or "unreviewed"
        by_proj.setdefault(p, {})[imp] = r["cnt"]
    print("=== Findings by Project ===")
    for p in sorted(by_proj.keys()):
        total = sum(by_proj[p].values())
        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(by_proj[p].items()))
        print(f"  {p:18} total: {total:3} ({breakdown})")


def cmd_classify(args, find_secrets_fn=None):
    """Generic reviewed classification apply/dry-run tool.
    Loads a JSON mapping: [{"id": 1, "project": "slug", "importance": "high", "rationale": "..."}, ...]
    Applies under atomic transaction with verification. Preserves existing manual assignments unless --force.
    """
    mapping_path = args.file
    if not os.path.isfile(mapping_path):
        print(f"[!] file not found: {mapping_path}", file=sys.stderr)
        sys.exit(1)
    with open(mapping_path, "r", encoding="utf-8") as fp:
        try:
            raw_data = json.load(fp)
        except Exception as e:
            print(f"[!] invalid JSON mapping file: {e}", file=sys.stderr)
            sys.exit(1)

    if isinstance(raw_data, list):
        records = raw_data
    elif isinstance(raw_data, dict) and "records" in raw_data and isinstance(raw_data["records"], list):
        records = raw_data["records"]
    else:
        print("[!] mapping file must contain a JSON list or an object with 'records' list", file=sys.stderr)
        sys.exit(1)

    if not records:
        print("[!] mapping file contains no records", file=sys.stderr)
        sys.exit(1)

    # Validate all records structure in memory first before touching the database
    seen_ids = set()
    validated_records = []
    for idx, item in enumerate(records):
        if not isinstance(item, dict):
            print(f"[!] record #{idx} is not an object: {item!r}", file=sys.stderr)
            sys.exit(1)

        fid = item.get("id")
        if isinstance(fid, bool) or not isinstance(fid, int) or fid <= 0:
            print(f"[!] record #{idx} has invalid integer id: {fid!r}", file=sys.stderr)
            sys.exit(1)

        if fid in seen_ids:
            print(f"[!] duplicate finding id {fid} in mapping file (rejected to avoid hidden ordering bugs)", file=sys.stderr)
            sys.exit(1)
        seen_ids.add(fid)

        raw_proj = item.get("candidate_project", item.get("project", "unknown"))
        try:
            proj = validate_project_slug(raw_proj)
        except ValueError as e:
            print(f"[!] record for finding #{fid} has invalid project slug: {e}", file=sys.stderr)
            sys.exit(1)

        imp = item.get("candidate_importance", item.get("importance", "unreviewed"))
        if imp not in IMPORTANCE_LEVELS:
            print(f"[!] invalid importance '{imp}' for finding #{fid}", file=sys.stderr)
            sys.exit(1)

        prov = item.get("provenance", "reviewed_mapping")
        ev = item.get("rationale", item.get("evidence", ""))
        if not ev:
            ev = item.get("project_rationale", "")
        imp_ev = item.get("importance_rationale", ev)

        # Lint rationale / evidence strings for secrets if find_secrets_fn provided
        if find_secrets_fn and not getattr(args, "force", False):
            for label, txt in [("evidence", ev), ("importance_evidence", imp_ev)]:
                if txt:
                    sec, _ = find_secrets_fn(str(txt))
                    if sec:
                        print(f"[!] possible secret in {label} for finding #{fid} ({len(sec)} hit(s)) — REFUSED.", file=sys.stderr)
                        sys.exit(2)

        validated_records.append({
            "id": fid,
            "project": proj,
            "importance": imp,
            "provenance": prov,
            "evidence": ev,
            "importance_evidence": imp_ev,
        })

    is_dry_run = getattr(args, "dry_run", False)
    # Dry run uses read-only connection to ensure zero writes/zero schema mutation on DB.
    # We avoid connect() on dry-run so an un-migrated DB is never mutated.
    if is_dry_run:
        con = sqlite3.connect(f"file:{findings_db.DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
    else:
        con = connect()
    cur = con.cursor()
    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    applied = 0
    skipped = 0

    try:
        # Pre-check all IDs existence in findings before any writes
        cols = {c[1] for c in cur.execute("PRAGMA table_info(findings)").fetchall()}
        for item in validated_records:
            fid = item["id"]
            row = cur.execute("SELECT 1 FROM findings WHERE id = ?", (fid,)).fetchone()
            if not row:
                raise ValueError(f"Finding #{fid} does not exist in findings database (aborted entire batch)")

        if not is_dry_run:
            cur.execute("BEGIN TRANSACTION")

        for item in validated_records:
            fid = item["id"]
            curr = cur.execute("SELECT * FROM findings WHERE id = ?", (fid,)).fetchone()
            curr_proj = (curr["project"] if "project" in cols else "unknown") or "unknown"
            curr_imp = (curr["importance"] if "importance" in cols else "unreviewed") or "unreviewed"
            # Idempotence: if already classified manually/customized (not unreviewed and not unknown) and not --force, skip
            is_unclassified = (curr_proj == "unknown" and curr_imp == "unreviewed")
            if not is_unclassified and not getattr(args, "force", False):
                skipped += 1
                continue

            if not is_dry_run:
                cur.execute("UPDATE findings SET project = ?, importance = ? WHERE id = ?",
                            (item["project"], item["importance"], fid))
                cur.execute("""
                    INSERT OR REPLACE INTO finding_classifications (
                        finding_id, project, project_provenance, project_evidence,
                        importance, importance_provenance, importance_evidence,
                        classified_at, classified_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (fid, item["project"], item["provenance"], item["evidence"],
                      item["importance"], item["provenance"], item["importance_evidence"],
                      now, "batch_classify"))
            applied += 1

        if is_dry_run:
            print(f"[dry-run] would classify {applied} findings (skipped {skipped} existing)")
        else:
            con.commit()
            print(f"[✓] successfully classified {applied} findings (skipped {skipped} existing)")
    except Exception as e:
        if not is_dry_run:
            con.rollback()
        print(f"[!] classification aborted and rolled back: {e}", file=sys.stderr)
        con.close()
        sys.exit(1)
    con.close()
