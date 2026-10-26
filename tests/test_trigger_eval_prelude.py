"""Contract tests for the trigger_eval prompt prelude.

Era-2 evidence (findings #54/#55 era): executor models ignore a merely
descriptive skills listing — 8/10 skills sat at a 0.00 trigger rate even
with the listing present. The prelude must therefore force attention to it:

- an explicit mandatory-choice instruction ("You MUST choose from this list")
- few-shot examples showing the exact output format (SKILLS LOADED: <slug>)
- the listing still interpolated into the assembled prompt

The detection contract (trigger_eval.detect: slug as a standalone token)
is unchanged; these tests pin only the prompt-side text. No model calls.
"""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from trigger_eval import PRELUDE, prompt_for  # noqa: E402

def _listing() -> list:
    from trigger_eval import listing_entries
    return listing_entries()


class PreludeMandatoryChoiceTest(unittest.TestCase):
    def test_prelude_contains_mandatory_choice_instruction(self):
        self.assertIn("You MUST choose from this list", PRELUDE)

    def test_prelude_names_the_output_marker(self):
        self.assertIn("SKILLS LOADED:", PRELUDE)


class PreludeFewShotTest(unittest.TestCase):
    """Few-shot rows must show the exact expected output format, so the
    answer's final line is machine-detectable by trigger_eval.detect."""

    def test_prelude_shows_few_shot_fired_example(self):
        # An example where a skill fires: "SKILLS LOADED: <slug>" line.
        self.assertRegex(PRELUDE, r"(?im)^SKILLS LOADED: sec-review\s*$")

    def test_prelude_shows_few_shot_none_example(self):
        self.assertRegex(PRELUDE, r"(?im)^SKILLS LOADED: none\s*$")


class PreludeListingInterpolationTest(unittest.TestCase):
    def test_prompt_for_interpolates_real_listing_and_query(self):
        prompt = prompt_for("add an unused abstraction")
        # The prelude instructions come first (the placeholder is the only
        # part allowed to differ)...
        self.assertTrue(
            prompt.startswith(
                PRELUDE.replace("<skills listing>", "").rstrip()[:120]))
        # ...the user request is appended after it...
        self.assertIn("User request: add an unused abstraction\n", prompt)
        # ...and the listing is REALLY filled in from skills/ frontmatter —
        # not left as a literal placeholder (live incident 2026-08-29: the
        # executor answered from its ambient global skills because the
        # measured listing never entered the prompt).
        self.assertNotIn("<skills listing>", prompt)
        manifest = _listing()
        self.assertTrue(
            len(manifest) >= 10,
            "assembled prompt must carry at least 10 skill entries")
        for slug in ("ponytail", "testing-discipline", "skill-authoring"):
            self.assertIn(slug, prompt)

    def test_prompt_contains_both_few_shot_markers(self):
        prompt = prompt_for("fix the broken test")
        self.assertIn("SKILLS LOADED: sec-review", prompt)
        self.assertIn("SKILLS LOADED: none", prompt)

class DetectionContractUnchangedTest(unittest.TestCase):
    """The prelude fix must not move the detection contract: the slug is
    detected as a standalone token in the answer (trigger_eval.detect)."""

    def test_detect_still_matches_few_shot_style_answer(self):
        from trigger_eval import detect
        self.assertTrue(detect("yagni", "SKILLS LOADED: yagni"))
        self.assertFalse(detect("yagni", "SKILLS LOADED: none"))


if __name__ == "__main__":
    unittest.main()
