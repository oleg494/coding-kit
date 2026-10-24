"""Semantic findings presentation adapter; retrieval lives in search_all."""
import json
import sys


def _semantic_record(hit):
    meta = getattr(hit, "meta", None) or {}
    topic = meta.get("topic")
    if topic is None:
        label = hit[2] or ""
        topic = label.split(" ", 1)[1] if " " in label else label
    score = hit[0]
    return {"id": hit[4], "created": meta.get("created", ""), "topic": topic,
            "tags": meta.get("tags", ""), "source": meta.get("source", ""),
            "file": meta.get("file", ""),
            "score": round(float(score), 4) if score is not None else None,
            "superseded_by": meta.get("superseded_by"),
            "has_verify": bool(meta.get("verify_cmd")),
            "verified_at": meta.get("verified_at", "") or "",
            "project": meta.get("project") or "unknown",
            "importance": meta.get("importance") or "unreviewed",
            "snippet": hit[3]}


def cmd_search_semantic(args, mode, db, log_search):
    from search_all import SearchError, search_all
    try:
        hits = search_all(
            args.query, limit=args.limit, db_dir=None, research_db=db,
            project=getattr(args, "project", ""),
            importance=getattr(args, "importance", ""), mode=mode,
            findings_only=True, source=getattr(args, "source", ""),
            tag=getattr(args, "tag", ""),
            state=getattr(args, "state", "all") or "all",
            verification=getattr(args, "verification", "all") or "all",
            model_dir=getattr(args, "model_dir", None),
            index_path=getattr(args, "index_path", None))
    except SearchError as exc:
        print(f"findings search (--mode {mode}): {exc}", file=sys.stderr)
        sys.exit(1)
    records = [_semantic_record(hit) for hit in hits]
    log_search(args.query, len(records), db)
    if getattr(args, "json_mode", False):
        print(json.dumps(records, ensure_ascii=False))
        return
    source = getattr(args, "source", "")
    tag = getattr(args, "tag", "")
    if not records:
        print(f"not found for \"{args.query}\""
              + (f" (source ~ \"{source}\")" if source else "")
              + (f" (tag \"{tag}\")" if tag else ""))
        return
    print(f"found: {len(records)}, showing: {len(records)}\n")
    for rec in records:
        badge = (f"  ⚠ superseded by #{rec['superseded_by']}"
                 if rec["superseded_by"] else "")
        proj_badge = (f" [{rec['project']}]"
                      if rec["project"] and rec["project"] != "unknown" else "")
        print(f"[{rec['id']}] {rec['created']}  {rec['topic']}{proj_badge}  "
              f"({rec['tags']}){badge}")
        print(f"  …{rec['snippet']}")
        print()
