"""Offline contract for eval/memory_experiment.py (CK-04 preparation).

The evaluator never calls a model: `prepare` exports session A/B inputs and
`grade` scores answers produced elsewhere. These tests pin the properties the
benchmark's validity depends on — runs cannot be reused (no leakage between
runs), the memory arm retrieves notes from native storage while the inline arm carries
the identical note as context (information-parity control), missing attempts
are never counted as failures, and only well-formed answers are graded.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import memory_experiment


def _notes(cases):
    return {c["id"]: {"note": f"{c['decision']['id']} ({c['decision']['date']})"}
            for c in cases}


def test_session_a_export_carries_the_decision_and_no_arms(tmp_path):
    result = memory_experiment.prepare(tmp_path / "a", None)
    assert result["session"] == "A"
    assert result["model_runs"] == 0, "preparation must not run a model"
    for case in memory_experiment.load_cases()["cases"]:
        root = tmp_path / "a" / case["id"]
        doc = json.loads((root / "session_a.json").read_text(encoding="utf-8"))
        assert doc["decision"] == case["decision"]
        assert sorted(p.name for p in root.iterdir()) == ["session_a.json"]


def test_session_b_separates_retrieval_arm_from_inline_control(tmp_path):
    cases = memory_experiment.load_cases()["cases"]
    notes = _notes(cases)
    memory_experiment.prepare(tmp_path / "b", notes)
    for case in cases:
        root = tmp_path / "b" / case["id"]
        entry = {"id": case["decision"]["id"], "note": notes[case["id"]]["note"]}

        memory_input = json.loads((root / "memory" / "input.json").read_text(encoding="utf-8"))
        assert "inline_context" not in memory_input
        memory_root = root / "memory" / memory_input["memory_path"]
        stored = json.loads(memory_experiment.memory_command(
            memory_root, ["search", case["id"], "--json"]))
        assert len(stored) == 1
        assert stored[0]["source"] == entry["id"]
        for other in cases:
            if other["id"] != case["id"]:
                assert json.loads(memory_experiment.memory_command(
                    memory_root, ["search", other["id"], "--json"])) == []

        inline_input = json.loads((root / "inline" / "input.json").read_text(encoding="utf-8"))
        assert inline_input["inline_context"] == entry
        assert "memory_path" not in inline_input
        assert not (root / "inline" / "notes.json").exists()

        control = json.loads((root / "repository_only" / "input.json").read_text(encoding="utf-8"))
        assert "memory_path" not in control and "inline_context" not in control
        for arm in memory_experiment.ARMS:
            arm_input = json.loads((root / arm / "input.json").read_text(encoding="utf-8"))
            assert arm_input["repository"] == case["repository"]
            assert arm_input["actions"] == case["actions"]


def test_prepare_refuses_to_reuse_an_export_directory(tmp_path):
    memory_experiment.prepare(tmp_path / "run", None)
    with pytest.raises(FileExistsError):
        memory_experiment.prepare(tmp_path / "run", None)


def test_prepare_rejects_an_empty_note(tmp_path):
    case_id = memory_experiment.load_cases()["cases"][0]["id"]
    with pytest.raises(ValueError, match=case_id):
        memory_experiment.prepare(tmp_path / "b", {case_id: {"note": "   "}})


def test_grade_keeps_missing_attempts_out_of_the_failure_count():
    case = memory_experiment.load_cases()["cases"][0]
    result = memory_experiment.grade({})
    assert {row["status"] for row in result["rows"]} == {"missing"}
    assert len(result["rows"]) == len(memory_experiment.load_cases()["cases"]) * len(memory_experiment.ARMS)


def test_grade_flags_malformed_answers_and_scores_well_formed_ones():
    case = memory_experiment.load_cases()["cases"][0]
    answers = {
        case["id"]: {
            "memory": {"action": case["expected"], "evidence": [case["required_source"]],
                       "retrieved": [case["decision"]["id"]]},
            "inline": {"action": case["expected"]},
            "repository_only": {"action": case["actions"][1], "evidence": [], "retrieved": []},
        }
    }
    rows = {(row["case"], row["arm"]): row for row in memory_experiment.grade(answers)["rows"]}

    best = rows[(case["id"], "memory")]
    assert best["status"] == "observed"
    assert best["correct"] is True and best["provenance"] is True and best["retrieval_claimed"] is True

    wrong = rows[(case["id"], "repository_only")]
    assert wrong["status"] == "observed" and wrong["correct"] is False
    assert wrong["provenance"] is False and wrong["retrieval_claimed"] is False

    assert rows[(case["id"], "inline")]["status"] == "invalid"
    assert rows[(memory_experiment.load_cases()["cases"][1]["id"], "memory")]["status"] == "missing"
