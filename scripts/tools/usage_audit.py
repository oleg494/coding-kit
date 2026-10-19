#!/usr/bin/env python3
"""usage_audit (v4.2.1): normalized-transcript usage audit.

Wave6 Task 20 rewired this tool onto eval/transcript_normalize.py: every
harness transcript (Claude Code JSONL, omp JSONL, Gemini chats, Hermes
state.db) is first normalized into the trajectory-v1 record shape, and
ALL audit logic consumes only that form. Per-harness parsing lives in
exactly one place (the normalizer readers).

Per session we count:
- human_turns  — user records that are not tool results / reminders;
- memory_calls — shell-tool command executable entries matching explicit
  memory-engine entrypoints (memory-warmup, search_all.py, findings.py,
  repomap, build-memory), plus build.py only with a memory path marker
  on the same command line. Reads of those files, echo/grep strings and
  prompt/prose fields are NOT executions and do not count;
- kit_diag_calls — shell-tool entries invoking kit diagnostic/maintenance
  commands (doctor.py, check_file_sizes), reported separately;
- skill_search_calls — shell-tool entries invoking skills_search.py —
  kit skill discovery, not memory-engine usage;
- skill_reads  — distinct skills targeted by explicit read-tool calls on
  any payload file (SKILL.md, references, evals, assets) under the skill;
- ops_markers  — distinct "Coding Agent OS" / "Execution Lock" /
  db-tools/search_all markers present anywhere in the records.

Skill reads measure requests, not successful loads or applied guidance. Shell/eval
reads and harness-native skill loaders are not inferred from free text.
Memory/kit-diag/skills_search attribution parses recognized shell tool
records into command executable entries (a runner such as python plus the
script it runs, or a directly invoked script), walking parallel tool
wrappers recursively with their decoded arguments; non-shell tools and
prose fields never count. Distinctive entrypoint basenames stay counted
wherever executed — same-named scripts in unrelated projects included
(lexical ambiguity, see MEMORY_CALLS_NOTE). Historical totals from before
this attribution fix are not comparable.

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

try:
    from . import kit_inventory
except (ImportError, ValueError):
    try:
        import kit_inventory
    except ImportError:
        import importlib.util as _ilu
        _ki_spec = _ilu.spec_from_file_location(
            "kit_inventory",
            Path(__file__).resolve().parent / "kit_inventory.py")
        kit_inventory = _ilu.module_from_spec(_ki_spec)
        _ki_spec.loader.exec_module(kit_inventory)
tn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tn)

KIT_PATTERNS = (
    "coding-kit", "coding_kit", "codingkit", "kit-eval", "kit_eval",
    "kodekittest", "claudetests", "код кит", "код-кит",
)

# Command-entry attribution (2026-10-20 corrections, v4.2.1): memory_calls
# counts command ENTRIES parsed from recognized shell tool calls, not
# substring hits anywhere in the record. A read of findings.py or an echo
# string mentioning search_all.py is not an execution. Command strings are
# tokenized with a quote-aware scanner and split into commands only at
# unquoted newline/;/&&/|| (a quoted payload never splits mid-quote);
# bash/sh/pwsh -c inner scripts are parsed recursively; `uv run` resolves
# to the executed script (`uv run python x.py` -> x.py). skills_search.py
# is kit skill discovery (separate counter), not memory. Distinctive
# entrypoint basenames stay counted wherever executed (lexical ambiguity,
# see MEMORY_CALLS_NOTE); generic build.py needs a memory path marker.
MEMORY_ENTRY_RE = re.compile(
    r"memory-warmup\.py|search_all\.py|findings\.py|repomap"
    r"|build-memory")
BUILD_ENTRY_RE = re.compile(r"build\.py")
MEMORY_MARKER_RE = re.compile(r"\.memory\b|db-tools|memory[/\\]")
SKILL_SEARCH_ENTRY_RE = re.compile(r"skills_search\.py")
# Kit diagnostic/maintenance commands, reported separately so
# historical memory_calls consumers see no inflation.
KIT_DIAG_RE = re.compile(r"doctor\.py|check_file_sizes")
SHELL_TOOL_RE = re.compile(r"(?i)^(?:[^./]*[./])?(bash|sh|zsh|shell|"
                           r"terminal|execute_?command|run_command)$")
MEMORY_CALLS_NOTE = (
    "memory_calls counts command entries parsed from recognized shell "
    "tool calls (runner + script, or a directly invoked script) that "
    "match explicit memory-engine entrypoints, plus build.py only with "
    "a memory path marker. Command strings are split into commands only "
    "at unquoted separators, so quoted payloads (bash -c \"a; b\") are "
    "parsed as the inner script; uv run resolves to the executed script. "
    "Reads of those files, echo strings, prompt and prose fields are not "
    "executions. Distinctive entrypoint basenames (memory-warmup, "
    "search_all.py, findings.py, repomap, build-memory) stay counted even "
    "when an unrelated project ships a same-named script — lexical "
    "ambiguity, mitigated only for generic build.py via the marker rule. "
    "Counts from before this attribution fix are not directly comparable.")

SKILL_URI_RE = re.compile(r"skill://([A-Za-z0-9_-]+)(?:/[^?#]*)?(?:[:?#].*)?$")
SKILL_PATH_RE = re.compile(
    r"(?:^|/)skills/([A-Za-z0-9_-]+)/(?!skills\b)[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*(?:[:?#].*)?$")
SKILL_READ_NOTE = (
    "Skill reads are explicit read-tool requests, not successful loads or "
    "proof of use. Shell/eval reads, native skill loaders and omitted tool "
    "traffic are not measured; zero observed reads alone do not justify retirement."
)
OPS_MARKER_RE = re.compile(r"Coding Agent OS|Execution Lock|db-tools/search_all")
HUMAN_EXCLUDE_RE = re.compile(
    r"<system-reminder>|Caveat:|tool_result|command-name|local-command")


def _kit(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in KIT_PATTERNS)


def _mtime_date(p: Path) -> date:
    return datetime.fromtimestamp(p.stat().st_mtime).date()  # noqa: DTZ006


def _skill_read_targets(name: str, arguments) -> set[str]:
    # Hermes may wrap an already serialized function-arguments object.
    for _ in range(2):
        if not isinstance(arguments, str):
            break
        try:
            arguments = json.loads(arguments)
        except (ValueError, TypeError):
            return set()
    if not isinstance(arguments, dict):
        return set()
    if name == "multi_tool_use.parallel":
        calls = arguments.get("tool_uses")
        found: set[str] = set()
        for call in calls if isinstance(calls, list) else []:
            if isinstance(call, dict):
                found.update(_skill_read_targets(
                    call.get("recipient_name", ""), call.get("parameters")))
        return found
    if name not in ("read", "Read", "read_file", "functions.read"):
        return set()
    for key in ("path", "file_path", "absolute_path"):
        target = arguments.get(key)
        if isinstance(target, str):
            target = target.replace("\\", "/")
            match = SKILL_URI_RE.fullmatch(target) or SKILL_PATH_RE.search(target)
            if match:
                return {match[1]}
    return set()


RUNNER_RE = re.compile(r"(?i)^(?:python|python3|py|uv|uvx|pip|pip3"
                       r"|pythonw)(?:[.]exe)?$")
_CMD_VALUE_RE = re.compile(
    r"""(?xi)
    "(?:[^"\\]|\\.)*"         # double-quoted
  | '(?:[^'\\]|\\.)*'         # single-quoted
  | [^\s;&|]+                 # bare token
""")


def _decode_arguments(arguments) -> dict | list | None:
    """Decoded arguments: dict/list already, JSON string unwrapped (up to
    twice for double-wrapped serialization); anything else -> None."""
    for _ in range(2):
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (ValueError, TypeError):
                return None
        else:
            break
    return arguments if isinstance(arguments, (dict, list)) else None


def _shell_tool_name(name: str) -> bool:
    """Recognized shell tool: bare name or a namespaced recipient like
    functions.bash / tools.ExecuteCommand."""
    base = (name or "").rsplit(".", 1)[-1].strip()
    return bool(SHELL_TOOL_RE.fullmatch(base))


def _command_fields(arguments) -> list[str]:
    """Every string that can carry a command line from a decoded
    shell-tool arguments object (union: command fields, args lists,
    standalone strings). Fields like `i`, `prompt` and prose payloads
    never reach the parser."""
    if isinstance(arguments, str):
        return [arguments]
    if isinstance(arguments, dict):
        out: list[str] = []
        for key, val in arguments.items():
            if isinstance(val, str) and key.lower() in (
                    "command", "cmd", "script", "inline_script"):
                out.append(val)
            elif isinstance(val, list):
                for v in val:
                    if isinstance(v, str):
                        out.append(v)
        return out
    if isinstance(arguments, list):
        return [v for v in arguments if isinstance(v, str)]
    return []


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1].replace('\\"', '"').replace("\\'", "'")
    return token


_SHELL_RUNNER_RE = re.compile(r"(?i)^(?:cmd|powershell|pwsh|bash|sh|"
                              r"zsh)(?:[.]exe)?$")


def _split_commands(text: str) -> list[str]:
    """Command segments: text split on unquoted newline, `;`, `&&`, `||`
    only. Content inside quotes never splits (bash -c "a; b" stays one
    segment, so its quoted payload reaches the -c handler intact)."""
    segments: list[str] = []
    current: list[str] = []
    quote = ""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < n:
                current.extend((ch, text[i + 1]))
                i += 2
                continue
            if ch == quote:
                quote = ""
            current.append(ch)
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch == "&" and text[i + 1:i + 2] == "&":
            segments.append("".join(current))
            current = []
            i += 2
            continue
        if ch == "|" and text[i + 1:i + 2] == "|":
            segments.append("".join(current))
            current = []
            i += 2
            continue
        if ch in ("\n", ";"):
            segments.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    segments.append("".join(current))
    return [s for s in (seg.strip() for seg in segments) if s]


def _is_quoted(token: str) -> bool:
    return len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'"


def _entries_from_command(text: str) -> list[tuple[str, str]]:
    """(executable, context) pairs from one shell command string, split
    on unquoted newlines, `;`, `&&` and `||` so multi-command lines
    contribute each executable. Only tokens in command position (first
    token, or the script following a python-family runner) are kept.
    `bash -c "script"` / `sh -c` / `pwsh -c` parse the quoted inner
    script recursively. `uv run <script>` (and `uv run python
    <script>`) resolves to the actually executed script. Context is the
    command segment plus markers carried by a preceding `cd <dir>` (so
    `cd db-tools && python build.py` keeps the marker), never unrelated
    echo strings."""
    entries: list[tuple[str, str]] = []
    cd_marks: list[str] = []
    for chunk in _split_commands(text or ""):
        if chunk.startswith("#"):
            continue
        raw = _CMD_VALUE_RE.findall(chunk)
        toks = [t for t in (_unquote(r) for r in raw) if t.strip()]
        if not toks:
            continue
        first = toks[0].strip()
        context = " ".join(cd_marks + [chunk])
        if first == "cd":
            if len(toks) > 1 and MEMORY_MARKER_RE.search(toks[1]):
                cd_marks = [toks[1]]
            continue
        if RUNNER_RE.fullmatch(first) and len(toks) > 1:
            script_index = 1
            if first.lower() in ("uv", "uvx") and toks[1] == "run":
                # uv run <script> / uv run python <script>: the script is
                # what actually executes, not the `run` subcommand. Skip
                # run-flags and a nested runner to find it.
                for j in range(2, len(toks)):
                    tok = toks[j].strip()
                    if tok.startswith("-") or RUNNER_RE.fullmatch(tok):
                        continue
                    script_index = j
                    break
                else:
                    script_index = len(toks)
            if script_index < len(toks):
                script = toks[script_index].strip()
                if script and script not in ("-c", "-m"):
                    entries.append((script, context))
        elif _SHELL_RUNNER_RE.fullmatch(first) and len(toks) > 2 and \
                toks[1].lower() in ("-c", "-lc", "-ic") and toks[2].strip():
            # bash -c "findings.py add x; echo done": the quoted inner
            # script is what executes — parse it recursively (quote-aware
            # splitting keeps it out of the outer command stream).
            if _is_quoted(raw[2] if len(raw) > 2 else ""):
                entries.extend(_entries_from_command(toks[2]))
            else:
                entries.append((toks[2].strip(), context))
        else:
            entries.append((first, context))
    return entries

def _entry_is_memory(executable: str, command_line: str) -> bool:
    """memory-engine command entry: distinctive entrypoint basename
    (wherever it lives), or build.py with a memory path marker on the
    same command line."""
    if MEMORY_ENTRY_RE.search(executable):
        return True
    if BUILD_ENTRY_RE.search(executable):
        return bool(MEMORY_MARKER_RE.search(command_line))
    return False


def _entry_is_kit_diag(executable: str) -> bool:
    return bool(KIT_DIAG_RE.search(executable))


def _entry_is_skill_search(executable: str) -> bool:
    return bool(SKILL_SEARCH_ENTRY_RE.search(executable))


def _classify_tool_calls(name, arguments, counters: dict) -> None:
    """Recursively classify a tool call (following parallel wrappers to
    any depth) into memory / kit-diag / skills_search command counters."""
    if _shell_tool_name(name):
        decoded = _decode_arguments(arguments)
        commands = (_command_fields(decoded) if decoded is not None
                    else ([arguments] if isinstance(arguments, str) else []))
        for command in commands:
            for executable, command_line in _entries_from_command(command):
                if _entry_is_memory(executable, command_line):
                    counters["memory_calls"] += 1
                elif _entry_is_kit_diag(executable):
                    counters["kit_diag_calls"] += 1
                elif _entry_is_skill_search(executable):
                    counters["skill_search_calls"] += 1
        return
    decoded = _decode_arguments(arguments)
    if isinstance(decoded, dict) and isinstance(
            decoded.get("tool_uses"), list):
        for call in decoded["tool_uses"]:
            if isinstance(call, dict):
                _classify_tool_calls(call.get("recipient_name", ""),
                                     call.get("parameters"), counters)
        return
    # plain wrappers: a non-shell tool whose arguments carry a recognized
    # nested tool call ({"name"|"tool_name":..., "arguments":...})
    if isinstance(decoded, dict) and isinstance(
            decoded.get("arguments"), (dict, list, str)):
        inner_name = decoded.get("name") or decoded.get("tool_name") or ""
        if isinstance(inner_name, str) and inner_name:
            _classify_tool_calls(inner_name, decoded["arguments"], counters)
            return
    if isinstance(decoded, list):
        for item in decoded:
            if isinstance(item, dict):
                _classify_tool_calls(
                    item.get("name") or item.get("tool_name")
                    or item.get("recipient_name") or "",
                    item.get("arguments") or item.get("parameters")
                    or item.get("args"), counters)


def _audit_records(records: list) -> dict:
    """Counters over normalized records (the ONLY place audit logic
    lives — no harness format knowledge here)."""
    counters = {"memory_calls": 0, "kit_diag_calls": 0,
                "skill_search_calls": 0}
    skill_reads: set[str] = set()
    ops_seen = 0
    human_turns = 0
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
            _classify_tool_calls(r.get("name"), r.get("arguments"),
                                 counters)
            skill_reads.update(_skill_read_targets(
                r.get("name"), r.get("arguments")))
        blob = json.dumps(r, ensure_ascii=False)
        ops_seen += len(OPS_MARKER_RE.findall(blob))
    return {"human_turns": human_turns,
            **counters,
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
        "kit_diag_calls": counts["kit_diag_calls"],
        "skill_search_calls": counts["skill_search_calls"],
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
            "kit_diag_calls": sum(s["kit_diag_calls"] for s in subset),
            "skill_search_calls": sum(
                s.get("skill_search_calls", 0) for s in subset),
            "skill_reads": len({n for s in subset for n in s["skill_reads"]}),
            "ops_markers": sum(s["ops_markers"] for s in subset),
        }
    return {"generated": datetime.now().isoformat(  # noqa: DTZ005
        timespec="seconds"),
            "since": None if since == date.min else since.isoformat(),
            "roots": {"claude": str(claude_root), "omp": str(omp_root)},
            "sessions": sessions, "aggregate": aggregate,
            "skill_read_note": SKILL_READ_NOTE,
            "memory_calls_note": MEMORY_CALLS_NOTE}


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
                   f"{a['kit_diag_calls']} kit diag calls, "
                   f"{a.get('skill_search_calls', 0)} skills_search calls, "
                   f"{a['skill_reads']} skills with read requests, "
                   f"{a['ops_markers']} OPS markers")
    out.append(SKILL_READ_NOTE)
    out.append(MEMORY_CALLS_NOTE)
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
    """Proposal for skills with no observed read requests in REAL sessions.

    Kit-internal sessions are excluded. Never deletes: missing observations
    are not proof of non-use; retirement remains an owner decision.
    """
    skills_root = Path(skills_root) if skills_root else Path.home()
    fired: set[str] = set()
    real_sessions = 0
    for s in res["sessions"]:
        if s["kit_internal"]:
            continue
        real_sessions += 1
        fired.update(s["skill_reads"])
    if (skills_root / "skills").is_dir():
        profile = skills_root / "profile.yml"
        if profile.is_file():
            installed = sorted(
                kit_inventory.load_owned_skills(
                    skills_root, profile_path=profile))
        else:
            installed = sorted(d.name for d in
                               (skills_root / "skills").iterdir()
                               if d.is_dir())
    else:
        installed = all_skills
    zero = sorted(s for s in installed if s not in fired)
    return {"since": res.get("since"),
            "action": "proposal-only",
            "sessions_audited": real_sessions,
            "skills_total": len(installed),
            "fired_count": len(fired),
            "count": len(zero),
            "zero_use": zero, "skill_read_note": SKILL_READ_NOTE}


def retirement_report_human(report: dict) -> str:
    out = [(f"retirement proposal (since {report['since'] or 'all time'}, "
            f"{report['sessions_audited']} real sessions audited)"),
           (f"action: {report['action']} — owner decides, nothing is "
            "deleted"),
           SKILL_READ_NOTE,
           (f"skills with no observed reads ({len(report['zero_use'])}/"
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
                    help="list skills with no observed read requests in the "
                         "audited window (proposal only — nothing is deleted)")
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
