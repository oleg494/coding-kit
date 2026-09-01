#!/usr/bin/env python3
"""eval/atif_export.py — ATIF v1.7 export of schema-v1 results payloads.

Maps one stored results run onto a single Harbor Agent Trajectory
Interchange Format (ATIF) v1.7 document:

https://github.com/harbor-framework/harbor — RFC 0001 (trajectory-format).

Coverage decisions (wave6 Task 19):
- one Trajectory per results run; `session_id` = the store run_id;
- steps are derived from rows: a system preamble, one user step per task
  prompt (`gen_ai.prompt.name` when the row carries it), and one agent step
  per attempt carrying `metrics` (prompt/completion/cached tokens, cost),
  `tool_calls[]` and an `observation.results[]` linked back through
  `source_call_id`;
- `final_metrics` aggregates the per-step metrics; `llm_call_count` lives in
  `extra` (the run-level number of LLM inferences the payload evidences);
- RL-oriented `token_ids`/`logprobs` are deliberately skipped (roadmap
  non-goal), as are `subagent_trajectories`.

The kit's task rows record durations and verdicts — not per-call token
streams — so per-step metrics come only from attempt-level `metrics` dicts
previously recorded by the harness or richer executors; they are never
fabricated from durations.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT_VERSION_FILE = HERE.parent / "VERSION"

AGENT_NAME = "coding-kit"
SCHEMA_VERSION = "ATIF-v1.7"
_SOURCES = ("system", "user", "agent")


class AtifValidationError(ValueError):
    """Raised when an exported trajectory fails the RFC structural checks."""


def _kit_version() -> str:
    try:
        return KIT_VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _step_metrics(metrics: object) -> dict | None:
    """Pass through only the four ATIF MetricsSchema fields the kit uses."""
    if not isinstance(metrics, dict):
        return None
    out = {}
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens",
                "cost_usd"):
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = value
    return out or None


def _agent_step(step_id: int, attempt: dict, model: str,
                row_calls: list | None = None,
                row_results: list | None = None) -> dict:
    """One agent step per attempt. The row-level `tool_calls`/`observation`
    (the executor's interaction record) attach to the row's first agent
    step; attempt-level copies override them when present."""
    step: dict = {
        "step_id": step_id,
        "source": "agent",
        "model_name": model,
        "message": str(attempt.get("verdict", "")),
        "llm_call_count": 1,
    }
    metrics = _step_metrics(attempt.get("metrics"))
    if metrics:
        step["metrics"] = metrics
    calls = attempt.get("tool_calls")
    if calls is None and row_calls is not None:
        calls = row_calls
    if isinstance(calls, list) and calls:
        step["tool_calls"] = [
            {
                "tool_call_id": str(c.get("tool_call_id",
                                          f"call_{step_id}_{i}")),
                "function_name": str(c.get("function_name", "unknown")),
                "arguments": c.get("arguments") or {},
            }
            for i, c in enumerate(calls) if isinstance(c, dict)
        ]
    observation = attempt.get("observation")
    if observation is None and row_results is not None:
        observation = {"results": row_results}
    results = observation.get("results") \
        if isinstance(observation, dict) else None
    if isinstance(results, list) and results:
        step["observation"] = {"results": [
            {"source_call_id": r.get("source_call_id"),
             "content": r.get("content", "")}
            for r in results if isinstance(r, dict)
        ]}
    return step


def to_atif(results_payload: dict, *, run_id: str, model: str, utc: str,
            agent_version: str | None = None) -> dict:
    """Build one ATIF v1.7 Trajectory dict from a schema-v1 results payload.

    Raises AtifValidationError when the payload lacks the minimal schema-v1
    envelope (run_id/model/utc are supplied by the caller from the stored
    document, so only payload-level shape errors surface here).
    """
    if not isinstance(results_payload, dict):
        raise AtifValidationError("results_payload must be a dict")
    rows = results_payload.get("rows")
    if rows is None or not isinstance(rows, list):
        raise AtifValidationError("results_payload.rows must be a list")

    steps: list[dict] = [{
        "step_id": 1,
        "source": "system",
        "message": (f"{AGENT_NAME} task-suite run {run_id} "
                    f"({results_payload.get('mode', 'unknown')} mode)"),
    }]
    llm_call_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "task"))
        prompt_name = row.get("gen_ai.prompt.name") or name
        steps.append({
            "step_id": len(steps) + 1,
            "source": "user",
            "message": str(prompt_name),
        })
        row_calls = row.get("tool_calls")
        row_calls = row_calls if isinstance(row_calls, list) else None
        observation = row.get("observation")
        row_results = observation.get("results") \
            if isinstance(observation, dict) else None
        row_results = row_results if isinstance(row_results, list) else None
        first_agent = True
        for attempt in row.get("attempts", []) or []:
            if not isinstance(attempt, dict):
                continue
            agent_step = _agent_step(len(steps) + 1, attempt, model,
                                     row_calls if first_agent else None,
                                     row_results if first_agent else None)
            if agent_step.pop("llm_call_count", None):
                llm_call_count += 1
            first_agent = False
            steps.append(agent_step)

    totals = {key: 0 for key in ("total_prompt_tokens",
                                 "total_completion_tokens",
                                 "total_cached_tokens")}
    total_cost = 0.0
    for s in steps:
        m = s.get("metrics") or {}
        for tkey, skey in (("total_prompt_tokens", "prompt_tokens"),
                           ("total_completion_tokens", "completion_tokens"),
                           ("total_cached_tokens", "cached_tokens")):
            value = m.get(skey)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[tkey] += value
        cost = m.get("cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            total_cost += cost

    final_metrics = {**totals, "total_cost_usd": round(total_cost, 6),
                     "total_steps": len(steps)}
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": run_id,
        "agent": {
            "name": AGENT_NAME,
            "version": agent_version or _kit_version(),
            "model_name": model,
        },
        "steps": steps,
        "final_metrics": final_metrics,
        "extra": {
            "utc": utc,
            "llm_call_count": llm_call_count,
            "passed": results_payload.get("passed"),
            "total": results_payload.get("total"),
        },
    }


def validate_atif(traj: dict) -> list[str]:
    """Structural checks against the Harbor RFC v1.7 tables.

    Returns a list of human-readable errors (empty = valid). Scope: the
    tables this exporter produces — root metadata, Agent, StepObject,
    ToolCall, Observation(Result), Metrics, FinalMetrics. Skips the
    RL-oriented `token_ids`/`logprobs` fields (roadmap non-goal) and the
    multimodal/audio tables (v1.6/v1.8 content this exporter never emits).
    """
    errors: list[str] = []

    def err(path: str, problem: str) -> None:
        errors.append(f"{path}: {problem}")

    if not isinstance(traj, dict):
        return ["trajectory: must be a JSON object"]
    if not traj.get("schema_version"):
        err("schema_version", "required field is missing")
    elif traj["schema_version"] != SCHEMA_VERSION:
        err("schema_version", f"expected {SCHEMA_VERSION}, got "
            f"{traj['schema_version']!r}")
    agent = traj.get("agent")
    if not isinstance(agent, dict):
        err("agent", "required object is missing")
    else:
        if not agent.get("name"):
            err("agent.name", "required field is missing")
        if not agent.get("version"):
            err("agent.version", "required field is missing")
    steps = traj.get("steps")
    if not isinstance(steps, list) or not steps:
        err("steps", "required non-empty array is missing")
        return errors
    call_ids = set()
    for index, step in enumerate(steps):
        path = f"steps.{index}"
        if not isinstance(step, dict):
            err(path, "step must be an object")
            continue
        sid = step.get("step_id")
        if sid != index + 1:
            err(f"{path}.step_id", f"expected {index + 1} "
                f"(sequential from 1), got {sid!r}")
        if step.get("source") not in _SOURCES:
            err(f"{path}.source", f"must be one of {list(_SOURCES)}, got "
                f"{step.get('source')!r}")
        if "message" not in step or not isinstance(step["message"], str):
            err(f"{path}.message", "required string is missing")
        if step.get("source") != "agent":
            for agent_only in ("model_name", "metrics", "tool_calls",
                               "reasoning_content"):
                if agent_only in step:
                    err(f"{path}.{agent_only}",
                        "agent-only field on non-agent step")
        for call in step.get("tool_calls", []) or []:
            cpath = f"{path}.tool_calls"
            if not isinstance(call, dict):
                err(cpath, "tool call must be an object")
                continue
            if not call.get("tool_call_id"):
                err(f"{cpath}.tool_call_id", "required field is missing")
            else:
                call_ids.add(call["tool_call_id"])
            if not call.get("function_name"):
                err(f"{cpath}.function_name", "required field is missing")
            if not isinstance(call.get("arguments"), dict):
                err(f"{cpath}.arguments", "required object is missing")
        obs = step.get("observation")
        if obs is not None:
            if not isinstance(obs, dict) or not isinstance(
                    obs.get("results"), list):
                err(f"{path}.observation.results",
                    "required array is missing")
                continue
            for ri, result in enumerate(obs["results"]):
                rpath = f"{path}.observation.results.{ri}"
                if not isinstance(result, dict):
                    err(rpath, "result must be an object")
                    continue
                ref = result.get("source_call_id")
                if ref is not None and ref not in call_ids:
                    err(f"{rpath}.source_call_id",
                        f"references unknown tool_call_id {ref!r}")
        metrics = step.get("metrics")
        if metrics is not None and not isinstance(metrics, dict):
            err(f"{path}.metrics", "must be an object when present")
    fm = traj.get("final_metrics")
    if fm is not None:
        if not isinstance(fm, dict):
            err("final_metrics", "must be an object when present")
        elif fm.get("total_steps") is not None \
                and fm["total_steps"] != len(steps):
            err("final_metrics.total_steps",
                f"expected {len(steps)} (len of steps), got "
                f"{fm['total_steps']!r}")
    return errors


def _load_document(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise AtifValidationError("results document must be a JSON object")
    for key in ("run_id", "utc"):
        if not doc.get(key):
            raise AtifValidationError(f"results document.{key} is missing")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", required=True, metavar="PATH",
                    help="schema-v1 results JSON document")
    ap.add_argument("--out", dest="out", required=True, metavar="PATH",
                    help="destination ATIF trajectory JSON path")
    ap.add_argument("--agent-version", default=None, metavar="V",
                    help="agent.version stamp (default: the kit VERSION)")
    args = ap.parse_args()
    try:
        sys.path.insert(0, str(HERE))
        doc = _load_document(Path(args.src))
        traj = to_atif(
            {k: v for k, v in doc.items()
             if k not in ("schema_version", "run_id", "kind", "model",
                          "utc", "executor_name", "harness_sha")},
            run_id=doc["run_id"], model=doc.get("model", "unspecified"),
            utc=doc["utc"], agent_version=args.agent_version)
        errors = validate_atif(traj)
        if errors:
            print("ATIF validation failed:\n  - " + "\n  - ".join(errors),
                  file=sys.stderr)
            return 1
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(traj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except (AtifValidationError, OSError, json.JSONDecodeError) as exc:
        print(f"atif_export: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001, S110 — optional, lives without it
        pass
    sys.exit(main())
