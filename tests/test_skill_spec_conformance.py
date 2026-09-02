#!/usr/bin/env python3
"""agentskills.io Agent Skills spec conformance (wave3 Task 8).

Rules as data: name 1-64 chars, ^[a-z0-9]+(-[a-z0-9]+)*$ (no lead/trail/
consecutive hyphens), MUST equal the parent dir name; description 1-1024;
compatibility <= 500 when present; metadata is a str->str map; allowed-tools
a non-empty space-separated string. Hard FAIL: charset/length/missing
description/wrong types. WARN tier (doctor stays green): name != dir,
compat > 500, missing metadata.version.

The real kit corpus must produce zero hard violations — the doctor names
WARNs without breaking the 4-harness reality.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "doctor", KIT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def write_skill(root: Path, slug: str, fm_text: str) -> Path:
    d = root / "skills" / slug
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(fm_text, encoding="utf-8", newline="\n")
    return d


def both_paths(fm_text: str, slug: str):
    """Run frontmatter_spec_problems via the regex fallback AND the yaml
    dict path; returns (hard_regex, warn_regex, hard_yaml, warn_yaml)."""
    fm_text_inner = fm_text.split("---")[1]
    hard_r, warn_r = doctor.frontmatter_spec_problems(slug, fm_text_inner, None)
    try:
        import yaml
    except ImportError:
        return hard_r, warn_r, hard_r, warn_r
    hard_y, warn_y = doctor.frontmatter_spec_problems(
        slug, fm_text_inner, yaml.safe_load(fm_text_inner))
    return hard_r, warn_r, hard_y, warn_y


class SpecRuleCasesTest(unittest.TestCase):
    """The 8 violation classes from the plan, each on its own tmp skill."""

    def test_name_bad_charset_fails(self):
        fm = "---\nname: My_Skill\ndescription: 'x'\n---\n"
        hard_r, _, hard_y, _ = both_paths(fm, "my-skill")
        self.assertTrue(any("charset" in p or "shape" in p for p in hard_r))
        self.assertTrue(any("charset" in p or "shape" in p for p in hard_y))

    def test_name_over_64_fails(self):
        long_name = "a" + "-b" * 32  # valid charset, 65 chars
        fm = f"---\nname: {long_name}\ndescription: 'x'\n---\n"
        hard_r, _, hard_y, _ = both_paths(fm, long_name)
        self.assertTrue(any("64" in p for p in hard_r), hard_r)
        self.assertTrue(any("64" in p for p in hard_y), hard_y)

    def test_name_missing_fails(self):
        fm = "---\ndescription: 'x'\n---\n"
        hard_r, _, hard_y, _ = both_paths(fm, "some-skill")
        self.assertTrue(any("name missing" in p for p in hard_r))
        self.assertTrue(any("name missing" in p for p in hard_y))

    def test_description_missing_fails(self):
        fm = "---\nname: some-skill\n---\n"
        hard_r, _, hard_y, _ = both_paths(fm, "some-skill")
        self.assertTrue(any("description missing" in p for p in hard_r))
        self.assertTrue(any("description missing" in p for p in hard_y))

    def test_description_over_1024_fails(self):
        fm = "---\nname: some-skill\ndescription: '" + "x" * 1025 + "'\n---\n"
        hard_r, _, hard_y, _ = both_paths(fm, "some-skill")
        self.assertTrue(any("1024" in p for p in hard_r), hard_r)
        self.assertTrue(any("1024" in p for p in hard_y), hard_y)

    def test_description_must_be_non_empty_scalar_string(self):
        bad_values = ("{}", "[]", "null", "~", "|")
        for value in bad_values:
            with self.subTest(value=value):
                fm = ("---\nname: some-skill\n"
                      f"description: {value}\n---\n")
                hard_r, _, hard_y, _ = both_paths(fm, "some-skill")
                self.assertTrue(
                    any("description" in p and "string" in p
                        for p in hard_r), hard_r)
                self.assertTrue(
                    any("description" in p and "string" in p
                        for p in hard_y), hard_y)
        fm = ("---\nname: some-skill\ndescription: |\n"
              "metadata:\n  version: \"4.0.2\"\n---\n")
        hard_r, _, hard_y, _ = both_paths(fm, "some-skill")
        self.assertTrue(
            any("description" in p and "string" in p for p in hard_r),
            hard_r)
        self.assertTrue(
            any("description" in p and "string" in p for p in hard_y),
            hard_y)

    def test_description_block_scalar_with_content_is_valid(self):
        fm = ("---\nname: some-skill\n"
              "description: |\n  Use when testing scalar parsing.\n"
              "metadata:\n  version: \"4.0.2\"\n---\n")
        hard_r, _, hard_y, _ = both_paths(fm, "some-skill")
        self.assertEqual(hard_r + hard_y, [])


    def test_metadata_wrong_type_fails_yaml_path(self):
        fm = "---\nname: some-skill\ndescription: 'x'\nmetadata: {version: 3}\n---\n"
        _, _, hard_y, _ = both_paths(fm, "some-skill")
        self.assertTrue(any("str->str" in p for p in hard_y), hard_y)

    def test_name_ne_dir_warns_not_fails(self):
        fm = "---\nname: other-name\ndescription: 'x'\n---\n"
        _, warn_r, _, warn_y = both_paths(fm, "some-skill")
        self.assertTrue(any("name != dir" in p for p in warn_r), warn_r)
        self.assertTrue(any("name != dir" in p for p in warn_y), warn_y)

    def test_compat_over_500_warns_not_fails(self):
        fm = ("---\nname: some-skill\ndescription: 'x'\n"
              "compatibility: '" + "y" * 501 + "'\n---\n")
        hard_r, warn_r, hard_y, warn_y = both_paths(fm, "some-skill")
        self.assertEqual(hard_r + hard_y, [])
        self.assertTrue(any("500" in p for p in warn_r), warn_r)
        self.assertTrue(any("500" in p for p in warn_y), warn_y)

    def test_allowed_tools_wrong_type_fails_yaml_path(self):
        fm = "---\nname: some-skill\ndescription: 'x'\nallowed-tools: 3\n---\n"
        _, _, hard_y, _ = both_paths(fm, "some-skill")
        self.assertTrue(any("allowed-tools" in p for p in hard_y), hard_y)

    def test_clean_skill_passes_both_paths(self):
        fm = ("---\nname: some-skill\ndescription: 'x'\n"
              "metadata:\n  version: \"3.7.0\"\n---\n")
        hard_r, warn_r, hard_y, warn_y = both_paths(fm, "some-skill")
        self.assertEqual(hard_r + hard_y, [])
        self.assertEqual(warn_r + warn_y, [])


class KitPatchedRowTest(unittest.TestCase):
    """check_frontmatter_spec against a tmp KIT (test_doctor.py pattern)."""

    def test_bad_skill_fails_row_and_names_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "skills").mkdir()
            write_skill(root, "bad_name",
                        "---\nname: bad_name\ndescription: 'x'\n---\n")
            with mock.patch.object(doctor, "KIT", root):
                ok, detail = doctor.check_frontmatter_spec()
        self.assertFalse(ok)
        self.assertIn("bad_name", detail)

    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "skills").mkdir()
            write_skill(root, "clean-skill",
                        "---\nname: clean-skill\ndescription: 'x'\n---\n")
            with mock.patch.object(doctor, "KIT", root):
                ok, detail = doctor.check_frontmatter_spec()
            self.assertTrue(ok, detail)


class RealCorpusTest(unittest.TestCase):
    """Plan step 8.2: the current 36-skill corpus passes the new check."""

    def test_corpus_zero_hard_violations(self):
        ok, detail = doctor.check_frontmatter_spec()
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
