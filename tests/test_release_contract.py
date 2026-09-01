#!/usr/bin/env python3
"""Release contract regression test for coding-kit v3.4.6.

Asserts the observable release invariants, independent of any
historical changelog wording that was accurate at the time:

- VERSION and profile.yml version are both 3.4.3 (doctor check_versions).
- profile.yml's skill manifest equals the on-disk skills/ dirs; total is 38.
- the ponytail skill is present in both the manifest and the skill dirs.
- the current public release text no longer contains any identity-declaration
  phrase ("Engineer agent", "Not a chatbot", "Not a theorist", "Not a PM",
  "not a polite assistant") — the v3.4.2 persona-to-behavior conversion must
  hold across README/OPS/AGENTS/SKILL_RUNTIME/CONTRIBUTING/SECURITY/
  profile.yml + adapters.
- the accidental-scope skill family (two skills that never had a consumer,
  added only in the reverted mixed commit) is absent from the skill dirs and
  the manifest. The slugs are built from parts so this meta-test's own source
  stays free of the very strings it asserts are gone; public docs may name
  the feature only to document its removal.
- the current public release text (README/OPS/AGENTS/SKILL_RUNTIME/
  CONTRIBUTING/SECURITY/profile.yml + adapters) contains no literal personal
  machine path in any separator form (slash, single backslash, or
  JSON-escaped double backslash) — the v3.3.1 sanitization must hold.
- the four stale pre-oracle result basenames (from the reverted mixed
  commit) are absent from eval/results/.
- the context-monitor script and its tests are removed (YAGNI), and no ACTIVE
  doc/code references it — the OPS.md CHANGELOG may name it historically.

Run: python -m pytest tests/test_release_contract.py -v
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_VERSION = "3.7.0"
EXPECTED_SKILL_COUNT = 36
EXPECTED_SCENARIO_COUNT = 23
EXPECTED_TRIGGER_QUERY_COUNT = 80
EXPECTED_TASK_COUNT = 6

# Identity-declaration phrases the v3.4.2 release removed from the public
# release text. Built from parts so this meta-test's own source never
# contains the very strings it asserts are gone.
_ENGINEER_AGENT = "Engineer" + " agent"
_NOT_A_CHATBOT = "Not a" + " chatbot"
_NOT_A_THEORIST = "Not a" + " theorist"
_NOT_A_PM = "Not a" + " PM"
_NOT_A_POLITE_ASSISTANT = "not a polite" + " assistant"
_IDENTITY_PHRASES = (_ENGINEER_AGENT, _NOT_A_CHATBOT, _NOT_A_THEORIST,
                     _NOT_A_PM, _NOT_A_POLITE_ASSISTANT)

# The accidental-scope skill family, built from parts so this meta-test's
# source never contains the very string it asserts is gone.
_ACCIDENTAL = "screen" + "pipe"
_ACCIDENTAL_API = _ACCIDENTAL + "-api"
_ACCIDENTAL_CLI = _ACCIDENTAL + "-cli"

# Stale pre-oracle evidence result files introduced by the reverted mixed
# commit (e7449f6) and excluded from this release.
STALE_RESULT_BASENAMES = frozenset({
    "tasks-20260825-220459-942147-1aded64e-0186-4df1-9093-46937a56f006.json",
    "trap-20260825-222921-092127-bf38630e-ff98-455a-8250-550232e3558c.json",
    "trigger-20260825-223013-492206-7bde53a1-ed2b-4200-8d58-4cc71e53073d.json",
    "trigger-20260825-225622-672610-b3d402e4-91d5-41a8-8331-bfd26b8bc34f.json",
})

# Same regexes scripts/doctor.py uses (checks 1 & 2).
_SKILL_ENTRY_RE = re.compile(r"^\s*-\s+([a-z0-9-]+)", re.M)
_VERSION_RE = re.compile(r'^version:\s*"([^"]+)"', re.M)

# Personal machine path in ANY separator form: slash, single backslash, or
# JSON-escaped double backslash. Built from parts so this meta-test's own
# source carries no literal path string.
_DRIVE = "C" + ":"
_DIR = "U" + "sers"
_USER = "ole" + "g2"
_SEP = r"[\\/]+"
_PERSONAL_PATH_RE = re.compile(_DRIVE + _SEP + _DIR + _SEP + _USER)

# Files that constitute the "current public release text".
_PUBLIC_DOC_NAMES = ("README.md", "OPS.md", "AGENTS.md", "SKILL_RUNTIME.md",
                     "CONTRIBUTING.md", "SECURITY.md", "profile.yml")


def _manifest_section() -> str:
    text = (ROOT / "profile.yml").read_text(encoding="utf-8")
    return text.split("always_on:")[-1].split("adapters:")[0]


def _declared_skills() -> set:
    return set(_SKILL_ENTRY_RE.findall(_manifest_section()))


def _on_disk_skills() -> set:
    return {d.name for d in (ROOT / "skills").iterdir() if d.is_dir()}


def _public_release_files() -> list:
    out = [ROOT / n for n in _PUBLIC_DOC_NAMES if (ROOT / n).is_file()]
    out.extend(sorted((ROOT / "adapters").glob("*.md")))
    return out


def _release_text() -> str:
    """Concatenated text of the current public release docs."""
    parts = []
    for p in _public_release_files():
        try:
            parts.append(p.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            pass
    return "\n".join(parts)


def _active_release_text() -> str:
    """Current public release text, EXCLUDING the OPS.md CHANGELOG section.

    The changelog is a historical record and may legitimately name tools
    (e.g. context-monitor) that a later release removed. The ACTIVE release
    text must not, so the two consumers separate.
    """
    parts = []
    for p in _public_release_files():
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if p.name == "OPS.md":
            t = re.split(r"^##\s+\d+\.\s+CHANGELOG", t, 1, flags=re.M)[0]
        parts.append(t)
    return "\n".join(parts)


class VersionContractTest(unittest.TestCase):
    def test_version_equals_3_4_6(self):
        self.assertEqual(
            (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            EXPECTED_VERSION)

    def test_profile_version_equals_3_4_6(self):
        m = _VERSION_RE.search((ROOT / "profile.yml").read_text(encoding="utf-8"))
        self.assertIsNotNone(m, "profile.yml must declare version")
        self.assertEqual(m.group(1), EXPECTED_VERSION)


class NoIdentityDeclarationTest(unittest.TestCase):
    def test_no_identity_declarations_in_public_release_text(self):
        text = _release_text()
        for phrase in _IDENTITY_PHRASES:
            self.assertNotIn(
                phrase, text,
                "identity-declaration phrase must be gone from the "
                "public release text: %r" % phrase)


class ManifestContractTest(unittest.TestCase):
    def test_manifest_matches_on_disk_and_count_is_36(self):
        declared = _declared_skills()
        on_disk = _on_disk_skills()
        self.assertEqual(declared, on_disk,
                         "profile.yml skill manifest must equal skills/ dirs")
        self.assertEqual(len(on_disk), EXPECTED_SKILL_COUNT)


class DashboardSkillsPresentTest(unittest.TestCase):
    """v3.4.6: ui-review + data-viz merged into dashboard-design; agent-ux
    killed (0 real uses since 2026-08-15). Only the merged skill + design-system
    remain."""

    NEW_SKILLS = (
        "dashboard-design",
        "design-system",
    )

    KILLED_SKILLS = (
        "agent-ux",
        "dashboard-ui-review",
        "data-visualization",
    )

    def test_dashboard_skills_in_manifest_and_on_disk(self):
        declared = _declared_skills()
        on_disk = _on_disk_skills()
        for sk in self.NEW_SKILLS:
            self.assertIn(sk, declared, f"{sk} must be declared in profile.yml manifest")
            self.assertIn(sk, on_disk, f"{sk} skill dir must exist on disk")
        for sk in self.KILLED_SKILLS:
            self.assertNotIn(sk, declared, f"{sk} must be gone from the manifest")
            self.assertNotIn(sk, on_disk, f"{sk} skill dir must be gone")


class LearnFoldedIntoSkillAuthoringTest(unittest.TestCase):
    """v3.4.6: the former learn skill (session → SKILL.md flow) folded into
    skill-authoring §6; learn/executing-plans/subagent-driven-development
    killed (0 real uses)."""

    def test_learn_absent_skill_authoring_present_with_flow(self):
        declared = _declared_skills()
        on_disk = _on_disk_skills()
        self.assertNotIn("learn", declared)
        self.assertNotIn("learn", on_disk)
        self.assertNotIn("executing-plans", declared)
        self.assertNotIn("subagent-driven-development", declared)
        self.assertIn("skill-authoring", declared)
        body = (ROOT / "skills" / "skill-authoring" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Turning a session into a skill", body,
                      "skill-authoring must carry the former /learn flow")
        self.assertIn("сделай скилл из этой процедуры", body,
                      "RU trigger phrases from learn must survive in skill-authoring")


class PonytailPresentTest(unittest.TestCase):
    def test_ponytail_in_manifest_and_on_disk(self):
        self.assertIn("ponytail", _declared_skills(),
                      "ponytail must be declared in the manifest")
        self.assertIn("ponytail", _on_disk_skills(),
                      "ponytail skill dir must exist")


class AccidentalScopeAbsentTest(unittest.TestCase):
    def test_accidental_scope_absent_from_manifest(self):
        declared = _declared_skills()
        self.assertNotIn(_ACCIDENTAL_API, declared,
                         "accidental-scope slug must not be in the manifest")
        self.assertNotIn(_ACCIDENTAL_CLI, declared,
                         "accidental-scope slug must not be in the manifest")

    def test_accidental_scope_absent_from_skill_dirs(self):
        on_disk = _on_disk_skills()
        self.assertNotIn(_ACCIDENTAL_API, on_disk)
        self.assertNotIn(_ACCIDENTAL_CLI, on_disk)
        prefixed = [d for d in on_disk if d.startswith(_ACCIDENTAL)]
        self.assertEqual(prefixed, [],
                         "no accidental-scope skill dir may remain")


class NoPersonalPathTest(unittest.TestCase):
    def test_no_personal_path_in_public_release_text(self):
        text = _release_text()
        self.assertIsNone(
            _PERSONAL_PATH_RE.search(text),
            "public release text must not leak the personal machine path "
            "in slash/backslash/JSON-escaped form")


class StaleResultsAbsentTest(unittest.TestCase):
    def test_stale_results_basenames_absent(self):
        present = [b for b in STALE_RESULT_BASENAMES
                   if list((ROOT / "eval" / "results").glob(b))]
        self.assertEqual(
            present, [],
            "stale pre-oracle results must be absent from eval/results")


class ContextMonitorAbsentTest(unittest.TestCase):
    def test_context_monitor_script_absent(self):
        self.assertFalse(
            (ROOT / "scripts" / "context-monitor.py").exists(),
            "context-monitor script must be removed (YAGNI: no consumer)")

    def test_context_monitor_tests_absent(self):
        self.assertFalse(
            (ROOT / "tests" / "test_context_monitor.py").exists(),
            "context-monitor tests must be removed with the script")

    def test_no_active_doc_references_context_monitor(self):
        text = _active_release_text()
        self.assertNotIn(
            "context-monitor", text,
            "active docs must not reference the removed context-monitor "
            "script (historical changelog excepted)")


class AssetCountsContractTest(unittest.TestCase):
    def test_scenario_count_is_21(self):
        scenarios = list((ROOT / "eval" / "scenarios").glob("*.md"))
        self.assertEqual(len(scenarios), EXPECTED_SCENARIO_COUNT,
                         f"eval/scenarios/*.md count must be {EXPECTED_SCENARIO_COUNT}, found {len(scenarios)}")

    def test_trigger_queries_count_is_80(self):
        query_file = ROOT / "eval" / "trigger_queries.json"
        self.assertTrue(query_file.is_file(), "eval/trigger_queries.json must exist")
        import json
        data = json.loads(query_file.read_text(encoding="utf-8"))
        self.assertEqual(len(data), EXPECTED_TRIGGER_QUERY_COUNT,
                         f"eval/trigger_queries.json entry count must be {EXPECTED_TRIGGER_QUERY_COUNT}, found {len(data)}")

    def test_task_count_is_4(self):
        import sys
        if str(ROOT / "eval") not in sys.path:
            sys.path.insert(0, str(ROOT / "eval"))
        import task_runner
        tasks = task_runner.discover()
        self.assertEqual(len(tasks), EXPECTED_TASK_COUNT,
                         f"eval/tasks discoverable count must be {EXPECTED_TASK_COUNT}, found {len(tasks)}")

class StaleDocReferencesTest(unittest.TestCase):
    def test_no_active_doc_references_stale_eval_paths(self):
        text = _active_release_text()
        skills_text = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in (ROOT / "skills").glob("**/*.md") if p.is_file()
        )
        all_text = text + "\n" + skills_text
        for stale in ("scripts/task-brief", "eval/workflow.js", "fable-method/eval", "eval/README.md"):
            self.assertNotIn(
                stale, all_text,
                f"active docs/skills must not reference stale path: {stale}"
            )

if __name__ == "__main__":
    unittest.main()
