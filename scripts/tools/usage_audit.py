#!/usr/bin/env python3

"""Usage audit: memory-engine usage in Claude Code / omp session transcripts.

Answers "is the memory engine actually used in real work?" by reading:
- ~/.claude/projects/<project-slug>/<uuid>.jsonl  (Claude Code format:
  {type:user|assistant, message:{role, content: str | [{type:tool_use,...}]},
  cwd, timestamp});
- ~/.omp/agent/sessions/<project-slug>/*.jsonl  (omp format:
  {type:session|message|custom, message:{role, content items incl.
  {type:toolCall, name, arguments}}, custom customType:tool_execution_start
  data:{toolName, args}}).

Each file is one session. Sessions are segregated kit-internal vs real by
patterns: coding-kit / kit-eval / KODEKITTEST / CLAUDETESTS in the
directory slug or session cwd, or «код кит» in the session title / first
human turn. Per session we count:
- human_turns  — user turns that are not tool results / reminders;
- memory_calls — Bash (and omp bash tool) calls touching the memory engine
  (memory-warmup, search_all.py, findings.py, build.py, repomap,
  skills_search, doctor.py, check_file_sizes);
- skill_reads  — distinct skill://<name> reads;
- ops_markers  — distinct "Coding Agent OS" / "Execution Lock" /
  db-tools/search_all markers present anywhere in the transcript.

Run:
    python3 scripts/tools/usage_audit.py                  # human summary
    python3 scripts/tools/usage_audit.py --json           # machine output
    python3 scripts/tools/usage_audit.py --since 2026-08-01
    python3 scripts/tools/usage_audit.py --claude-root DIR --omp-root DIR
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

# stdlib-only: no scripts/_compat.py dependency (memory/ moved out of the kit)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: S110 — optional, lives without it
    pass

HOME = Path.home()
CLAUDE_ROOT = HOME / ".claude" / "projects"
OMP_ROOT = HOME / ".omp" / "agent" / "sessions"

# Kit-internal session markers: directory slug / cwd / title / first human
# turn, lowercased before matching.
KIT_PATTERNS = (
    "coding-kit", "coding_kit", "codingkit", "kit-eval", "kit_eval",
    "kodekittest", "claudetests", "код кит", "код-кит",
)

# Memory-engine tool calls: any Bash command mentioning a memory script.
MEMORY_RE = re.compile(
    r"memory-warmup|search_all\.py|findings\.py|build\.py|repomap"
    r"|skills_search|doctor\.py|check_file_sizes")

SKILL_READ_RE = re.compile(r"skill://([A-Za-z0-9_-]+)")
OPS_MARKER_RE = re.compile(r"Coding Agent OS|Execution Lock|db-tools/search_all")

# User lines that are not a human turn.
HUMAN_EXCLUDE_RE = re.compile(
    r"<system-reminder>|Caveat:|tool_result|command-name|local-command")


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
                continue
            except json.JSONDecodeError:
                pass
            try:  # tolerant retry (BOM, stray prefix)
                yield json.loads(line.lstrip("\ufeff"))
                continue
            except json.JSONDecodeError:
                continue


def _text_of(content) -> str:
    """Flatten a Claude/omp content value (str or block list) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if isinstance(b.get("text"), str):
                    parts.append(b["text"])
                elif b.get("type") == "thinking":
                    parts.append(b.get("thinking") or "")
                elif b.get("type") == "tool_result":
                    parts.append(json.dumps(b.get("content"),
                                            ensure_ascii=False))
                elif b.get("type") == "toolCall":
                    parts.append(json.dumps(b.get("arguments"),
                                            ensure_ascii=False))
        return "\n".join(parts)
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return ""


def _tool_blob(name, args) -> str:
    """One tool call rendered to searchable text (name + input)."""
    return f"{name} {json.dumps(args, ensure_ascii=False)}"


def _mtime_date(p: Path) -> date:
    return datetime.fromtimestamp(p.stat().st_mtime).date()


def _iter_jsonl_safe(path: Path):
    try:
        yield from _iter_jsonl(path)
    except OSError:
        return


def _kit(text) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(p in low for p in KIT_PATTERNS)


def _count_ops(text: str) -> int:
    """Distinct OPS markers present in the text (0..3)."""
    return len({m.lower() for m in OPS_MARKER_RE.findall(text or "")})


def audit_session(path: Path, source: str, since: date) -> dict | None:
    """Parse one transcript file into per-session counters.

    Returns None when the session is outside the --since window.
    """
    if _mtime_date(path) < since:
        return None
    human_turns = 0
    memory_calls = 0
    skill_reads = set()
    ops_seen = 0
    first_human = ""
    session_cwd = ""
    session_title = ""
    omp_call_ids = set()
    for d in _iter_jsonl_safe(path):
        typ = d.get("type")
        if typ == "session":  # omp header
            session_cwd = d.get("cwd") or session_cwd
            session_title = d.get("title") or session_title
        elif typ == "user":  # Claude Code
            if not session_cwd:
                session_cwd = d.get("cwd") or ""
            msg = d.get("message") or {}
            c = msg.get("content")
            if isinstance(c, list):
                continue  # tool result — not a human turn
            text = _text_of(c)
            if not text.strip() or HUMAN_EXCLUDE_RE.search(text):
                continue
            if not first_human:
                first_human = text[:300]
            human_turns += 1
        elif typ == "assistant":  # Claude Code tool_use blocks
            msg = d.get("message") or {}
            for b in msg.get("content") or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                blob = _tool_blob(b.get("name"), b.get("input"))
                if MEMORY_RE.search(blob):
                    memory_calls += 1
                for name in SKILL_READ_RE.findall(blob):
                    skill_reads.add(name)
            blob = json.dumps(msg, ensure_ascii=False)
            for name in SKILL_READ_RE.findall(blob):
                skill_reads.add(name)
        elif typ == "message":  # omp role messages
            msg = d.get("message") or {}
            role = msg.get("role")
            if role == "user":
                text = _text_of(msg.get("content"))
                if not text.strip() or HUMAN_EXCLUDE_RE.search(text):
                    continue
                if not first_human:
                    first_human = text[:300]
                human_turns += 1
            elif role == "assistant":
                for b in msg.get("content") or []:
                    if not isinstance(b, dict) or b.get("type") != "toolCall":
                        continue
                    cid = b.get("id")
                    if cid:
                        omp_call_ids.add(cid)
                    blob = _tool_blob(b.get("name"), b.get("arguments"))
                    if MEMORY_RE.search(blob):
                        memory_calls += 1
                    for name in SKILL_READ_RE.findall(blob):
                        skill_reads.add(name)
        elif typ == "custom" and d.get("customType") == "tool_execution_start":
            data = d.get("data") or {}
            cid = data.get("toolCallId")
            if cid and cid in omp_call_ids:
                continue  # same call already counted from the toolCall block
            blob = _tool_blob(data.get("toolName"), data.get("args"))
            if MEMORY_RE.search(blob):
                memory_calls += 1
            for name in SKILL_READ_RE.findall(blob):
                skill_reads.add(name)
        # scan every line for skill:// and OPS markers
        blob = json.dumps(d, ensure_ascii=False)
        ops_seen += _count_ops(blob)
        for name in SKILL_READ_RE.findall(blob):
            skill_reads.add(name)
    kit = (_kit(session_cwd) or _kit(session_title)
           or _kit(path.parent.name) or _kit(first_human))
    return {
        "source": source,
        "file": str(path),
        "project_slug": path.parent.name,
        "kit_internal": kit,
        "human_turns": human_turns,
        "memory_calls": memory_calls,
        "skill_reads": sorted(skill_reads),
        "ops_markers": ops_seen,
    }


def audit(claude_root: Path, omp_root: Path, since) -> dict:
    """Audit both transcript roots. since=None means no time filter."""
    since = since or date.min
    sessions = []
    for source, root in (("claude", claude_root), ("omp", omp_root)):
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*/*.jsonl")):
            res = audit_session(path, source, since)
            if res:
                sessions.append(res)
    aggregate = {}
    for label in ("kit_internal", "real"):
        subset = [s for s in sessions
                  if s["kit_internal"] == (label == "kit_internal")]
        aggregate[label] = {
            "sessions": len(subset),
            "human_turns": sum(s["human_turns"] for s in subset),
            "memory_calls": sum(s["memory_calls"] for s in subset),
            "skill_reads": len({n for s in subset for n in s["skill_reads"]}),
            "ops_markers": sum(s["ops_markers"] for s in subset),
        }
    return {"generated": datetime.now().isoformat(timespec="seconds"),
            "since": None if since == date.min else since.isoformat(),
            "roots": {"claude": str(claude_root), "omp": str(omp_root)},
            "sessions": sessions, "aggregate": aggregate}


def _human(res: dict) -> str:
    out = []
    since = res["since"] or "all time"
    out.append(f"usage audit (since {since})")
    for label, title in (("real", "REAL work sessions"),
                         ("kit_internal", "KIT-INTERNAL sessions")):
        a = res["aggregate"][label]
        out.append(f"{title}: {a['sessions']} sessions, "
                   f"{a['human_turns']} human turns, "
                   f"{a['memory_calls']} memory calls, "
                   f"{a['skill_reads']} skill:// reads, "
                   f"{a['ops_markers']} OPS markers")
    real = res["aggregate"]["real"]
    if real["sessions"]:
        out.append(f"real-session memory calls per session: "
                   f"{real['memory_calls'] / real['sessions']:.2f}")
    for s in res["sessions"]:
        tag = "kit" if s["kit_internal"] else "real"
        out.append(f"  [{tag}] {s['source']}: {s['project_slug']} — "
                   f"{s['human_turns']} turns, {s['memory_calls']} memory, "
                   f"{len(s['skill_reads'])} skills, {s['ops_markers']} ops")
    return "\n".join(out)


def retirement_report(res: dict, all_skills: list[str],
                      skills_root=None) -> dict:
    """Zero-use retirement proposal (wave3 Task 11): skills with 0
    firings across the audited REAL sessions (kit-internal sessions are
    excluded — their skill reads are evals/tests, not usage). Proposal
    only: never deletes; retirement is an owner decision (v3.4.6
    precedent: agent-ux removed after 0 real uses)."""
    skills_root = Path(skills_root) if skills_root else Path.home()
    fired: set[str] = set()
    for s in res["sessions"]:
        if s["kit_internal"]:
            # eval/test transcripts do not count as real usage
            continue
        fired.update(s["skill_reads"])
    if (skills_root / "skills").is_dir():
        installed = sorted(d.name for d in
                           (skills_root / "skills").iterdir()
                           if d.is_dir())
    else:
        installed = all_skills
    zero = sorted(s for s in installed if s not in fired)
    return {"since": res.get("since"),
            "action": "proposal-only",
            "sessions_audited": len(res["sessions"]),
            "skills_total": len(installed),
            "fired_count": len(fired),
            "count": len(zero),
            "zero_use": zero}


def retirement_report_human(report: dict) -> str:
    out = [(f"retirement proposal (since {report['since'] or 'all time'}, "
            f"{report['sessions_audited']} real sessions audited)"),
           (f"action: {report['action']} — owner decides, nothing is "
            "deleted"),
           (f"zero-use skills ({len(report['zero_use'])}/"
            f"{report['skills_total']}):")]
    out += [f"  - {s}" for s in report["zero_use"]] or ["  (none)"]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description="Audit memory-engine usage in Claude Code / omp "
                    "session transcripts")
    ap.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="only sessions modified since this date "
                         "(default: 14 days back)")
    ap.add_argument("--claude-root", default=None, metavar="DIR",
                    help="Claude Code transcripts root "
                         "(default: ~/.claude/projects)")
    ap.add_argument("--omp-root", default=None, metavar="DIR",
                    help="omp transcripts root "
                         "(default: ~/.omp/agent/sessions)")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON output")
    ap.add_argument("--retirement-report", action="store_true",
                    help="list skills with 0 firings in the audited "
                         "window (proposal only — nothing is deleted)")
    args = ap.parse_args()

    since = (date.fromisoformat(args.since) if args.since
             else date.today() - timedelta(days=14))
    res = audit(claude_root=Path(args.claude_root) if args.claude_root
                else CLAUDE_ROOT,
                omp_root=Path(args.omp_root) if args.omp_root else OMP_ROOT,
                since=since)
    if args.retirement_report:
        report = retirement_report(res, all_skills=[],
                                   skills_root=Path(
                                       __file__).resolve().parents[2])
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(retirement_report_human(report))
        sys.exit(0)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(_human(res))
    sys.exit(0)


if __name__ == "__main__":
    main()
