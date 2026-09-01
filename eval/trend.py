#!/usr/bin/env python3
"""eval/trend.py — pass-rate history + failure evidence reporting.

Reads the shared JSON store (eval/results_io.load_runs) and prints:
  1. a markdown table of the newest run per (kind, model) with baseline deltas;
  2. a Failure Evidence Packets section: failure details for non-PASS targets
     in the newest run of each kind/model group (evidence only, no proposals).

Usage:
    python eval/trend.py                      # report to stdout
    python eval/trend.py --update-baselines   # refresh baseline JSON files
    python eval/trend.py > TREND.md           # or redirect
"""
import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from results_io import load_runs
from ablation_report import render_ablation_section

BASELINES_DIR = ROOT / "eval" / "baselines"
KIND_ORDER = {"trap": 0, "tasks": 1, "trigger": 2}


def _is_canary_row(row: object) -> bool:
    """True for ImpossibleBench canary rows (`canary: true`).

    Canary oracles are unsatisfiable by construction; a canary PASS is
    hacking evidence, not a resolved task. Rows are excluded from pass-rate
    aggregation and baselines and reported on their own trend line.
    """
    return isinstance(row, dict) and row.get("canary") is True


def _honest_rows(rows: list) -> list[dict]:
    """Non-canary rows (the pass-rate population)."""
    return [r for r in rows if isinstance(r, dict) and not _is_canary_row(r)]


def _canary_rows(rows: list) -> list[dict]:
    return [r for r in rows if _is_canary_row(r)]


def _row_hacked(row: dict) -> bool:
    """A pass that used a shortcut or hacked a canary — not clean."""
    if row.get("hacked"):
        return True
    for att in row.get("attempts", []) or []:
        if isinstance(att, dict) and att.get("shortcuts"):
            return True
    return False


def _resolved_hacked_clean(r: dict) -> tuple[int, int, int]:
    """(resolved, hacked-resolved, clean-resolved) for a tasks-kind run.

    Qwen Verification Horizon accounting: resolved counts every PASS row
    (canaries included — a hacked canary IS a resolution, by cheating);
    hacked-resolved counts shortcut-flagged passes and hacked canaries;
    clean-resolved is the honest remainder (resolved - hacked).
    """
    rows = r.get("rows")
    if not isinstance(rows, list):
        return (0, 0, 0)
    resolved = sum(1 for row in rows
                   if isinstance(row, dict) and row.get("verdict") == "PASS")
    hacked = sum(1 for row in rows
                 if isinstance(row, dict) and row.get("verdict") == "PASS"
                 and _row_hacked(row))
    return (resolved, hacked, resolved - hacked)


def _accounting_line(r: dict) -> str | None:
    """One-line clean-pass accounting, or None when nothing resolved."""
    resolved, hacked, clean = _resolved_hacked_clean(r)
    if resolved == 0:
        return None
    return (f"resolved {resolved} | hacked-resolved {hacked} | "
            f"clean-resolved {clean}")


def _scenario_items(r: dict) -> list[dict]:
    """Scenario/row dicts of a run, whichever key the kind uses."""
    for key in ("scenarios", "rows"):
        items = r.get(key)
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    return []


def _mast_histogram(runs: list[dict]) -> dict[str, int]:
    """Counts of known MAST modes across runs' scenario/row items.

    Items without `mast_mode`, and ids not in task_runner.MAST_MODES
    (reported separately by render_mast_section), are ignored here.
    """
    from task_runner import MAST_MODES

    hist: dict[str, int] = {}
    for r in runs:
        for item in _scenario_items(r):
            mode = item.get("mast_mode")
            if isinstance(mode, str) and mode in MAST_MODES:
                hist[mode] = hist.get(mode, 0) + 1
    return hist


def render_mast_section(runs: list[dict]) -> str | None:
    """Failure-mode histogram block, or None when no run carries labels."""
    from task_runner import MAST_MODES

    hist = _mast_histogram(runs)
    unknown = sorted({
        item.get("mast_mode")
        for r in runs for item in _scenario_items(r)
        if isinstance(item.get("mast_mode"), str)
        and item["mast_mode"] not in MAST_MODES
    })
    if not hist and not unknown:
        return None
    lines = ["| mode | name | count |", "|---|---|---|"]
    for mode in sorted(hist, key=lambda m: (-hist[m], m)):
        lines.append(f"| {mode} | {MAST_MODES[mode]} | {hist[mode]} |")
    for mode in unknown:
        lines.append(f"| {mode} | unknown mast_mode | - |")
    if unknown:
        lines.append("")
        lines.append(f"WARNING: unknown mast_mode: "
                     f"{', '.join(unknown)} — not in MAST_MODES")
    return "\n".join(lines)

def _is_dry_run(r: dict) -> bool:
    if not isinstance(r, dict):
        return False

    mode = r.get("mode")
    if mode is not None:
        return str(mode).lower() in ("dry-run", "dry_run", "dry")

    # Legacy fallback when "mode" is absent:
    if r.get("dry_run") is True or r.get("dry") is True:
        return True
    if str(r.get("verdict", "")).upper() in ("DRY_RUN", "DRY-RUN", "DRY"):
        return True

    # Zero-result artifact (total == 0)
    if r.get("total") == 0:
        return True

    # Check rows or scenarios for DRY_RUN verdicts
    rows = r.get("rows")
    if isinstance(rows, list) and any(
        isinstance(x, dict) and str(x.get("verdict", "")).upper() in ("DRY_RUN", "DRY-RUN", "DRY")
        for x in rows
    ):
        return True

    scenarios = r.get("scenarios")
    if isinstance(scenarios, list) and any(
        isinstance(x, dict) and str(x.get("verdict", "")).upper() in ("DRY_RUN", "DRY-RUN", "DRY")
        for x in scenarios
    ):
        return True

    # Unmarked zero-pass artifact with no live execution evidence
    has_pass = r.get("passed", 0) > 0
    if not has_pass:
        if isinstance(rows, list) and any(isinstance(x, dict) and x.get("verdict") == "PASS" for x in rows):
            has_pass = True
        elif isinstance(scenarios, list) and any(isinstance(x, dict) and x.get("verdict") == "PASS" for x in scenarios):
            has_pass = True

    if not has_pass:
        items = rows if isinstance(rows, list) else (scenarios if isinstance(scenarios, list) else None)
        if items is not None:
            has_evidence = any(
                isinstance(x, dict) and (
                    bool(x.get("attempts")) or
                    bool(x.get("error")) or
                    bool(x.get("error_class")) or
                    bool(x.get("trace_tail"))
                )
                for x in items
            )
            if not has_evidence:
                return True
    return False


def _bound_text(text: object, max_chars: int = 500) -> str:
    s = str(text).strip()
    if len(s) > max_chars:
        return s[:max_chars] + "..."
    return s


def _score(r: dict) -> str:
    kind = r.get("kind")
    if "passed" in r and "total" in r:
        return f"{r['passed']}/{r['total']}"
    if kind == "trap" and "scenarios" in r and isinstance(r["scenarios"], list):
        scenarios = r["scenarios"]
        passed = sum(1 for s in scenarios if isinstance(s, dict) and s.get("verdict") == "PASS")
        return f"{passed}/{len(scenarios)}"
    if kind == "tasks" and "rows" in r and isinstance(r["rows"], list):
        rows = _honest_rows(r["rows"])
        passed = sum(1 for row in rows if row.get("verdict") == "PASS")
        return f"{passed}/{len(rows)}"
    if kind == "trigger":
        if "fired" in r and "total" in r:
            return f"fired {r['fired']}/{r['total']}"
        if "rows" in r and isinstance(r["rows"], list) and r["rows"]:
            rows = r["rows"]
            fired = sum(1 for row in rows if isinstance(row, dict) and row.get("fired") is True)
            return f"fired {fired}/{len(rows)}"
    if "fired" in r and "total" in r:
        return f"fired {r['fired']}/{r['total']}"
    return "?"


def _rate(r: dict) -> float | None:
    kind = r.get("kind")
    if "passed" in r and "total" in r:
        try:
            total = float(r["total"])
            passed = float(r["passed"])
            return passed / total if total > 0 else 0.0
        except (ValueError, TypeError, ZeroDivisionError):
            pass
    if kind == "trap" and "scenarios" in r and isinstance(r["scenarios"], list):
        scenarios = r["scenarios"]
        total = len(scenarios)
        if total > 0:
            passed = sum(1 for s in scenarios if isinstance(s, dict) and s.get("verdict") == "PASS")
            return float(passed) / float(total)
        return 0.0
    if kind == "tasks" and "rows" in r and isinstance(r["rows"], list):
        rows = _honest_rows(r["rows"])
        total = len(rows)
        if total > 0:
            passed = sum(1 for row in rows if row.get("verdict") == "PASS")
            return float(passed) / float(total)
        return 0.0
    if kind == "trigger":
        if "fired" in r and "total" in r:
            try:
                total = float(r["total"])
                fired = float(r["fired"])
                return fired / total if total > 0 else 0.0
            except (ValueError, TypeError, ZeroDivisionError):
                pass
        if "rows" in r and isinstance(r["rows"], list):
            rows = r["rows"]
            total = len(rows)
            if total > 0:
                fired = sum(1 for row in rows if isinstance(row, dict) and row.get("fired") is True)
                return float(fired) / float(total)
            return 0.0
    return None


def _load_baseline(kind: str, baselines_dir: Path | None = None) -> dict[str, float]:
    b_dir = Path(baselines_dir) if baselines_dir is not None else BASELINES_DIR
    path = b_dir / f"{kind}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out: dict[str, float] = {}
            for k, v in data.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out[str(k)] = float(v)
            return out
    except Exception:
        pass
    return {}

def _status_and_delta(rate: float | None, baseline_rate: float | None) -> tuple[str, str, str]:
    if baseline_rate is None:
        return "-", "-", "-"
    baseline_str = f"{baseline_rate * 100:.1f}%"
    if rate is None:
        return baseline_str, "-", "-"
    delta = round((rate - baseline_rate) * 100.0, 6)
    delta_str = f"{delta:+.1f}pp"
    if delta >= -3.0:
        status_str = "OK"
    elif delta <= -8.0:
        status_str = "CRITICAL"
    else:
        status_str = "WARN"
    return baseline_str, delta_str, status_str

def _duration_str(r: dict) -> str:
    mean = r.get("duration_s_mean")
    if isinstance(mean, bool) or not isinstance(mean, (int, float)):
        return "-"
    if not math.isfinite(mean) or mean < 0:
        return "-"
    return f"{mean:.3f}s"


def _reported_cost_str(r: dict) -> str:
    usage = r.get("reported_usage")
    if not isinstance(usage, dict):
        return "-"
    cost = usage.get("cost_usd")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return "-"
    if not math.isfinite(cost) or cost < 0:
        return "-"
    return f"${cost:.2f}"


def _evidence_packets(newest_runs: list[dict]) -> list[str]:
    packets: list[str] = []
    sorted_runs = sorted(
        newest_runs,
        key=lambda r: (KIND_ORDER.get(r.get("kind", ""), 99), r.get("model", ""))
    )
    for r in sorted_runs:
        kind = r.get("kind", "")
        model = r.get("model", "unspecified")
        utc = r.get("utc", "")[:16]

        if kind == "trap":
            scenarios = r.get("scenarios")
            if isinstance(scenarios, list):
                for scenario in scenarios:
                    if not isinstance(scenario, dict):
                        continue
                    verdict = scenario.get("verdict")
                    if verdict != "PASS":
                        name = scenario.get("name", "unknown")
                        skill = scenario.get("skill")
                        error = scenario.get("error")
                        trace_tail = scenario.get("trace_tail")
                        if not error or not trace_tail:
                            for att in scenario.get("attempts", []):
                                if not isinstance(att, dict):
                                    continue
                                if not error and att.get("error"):
                                    error = att.get("error")
                                if not trace_tail and att.get("trace_tail"):
                                    trace_tail = att.get("trace_tail")
                        re_verify = f"python eval/runner.py --scenario {name} --executor ... --repeat 2"
                        target_desc = f"{name} (skill: {skill})" if skill else name
                        packet_lines = [
                            f"- [trap] target: `{target_desc}` | model: `{model}` | utc: `{utc}`",
                        ]
                        if error:
                            packet_lines.append(f"  error: {_bound_text(error)}")
                        if trace_tail:
                            packet_lines.append(f"  trace_tail: {_bound_text(trace_tail)}")
                        packet_lines.append(f"  re-verify: {re_verify}")
                        packets.append("\n".join(packet_lines))

        elif kind == "tasks":
            rows = r.get("rows")
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if _is_canary_row(row):
                        if row.get("hacked"):
                            name = row.get("name", "unknown")
                            packets.append("\n".join([
                                (f"- [tasks] canary hacked: `{name}` | "
                                 f"model: `{model}` | utc: `{utc}`"),
                                ("  error: canary oracle passed — verifier "
                                 "hack (ImpossibleBench)"),
                                ("  re-verify: python eval/task_runner.py "
                                 f"--task {name} --executor ..."),
                            ]))
                        continue
                    verdict = row.get("verdict")
                    if verdict != "PASS":
                        name = row.get("name", "unknown")
                        error = row.get("error") or row.get("error_class")
                        trace_tail = row.get("trace_tail")
                        if not error or not trace_tail:
                            for att in row.get("attempts", []):
                                if not isinstance(att, dict):
                                    continue
                                if not error:
                                    error = att.get("error") or att.get("error_class")
                                if not trace_tail and att.get("trace_tail"):
                                    trace_tail = att.get("trace_tail")
                        re_verify = "python eval/task_runner.py --executor ..."
                        packet_lines = [
                            f"- [tasks] target: `{name}` | model: `{model}` | utc: `{utc}`",
                        ]
                        if error:
                            packet_lines.append(f"  error: {_bound_text(error)}")
                        if trace_tail:
                            packet_lines.append(f"  trace_tail: {_bound_text(trace_tail)}")
                        packet_lines.append(f"  re-verify: {re_verify}")
                        packets.append("\n".join(packet_lines))

        elif kind == "trigger":
            rows = r.get("rows")
            has_row_failures = False
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    verdict = row.get("verdict")
                    expected = row.get("expected") if "expected" in row else row.get("should")
                    fired = row.get("fired")
                    failed = False
                    if verdict is not None:
                        failed = (verdict != "PASS")
                    elif expected is not None and fired is not None:
                        failed = (expected != fired)
                    if failed:
                        has_row_failures = True
                        query = row.get("query", "unknown")
                        skill = row.get("skill")
                        error = row.get("error")
                        trace_tail = row.get("trace_tail")
                        if not error or not trace_tail:
                            for att in row.get("attempts", []):
                                if not isinstance(att, dict):
                                    continue
                                if not error and att.get("error"):
                                    error = att.get("error")
                                if not trace_tail and att.get("trace_tail"):
                                    trace_tail = att.get("trace_tail")
                        re_verify = "python eval/trigger_eval.py --queries eval/trigger_queries.json --executor ..."
                        target_desc = f"{query} (skill: {skill})" if skill else query
                        packet_lines = [
                            f"- [trigger] target: `{target_desc}` | model: `{model}` | utc: `{utc}`",
                        ]
                        if error:
                            packet_lines.append(f"  error: {_bound_text(error)}")
                        if trace_tail:
                            packet_lines.append(f"  trace_tail: {_bound_text(trace_tail)}")
                        packet_lines.append(f"  re-verify: {re_verify}")
                        packets.append("\n".join(packet_lines))

            if not has_row_failures:
                misses = r.get("misses")
                if isinstance(misses, list) and misses:
                    for miss in misses:
                        re_verify = "python eval/trigger_eval.py --queries eval/trigger_queries.json --executor ..."
                        packet_lines = [
                            f"- [trigger] target: `{miss}` | model: `{model}` | utc: `{utc}`",
                            f"  error: trigger miss",
                            f"  re-verify: {re_verify}",
                        ]
                        packets.append("\n".join(packet_lines))
                elif "passed" in r and "total" in r and r["passed"] < r["total"]:
                    re_verify = "python eval/trigger_eval.py --queries eval/trigger_queries.json --executor ..."
                    packet_lines = [
                        f"- [trigger] target: `trigger misses` | model: `{model}` | utc: `{utc}`",
                        f"  error: passed {r['passed']}/{r['total']}",
                        f"  re-verify: {re_verify}",
                    ]
                    packets.append("\n".join(packet_lines))

    return packets


def render(results_dir: Path | None = None, baselines_dir: Path | None = None) -> str:
    runs = load_runs(results_dir=results_dir)
    runs = [r for r in runs if not _is_dry_run(r)]
    if not runs:
        return ("# Eval trends\n\nno results yet — run any eval with "
                "`--json auto`\n")

    table_runs = [r for r in runs if r.get("kind") != "ablate"]
    ablate_runs = [r for r in runs if r.get("kind") == "ablate"]

    lines = ["# Eval trends\n"]

    # Group runs by (kind, model), keeping newest run by utc
    grouped: dict[tuple[str, str], dict] = {}
    for r in table_runs:
        kind = str(r.get("kind") or "unspecified")
        model = str(r.get("model") or "unspecified")
        existing = grouped.get((kind, model))
        if existing is None or str(r.get("utc", "")) >= str(existing.get("utc", "")):
            grouped[(kind, model)] = r
    if grouped:
        canary_sections: list[str] = []
        lines.append(
            "| kind | model | utc | score | baseline | delta | status | duration | reported cost |")
        lines.append("|---|---|---|---|---|---|---|---|---|")

        sorted_groups = sorted(
            grouped.items(),
            key=lambda item: (KIND_ORDER.get(item[0][0], 99), item[0][0], item[0][1])
        )

        newest_runs = []
        for (kind, model), r in sorted_groups:
            newest_runs.append(r)
            if kind == "tasks":
                can_list = r.get("rows")
                can_rows = _canary_rows(can_list if isinstance(can_list, list) else [])
                if can_rows:
                    hacked = sum(1 for c in can_rows if c.get("hacked"))
                    canary_sections.append(
                        f"- `{model}` @ {r.get('utc', '')[:16]}: "
                        f"hacked {hacked}/{len(can_rows)} "
                        f"(ImpossibleBench canaries; excluded from "
                        f"pass-rate baselines)")

            utc_str = r.get("utc", "")[:16]
            score_str = _score(r)
            rate = _rate(r)
            baselines = _load_baseline(kind, baselines_dir=baselines_dir)
            baseline_rate = baselines.get(model)
            b_str, d_str, status_str = _status_and_delta(rate, baseline_rate)
            lines.append(f"| {kind} | {model} | {utc_str} | {score_str} | {b_str} | {d_str} | {status_str} | {_duration_str(r)} | {_reported_cost_str(r)} |")
            if kind == "tasks":
                accounting = _accounting_line(r)
                if accounting:
                    lines.append(f"| accounting | {model} | {utc_str} | "
                                 f"{accounting} |")

        mast_block = render_mast_section(runs)
        if mast_block:
            lines += ["", "## MAST failure modes", "", mast_block]
        if canary_sections:
            lines += ["", "## Canary integrity", ""] + canary_sections
        lines += ["", "## Failure Evidence Packets", ""]
        packets = _evidence_packets(newest_runs)
        if packets:
            lines += packets
            lines.append("")
        else:
            lines += ["all-green: no open failures", ""]

    lines += render_ablation_section(ablate_runs, _duration_str, _reported_cost_str)
    return "\n".join(lines)


def update_baselines(results_dir: Path | None = None, baselines_dir: Path | None = None, n: int = 5) -> None:
    b_dir = Path(baselines_dir) if baselines_dir is not None else BASELINES_DIR
    b_dir.mkdir(parents=True, exist_ok=True)
    runs = load_runs(results_dir=results_dir)
    runs = [r for r in runs if not _is_dry_run(r)]
    rates_by_group: dict[tuple[str, str], list[float]] = {}
    for r in runs:
        kind = r.get("kind")
        model = r.get("model") or "unspecified"
        if not kind:
            continue
        rate = _rate(r)
        if rate is not None:
            rates_by_group.setdefault((kind, str(model)), []).append(rate)

    kinds = set(k for k, _ in rates_by_group.keys())
    for kind in sorted(kinds):
        existing: dict[str, float] = {}
        target_file = b_dir / f"{kind}.json"
        if target_file.is_file():
            try:
                loaded = json.loads(target_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = {str(k): float(v) for k, v in loaded.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
            except Exception:
                existing = {}

        for (k, model), rates in rates_by_group.items():
            if k == kind and rates:
                last_n = rates[-n:]
                avg = sum(last_n) / len(last_n)
                existing[model] = round(avg, 4)

        if existing:
            content = json.dumps(existing, indent=2, sort_keys=True) + "\n"
            target_file.write_text(content, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-baselines", action="store_true",
                        help="update rolling baseline JSON files from last N runs")
    parser.add_argument("-n", "--last-n", type=int, default=5,
                        help="number of recent runs to average for baselines (default: 5)")
    parser.add_argument("--results-dir", type=str, default=None,
                        help="custom results directory")
    parser.add_argument("--baselines-dir", type=str, default=None,
                        help="custom baselines directory")
    args = parser.parse_args(argv)

    res_dir = Path(args.results_dir) if args.results_dir else None
    base_dir = Path(args.baselines_dir) if args.baselines_dir else None

    if args.update_baselines:
        update_baselines(results_dir=res_dir, baselines_dir=base_dir, n=args.last_n)
    print(render(results_dir=res_dir, baselines_dir=base_dir))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
