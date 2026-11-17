"""Contract tests for scripts/tools/skills_search.py — catalog parsing,
ranking, and boundary behavior. No model calls."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tools"))
from skills_search import catalog, parse_skill, score, search


def _make_skill(dir_: Path, name: str, desc: str) -> Path:
    d = dir_ / name
    d.mkdir()
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: '{desc}'\n---\n\n# Body\n",
        encoding="utf-8")
    return d


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-ssearch-"))
        _make_skill(self.tmp, "yagni",
                    "Use for minimalism decisions, delete dead code")
        _make_skill(self.tmp, "money-safety",
                    "Use for payments, refunds, promo codes")
        _make_skill(self.tmp, "broken", "")          # empty description
        (self.tmp / "no-frontmatter").mkdir()
        (self.tmp / "no-frontmatter" / "SKILL.md").write_text(
            "# no frontmatter here", encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parses_valid_skills_only(self):
        skills = catalog(self.tmp)
        self.assertEqual({s["name"] for s in skills},
                         {"yagni", "money-safety"})

    def test_name_match_ranks_above_description_match(self):
        skills = catalog(self.tmp)
        hits = search(skills, "yagni", top=5)
        self.assertEqual(hits[0][1]["name"], "yagni")
        hits = search(skills, "payments", top=5)
        self.assertEqual(hits[0][1]["name"], "money-safety")

    def test_no_match_returns_empty(self):
        skills = catalog(self.tmp)
        self.assertEqual(search(skills, "zzzznothing", top=5), [])

    def test_score_zero_on_empty_query(self):
        skills = catalog(self.tmp)
        self.assertEqual(score(skills[0], "   "), 0.0)

    def test_multiline_folded_and_literal_descriptions_and_nonpositive_top(self):
        d = self.tmp / "multi"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: multi\ndescription: >\n  Line one\n  line two\n---\nBody\n",
            encoding="utf-8",
        )
        parsed = parse_skill(d / "SKILL.md")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["description"], "Line one line two")
        skills = catalog(self.tmp)
        self.assertEqual(search(skills, "Line", top=0), [])
        self.assertEqual(search(skills, "Line", top=-3), [])


if __name__ == "__main__":
    unittest.main()