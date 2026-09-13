"""Contract tests for eval/ablate.py — skill ablation (pure + persistence)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import ablate
from ablate import ablation_result, discover_ablations, run_ablation
from rigor import container

MOCK_SPEC = "docker:python:3.12-alpine python"
# resolve_cmd only parses the spec (no backend probing), so the rows-level
# tests below run without a live daemon; _evaluate_scenarios is faked.
_MOCK_RECORD = ablate.resolve_cmd(MOCK_SPEC)
_RUNTIME = container.docker_status()
_SKIP_REASON = f"no container runtime: {_RUNTIME.get('reason', 'unavailable')}"


def _row(name, skill, verdict, duration=1.0):
    return {"name": name, "skill": skill, "verdict": verdict,
            "attempts": [{"verdict": verdict, "phase": "verdict",
                          "duration_s": duration}]}


def _scenario(tmp_path, fname, skill):
    p = tmp_path / fname
    p.write_text(
        f"name: {fname[:-3]}\nskill: {skill}\ntrap: t\nexpect: e\n\nbody",
        encoding="utf-8", newline="\n")
    return p


def _write_skill(root, name):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: '{name} desc'\n---\n\n# {name}\n\nbody\n",
        encoding="utf-8", newline="\n")
    return d


def test_discover_ablations_reads_scenario_frontmatter(tmp_path):
    (tmp_path / "a.md").write_text(
        "name: a\nskill: yagni\ntrap: x\nexpect: y\n\nbody", encoding="utf-8")
    (tmp_path / "b.md").write_text(
        "name: b\nskill: yagni\ntrap: x\nexpect: y\n\nbody", encoding="utf-8")
    (tmp_path / "c.md").write_text(
        "name: c\nskill: fable-judge\ntrap: x\nexpect: y\n\nbody", encoding="utf-8")
    assert discover_ablations(sorted(tmp_path.glob("*.md"))) == ["fable-judge", "yagni"]


def test_ablation_result_computes_delta():
    baseline = [_row("a", "yagni", "PASS"), _row("b", "yagni", "FAIL")]
    ablated = {"yagni": [_row("a", "yagni", "PASS"), _row("b", "yagni", "PASS")]}
    res = ablation_result(baseline, ablated)
    entry = res["per_skill"][0]
    assert entry["skill"] == "yagni"
    assert entry["pass_rate_with"] == 0.5
    assert entry["pass_rate_without"] == 1.0
    assert entry["delta"] == round(0.5 - 1.0, 3)


def test_ablation_result_skill_absent_from_baseline():
    res = ablation_result([_row("a", "yagni", "PASS")], {"missing": []})
    assert res["per_skill"] == []


def test_ablation_result_scenario_count():
    baseline = [_row("a", "yagni", "PASS"), _row("b", "yagni", "PASS"),
                _row("c", "yagni", "FAIL")]
    res = ablation_result(baseline, {"yagni": []})
    assert res["per_skill"][0]["scenarios_affected"] == 3


def _fake_eval(rows_by_disable):
    def fake(executor, judge, files, repeat, timeout,
             skills_root=None, disable=frozenset()):
        key = frozenset(disable) if isinstance(disable, frozenset) else frozenset()
        return 0, rows_by_disable[key]
    return fake


def test_run_ablation_persists_single_doc(tmp_path, monkeypatch):
    files = [_scenario(tmp_path, "a.md", "yagni"),
             _scenario(tmp_path, "b.md", "fable-judge")]
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")
    _write_skill(skills, "fable-judge")

    rows = {
        frozenset(): [
            _row("a", "yagni", "PASS", 1.0),
            _row("b", "fable-judge", "FAIL", 2.0),
        ],
        frozenset({"yagni"}): [_row("a", "yagni", "FAIL", 3.0)],
        frozenset({"fable-judge"}): [_row("b", "fable-judge", "PASS", 4.0)],
    }
    monkeypatch.setattr(ablate, "_evaluate_scenarios", _fake_eval(rows))

    out = tmp_path / "ab.json"
    rc = run_ablation(
        executor=_MOCK_RECORD, judge=_MOCK_RECORD, scenario_files=files,
        skills_root=skills, repeat=1, timeout=30, model="m1",
        executor_spec=MOCK_SPEC, json_out=out,
        reported_usage={"tokens_total": 10, "cost_usd": 0.5})
    assert rc == 0

    docs = list(tmp_path.glob("*.json"))
    assert len(docs) == 1  # exactly one doc, no intermediate trap docs
    doc = json.loads(docs[0].read_text(encoding="utf-8"))
    assert doc["kind"] == "ablate"
    assert doc["metric"] == "inlined-prompt contribution"
    assert doc["experimental"] is True
    assert doc["ambient_skills_controlled"] is False
    assert doc["repeat"] == 1
    assert doc["duration_s_total"] == 10.0
    assert doc["duration_s_mean"] == 2.5
    assert doc["reported_usage"] == {"tokens_total": 10, "cost_usd": 0.5}
    assert {e["skill"] for e in doc["per_skill"]} == {"yagni", "fable-judge"}


def test_run_ablation_no_json_writes_nothing(tmp_path, monkeypatch):
    files = [_scenario(tmp_path, "a.md", "yagni")]
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")
    rows = {frozenset(): [_row("a", "yagni", "PASS")],
            frozenset({"yagni"}): [_row("a", "yagni", "PASS")]}
    monkeypatch.setattr(ablate, "_evaluate_scenarios", _fake_eval(rows))

    rc = run_ablation(
        executor=_MOCK_RECORD, judge=_MOCK_RECORD, scenario_files=files,
        skills_root=skills, repeat=1, timeout=30, model="m1", json_out=None)
    assert rc == 0
    assert list(tmp_path.glob("*.json")) == []


def test_run_ablation_requires_executor():
    with pytest.raises(ValueError, match="executor"):
        run_ablation(executor=None, judge=None, scenario_files=[],
                     skills_root=Path("."), repeat=1, timeout=30, model="m1")


def test_run_ablation_no_executor_answer_returns_2(tmp_path, monkeypatch):
    files = [_scenario(tmp_path, "a.md", "yagni")]
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")

    def fake_eval(executor, judge, files, repeat, timeout,
                  skills_root=None, disable=frozenset()):
        rows = [{
            "name": "a", "skill": "yagni", "verdict": "FAIL",
            "attempts": [{
                "verdict": "FAIL", "phase": "executor", "duration_s": 0.0,
                "error": "executor FileNotFoundError: no such command",
            }],
        }]
        return 1, rows

    monkeypatch.setattr(ablate, "_evaluate_scenarios", fake_eval)
    out = tmp_path / "ab.json"
    rc = run_ablation(
        executor=_MOCK_RECORD, judge=_MOCK_RECORD, scenario_files=files,
        skills_root=skills, repeat=1, timeout=30, model="m1", json_out=out)
    assert rc == 2
    assert not out.exists()


def test_run_ablation_treatment_no_executor_answer_returns_2(tmp_path, monkeypatch):
    files = [_scenario(tmp_path, "a.md", "yagni")]
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")

    def fake_eval(executor, judge, files, repeat, timeout,
                  skills_root=None, disable=frozenset()):
        if not disable:
            # baseline: executor answered, judge -> PASS
            return 0, [{
                "name": "a", "skill": "yagni", "verdict": "PASS",
                "attempts": [{"verdict": "PASS", "phase": "verdict",
                              "duration_s": 1.0}],
            }]
        # treatment: every attempt is an executor-phase failure
        return 1, [{
            "name": "a", "skill": "yagni", "verdict": "FAIL",
            "attempts": [{"verdict": "FAIL", "phase": "executor",
                          "duration_s": 0.0, "error": "executor OSError"}],
        }]

    monkeypatch.setattr(ablate, "_evaluate_scenarios", fake_eval)
    out = tmp_path / "ab.json"
    rc = run_ablation(
        executor=_MOCK_RECORD, judge=_MOCK_RECORD, scenario_files=files,
        skills_root=skills, repeat=1, timeout=30, model="m1", json_out=out)
    assert rc == 2
    assert not out.exists()


def test_run_ablation_baseline_judge_failure_returns_2(tmp_path, monkeypatch):
    files = [_scenario(tmp_path, "a.md", "yagni")]
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")

    def fake_eval(executor, judge, files, repeat, timeout,
                  skills_root=None, disable=frozenset()):
        # baseline: executor answered but the judge phase failed (infra)
        return 1, [{
            "name": "a", "skill": "yagni", "verdict": "FAIL",
            "attempts": [{"verdict": "FAIL", "phase": "judge",
                          "duration_s": 0.0, "error": "judge OSError"}],
        }]

    monkeypatch.setattr(ablate, "_evaluate_scenarios", fake_eval)
    out = tmp_path / "ab.json"
    rc = run_ablation(
        executor=_MOCK_RECORD, judge=_MOCK_RECORD, scenario_files=files,
        skills_root=skills, repeat=1, timeout=30, model="m1", json_out=out)
    assert rc == 2
    assert not out.exists()


def test_run_ablation_treatment_judge_failure_returns_2(tmp_path, monkeypatch):
    files = [_scenario(tmp_path, "a.md", "yagni")]
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")

    def fake_eval(executor, judge, files, repeat, timeout,
                  skills_root=None, disable=frozenset()):
        if not disable:
            # baseline: fully comparable verdict-phase PASS
            return 0, [{
                "name": "a", "skill": "yagni", "verdict": "PASS",
                "attempts": [{"verdict": "PASS", "phase": "verdict",
                              "duration_s": 1.0}],
            }]
        # treatment: executor answered but the judge phase failed (infra)
        return 1, [{
            "name": "a", "skill": "yagni", "verdict": "FAIL",
            "attempts": [{"verdict": "FAIL", "phase": "judge",
                          "duration_s": 0.0, "error": "judge OSError"}],
        }]

    monkeypatch.setattr(ablate, "_evaluate_scenarios", fake_eval)
    out = tmp_path / "ab.json"
    rc = run_ablation(
        executor=_MOCK_RECORD, judge=_MOCK_RECORD, scenario_files=files,
        skills_root=skills, repeat=1, timeout=30, model="m1", json_out=out)
    assert rc == 2
    assert not out.exists()


def test_run_ablation_verdict_fail_is_not_infra_failure(tmp_path, monkeypatch):
    files = [_scenario(tmp_path, "a.md", "yagni")]
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")

    def fake_eval(executor, judge, files, repeat, timeout,
                  skills_root=None, disable=frozenset()):
        # verdict-phase FAIL (legitimate score) in both baseline and treatment
        return 1, [{
            "name": "a", "skill": "yagni", "verdict": "FAIL",
            "attempts": [{"verdict": "FAIL", "phase": "verdict",
                          "duration_s": 1.0}],
        }]

    monkeypatch.setattr(ablate, "_evaluate_scenarios", fake_eval)
    out = tmp_path / "ab.json"
    rc = run_ablation(
        executor=_MOCK_RECORD, judge=_MOCK_RECORD, scenario_files=files,
        skills_root=skills, repeat=1, timeout=30, model="m1", json_out=out)
    assert rc == 0
    assert out.exists()


def test_run_ablation_validates_before_evaluator(tmp_path, monkeypatch):
    calls = []

    def spy(executor, judge, files, repeat, timeout,
            skills_root=None, disable=frozenset()):
        calls.append(1)
        return 0, []

    monkeypatch.setattr(ablate, "_evaluate_scenarios", spy)
    with pytest.raises(ValueError, match="skills root not found"):
        run_ablation(
            executor=_MOCK_RECORD, judge=_MOCK_RECORD,
            scenario_files=[tmp_path / "a.md"],
            skills_root=tmp_path / "nope", repeat=1, timeout=30, model="m")
    assert calls == []


def test_run_ablation_rejects_no_scenario_files(tmp_path):
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")
    with pytest.raises(ValueError, match="no scenario files"):
        run_ablation(executor=_MOCK_RECORD, judge=_MOCK_RECORD, scenario_files=[],
                     skills_root=skills, repeat=1, timeout=30, model="m")


def test_validate_inputs_rejects_missing_skills_root(tmp_path):
    err = ablate.validate_inputs(
        skills_root=tmp_path / "nope", scenario_files=[tmp_path / "a.md"],
        repeat=1, timeout=30)
    assert err is not None
    assert "skills root not found" in err


def test_validate_inputs_rejects_unknown_skill(tmp_path):
    skills = tmp_path / "skills"
    _write_skill(skills, "yagni")
    sc = _scenario(tmp_path, "a.md", "not-a-skill")
    err = ablate.validate_inputs(
        skills_root=skills, scenario_files=[sc], repeat=1, timeout=30)
    assert "unknown skill" in err


def test_validate_inputs_rejects_bad_repeat_and_timeout(tmp_path):
    skills = tmp_path / "skills"
    _write_skill(skills, "y")
    err = ablate.validate_inputs(
        skills_root=skills, scenario_files=[], repeat=0, timeout=30)
    assert "--repeat" in err
    err = ablate.validate_inputs(
        skills_root=skills, scenario_files=[], repeat=1, timeout=0)
    assert "--timeout" in err


def test_validate_inputs_rejects_missing_metadata(tmp_path):
    skills = tmp_path / "skills"
    _write_skill(skills, "y")
    sc = tmp_path / "a.md"
    sc.write_text("name: a\nskill: y\ntrap: t\n\nbody", encoding="utf-8")
    err = ablate.validate_inputs(
        skills_root=skills, scenario_files=[sc], repeat=1, timeout=30)
    assert err is not None
    assert "expect" in err


def test_ablate_cli_rejects_host_executor_spec(tmp_path):
    """A bare host CLI must fail closed at the CLI: readable nonzero error,
    no traceback, no result document written."""
    out = tmp_path / "ab.json"
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "ablate.py"),
         "--executor", f"{sys.executable} -c print(1)",
         "--scenario", "premature-abstraction",
         "--model", "fixture",
         "--skills-dir", str(ROOT / "skills"),
         "--json", str(out)],
        capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode != 0
    assert "host prompt execution refused" in r.stderr
    assert "Traceback" not in r.stderr
    assert not out.exists()


def test_ablate_cli_help_documents_docker_executor():
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "ablate.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    assert "docker:" in r.stdout


@pytest.mark.skipif(not _RUNTIME["available"], reason=_SKIP_REASON)
def test_ablate_cli_end_to_end_confined_executor(tmp_path):
    """The whole ablation runs inside the container boundary: the fake
    executor is reachable only through the declared read-only mount, so a
    host-side script path would not run at all."""
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "fake_exec.py").write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        "if 'EXPECT:' in data:\n"
        "    sys.stdout.write('PASS\\n')\n"
        "else:\n"
        "    sys.stdout.write('ANSWER FROM FAKE\\n')\n",
        encoding="utf-8", newline="\n")
    out = tmp_path / "ab.json"
    spec = (f"docker:{container.DEFAULT_IMAGE} "
            f"@ro:{fixture.as_posix()}:/fixture python /fixture/fake_exec.py")
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "ablate.py"),
         "--executor", spec,
         "--scenario", "premature-abstraction",
         "--skills-dir", str(ROOT / "skills"),
         "--model", "fake-model",
         "--json", str(out),
         "--repeat", "1"],
        capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["kind"] == "ablate"
    assert doc["model"] == "fake-model"
    assert doc["per_skill"]
    assert doc["duration_s_total"] >= 0
    assert len(list(tmp_path.glob("*.json"))) == 1