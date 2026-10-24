"""Read-only document inventory and lifecycle selection for retrieval/indexing."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def connect_ro(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def selected(record, project="", importance="", state="all", verification="all", source="", tag=""):
    if project and record["project"] != project:
        return False
    if importance and record.get("importance") != importance:
        return False
    if state != "all" and record["kind"] != "finding":
        return False
    if state == "current" and record.get("superseded"):
        return False
    if state == "superseded" and not record.get("superseded"):
        return False
    if verification != "all" and record["kind"] != "finding":
        return False
    if verification == "verified" and not record.get("verified_at"):
        return False
    if verification == "unverified" and record.get("verified_at"):
        return False
    if source and source not in (record.get("source") or ""):
        return False
    if tag and tag not in (record.get("tags") or "").split():
        return False
    return True


def findings(path):
    path = Path(path)
    if not path.is_file():
        return []
    with closing(connect_ro(path)) as con:
        con.row_factory = sqlite3.Row
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        replacements = {}
        if "links" in names:
            replacements = dict(con.execute("SELECT to_id, MIN(from_id) FROM links WHERE kind='supersedes' GROUP BY to_id"))
        records = []
        for row in con.execute("SELECT * FROM findings ORDER BY id"):
            row = dict(row)
            fid = row["id"]
            row.update(key=f"finding:{fid}", kind="finding", finding_id=fid,
                       project=row.get("project") or "unknown",
                       importance=row.get("importance") or "unreviewed",
                       superseded_by=replacements.get(fid))
            row["verified"] = bool(row.get("verified_at"))
            row["superseded"] = bool(row["superseded_by"] or "[superseded:" in row["text"])
            row["db"] = "research" if row["project"] == "unknown" else f"research:{row['project']}"
            row["path"] = f"finding#{fid} {row['topic']}"
            row["embedding_text"] = row["topic"] + "\n" + row["text"]
            records.append(row)
        return records


def inventory(db_dir, research_db, findings_only=False, project="", importance="", state="all", verification="all", source="", tag=""):
    """Return documents, failures, number of searchable stores; never repair."""
    records, errors, attempted = [], [], 0
    finding_scope = findings_only or importance or state != "all" or verification != "all" or source or tag
    if not finding_scope:
        for path in sorted(Path(db_dir).glob("*.db")):
            if project and path.stem != project:
                continue
            try:
                with closing(connect_ro(path)) as con:
                    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not {"files_fts", "files_fts_trigram"} & names:
                        continue
                    attempted += 1
                    for rel, content in con.execute("SELECT rel_path, content FROM files ORDER BY rel_path"):
                        records.append(dict(key=f"file:{path.stem}:{rel}", kind="file", db=path.stem,
                                            path=rel, text=content or "", project=path.stem,
                                            finding_id=None, embedding_text=f"{rel}\n{content or ''}"))
            except sqlite3.Error as exc:
                errors.append(f"{path.name}: {exc}")
    if Path(research_db).is_file():
        attempted += 1
        try:
            records += findings(research_db)
        except sqlite3.Error as exc:
            errors.append(f"{Path(research_db).name}: {exc}")
    filters = dict(project=project, importance=importance, state=state,
                   verification=verification, source=source, tag=tag)
    return [r for r in records if selected(r, **filters)], errors, attempted


def content_digest(record):
    # Include lifecycle and scope fields so stale indexes cannot resurrect deleted corrections.
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
