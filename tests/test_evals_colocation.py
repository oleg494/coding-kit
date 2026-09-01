#!/usr/bin/env python3
"""Per-skill evals/evals.json co-location (wave3 Task 9).

Contract:
- load_queries(skills_root, legacy_path) -> list[Query] prefers
  skills/<slug>/evals/evals.json ({skill_name, evals: [{id, prompt,
  should_trigger}]}) and falls back to the central eval/trigger_queries.json
  for skills that lack the per-skill file. Central file stays as fallback
  source (never deleted).
- IDs are stable across the migration: <slug>-<n> (position within the
  skill's query list), so baselines pair before/after.
- Total query count is exactly 86 (wave4 Task 12): the 80 central rows
  migrated at wave3 plus 6 relocated-rule queries appended to the
  per-skill files (2 new: git-workflow-and-versioning, testing-discipline;
  +1 each: money-path-safety, security-and-hardening). No loss, no
  duplication (a query present in both sources is taken once).
- validate() still accepts the merged flat list (same {skill, should,
  query} rows + optional id).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "eval"))
import trigger_eval

CENTRAL = KIT / "eval" / "trigger_queries.json"


def write_evals(skill_dir: Path, slug: str, queries):
    d = skill_dir / slug / "evals"
    d.mkdir(parents=True)
    payload = {"skill_name": slug,
               "evals": [{"id": f"{slug}-{i}", "prompt": q,
                          "should_trigger": s}
                         for i, (q, s) in enumerate(queries)]}
    (d / "evals.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8", newline="\n")


def as_rows(queries):
    return [(q["skill"], q["query"], q["should"]) for q in queries]


class LoaderPrefersPerSkillTest(unittest.TestCase):
    def test_per_skill_file_wins_over_central(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_evals(root, "alpha", [("alpha per-skill q", True)])
            central = root / "central.json"
            central.write_text(json.dumps([
                {"skill": "alpha", "should": True, "query": "central q"}]),
                encoding="utf-8")
            got = trigger_eval.load_queries(root, central)
        self.assertEqual(as_rows(got),
                         [("alpha", "alpha per-skill q", True)])

    def test_fallback_for_skill_without_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_evals(root, "alpha", [("alpha per-skill q", True)])
            central = root / "central.json"
            central.write_text(json.dumps([
                {"skill": "alpha", "should": True, "query": "alpha q1"},
                {"skill": "beta", "should": False, "query": "beta near-miss"}]),
                encoding="utf-8")
            got = trigger_eval.load_queries(root, central)
        rows = as_rows(got)
        self.assertIn(("beta", "beta near-miss", False), rows)
        self.assertEqual(sum(1 for r in rows if r[0] == "alpha"), 1)

    def test_no_central_file_returns_per_skill_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_evals(root, "alpha", [("q1", True), ("q2", False)])
            got = trigger_eval.load_queries(root, root / "missing.json")
        self.assertEqual(len(got), 2)
        self.assertTrue(all(q["id"].startswith("alpha-") for q in got))


class MigrationShapeTest(unittest.TestCase):
    """Plan step 9.3 + wave4 Task 12: every skill dir with queries has
    evals.json; total count == 86 (80 central + 6 relocated-rule rows)."""

    TOTAL = 86

    def test_every_skill_with_queries_has_evals_json(self):
        central = json.loads(CENTRAL.read_text(encoding="utf-8"))
        slugs = {q["skill"] for q in central}
        missing = [s for s in sorted(slugs)
                   if not (KIT / "skills" / s / "evals" / "evals.json")
                   .is_file()]
        self.assertEqual(missing, [])

    def test_total_query_count_is_exactly_86(self):
        got = trigger_eval.load_queries(KIT / "skills", CENTRAL)
        self.assertEqual(len(got), self.TOTAL)

    def test_central_file_still_present(self):
        self.assertTrue(CENTRAL.is_file())
    def test_ids_stable_and_unique(self):
        got = trigger_eval.load_queries(KIT / "skills", CENTRAL)
        ids = [q["id"] for q in got]
        self.assertEqual(len(ids), len(set(ids)))
        # stable: every id is <slug>-<n> with n a small non-negative int
        for qid, q in zip(ids, got):
            self.assertTrue(qid.startswith(q["skill"] + "-"), qid)
            self.assertTrue(qid[len(q["skill"]) + 1:].isdigit(), qid)

    def test_merged_rows_are_central_plus_relocated_rules(self):
        central = json.loads(CENTRAL.read_text(encoding="utf-8"))
        got = trigger_eval.load_queries(KIT / "skills", CENTRAL)
        central_rows = sorted(as_rows(central))
        got_rows = sorted(as_rows(got))
        # every central row survives...
        for row in central_rows:
            self.assertIn(row, got_rows)
        # ...plus exactly the 6 wave4 relocated-rule rows
        extra = [r for r in got_rows if r not in central_rows]
        self.assertEqual(len(extra), 6)
        by_skill = {}
        for r in extra:
            by_skill[r[0]] = by_skill.get(r[0], 0) + 1
        self.assertEqual(by_skill, {"git-workflow-and-versioning": 2,
                                    "testing-discipline": 2,
                                    "money-path-safety": 1,
                                    "security-and-hardening": 1})

    def test_validate_accepts_merged_list(self):
        got = trigger_eval.load_queries(KIT / "skills", CENTRAL)
        self.assertEqual(trigger_eval.validate(got), [])


if __name__ == "__main__":
    unittest.main()
