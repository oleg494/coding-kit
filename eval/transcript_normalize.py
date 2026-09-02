#!/usr/bin/env python3
"""transcript_normalize.py — one normalized record schema for all harnesses.

Each harness writes transcripts in its own shape (OMP JSONL, Claude Code
JSONL, Gemini single-JSON chats, Hermes SQLite). This module reads any of
them and emits the Letta trajectory-v1 record shape: a flat array of
meta/user/system/reasoning/assistant/tool records, tool results linked by
tool_call_id, the meta record carrying source/cwd/model. Downstream
consumers (usage_audit) see ONE format.

Records (trajectory-v1, adapted):
  {"type":"meta", "source":..., "session_id":..., "cwd":..., "model":...,
   "timestamp": ISO-8601 or ""}
  {"type":"user", "content": str, "timestamp": ...}
  {"type":"system", "content": str, "timestamp": ...}
  {"type":"assistant", "content": str, "timestamp": ...}
  {"type":"reasoning", "content": str, "timestamp": ...}
  {"type":"tool", "tool_call_id":..., "name":..., "arguments": str|None,
   "result": str|None, "timestamp": ...}

Usage:
    python eval/transcript_normalize.py --source omp PATH
    python eval/transcript_normalize.py --source gemini PATH
    python eval/transcript_normalize.py --source hermes PATH   (state.db; PATH may be "-" for default)
    python eval/transcript_normalize.py --source claude PATH
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

HERMES_DEFAULT_DB = Path.home() / "AppData" / "Local" / "hermes" / "state.db"


def _records(source: str) -> list:
    out: list[dict] = []
    out.append({"type": "meta", "source": source, "session_id": "",
                "cwd": "", "model": "", "timestamp": ""})
    return out


def normalize_omp(path: Path) -> dict:
    """OMP session JSONL: {type:session|message|custom, message:{role,
    content items incl. {type:toolCall,...}}, custom tool_execution_*."""
    records: list[dict] = [{"type": "meta", "source": "omp",
                            "session_id": path.stem, "cwd": "", "model": "",
                            "timestamp": ""}]
    diagnostics: list[str] = []
    pending_tools: dict[str, dict] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                diagnostics.append(f"line {i}: bad json skipped")
                continue
            if not isinstance(d, dict):
                diagnostics.append(f"line {i}: non-object skipped")
                continue
            typ = d.get("type")
            if typ == "session":
                records[0]["cwd"] = d.get("cwd") or records[0]["cwd"]
                sid = d.get("id") or d.get("sessionId") or d.get("session_id")
                if sid:
                    records[0]["session_id"] = str(sid)
            elif typ == "message":
                msg = d.get("message") or {}
                role = msg.get("role")
                ts = d.get("timestamp") or msg.get("timestamp") or ""
                content = msg.get("content")
                texts = []
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "toolCall":
                            cid = str(b.get("id") or "")
                            rec = {"type": "tool", "tool_call_id": cid,
                                   "name": str(b.get("name") or ""),
                                   "arguments": json.dumps(
                                       b.get("arguments") or {},
                                       ensure_ascii=False),
                                   "result": None, "timestamp": ts}
                            records.append(rec)
                            if cid:
                                pending_tools[cid] = rec
                        elif b.get("type") == "text" or "text" in b:
                            texts.append(str(b.get("text") or ""))
                text = "\n".join(t for t in texts if t)
                if role in ("user", "assistant", "system") and text:
                    records.append({"type": role, "content": text,
                                    "timestamp": ts})
            elif typ == "custom":
                ct = d.get("customType") or ""
                data = d.get("data") or {}
                if ct == "tool_execution_start":
                    cid = str(data.get("toolCallId") or "")
                    rec = pending_tools.get(cid)
                    if rec is not None:
                        rec["name"] = rec["name"] or str(
                            data.get("toolName") or "")
                    else:
                        records.append({
                            "type": "tool", "tool_call_id": cid,
                            "name": str(data.get("toolName") or ""),
                            "arguments": json.dumps(data.get("args") or {},
                                                    ensure_ascii=False),
                            "result": None,
                            "timestamp": data.get("timestamp") or ""})
                elif ct in ("tool_execution_end", "tool_execution_result"):
                    cid = str(data.get("toolCallId") or "")
                    rec = pending_tools.get(cid)
                    result = data.get("result") or data.get("output") or ""
                    if rec is not None and rec["result"] is None:
                        rec["result"] = str(result)[:4000]
    return {"records": records, "diagnostics": diagnostics}


def normalize_claude(path: Path) -> dict:
    """Claude Code JSONL: {type:user|assistant, message:{role, content:
    str | [{type:tool_use|tool_result|text,...}]}, cwd, timestamp}."""
    records: list[dict] = [{"type": "meta", "source": "claude",
                            "session_id": path.stem, "cwd": "", "model": "",
                            "timestamp": ""}]
    diagnostics: list[str] = []
    pending: dict[str, dict] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                diagnostics.append(f"line {i}: bad json skipped")
                continue
            if not isinstance(d, dict):
                continue
            typ = d.get("type")
            ts = d.get("timestamp") or ""
            if d.get("cwd") and not records[0]["cwd"]:
                records[0]["cwd"] = d["cwd"]
            msg = d.get("message") or {}
            if typ in ("user", "assistant"):
                if msg.get("model") and not records[0]["model"]:
                    records[0]["model"] = str(msg["model"])
                content = msg.get("content")
                if isinstance(content, str):
                    records.append({"type": typ, "content": content,
                                    "timestamp": ts})
                    continue
                if isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        bt = b.get("type")
                        if bt == "text":
                            records.append({"type": typ,
                                            "content": str(b.get("text") or ""),
                                            "timestamp": ts})
                        elif bt == "tool_use":
                            cid = str(b.get("id") or "")
                            rec = {"type": "tool", "tool_call_id": cid,
                                   "name": str(b.get("name") or ""),
                                   "arguments": json.dumps(
                                       b.get("input") or {},
                                       ensure_ascii=False),
                                   "result": None, "timestamp": ts}
                            records.append(rec)
                            if cid:
                                pending[cid] = rec
                        elif bt == "tool_result":
                            cid = str(b.get("tool_use_id") or "")
                            rec = pending.get(cid)
                            c = b.get("content")
                            text = c if isinstance(c, str) else json.dumps(
                                c, ensure_ascii=False)[:4000]
                            if rec is not None and rec["result"] is None:
                                rec["result"] = text
    return {"records": records, "diagnostics": diagnostics}


def normalize_gemini(path: Path) -> dict:
    """Gemini CLI chat: single JSON {sessionId, projectHash, startTime,
    messages: [{id, timestamp, type, content, tokens, model}]}."""
    diagnostics: list[str] = []
    try:
        d = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"records": [], "diagnostics": [f"unreadable: {exc}"]}
    if not isinstance(d, dict) or not isinstance(d.get("messages"), list):
        return {"records": [], "diagnostics": ["not a gemini chat object"]}
    records: list[dict] = [{"type": "meta", "source": "gemini",
                            "session_id": str(d.get("sessionId") or path.stem),
                            "cwd": "", "model": "",
                            "timestamp": str(d.get("startTime") or "")}]
    for m in d["messages"]:
        if not isinstance(m, dict):
            continue
        mtype = str(m.get("type") or "")
        text = str(m.get("content") or "")
        ts = str(m.get("timestamp") or "")
        if m.get("model") and not records[0]["model"]:
            records[0]["model"] = str(m["model"])
        if mtype in ("user", "gemini", "assistant"):
            rtype = "assistant" if mtype != "user" else "user"
            if text:
                records.append({"type": rtype, "content": text,
                                "timestamp": ts})
        elif mtype == "system" and text:
            records.append({"type": "system", "content": text,
                            "timestamp": ts})
        # tool traffic in gemini chats rides other type values; keep them
        # as diagnostics rather than guessing shapes
        elif mtype not in ("user", "gemini", "assistant", "system"):
            diagnostics.append(f"message type {mtype!r} kept as-is omitted")
    return {"records": records, "diagnostics": diagnostics}


def normalize_hermes(db_path: Path | None = None,
                     session_id: str | None = None) -> dict:
    """Hermes state.db: sessions + messages tables (role/content/
    tool_call_id/tool_calls/timestamp epoch-float)."""
    db = db_path or HERMES_DEFAULT_DB
    diagnostics: list[str] = []
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        if session_id is None:
            row = con.execute(
                "SELECT id, cwd, model, started_at FROM sessions"
                " ORDER BY started_at DESC LIMIT 1").fetchone()
        else:
            row = con.execute(
                "SELECT id, cwd, model, started_at FROM sessions"
                " WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return {"records": [],
                    "diagnostics": ["no sessions in db"]}
        sid, cwd, model, started = row
        import datetime as _dt
        try:
            ts0 = _dt.datetime.fromtimestamp(  # noqa: DTZ006
                float(started)).isoformat(timespec="seconds")
        except (TypeError, ValueError, OSError):
            ts0 = ""
        records: list[dict] = [{"type": "meta", "source": "hermes",
                                "session_id": str(sid),
                                "cwd": cwd or "", "model": model or "",
                                "timestamp": ts0}]
        q = ("SELECT role, content, tool_call_id, tool_calls, tool_name,"
             " timestamp FROM messages WHERE session_id = ?"
             " ORDER BY id")
        tools_by_id: dict = {}
        events: list = []
        for role, content, tool_call_id, tool_calls, tool_name, ts in \
                con.execute(q, (sid,)):
            try:
                iso = _dt.datetime.fromtimestamp(  # noqa: DTZ006
                    float(ts)).isoformat(timespec="seconds")
            except (TypeError, ValueError, OSError):
                iso = ""
            if role == "tool":
                events.append({"role": role, "content": content,
                               "tool_call_id": str(tool_call_id or ""),
                               "tool_name": str(tool_name or ""),
                               "timestamp": iso})
                continue
            if tool_calls:
                # assistant tool_calls blob: [{id, function:{name,args}}]
                try:
                    calls = json.loads(tool_calls)
                except (json.JSONDecodeError, TypeError):
                    calls = []
                for c in calls if isinstance(calls, list) else []:
                    cid = str(c.get("id") or "")
                    fn = (c.get("function") or {})
                    tools_by_id[cid] = {
                        "type": "tool", "tool_call_id": cid,
                        "name": str(fn.get("name") or tool_name or ""),
                        "arguments": json.dumps(fn.get("arguments") or {},
                                                ensure_ascii=False),
                        "result": None, "timestamp": iso}
            if role in ("user", "assistant", "system") and content:
                events.append({"role": role, "content": str(content),
                               "timestamp": iso})
        # attach results to their calls; one record per tool_call_id
        for ev in events:
            if ev["role"] == "tool":
                t = tools_by_id.get(ev["tool_call_id"])
                if t is not None:
                    t["result"] = str(ev["content"])[:4000]
                    continue
                tools_by_id[ev["tool_call_id"]] = {
                    "type": "tool", "tool_call_id": ev["tool_call_id"],
                    "name": ev["tool_name"], "arguments": None,
                    "result": str(ev["content"])[:4000],
                    "timestamp": ev["timestamp"]}
        records.extend(tools_by_id.values())
        for ev in events:
            if ev["role"] != "tool":
                records.append({"type": ev["role"],
                                "content": ev["content"],
                                "timestamp": ev["timestamp"]})
    finally:
        con.close()
    return {"records": records, "diagnostics": diagnostics}


def normalize(source: str, path: Path | None,
              session_id: str | None = None) -> dict:
    """Dispatch on source name -> normalized record set."""
    source = source.lower()
    if source == "omp":
        return normalize_omp(Path(path))
    if source == "claude":
        return normalize_claude(Path(path))
    if source == "gemini":
        return normalize_gemini(Path(path))
    if source == "hermes":
        return normalize_hermes(Path(path) if path else None, session_id)
    raise ValueError(f"unknown source: {source!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True,
                    choices=["omp", "claude", "gemini", "hermes"])
    ap.add_argument("path", nargs="?", default=None,
                    help="transcript file ('-' or omit for hermes default db)")
    ap.add_argument("--session-id", default=None,
                    help="hermes: pick a session by id (default: newest)")
    ap.add_argument("--json", action="store_true", help="machine output")
    args = ap.parse_args(argv)
    path = None if args.path in (None, "-") else Path(args.path)
    res = normalize(args.source, path, args.session_id)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        n = len(res["records"])
        print(f"{args.source}: {n} records, "
              f"{len(res['diagnostics'])} diagnostics")
        for d in res["diagnostics"][:10]:
            print(f"  ! {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
