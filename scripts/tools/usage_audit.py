#!/usr/bin/env python3
"""usage_audit (v4.0.0): normalized-transcript usage audit.

Wave6 Task 20 rewired this tool onto eval/transcript_normalize.py: every
harness transcript (Claude Code JSONL, omp JSONL, Gemini chats, Hermes
state.db) is first normalized into the trajectory-v1 record shape, and
ALL audit logic consumes only that form. Per-harness parsing lives in
exactly one place (the normalizer readers).

Per session we count (same semantics as the v3 audit):
- human_turns  — user records that are not tool results / reminders;
- memory_calls — tool records whose name/arguments mention the memory
  engine (memory-warmup, search_all.py, findings.py, build.py, repomap,
  skills_search, doctor.py, check_file_sizes);
- skill_reads  — distinct skill://<name> mentions anywhere in records;
- ops_markers  — distinct "Coding Agent OS" / "Execution Lock" /
  db-tools/search_all markers present anywhere in the records.

Sessions are segregated kit-internal vs real by patterns: coding-kit /
kit-eval / KODEKITTEST / CLAUDETESTS in the directory slug or session
cwd, or «код кит» in the session title / first human turn.

Run:
    python scripts/tools/usage_audit.py                  # human summary
    python scripts/tools/usage_audit.py --json           # machine output
    python scripts/tools/usage_audit.py --since 2026-08-01
    python scripts/tools/usage_audit.py --retirement-report
"""
import argparse
import importlib.util
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001,S110 — optional console nicety
    pass

HOME = Path.home()
CLAUDE_ROOT = HOME / ".claude" / "projects"
OMP_ROOT = HOME / ".omp" / "agent" / "sessions"
GEMINI_ROOT = HOME / ".gemini" / "tmp"
HERMES_DB = HOME / "AppData" / "Local" / "hermes" / "state.db"

KIT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "transcript_normalize", KIT / "eval" / "transcript_normalize.py")
tn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tn)

KIT_PATTERNS = (
    "coding-kit", "coding_kit", "codingkit", "kit-eval", "kit_eval",
    "kodekittest", "claudetests", "код кит", "код-кит",
)

MEMORY_RE = re.compile(
    r"memory-warmup|search_all\.py|findings\.py|build\.py|repomap"
    r"|skills_search|doctor\.py|check_file_sizes")

SKILL_READ_RE = re.compile(r"skill://([A-Za-z0-9_-]+)")
OPS_MARKER_RE = re.compile(r"Coding Agent OS|Execution Lock|db-tools/search_all")
HUMAN_EXCLUDE_RE = re.compile(
    r"<system-reminder>|Caveat:|tool_result|command-name|local-command")


def _kit(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in KIT_PATTERNS)


def _mtime_date(p: Path) -> date:
    return datetime.fromtimestamp(p.stat().st_mtime).date()  # noqa: DTZ006


def _audit_records(records: list) -> dict:
    """Counters over normalized records (the ONLY place audit logic
    lives — no harness format knowledge here)."""
    human_turns = 0
    memory_calls = 0
    skill_reads: set[str] = set()
    ops_seen = 0
    first_human = ""
    for r in records:
        rtype = r.get("type")
        if rtype == "user":
            text = r.get("content") or ""
            if not text.strip() or HUMAN_EXCLUDE_RE.search(text):
                continue
            if not first_human:
                first_human = text[:300]
            human_turns += 1
        elif rtype == "tool":
            blob = f"{r.get('name') or ''} {r.get('arguments') or ''}"
            if MEMORY_RE.search(blob):
                memory_calls += 1
        blob = json.dumps(r, ensure_ascii=False)
        ops_seen += len(OPS_MARKER_RE.findall(blob))
        for name in SKILL_READ_RE.findall(blob):
            skill_reads.add(name)
    return {"human_turns": human_turns, "memory_calls": memory_calls,
            "skill_reads": skill_reads, "ops_markers": ops_seen,
            "first_human": first_human}


def _session_from_records(source: str, records: list, slug: str,
                          path_str: str) -> dict:
    meta = records[0] if records and records[0].get("type") == "meta" else {}
    counts = _audit_records(records)
    kit = (_kit(meta.get("cwd", "")) or _kit(slug)
           or _kit(counts["first_human"]))
    return {
        "source": source,
        "file": path_str,
        "project_slug": slug,
        "kit_internal": kit,
        "human_turns": counts["human_turns"],
        "memory_calls": counts["memory_calls"],
        "skill_reads": sorted(counts["skill_reads"]),
        "ops_markers": counts["ops_markers"],
    }


def audit(claude_root: Path, omp_root: Path, since,
          gemini_root: Path | None = None,
          hermes_db: Path | None = None) -> dict:
    """Audit all harness transcript stores via the normalizer."""
    since = since or date.min
    sessions: list[dict] = []

    def _want(path: Path) -> bool:
        return _mtime_date(path) >= since

    if omp_root and omp_root.is_dir():
        for path in sorted(omp_root.glob("*/*.jsonl")):
            if not _want(path):
                continue
            res = tn.normalize("omp", path)
            if res["records"]:
                sessions.append(_session_from_records(
                    "omp", res["records"], path.parent.name, str(path)))
    if claude_root and claude_root.is_dir():
        for path in sorted(claude_root.glob("*/*.jsonl")):
            if not _want(path):
                continue
            res = tn.normalize("claude", path)
            if res["records"]:
                sessions.append(_session_from_records(
                    "claude", res["records"], path.parent.name, str(path)))
    if gemini_root and gemini_root.is_dir():
        for path in sorted(gemini_root.glob("*/chats/*.json")):
            if not _want(path):
                continue
            res = tn.normalize("gemini", path)
            if res["records"]:
                sessions.append(_session_from_records(
                    "gemini", res["records"], path.parts[-3], str(path)))
    if hermes_db and hermes_db.is_file():
        try:
            con_dates = _hermes_session_dates(hermes_db, since)
        except Exception:  # noqa: BLE001 — hermes store is best-effort
            con_dates = {}
        for sid, mtime in con_dates.items():
            if mtime < since:
                continue
            try:
                res = tn.normalize("hermes", hermes_db, sid)
            except Exception:  # noqa: BLE001,S112 — best-effort hermes store
                continue
            if res["records"]:
                sessions.append(_session_from_records(
                    "hermes", res["records"], "hermes", str(hermes_db)))

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
    return {"generated": datetime.now().isoformat(  # noqa: DTZ005
        timespec="seconds"),
            "since": None if since == date.min else since.isoformat(),
            "roots": {"claude": str(claude_root), "omp": str(omp_root)},
            "sessions": sessions, "aggregate": aggregate}


def _hermes_session_dates(db: Path, since: date) -> dict:
    import sqlite3
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT id, started_at FROM sessions").fetchall()
    finally:
        con.close()
    out: dict[str, date] = {}
    for sid, started in rows:
        try:
            d = datetime.fromtimestamp(  # noqa: DTZ006
                float(started)).date()
        except (TypeError, ValueError, OSError):
            continue
        out[str(sid)] = d
    return out


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
        description="Audit memory-engine usage in normalized session "
                    "transcripts (claude/omp/gemini/hermes)")
    ap.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="only sessions modified since this date "
                         "(default: 14 days back)")
    ap.add_argument("--claude-root", default=None, metavar="DIR",
                    help="Claude Code transcripts root "
                         "(default: ~/.claude/projects)")
    ap.add_argument("--omp-root", default=None, metavar="DIR",
                    help="omp transcripts root "
                         "(default: ~/.omp/agent/sessions)")
    ap.add_argument("--no-gemini", action="store_true",
                    help="skip the Gemini CLI chats store")
    ap.add_argument("--no-hermes", action="store_true",
                    help="skip the Hermes state.db store")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON output")
    ap.add_argument("--retirement-report", action="store_true",
                    help="list skills with 0 firings in the audited "
                         "window (proposal only — nothing is deleted)")
    args = ap.parse_args()

    since = (date.fromisoformat(args.since) if args.since
             else date.today() - timedelta(days=14))  # noqa: DTZ011
    res = audit(claude_root=Path(args.claude_root) if args.claude_root
                else CLAUDE_ROOT,
                omp_root=Path(args.omp_root) if args.omp_root else OMP_ROOT,
                since=since,
                gemini_root=None if args.no_gemini else GEMINI_ROOT,
                hermes_db=None if args.no_hermes else HERMES_DB)
    if args.retirement_report:
        report = retirement_report(res, all_skills=[],
                                   skills_root=KIT)
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
