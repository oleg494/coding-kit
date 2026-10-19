"""Offline contract for eval/memory_experiment.py (CK-04 preparation).

The evaluator never calls a model: `prepare` exports session A/B inputs and
`grade` scores answers produced elsewhere. These tests pin the properties the
benchmark's validity depends on — runs cannot be reused (no leakage between
runs), the memory arm retrieves notes from native storage while the inline arm carries
the identical note as context (information-parity control), missing attempts
are never counted as failures, and only well-formed answers are graded.
Store verification (`--verify-retrieval`) re-runs the real isolated search
and cross-checks memory-arm retrieval claims against actual tool output; it
is deterministic plumbing verification, not model-behavior evidence.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import memory_experiment


def _answers(cases, **overrides):
    """Well-formed B answers per case/arm; per-case overrides by case id."""
    out = {}
    for case in cases:
        out[case["id"]] = {
            "memory": {"action": case["expected"], "evidence": [case["required_source"]],
                       "retrieved": [case["decision"]["id"]]},
            "inline": {"action": case["expected"], "evidence": [case["required_source"]],
                       "retrieved": []},
            "repository_only": {"action": case["actions"][1], "evidence": [], "retrieved": []},
        }
        out[case["id"]].update(overrides.get(case["id"], {}))
    return out


def _memory_rows(result):
    return {row["case"]: row for row in result["rows"] if row["arm"] == "memory"}


def _notes(cases):
    return {c["id"]: {"note": f"{c['decision']['id']} ({c['decision']['date']})"}
            for c in cases}


def _prepare_with_notes(tmp_path, cases):
    prepared = tmp_path / "b"
    memory_experiment.prepare(prepared, _notes(cases))
    return prepared


def test_verify_retrieval_reads_real_store_output_for_every_case(tmp_path):
    cases = memory_experiment.load_cases()["cases"]
    prepared = _prepare_with_notes(tmp_path, cases)
    stores = memory_experiment.verify_retrieval(prepared)
    assert set(stores) == {case["id"] for case in cases}
    for case in cases:
        assert stores[case["id"]] == {case["decision"]["id"]}


def test_verify_retrieval_marks_unusable_stores_absent_not_failed(tmp_path):
    cases = memory_experiment.load_cases()["cases"]
    prepared = _prepare_with_notes(tmp_path, cases)
    shutil.rmtree(prepared / cases[0]["id"] / "memory" / "memory-root")
    stores = memory_experiment.verify_retrieval(prepared)
    assert stores == {case["id"]: {case["decision"]["id"]}
                      for case in cases if case is not cases[0]}


def test_grade_distinguishes_real_from_fabricated_retrieval(tmp_path):
    cases = memory_experiment.load_cases()["cases"]
    prepared = _prepare_with_notes(tmp_path, cases)
    stores = memory_experiment.verify_retrieval(prepared)
    # One case answers without any retrieval claim: the decision id IS in the
    # real store output, but with no claim there is nothing verified true.
    answers = _answers(cases, **{cases[0]["id"]: {
        "memory": {"action": cases[0]["expected"], "evidence": [], "retrieved": []}}})
    rows = _memory_rows(memory_experiment.grade(answers, stores))
    assert rows[cases[0]["id"]]["retrieval_claimed"] is False
    assert rows[cases[0]["id"]]["retrieval_verified"] is False
    for case in cases[1:]:
        assert rows[case["id"]]["retrieval_claimed"] is True
        assert rows[case["id"]]["retrieval_verified"] is True
    # Control arms never carry verification: they have no store to check.
    for row in memory_experiment.grade(answers, stores)["rows"]:
        if row["arm"] != "memory":
            assert "retrieval_verified" not in row


def test_grade_marks_claimed_retrieval_absent_from_store_as_unverified(tmp_path):
    cases = memory_experiment.load_cases()["cases"]
    prepared = _prepare_with_notes(tmp_path, cases)
    # Empty real search output for one case: claim must not pass.
    stores = memory_experiment.verify_retrieval(prepared)
    stores[cases[0]["id"]] = set()
    answers = _answers(cases)
    rows = _memory_rows(memory_experiment.grade(answers, stores))
    assert rows[cases[0]["id"]]["retrieval_claimed"] is True
    assert rows[cases[0]["id"]]["retrieval_verified"] is False
    assert rows[cases[1]["id"]]["retrieval_verified"] is True


def test_grade_without_store_verification_leaves_claims_self_reported():
    cases = memory_experiment.load_cases()["cases"]
    answers = _answers(cases)
    rows = _memory_rows(memory_experiment.grade(answers, None))
    for case in cases:
        assert rows[case["id"]]["retrieval_verified"] is None
    # Absent store entry is a real empty result from a usable store, not
    # the same as no verification: a claimed id that is not in real tool
    # output must fail verification.
    rows = _memory_rows(memory_experiment.grade(answers, {cases[0]["id"]: set()}))
    assert rows[cases[0]["id"]]["retrieval_verified"] is False


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
