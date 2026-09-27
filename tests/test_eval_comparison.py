"""Comparison cohorts follow exercised inputs, never scores or file locations."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import runner
import trigger_eval


@pytest.fixture
def corpus(tmp_path):
    skills = tmp_path / "skills"
    skill = skills / "sample" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: sample\ndescription: sample description\n---\nKeep scope.\n", encoding="utf-8")
    cases = []
    for name in ("first", "second"):
        case = tmp_path / (name + ".md")
        case.write_text(f"name: {name}\nskill: sample\ntrap: wrong choice\nexpect: preserve scope\n\nFix {name} only.", encoding="utf-8")
        cases.append(case)
    return skills, skill, cases


def test_trap_conditions_change_only_with_inputs(tmp_path, monkeypatch, corpus):
    skills, skill, cases = corpus
    executor = {"mode": "container", "argv": ["agent", "--secret", "PRIVATE_SENTINEL"],
                "image": "local", "network": False, "mounts": ()}
    monkeypatch.setattr(runner, "run_prompt", lambda *a, **k: "answer")
    monkeypatch.setattr(runner, "judge_one", lambda *a, **k: "PASS")
    results = []

    def run(*, selected=None, inline=False, repeat=1, judge=None):
        out = tmp_path / f"run-{len(results)}.json"
        runner.run_scenarios(executor, judge, cases if selected is None else selected,
                             skills_root=skills if inline else None, repeat=repeat,
                             json_out=out, model="test-model")
        doc = json.loads(out.read_text(encoding="utf-8"))
        results.append(doc)
        assert "PRIVATE_SENTINEL" not in json.dumps(doc)
        assert len(doc["comparison_id"]) == 64
        return doc["comparison_id"]

    bare = run()
    assert run(selected=list(reversed(cases))) == bare
    monkeypatch.setattr(runner, "judge_one", lambda *a, **k: "FAIL")
    assert run() == bare  # A failed answer is comparable to a passed answer.
    inline = run(inline=True)
    assert inline != bare
    assert run(selected=[cases[0]]) != bare
    assert run(repeat=2) != bare
    assert run(judge={**executor, "image": "different-judge"}) != bare
    skill.write_text(skill.read_text(encoding="utf-8") + "Do not expand the goal.\n", encoding="utf-8")
    assert run(inline=True) != inline
    assert run() == bare  # An unconsumed skill must not alter bare-prompt identity.
    cases[0].write_text(cases[0].read_text(encoding="utf-8").replace("preserve scope", "repair completely"), encoding="utf-8")
    assert run() != bare


def test_trap_fingerprints_executed_snapshot_not_later_edits(tmp_path, monkeypatch, corpus):
    skills, skill, cases = corpus
    prompts = []
    original = skill.read_text(encoding="utf-8")

    def backend(cmd, prompt, timeout=600):
        prompts.append(prompt)
        skill.write_text(original + "Changed while executor ran.\n", encoding="utf-8")
        return "answer"

    monkeypatch.setattr(runner, "run_prompt", backend)
    monkeypatch.setattr(runner, "judge_one", lambda *a, **k: "PASS")
    def run(name):
        out = tmp_path / name
        runner.run_scenarios(["executor"], None, cases[:1], repeat=2,
                             skills_root=skills, json_out=out, model="m")
        return json.loads(out.read_text(encoding="utf-8"))["comparison_id"]

    first = run("first.json")
    assert prompts[0] == prompts[1]
    skill.write_text(original, encoding="utf-8")
    assert run("same.json") == first
    assert run("changed.json") != first


def test_trigger_cohorts_track_listing_expectations_and_selection(tmp_path, monkeypatch):
    queries = [
        {"skill": "yagni", "query": "Do the requested work", "should": True},
        {"skill": "yagni", "query": "A greeting", "should": False},
        {"skill": "testing-discipline", "query": "A greeting", "should": True},
        {"skill": "testing-discipline", "query": "Do the requested work", "should": False},
    ]
    query_file = tmp_path / "queries.json"
    listing = [{"name": "yagni", "description": "Keep scope"},
               {"name": "testing-discipline", "description": "Check behavior"}]
    monkeypatch.setattr(trigger_eval, "listing_entries", lambda: listing)
    monkeypatch.setattr(trigger_eval, "run_prompt", lambda cmd, prompt, **kw:
                        "SKILLS LOADED: yagni" if "Do the requested work" in prompt
                        else "SKILLS LOADED: testing-discipline")
    index = 0
    def run(rows, *extra):
        nonlocal index
        index += 1
        query_file.write_text(json.dumps(rows), encoding="utf-8")
        out = tmp_path / f"trigger-{index}.json"
        monkeypatch.setattr(sys, "argv", ["trigger_eval.py", "--queries", str(query_file),
                            "--executor", "docker:local agent", "--model", "m",
                            "--runs", "1", "--json", str(out), *extra])
        trigger_eval.main()
        return json.loads(out.read_text(encoding="utf-8"))["comparison_id"]

    baseline = run(queries)
    assert len(baseline) == 64
    assert run(list(reversed(queries))) == baseline
    assert run(queries, "--only", "yagni") != baseline
    changed = [{**row, "should": not row["should"]} for row in queries]
    assert run(changed) != baseline
    listing[0]["description"] = "Finish requested work without extra architecture"
    assert run(queries) != baseline


def test_trigger_repeats_use_one_snapshot(monkeypatch):
    listing = [{"name": "yagni", "description": "Keep scope"}]
    monkeypatch.setattr(trigger_eval, "listing_entries", lambda: listing)
    prompts = []
    def backend(cmd, prompt, **kw):
        prompts.append(prompt)
        listing[0]["description"] = "Changed during first call"
        return "SKILLS LOADED: yagni"
    monkeypatch.setattr(trigger_eval, "run_prompt", backend)
    trigger_eval.run_query_detailed(["executor"],
                                   {"skill": "yagni", "should": True, "query": "Implement this"}, 2)
    assert prompts[0] == prompts[1]


def test_invalid_trap_case_cannot_share_valid_subset_identity(tmp_path, monkeypatch, corpus):
    _, _, cases = corpus
    invalid = tmp_path / "invalid.md"
    invalid.write_text("name: invalid\nskill: sample\ntrap: missing expectation\n\nbody", encoding="utf-8")
    monkeypatch.setattr(runner, "run_prompt", lambda *a, **k: "answer")
    monkeypatch.setattr(runner, "judge_one", lambda *a, **k: "PASS")
    out = tmp_path / "partial.json"
    assert runner.run_scenarios(["executor"], None, [cases[0], invalid],
                                json_out=out, model="m") == 1
    assert json.loads(out.read_text(encoding="utf-8"))["comparison_id"] is None


def test_trigger_worker_failure_cannot_share_valid_subset_identity(tmp_path, monkeypatch):
    queries = tmp_path / "queries.json"
    queries.write_text(json.dumps([
        {"skill": "yagni", "query": "positive", "should": True},
        {"skill": "yagni", "query": "negative", "should": False},
    ]), encoding="utf-8")
    original = trigger_eval.run_query_detailed
    def worker(cmd, query, *args, **kwargs):
        if query["query"] == "negative":
            raise RuntimeError("worker failed before snapshot")
        return original(cmd, query, *args, **kwargs)
    monkeypatch.setattr(trigger_eval, "run_query_detailed", worker)
    monkeypatch.setattr(trigger_eval, "run_prompt", lambda *a, **k: "SKILLS LOADED: yagni")
    out = tmp_path / "partial.json"
    monkeypatch.setattr(sys, "argv", ["trigger_eval.py", "--queries", str(queries),
                        "--executor", "docker:local agent", "--model", "m", "--json", str(out)])
    trigger_eval.main()
    assert json.loads(out.read_text(encoding="utf-8"))["comparison_id"] is None
