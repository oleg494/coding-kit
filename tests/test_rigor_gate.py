import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from eval.rigor import gate

ROUTE_IDS = tuple(
    row["id"]
    for row in json.loads(
        (ROOT / "eval" / "rigor" / "route" / "cases.json").read_text(
            encoding="utf-8"
        )
    )
)


def _attempt(task_name: str, candidate: bool) -> dict:
    tier = gate.TASK_TIERS[task_name]
    return {
        "clean_pass": True,
        "agent_steps": 2 if candidate and tier == "FAST" else 4,
        "tool_calls": 2,
        "input_tokens": 100,
    }


def _model_result(candidate: bool) -> dict:
    return {
        "controlled": True,
        "route_results": [
            {
                "id": case_id,
                "repetition": repetition,
                "verdict": "PASS",
                "under_classified": False,
            }
            for case_id in ROUTE_IDS
            for repetition in range(1, 4)
        ],
        "task_results": [
            {
                "name": task_name,
                "verdict": "PASS",
                "attempts": [_attempt(task_name, candidate)],
            }
            for task_name in gate.TASK_TIERS
        ],
        "trap_results": [
            {"name": name, "verdict": "PASS", "clean": True}
            for name in gate.NAMED_TRAPS
        ],
    }


def _document(candidate: bool, models: tuple[str, ...] = ("model-a", "model-b")) -> dict:
    return {
        "policy_bytes": 100,
        "models": {name: _model_result(candidate) for name in models},
    }


def _evaluate(tmp_path: Path, baseline: dict, candidate: dict) -> dict:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    return gate.evaluate(baseline_path, candidate_path, harness_green=True)


def _findings(report: dict) -> str:
    return "\n".join(report["findings"])


def test_gate_accepts_complete_controlled_two_model_corpus(tmp_path):
    report = _evaluate(tmp_path, _document(False), _document(True))

    assert report["verdict"] == "ACCEPT"


def test_gate_rejects_fewer_than_two_model_arms(tmp_path):
    report = _evaluate(
        tmp_path,
        _document(False, ("model-a",)),
        _document(True, ("model-a",)),
    )

    assert report["verdict"] == "REJECT"
    assert "requires exactly 2 matching model arms" in _findings(report)


def test_gate_rejects_mismatched_model_arms(tmp_path):
    report = _evaluate(
        tmp_path,
        _document(False, ("model-a", "model-b")),
        _document(True, ("model-a", "model-c")),
    )

    assert report["verdict"] == "REJECT"


def test_gate_rejects_zero_overlapping_model_arms_without_vacuous_pass(
    tmp_path,
):
    report = _evaluate(
        tmp_path,
        _document(False, ("model-a", "model-b")),
        _document(True, ("model-c", "model-d")),
    )

    assert report["verdict"] == "REJECT"
    assert not report["conditions"]["2"]["ok"]
    assert not report["conditions"]["3"]["ok"]
    assert not report["conditions"]["4"]["ok"]
    assert not report["conditions"]["5"]["ok"]
    assert "model arm sets differ" in _findings(report)


def test_gate_rejects_uncontrolled_model_arm(tmp_path):
    candidate = _document(True)
    candidate["models"]["model-b"]["controlled"] = False

    report = _evaluate(tmp_path, _document(False), candidate)

    assert report["verdict"] == "REJECT"
    assert "candidate/model-b: uncontrolled" in _findings(report)


def test_gate_rejects_missing_microtask(tmp_path):
    candidate = _document(True)
    candidate["models"]["model-a"]["task_results"] = [
        row
        for row in candidate["models"]["model-a"]["task_results"]
        if row["name"] != "005-contract-change"
    ]

    report = _evaluate(tmp_path, _document(False), candidate)

    assert report["verdict"] == "REJECT"
    assert "candidate/model-a: missing task 005-contract-change" in _findings(report)


def test_gate_rejects_route_case_below_three_repetitions(tmp_path):
    candidate = _document(True)
    rows = candidate["models"]["model-a"]["route_results"]
    target = ROUTE_IDS[0]
    candidate["models"]["model-a"]["route_results"] = [
        row
        for row in rows
        if not (row["id"] == target and row["repetition"] == 3)
    ]

    report = _evaluate(tmp_path, _document(False), candidate)

    assert report["verdict"] == "REJECT"
    assert f"candidate/model-a: route {target} has 2 repetitions; need >= 3" in _findings(report)


def test_gate_rejects_duplicate_trap_masking_missing_trap(tmp_path):
    candidate = _document(True)
    traps = candidate["models"]["model-a"]["trap_results"]
    traps[-1] = deepcopy(traps[0])

    report = _evaluate(tmp_path, _document(False), candidate)

    assert report["verdict"] == "REJECT"
    assert "candidate/model-a: trap coverage mismatch" in _findings(report)


def test_gate_rejects_more_than_two_task_attempts(tmp_path):
    candidate = _document(True)
    row = candidate["models"]["model-a"]["task_results"][0]
    row["attempts"] = [deepcopy(row["attempts"][0]) for _ in range(3)]

    report = _evaluate(tmp_path, _document(False), candidate)

    assert report["verdict"] == "REJECT"
    assert "candidate/model-a/001-doc-typo: 3 attempts; maximum 2" in _findings(
        report
    )
