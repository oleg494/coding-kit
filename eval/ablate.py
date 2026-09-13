#!/usr/bin/env python3
"""eval/ablate.py — measure inlined-prompt contribution per named skill.

Runs each trap scenario twice under controlled prompt assembly: a baseline
with the descriptor manifest plus the active skill's inlined body, then one
treatment per skill with only that skill's descriptor/body removed. The
contribution of a skill is the pass-rate change between those two conditions
on the scenarios that name it.

This is an experimental, descriptive measure. Ambient global skills loaded by
the host harness are NOT controlled here; the numbers are raw and may be
non-conclusive on small samples.

Executor and judge run inside a declared container exactly like eval/runner.py:
`docker:<image> [@ro:<host>:<container>]... [@net] <argv...>` (prompt on stdin,
answer on stdout). A bare host CLI is refused before anything runs.

Usage:
    python eval/ablate.py --executor "docker:agent-image agent -p" \
        --model gpt-4o --json auto
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "eval" / "scenarios"

sys.path.insert(0, str(ROOT / "eval"))
from runner import parse, resolve_cmd, _evaluate_scenarios, validate_inline_skills  # noqa: E402
from prompt_assembly import skill_manifest  # noqa: E402
from telemetry import load_reported_usage, summarize_durations  # noqa: E402
from results_io import save_result  # noqa: E402


def discover_ablations(scenario_files: list[Path]) -> list[str]:
    """Unique sorted `skill:` values named in scenario frontmatter."""
    skills = set()
    for f in scenario_files:
        sc = parse(f.read_text(encoding="utf-8"))
        if sc.get("skill"):
            skills.add(sc["skill"])
    return sorted(skills)


def _pass_rate(rows: list[dict], skill: str) -> float:
    mine = [r for r in rows if r.get("skill") == skill]
    if not mine:
        return 0.0
    return sum(1 for r in mine if r.get("verdict") == "PASS") / len(mine)


def ablation_result(baseline_rows: list[dict],
                    ablated: dict[str, list[dict]]) -> dict:
    """Per-skill `{skill, pass_rate_with, pass_rate_without, delta,
    scenarios_affected}`. `delta` = pass-rate(with) - pass-rate(without)."""
    per_skill = []
    for skill, rows in sorted(ablated.items()):
        if not any(r.get("skill") == skill for r in baseline_rows):
            continue
        w = round(_pass_rate(baseline_rows, skill), 3)
        wo = round(_pass_rate(rows, skill), 3)
        per_skill.append({
            "skill": skill,
            "pass_rate_with": w,
            "pass_rate_without": wo,
            "delta": round(w - wo, 3),
            "scenarios_affected": sum(
                1 for r in baseline_rows if r.get("skill") == skill),
        })
    return {"per_skill": per_skill}


def validate_inputs(*, skills_root: Path, scenario_files: list[Path],
                    repeat: int, timeout: int) -> str | None:
    """Return a clear error string, or None when the experiment config is
    valid. Runs before any model subprocess is spawned."""
    if repeat < 1:
        return "--repeat must be >= 1"
    if timeout < 1:
        return "--timeout must be >= 1"
    if not scenario_files:
        return "no scenario files"
    err = validate_inline_skills(skills_root, frozenset())
    if err:
        return err
    manifest = {m["name"] for m in skill_manifest(skills_root)}
    for f in scenario_files:
        if not f.is_file():
            return f"scenario file not found: {f}"
        sc = parse(f.read_text(encoding="utf-8"))
        missing = [k for k in ("name", "skill", "trap", "expect", "body")
                   if k not in sc]
        if missing:
            return f"scenario {f.name} missing metadata: {', '.join(missing)}"
        skill = sc.get("skill")
        if skill and skill not in manifest:
            return f"scenario {f.name} names unknown skill: {skill}"
    return None


def _condition_comparable(rows: list[dict]) -> bool:
    """True when the rows form a measurable experiment condition.

    A condition is comparable only when every attempt reached the `verdict`
    phase. Any attempt stuck at an infrastructure phase — `executor` (the
    model failed to launch/run) or `judge` (the verdict could not be
    produced) — or any attempt lacking a `phase` (legacy/malformed) makes the
    condition non-comparable, so a baseline and a treatment cannot be fairly
    contrasted. A FAIL at the `verdict` phase is a legitimate score and keeps
    the condition comparable.
    """
    attempts = [
        att for r in rows
        for att in (r.get("attempts", []) if isinstance(r, dict) else [])
        if isinstance(att, dict)
    ]
    if not attempts:
        return False
    return all(att.get("phase") == "verdict" for att in attempts)


def run_ablation(executor, judge, scenario_files, skills_root, repeat=1,
                 timeout=600, model=None, executor_spec=None,
                 json_out=None, reported_usage=None) -> int:
    if not executor:
        raise ValueError("ablation requires a live --executor")
    err = validate_inputs(
        skills_root=skills_root, scenario_files=scenario_files,
        repeat=repeat, timeout=timeout)
    if err:
        raise ValueError(err)

    def rowset(disable, files):
        _, rows = _evaluate_scenarios(
            executor, judge, files, repeat=repeat, timeout=timeout,
            skills_root=skills_root, disable=frozenset(disable))
        return rows

    baseline_rows = rowset(frozenset(), scenario_files)
    if not _condition_comparable(baseline_rows):
        print(
            "error: ablation baseline is not a comparable condition "
            "(executor or judge phase infrastructure failure); "
            "not writing a result doc", file=sys.stderr)
        return 2

    ablated: dict[str, list[dict]] = {}
    for skill in discover_ablations(scenario_files):
        tagged = [f for f in scenario_files
                  if parse(f.read_text(encoding="utf-8")).get("skill") == skill]
        treatment_rows = rowset({skill}, tagged)
        if not _condition_comparable(treatment_rows):
            print(
                f"error: ablation treatment for skill '{skill}' is not a "
                "comparable condition (executor or judge phase "
                "infrastructure failure); not writing a result doc",
                file=sys.stderr)
            return 2
        ablated[skill] = treatment_rows

    all_rows = list(baseline_rows)
    for rows in ablated.values():
        all_rows.extend(rows)
    total_s, mean_s = summarize_durations(all_rows)

    payload = {
        "metric": "inlined-prompt contribution",
        "experimental": True,
        "ambient_skills_controlled": False,
        "repeat": repeat,
        "baseline": {"rows": baseline_rows},
        "per_skill": ablation_result(baseline_rows, ablated)["per_skill"],
        "duration_s_total": total_s,
        "duration_s_mean": mean_s,
    }
    if reported_usage is not None:
        payload["reported_usage"] = reported_usage

    for e in payload["per_skill"]:
        print(f"{e['skill']}: with {e['pass_rate_with']} / without "
              f"{e['pass_rate_without']} (delta {e['delta']:+.3f}, "
              f"n={e['scenarios_affected']})")

    if json_out:
        override = None if str(json_out) == "auto" else Path(json_out)
        save_result("ablate", model or "unspecified", payload,
                    path=override, executor_spec=executor_spec)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--executor", required=True,
                    help="confined model executor: docker:<image> "
                         "[@ro:<host>:<container>]... [@net] <argv...> "
                         "(reads the prompt on stdin, prints the answer to "
                         "stdout; a bare host CLI is refused)")
    ap.add_argument("--judge", default=None,
                    help="judge executor spec (same docker:<image> ... form; "
                         "default = --executor)")
    ap.add_argument("--model", default=None,
                    help="model label; required for --json persistence")
    ap.add_argument("--repeat", type=int, default=1,
                    help="attempts per scenario per condition (default 1)")
    ap.add_argument("--timeout", type=int, default=600,
                    help="per-attempt timeout in seconds (default 600)")
    ap.add_argument("--scenario", default=None,
                    help="restrict to a single scenario name (no .md)")
    ap.add_argument("--skills-dir", default=None, metavar="PATH",
                    help="skills root (default <kit>/skills)")
    ap.add_argument("--json", default=None, metavar="PATH|auto",
                    help="persist one kind=ablate doc: explicit path or 'auto'")
    ap.add_argument("--usage-json", default=None, metavar="PATH",
                    help="optional user-reported {tokens_total, cost_usd} "
                         "JSON object for the whole experiment")
    args = ap.parse_args(argv)

    if args.json and not args.model:
        print("error: a live --json ablation requires an explicit --model",
              file=sys.stderr)
        return 2

    try:
        executor = resolve_cmd(args.executor)
        judge = resolve_cmd(args.judge) if args.judge else executor
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not executor:
        print("error: --executor resolved to no command", file=sys.stderr)
        return 2

    files = sorted(SCENARIOS.glob("*.md"))
    if args.scenario:
        files = [SCENARIOS / f"{args.scenario}.md"]

    skills_root = Path(args.skills_dir) if args.skills_dir else (ROOT / "skills")

    try:
        return run_ablation(
            executor, judge, files, skills_root,
            repeat=args.repeat, timeout=args.timeout, model=args.model,
            executor_spec=args.executor, json_out=args.json,
            reported_usage=load_reported_usage(args.usage_json))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())