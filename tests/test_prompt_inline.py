"""CLI/wiring tests for runner.py controlled prompt-assembly (--inline-skills)."""
import subprocess
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import runner


def _scenario(path: Path, name="sc", skill="yagni") -> Path:
    path.write_text(
        f"name: {name}\nskill: {skill}\ntrap: t\nexpect: pass\n\nSCENARIO BODY",
        encoding="utf-8", newline="\n")
    return path


def _skill(root: Path, name: str) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: '{name} description'\n---\n\n"
        f"# {name}\n\n{name.upper()} BODY\n",
        encoding="utf-8", newline="\n")
    return d


def test_run_scenarios_inlines_active_skill_prompt(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    _skill(skills, "foo")
    sc = _scenario(tmp_path / "sc.md", skill="foo")

    prompts = []

    def fake_run_prompt(cmd, prompt, timeout=600):
        prompts.append(prompt)
        return "answer"

    monkeypatch.setattr(runner, "run_prompt", fake_run_prompt)
    monkeypatch.setattr(runner, "judge_one",
                        lambda cmd, expect, answer, timeout=600: "PASS")

    code = runner.run_scenarios(
        executor=["mock"], judge=["mock"], scenario_files=[sc],
        skills_root=skills)
    assert code == 0
    prompt = prompts[0]
    assert "FOO BODY" in prompt          # active skill body inlined
    assert "foo description" in prompt   # descriptor present
    assert "SCENARIO BODY" in prompt     # task body preserved


def test_run_scenarios_without_skills_root_uses_raw_body(tmp_path, monkeypatch):
    sc = _scenario(tmp_path / "sc.md", skill="foo")
    prompts = []

    monkeypatch.setattr(runner, "run_prompt",
                        lambda cmd, prompt, timeout=600: prompts.append(prompt) or "answer")
    monkeypatch.setattr(runner, "judge_one",
                        lambda cmd, expect, answer, timeout=600: "PASS")

    code = runner.run_scenarios(
        executor=["mock"], judge=["mock"], scenario_files=[sc])
    assert code == 0
    assert prompts[0] == "SCENARIO BODY"
    assert "Available skills:" not in prompts[0]


def test_run_scenarios_disable_active_skill_absent(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    _skill(skills, "foo")
    sc = _scenario(tmp_path / "sc.md", skill="foo")
    prompts = []

    monkeypatch.setattr(runner, "run_prompt",
                        lambda cmd, prompt, timeout=600: prompts.append(prompt) or "answer")
    monkeypatch.setattr(runner, "judge_one",
                        lambda cmd, expect, answer, timeout=600: "PASS")

    code = runner.run_scenarios(
        executor=["mock"], judge=["mock"], scenario_files=[sc],
        skills_root=skills, disable=frozenset({"foo"}))
    assert code == 0
    prompt = prompts[0]
    assert "FOO BODY" not in prompt
    assert "foo description" not in prompt
    assert "SCENARIO BODY" in prompt


def test_cli_rejects_unknown_disable_skill(tmp_path):
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "runner.py"),
         "--disable-skill", "definitely-not-a-real-skill"],
        capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "unknown --disable-skill" in r.stderr
    assert "definitely-not-a-real-skill" in r.stderr


def test_cli_inline_skills_dry_run_no_crash(tmp_path):
    out = tmp_path / "r.json"
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "runner.py"),
         "--inline-skills", "--disable-skill", "yagni",
         "--json", str(out)],
        capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_rejects_missing_skills_root(tmp_path):
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "runner.py"),
         "--skills-dir", str(tmp_path / "nope")],
        capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "skills root not found" in r.stderr




def test_runner_dry_run_usage_json_not_loaded(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    out = tmp_path / "o.json"
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "runner.py"),
         "--json", str(out), "--usage-json", str(bad)],
        capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "usage-json" not in r.stderr


def test_task_runner_dry_run_usage_json_not_loaded(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "task_runner.py"),
         "--dry-run", "--usage-json", str(bad)],
        capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "usage-json" not in r.stderr


def test_run_scenarios_raises_on_missing_skills_root(tmp_path):
    sc = _scenario(tmp_path / "sc.md", skill="foo")
    with pytest.raises(ValueError, match="skills root not found"):
        runner.run_scenarios(
            executor=["mock"], judge=["mock"], scenario_files=[sc],
            skills_root=tmp_path / "nope")


def test_run_scenarios_raises_on_unknown_disable(tmp_path):
    skills = tmp_path / "skills"
    _skill(skills, "foo")
    sc = _scenario(tmp_path / "sc.md", skill="foo")
    with pytest.raises(ValueError, match="unknown --disable-skill"):
        runner.run_scenarios(
            executor=["mock"], judge=["mock"], scenario_files=[sc],
            skills_root=skills, disable=frozenset({"not-a-real-skill"}))