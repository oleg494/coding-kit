"""Wave 2 v3.6.0 Task 7: MAST labels for coordination failures.

MAST (Multi-Agent System Failure Taxonomy, arXiv:2503.13657): 14 failure
modes across 3 categories (FC1 System Design Issues, FC2 Inter-Agent
Misalignment, FC3 Task Verification). The kit vocabulary lives in
task_runner.MAST_MODES; scenario frontmatter carries optional
`mast: FM-x.y`; results rows MAY carry `mast_mode`; trend renders a
failure-mode histogram and flags unknown ids.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import results_io
import runner
import trend
from task_runner import MAST_MODES

TAXONOMY_DOC = ROOT / "docs" / "mast-taxonomy.md"


# 7.1 — taxonomy file + MAST_MODES integrity ---------------------------------


def test_taxonomy_doc_exists_under_300_lines():
    assert TAXONOMY_DOC.is_file()
    lines = TAXONOMY_DOC.read_text(encoding="utf-8").count("\n")
    assert lines < 300, f"mast-taxonomy.md must stay under 300 lines, has {lines}"


def test_taxonomy_lists_all_14_modes_in_3_categories():
    text = TAXONOMY_DOC.read_text(encoding="utf-8")
    ids = set(re.findall(r"FM-[123]\.\d", text))
    assert set(MAST_MODES) <= ids, "every MAST_MODES id must appear in the doc"
    assert len(MAST_MODES) == 14
    assert {m.split(".")[0] for m in MAST_MODES} == {"FM-1", "FM-2", "FM-3"}
    # verbatim source attribution
    assert "2503.13657" in text or "multi-agent-systems-failure-taxonomy" in text


def test_mast_mode_names_are_short_and_distinct():
    names = list(MAST_MODES.values())
    assert len(set(names)) == 14
    assert all(3 <= len(n) <= 48 for n in names)


def test_results_row_may_carry_mast_mode(tmp_path):
    res = tmp_path / "r"
    results_io.save_result(
        "trap", "m1",
        {"mode": "live",
         "scenarios": [{"name": "false-done", "verdict": "FAIL",
                        "mast_mode": "FM-3.1"}]},
        results_dir=res)
    doc = results_io.load_runs("trap", results_dir=res)[-1]
    sc = doc["scenarios"][0]
    assert sc["mast_mode"] == "FM-3.1"  # payload keys pass through untouched


# 7.2 — scenario frontmatter backfill ----------------------------------------


def test_five_highest_signal_scenarios_carry_mast():
    expected = {
        "false-done": "FM-3.1",
        "silent-failure": "FM-3.2",
        "weakened-test": "FM-3.3",
        "contract-drift": "FM-1.1",
        "silent-cross-write": "FM-2.6",
    }
    for name, mode in expected.items():
        text = (ROOT / "eval" / "scenarios" / f"{name}.md").read_text(
            encoding="utf-8")
        m = re.search(r"^mast:\s*(FM-\d\.\d)\s*$", text, re.MULTILINE)
        assert m, f"{name}.md must carry `mast: {mode}` frontmatter"
        assert m.group(1) == mode
        assert mode in MAST_MODES


def test_backfilled_scenarios_still_parse():
    # parse() must still see the required keys with the new field present
    sys.path.insert(0, str(ROOT / "eval"))
    import runner
    for name in ("false-done", "silent-failure", "weakened-test",
                 "contract-drift", "silent-cross-write"):
        sc = runner.parse(
            (ROOT / "eval" / "scenarios" / f"{name}.md").read_text(
                encoding="utf-8"))
        assert all(k in sc for k in ("name", "skill", "trap", "expect"))


# trend histogram + unknown-mode flag ----------------------------------------


def test_mast_histogram_counts_known_modes():
    doc = {"kind": "trap", "mode": "live", "scenarios": [
        {"name": "a", "verdict": "FAIL", "mast_mode": "FM-3.1"},
        {"name": "b", "verdict": "FAIL", "mast_mode": "FM-3.1"},
        {"name": "c", "verdict": "FAIL", "mast_mode": "FM-1.1"},
    ]}
    hist = trend._mast_histogram([doc])
    assert hist == {"FM-3.1": 2, "FM-1.1": 1}


def test_mast_histogram_ignores_unknown_mode():
    doc = {"kind": "trap", "mode": "live", "scenarios": [
        {"name": "a", "verdict": "FAIL", "mast_mode": "FM-9.9"},
    ]}
    assert trend._mast_histogram([doc]) == {}


def test_render_flags_unknown_mast_mode_and_shows_histogram(tmp_path):
    results_io.save_result(
        "trap", "mast-model",
        {"mode": "live", "scenarios": [
            {"name": "a", "verdict": "FAIL", "mast_mode": "FM-3.1"},
            {"name": "b", "verdict": "FAIL", "mast_mode": "FM-9.9"},
        ]}, results_dir=tmp_path)
    doc = results_io.load_runs("trap", results_dir=tmp_path)[-1]
    text = trend.render_mast_section([doc])
    assert "unknown mast_mode: FM-9.9" in text


# mast_mode persistence on runner result rows ---------------------------------


def _scenario_file(tmp_path, mast, valid=True):
    meta = "name: sc-mast\nskill: s1\ntrap: t1\nexpect: pass\n"
    if not valid:
        meta = "name: sc-mast\nskill: s1\ntrap: t1\n"  # missing expect -> skip row
    if mast:
        meta += f"mast: {mast}\n"
    f = tmp_path / ("sc_mast.md" if mast else "sc_nomast.md")
    f.write_text(meta + "\nbody", encoding="utf-8")
    return f


def test_capability_skip_fail_row_carries_mast_mode(tmp_path):
    f = _scenario_file(tmp_path, "FM-3.1", valid=False)
    rc, rows = runner._evaluate_scenarios(None, None, [f], repeat=1, timeout=1)
    assert rc == 1
    assert rows[0]["verdict"] == "FAIL" and rows[0]["attempts"] == []
    assert rows[0]["mast_mode"] == "FM-3.1"


def test_dry_run_pass_row_carries_mast_mode(tmp_path):
    f = _scenario_file(tmp_path, "FM-3.1")
    out = tmp_path / "dry.json"
    code = runner.run_scenarios(
        executor=None, judge=None, scenario_files=[f], json_out=out)
    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    row = doc["scenarios"][0]
    assert row["verdict"] == "PASS" and row["attempts"] == []
    assert row["mast_mode"] == "FM-3.1"


def test_live_final_row_carries_mast_mode(tmp_path, monkeypatch):
    f = _scenario_file(tmp_path, "FM-3.1")
    out = tmp_path / "live.json"
    monkeypatch.setattr(runner, "run_prompt", lambda cmd, prompt, timeout=600: "answer")
    monkeypatch.setattr(runner, "judge_one", lambda cmd, exp, ans, timeout=600: "PASS")
    code = runner.run_scenarios(
        executor=["mock_exe"], judge=["mock_judge"], scenario_files=[f],
        json_out=out, model="mast-live")
    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    row = doc["scenarios"][0]
    assert row["verdict"] == "PASS"
    assert row["mast_mode"] == "FM-3.1"


def test_unknown_mast_mode_is_preserved_not_invented(tmp_path):
    f = _scenario_file(tmp_path, "FM-9.9", valid=False)
    rc, rows = runner._evaluate_scenarios(None, None, [f], repeat=1, timeout=1)
    assert rc == 1
    assert rows[0]["mast_mode"] == "FM-9.9"
    assert "FM-9.9" not in MAST_MODES  # row keeps the raw id; trend flags it


def test_missing_mast_frontmatter_means_no_mast_mode_key(tmp_path):
    f = _scenario_file(tmp_path, None, valid=False)
    rc, rows = runner._evaluate_scenarios(None, None, [f], repeat=1, timeout=1)
    assert rc == 1
    assert "mast_mode" not in rows[0]


def test_mast_mode_rows_are_trend_compatible(tmp_path):
    f = _scenario_file(tmp_path, "FM-3.1", valid=False)
    rc, rows = runner._evaluate_scenarios(None, None, [f], repeat=1, timeout=1)
    assert rc == 1
    doc = {"kind": "trap", "mode": "live", "scenarios": rows}
    assert trend._mast_histogram([doc]) == {"FM-3.1": 1}
    text = trend.render_mast_section([doc])
    assert "FM-3.1" in text and "Premature termination" in text
