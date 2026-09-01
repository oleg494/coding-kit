#!/usr/bin/env python3
"""eval/trigger_eval.py — skill trigger-rate measurement for coding-kit.

Aims at the "agent does not load the right skill on its own" failure class:
it measures whether a skill's *description* makes an agent load the skill
for the natural user phrasing, with no other mechanisms helping.

Method (ported as ideas from the agentskills.io methodology):
- queries file: JSON array of {"skill": slug, "should": true|false,
  "query": "natural user wording"}. Per skill: several should-trigger
  queries and several should-not near-misses (similar words, different
  task) — not random unrelated questions.
- each query runs N times (default 3); a query passes if the majority of
  runs answer in a way that shows the skill was loaded (the slug appears
  in the answer — the kit souls mandate "mark the skill name").
- per-skill summary: trigger rate (should-queries passed) and false rate
  (should-not queries passed). Thresholds: trigger >= 0.5 and false <= 0.3.
- anti-overfitting: do NOT paste words from failed queries into the
  description; find the real trigger gap and reword (see skills/skill-authoring).
- always-on skills (ambient, never "loaded" on request) are measured by a
  behavior oracle instead of the slug-name signal — the answer must invoke
  the skill's mandated reflex commands/paths (see behavior_oracles.py), not
  merely acknowledge the request.

The model backend plugs in exactly like eval/runner.py: `--executor CMD`
reads the prompt from stdin, prints the answer to stdout (e.g.
`gemini -p -`, `claude -p`). Without `--executor` the queries file is only
validated (dry-run). The executor spec is developer-owned config, never
user input; parsed with shlex, run WITHOUT shell=True.

Usage:
    python eval/trigger_eval.py --queries eval/trigger_queries.json        # validate
    python eval/trigger_eval.py --queries eval/trigger_queries.json        \\
        --executor "gemini -p -" --model gemini-2.5-pro --runs 3 --parallel 4 --json auto
    python eval/trigger_eval.py --queries q.json --only yagni              # one skill
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
HERE = Path(__file__).resolve().parent          # eval/
ROOT = HERE.parent                              # kit root
sys.path.insert(0, str(HERE))
from runner import resolve_cmd, run_prompt      # same executor contract
from telemetry import load_reported_usage, summarize_durations
from behavior_oracles import behavior_fired, has_oracle


_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
_FM_NAME_RE = re.compile(r"^name:\s*([A-Za-z0-9_-]+)\s*$", re.M)
_FM_DESC_RE = re.compile(r"^description:\s*(.+)$", re.M)


def listing_entries() -> list[dict]:
    """One {name, description} row per skill, read live from skills/ frontmatter.

    The measured listing is the experiment's treatment: a placeholder that
    never gets replaced (live incident 2026-08-29) turns the run into a
    measurement of the executor's ambient global skills instead.
    """
    entries: list[dict] = []
    for d in sorted(_SKILLS_DIR.iterdir()) if _SKILLS_DIR.is_dir() else []:
        if not d.is_dir():
            continue
        text = (d / "SKILL.md").read_text(encoding="utf-8", errors="replace")[:4000]
        front = text.split("---", 2)
        if len(front) < 3:
            continue
        m = _FM_NAME_RE.search(front[1])
        if not m or m.group(1) != d.name:
            continue
        dm = _FM_DESC_RE.search(front[1])
        entries.append({"name": d.name,
                        "description": (dm.group(1).strip().strip("'\"")
                                        if dm else "")})
    return entries


def load_queries(skills_root, legacy_path) -> list[dict]:
    """Per-skill evals.json co-location (wave3 Task 9).

    Prefers skills/<slug>/evals/evals.json — {skill_name, evals:
    [{id, prompt, should_trigger, assertions?}]} — for every skill that
    has one; skills without the file fall back to the central
    eval/trigger_queries.json rows (which stay in place as the fallback
    source). Returns the flat validate()-compatible query list
    ({skill, should, query, id}); ids are stable <slug>-<position>.
    A query present in both sources is taken once, from the per-skill
    file."""
    skills_root = Path(skills_root)
    legacy_path = Path(legacy_path)
    out: list[dict] = []
    central: list[dict] = []
    if legacy_path.is_file():
        try:
            central = json.loads(
                legacy_path.read_text(encoding="utf-8")) or []
        except (json.JSONDecodeError, OSError):
            central = []
    covered: set[str] = set()
    for d in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        f = d / "evals" / "evals.json"
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        slug = data.get("skill_name") or d.name
        for i, ev in enumerate(data.get("evals") or []):
            out.append({"skill": slug,
                        "should": bool(ev.get("should_trigger")),
                        "query": ev.get("prompt", ""),
                        "id": ev.get("id") or f"{slug}-{i}"})
        covered.add(slug)
    pos: dict[str, int] = {}
    for q in central:
        if q.get("skill") in covered:
            continue
        slug = q.get("skill", "")
        n = pos.get(slug, 0)
        out.append({"skill": slug,
                    "should": bool(q.get("should")),
                    "query": q.get("query", ""),
                    "id": q.get("id") or f"{slug or 'x'}-{n}"})
        pos[slug] = n + 1
    return out


def _render_listing() -> str:
    rows = listing_entries()
    if not rows:
        return "<skills listing>"
    return "Skills:\n" + "\n".join(
        f"- {r['name']}: {r['description']}" for r in rows)

TRIGGER_RATE_MIN = 0.5
FALSE_RATE_MAX = 0.3
RUNS_DEFAULT = 3
TIMEOUT_DEFAULT = 300


def detect(slug: str, answer: str) -> bool:
    """True if the slug appears as a standalone token in the answer."""
    slug = re.escape(slug)
    return re.search(rf"(?<![a-z0-9_-]){slug}(?![a-z0-9_-])",
                     answer, re.IGNORECASE) is not None


def signal_fired(skill: str, answer: str) -> bool:
    """Behavior oracle for always-on skills; name detection otherwise."""
    if has_oracle(skill):
        return behavior_fired(skill, answer)
    return detect(skill, answer)


def validate(queries: list[dict]) -> list[str]:
    """Schema + balance checks. Returns a list of problems (empty = ok)."""
    problems = []
    if not queries:
        problems.append("queries file is empty")
        return problems
    by_skill: dict[str, dict[str, int]] = {}
    for i, q in enumerate(queries):
        where = f"queries[{i}]"
        if not isinstance(q, dict):
            problems.append(f"{where}: not an object"); continue
        for key in ("skill", "should", "query"):
            if key not in q:
                problems.append(f"{where}: missing '{key}'")
        if not isinstance(q.get("query"), str) or not q["query"].strip():
            problems.append(f"{where}: query is not a non-empty string")
        if not isinstance(q.get("should"), bool):
            problems.append(f"{where}: 'should' must be true/false")
        if q.get("skill"):
            s = by_skill.setdefault(q["skill"], {"should": 0, "not": 0})
            if q.get("should"):
                s["should"] += 1
            else:
                s["not"] += 1
    for skill, counts in by_skill.items():
        if counts["should"] == 0:
            problems.append(f"skill '{skill}': no should-trigger queries")
        if counts["not"] == 0:
            problems.append(f"skill '{skill}': no should-not (near-miss) queries")
    pairs = [(q["skill"], q["query"]) for q in queries
             if q.get("skill") and q.get("query")]
    if len(set(pairs)) != len(pairs):
        problems.append("duplicate (skill, query) entries")
    for i, q in enumerate(queries):
        if q.get("should") is False and q.get("skill") \
                and q["skill"].lower() in q["query"].lower():
            problems.append(f"queries[{i}]: should-not query names its own "
                            f"skill ('{q['skill']}') — near-miss must not")
    return problems


# --- prompt construction ---

PRELUDE = (
    "You are an agent. You have a skills directory available "
    "(Hermes-format SKILL.md skills), listed below.\n"
    "You MUST choose from this list: for every request, decide which "
    "single skill fits it best and load it; answer 'none' only when no "
    "skill in the list fits. Do not invent skills that are not listed.\n\n"
    "Examples of the required answer format:\n"
    "User request: review this security patch for a hardcoded-token leak\n"
    "SKILLS LOADED: sec-review\n"
    "User request: rename the variable to match the style guide\n"
    "SKILLS LOADED: none\n\n"
    "<skills listing>\n\n"
    "End your answer with a line: SKILLS LOADED: <comma-separated skill "
    "names you actually loaded, or 'none'>.\n\n"
)


def prompt_for(query: str) -> str:
    prelude = PRELUDE.replace("<skills listing>", _render_listing())
    return prelude + "User request: " + query + "\n"


def run_query_detailed(cmd: list[str], q: dict, runs: int,
                       timeout: int = TIMEOUT_DEFAULT) -> dict:
    """Runs one query `runs` times; records per-attempt timings and errors.

    Any execution error on an attempt fails the whole row, regardless of
    `should`; the first error and trace tail are promoted to row level.
    """
    hits = 0
    attempts: list[dict] = []
    errors: list[str] = []
    mode = "oracle" if has_oracle(q["skill"]) else "name"
    first_trace: "str | None" = None
    for _ in range(runs):
        t0 = time.perf_counter()
        err_msg = None
        is_fired = False
        trace_tail = None
        try:
            answer = run_prompt(cmd, prompt_for(q["query"]), timeout=timeout)
            is_fired = signal_fired(q["skill"], answer)
        except subprocess.TimeoutExpired as e:
            err_msg = f"TimeoutExpired: command timed out after {timeout}s"
            out = getattr(e, "stderr", None) or getattr(e, "stdout", None)
            if out:
                if isinstance(out, bytes):
                    out = out.decode("utf-8", errors="replace")
                trace_tail = str(out).strip()[-500:]
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            out = getattr(e, "stderr", None) or getattr(e, "stdout", None)
            if out:
                if isinstance(out, bytes):
                    out = out.decode("utf-8", errors="replace")
                trace_tail = str(out).strip()[-500:]
        dur = round(time.perf_counter() - t0, 4)
        if is_fired:
            hits += 1
        att: dict = {
            "fired": is_fired,
            "duration_s": dur,
            "mode": mode,
        }
        if err_msg:
            att["error"] = err_msg
            errors.append(err_msg)
            if first_trace is None:
                first_trace = trace_tail
        if trace_tail:
            att["trace_tail"] = trace_tail
        attempts.append(att)

    fired_aggregate = hits * 2 > runs
    expected = bool(q.get("should", False))
    is_pass = (not errors) and (fired_aggregate == expected)
    verdict = "PASS" if is_pass else "FAIL"
    total_dur = round(sum(a["duration_s"] for a in attempts), 4)

    row: dict = {
        "query": q.get("query", ""),
        "skill": q.get("skill", ""),
        "expected": expected,
        "fired": fired_aggregate,
        "verdict": verdict,
        "duration_s": total_dur,
        "mode": mode,
        "attempts": attempts,
    }
    if errors:
        row["error"] = "; ".join(errors)
    if first_trace:
        row["trace_tail"] = first_trace
    return row


def run_query(cmd: list[str], q: dict, runs: int,
              timeout: int = TIMEOUT_DEFAULT) -> tuple[str, bool]:
    """Runs one query `runs` times; majority vote decides triggered."""
    res = run_query_detailed(cmd, q, runs, timeout=timeout)
    return res["query"], res["fired"]

def summarize(results: dict[str, list[tuple[str, bool, bool]]]) -> tuple[list[str], dict]:
    """Return (problem lines, per-skill stats)."""
    problems, stats = [], {}
    for skill, rows in results.items():
        should = [p for (_, s, p) in rows if s]
        nots = [p for (_, s, p) in rows if not s]
        tr = sum(should) / len(should)
        fr = sum(nots) / len(nots)
        stats[skill] = {"trigger": tr, "false": fr,
                        "should": len(should), "not": len(nots)}
        if tr < TRIGGER_RATE_MIN:
            problems.append(f"{skill}: trigger rate {tr:.2f} < {TRIGGER_RATE_MIN} "
                            f"(failed: {[q for (q, s, p) in rows if s and not p]})")
        if fr > FALSE_RATE_MAX:
            problems.append(f"{skill}: false rate {fr:.2f} > {FALSE_RATE_MAX} "
                            f"(false-triggered: {[q for (q, s, p) in rows if not s and p]})")
    return problems, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", required=True,
                    help="JSON file with {skill, should, query}, or 'auto' "
                         "for per-skill evals.json + central fallback")
    ap.add_argument("--executor", help='CLI reading prompt from stdin, '
                     'printing answer to stdout (e.g. "gemini -p -")')
    ap.add_argument("--model", default=None,
                    help="model identifier (e.g. gpt-4o, claude-3-5-sonnet); "
                         "required for a live --json run (dry --json may omit)")
    ap.add_argument("--runs", type=int, default=RUNS_DEFAULT,
                    help=f"runs per query (default {RUNS_DEFAULT})")
    ap.add_argument("--parallel", type=int, default=1, help="parallel workers")
    ap.add_argument("--only", help="run a single skill (slug)")
    ap.add_argument("--timeout", type=int, default=TIMEOUT_DEFAULT,
                    help="per-call timeout seconds")
    ap.add_argument("--json", default=None, metavar="PATH|auto",
                    help="write a JSON result doc: explicit path or 'auto' "
                         "for the shared timestamped store (eval/results/)")
    ap.add_argument("--usage-json", default=None, metavar="PATH",
                    help="optional user-reported {tokens_total, cost_usd} "
                         "JSON object from the provider dashboard")
    args = ap.parse_args()

    if args.executor and args.json and not args.model:
        print("error: a live --json run requires an explicit --model",
              file=sys.stderr)
        return 2

    if args.queries == "auto":
        queries = load_queries(_SKILLS_DIR, ROOT / "eval"
                               / "trigger_queries.json")
        from collections import Counter
        per_skill = Counter(q["skill"] for q in queries)
        fallback = [s for s in sorted(per_skill)
                    if not (_SKILLS_DIR / s / "evals" / "evals.json")
                    .is_file()]
        if fallback:
            print(f"fallback to central file: {', '.join(fallback)}")
    else:
        try:
            queries = json.loads(
                Path(args.queries).read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(f"queries file not found: {args.queries}"); return 2
        except json.JSONDecodeError as e:
            print(f"queries file is not valid JSON: {e}"); return 2
    problems = validate(queries)
    if problems:
        print("queries validation FAILED:")
        print("\n".join(f"  - {p}" for p in problems)); return 1
    print(f"queries OK: {len(queries)} queries "
          f"({len({q['skill'] for q in queries})} skills)")

    if not args.executor:
        print("dry-run: no --executor, queries validated only")
        if args.json:
            _emit_json(args, mode="dry-run", total=len(queries),
                       passed=0, fired=0, misses=[], rows=[])
        return 0
    reported_usage = load_reported_usage(args.usage_json)
    cmd = resolve_cmd(args.executor)
    selected = [q for q in queries
                if not args.only or q["skill"] == args.only]
    if args.only and not selected:
        print(f"--only {args.only}: no such skill in queries"); return 2

    results: dict[str, list[tuple[str, bool, bool]]] = {}
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futs = {pool.submit(run_query_detailed, cmd, q, args.runs,
                            args.timeout): q for q in selected}
        for fut in as_completed(futs):
            q = futs[fut]
            try:
                row = fut.result()
            except Exception as e:
                row = {
                    "query": q.get("query", ""),
                    "skill": q.get("skill", ""),
                    "expected": bool(q.get("should", False)),
                    "fired": False,
                    "verdict": "FAIL",
                    "duration_s": 0.0,
                    "error": f"{type(e).__name__}: {e}",
                    "attempts": [{"fired": False, "duration_s": 0.0,
                                  "error": f"{type(e).__name__}: {e}"}],
                }
            rows.append(row)
            query_text = row["query"]
            passed_should = row["fired"]
            tag = row["verdict"]
            print(f"[{tag}] {q['skill']:30s} should={str(q['should']):5s} "
                  f"'{query_text[:60]}'")
            results.setdefault(q["skill"], []).append((query_text, q["should"], passed_should))

    problems, stats = summarize(results)
    print("\nper-skill summary (trigger = should-passed rate, false = should-not-passed):")
    for skill, s in sorted(stats.items()):
        print(f"  {skill:30s} trigger {s['trigger']:.2f}  false {s['false']:.2f}  "
              f"({s['should']}+{s['not']} queries)")

    fired_count = sum(1 for r in rows if r.get("fired") is True)
    passed_count = sum(1 for r in rows if r.get("verdict") == "PASS")

    if problems:
        print("\nBELOW THRESHOLD:")
        print("\n".join(f"  - {p}" for p in problems))
        if args.json:
            _emit_json(args, mode="live", total=len(selected),
                       passed=passed_count,
                       fired=fired_count,
                       misses=problems,
                       rows=rows, reported_usage=reported_usage)
        return 1
    print("\nall measured skills above threshold")
    if args.json:
        _emit_json(args, mode="live", total=len(selected),
                   passed=passed_count,
                   fired=fired_count,
                   misses=[],
                   rows=rows, reported_usage=reported_usage)
    return 0


def _emit_json(args, mode: str, total: int, passed: int, fired: int,
               misses: list[str], rows: list[dict] | None = None,
               reported_usage: dict | None = None) -> None:
    if not getattr(args, "json", None):
        return
    sys.path.insert(0, str(HERE))
    from results_io import save_result
    override = None if str(args.json) == "auto" else Path(args.json)
    model = getattr(args, "model", None)
    if mode == "live" and not model:
        raise ValueError("a live trigger result requires an explicit --model")
    model = model or "unspecified"
    rows = rows if rows is not None else []
    total_s, mean_s = summarize_durations(rows)
    payload = {
        "mode": mode,
        "passed": passed,
        "fired": fired,
        "total": total,
        "misses": misses,
        "rows": rows,
        "duration_s_total": total_s,
        "duration_s_mean": mean_s,
    }
    if mode == "live" and reported_usage is not None:
        payload["reported_usage"] = reported_usage
    save_result("trigger", model, payload, path=override,
                executor_spec=getattr(args, "executor", None))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())