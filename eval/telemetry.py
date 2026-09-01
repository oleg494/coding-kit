"""Wall-time aggregation and optional user-reported usage totals.

The harness itself measures ONLY wall-clock: model subprocesses are black
boxes with no token stream. `tokens_total`/`cost_usd` come from a
user-supplied `--usage-json` file (see `load_reported_usage`) — never
fabricated or inferred here.
"""
import json
import math
import sys
from pathlib import Path


def _finite_nonneg(value: object) -> bool:
    """True when `value` is a finite, non-negative number (not a bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value >= 0 and math.isfinite(value)


def summarize_durations(rows: list) -> tuple[float, float]:
    """(total_s, mean_s) over every attempt that recorded a finite,
    non-negative `duration_s`. Returns `(0.0, 0.0)` when none exist."""
    durations = [
        a["duration_s"]
        for row in rows
        if isinstance(row, dict)
        for a in row.get("attempts", []) or []
        if isinstance(a, dict) and _finite_nonneg(a.get("duration_s"))
    ]
    if not durations:
        return 0.0, 0.0
    return round(sum(durations), 3), round(sum(durations) / len(durations), 3)


def load_reported_usage(path: str | Path | None) -> dict | None:
    """Read a user-reported usage JSON object.

    Accepts only a JSON object with optional numeric `tokens_total` and
    `cost_usd` keys. Bools, negatives, NaN, and +/-Infinity are rejected.
    Returns `None` (with a stderr warning) when the path is absent,
    unreadable, invalid, or the object carries no usable key (empty `{}`,
    both keys null, or only unknown keys). Returns the validated key/value
    subset of the object otherwise. The empty dict is never returned, so
    live runs never attach a meaningless `reported_usage: {}`.
    """
    if path is None:
        return None
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[telemetry] --usage-json unreadable: {exc}", file=sys.stderr)
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[telemetry] --usage-json invalid JSON: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print("[telemetry] --usage-json must be a JSON object", file=sys.stderr)
        return None
    out: dict = {}
    for key in ("tokens_total", "input_tokens", "output_tokens", "cost_usd"):
        if key in data and data[key] is not None:
            value = data[key]
            if not _finite_nonneg(value):
                print(
                    f"[telemetry] --usage-json {key} must be a finite "
                    f"non-negative number (got {value!r})",
                    file=sys.stderr,
                )
                return None
            out[key] = value
    if not out:
        return None
    return out