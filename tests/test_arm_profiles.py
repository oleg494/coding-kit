"""Arm-profile bundle inventory tests (bare/thin/full rigor arms).

Exercises `prompt_assembly.assemble_arm_profile` inventory outputs:
determinism, pairwise distinctness, and per-arm file inclusion per
docs/research/2026-09-05-open-source-product-direction.md §5. No
source-text/wording assertions; only inventory structure and bytes.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

from prompt_assembly import (ARM_PROFILES, DEFAULT_SKILLS_DIR,
                             KitInventoryError, assemble_arm_profile,
                             skill_manifest)


def _make_kit(tmp_path: Path) -> Path:
    """Synthetic kit root: profile.yml, three policy files, two owned
    skills plus one foreign skill directory."""
    (tmp_path / "profile.yml").write_text(
        "skills:\n"
        "  always_on: []\n"
        "  domain:\n"
        "    - alpha\n"
        "    - beta\n",
        encoding="utf-8", newline="\n")
    for fn in ("AGENTS.md", "OPS.md", "SKILL_RUNTIME.md"):
        (tmp_path / fn).write_text(f"{fn} policy\n", encoding="utf-8",
                                   newline="\n")
    skills = tmp_path / "skills"
    for name in ("alpha", "beta", "gamma-foreign"):
        d = skills / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: '{name} desc'\n---\n"
            f"\n# {name}\n\n{name} body\n",
            encoding="utf-8", newline="\n")
    return tmp_path / "skills"


def test_three_profiles_distinct_deterministic_inventories(tmp_path):
    skills = _make_kit(tmp_path)
    bundles = {p: assemble_arm_profile(p, skills) for p in ARM_PROFILES}
    for profile, bundle in bundles.items():
        again = assemble_arm_profile(profile, skills)
        assert again == bundle          # deterministic re-resolution
        assert bundle["profile"] == profile
        assert bundle["files"] == sorted(bundle["files"])  # unambiguous
    file_sets = [frozenset(b["files"]) for b in bundles.values()]
    assert len({tuple(b["files"]) for b in bundles.values()}) == 3
    assert all(a != b for i, a in enumerate(file_sets)
               for j, b in enumerate(file_sets) if i < j)


def test_bare_includes_no_kit_policy(tmp_path):
    bundle = assemble_arm_profile("bare", _make_kit(tmp_path))
    assert bundle["files"] == []
    assert bundle["policy_bytes"] == 0


def test_thin_is_router_and_ops_only(tmp_path):
    skills = _make_kit(tmp_path)
    bundle = assemble_arm_profile("thin", skills)
    assert bundle["files"] == ["AGENTS.md", "OPS.md"]
    expected = (len((skills.parent / "AGENTS.md").read_bytes())
                + len((skills.parent / "OPS.md").read_bytes()))
    assert bundle["policy_bytes"] == expected


def test_full_matches_policy_plus_owned_manifest(tmp_path):
    skills = _make_kit(tmp_path)
    bundle = assemble_arm_profile("full", skills)
    assert bundle["files"][:3] == ["AGENTS.md", "OPS.md",
                                   "SKILL_RUNTIME.md"]
    assert "skills/gamma-foreign/SKILL.md" not in bundle["files"]
    assert bundle["files"][3:] == ["skills/alpha/SKILL.md",
                                   "skills/beta/SKILL.md"]
    expected_files = len((skills.parent / "AGENTS.md").read_bytes())
    expected_files += len((skills.parent / "OPS.md").read_bytes())
    expected_files += len((skills.parent / "SKILL_RUNTIME.md").read_bytes())
    expected_files += len(json.dumps(
        skill_manifest(skills), sort_keys=True,
        ensure_ascii=False).encode("utf-8"))
    assert bundle["policy_bytes"] == expected_files


def test_unknown_profile_rejected(tmp_path):
    with pytest.raises(ValueError):
        assemble_arm_profile("medium", _make_kit(tmp_path))


def test_missing_policy_files_fail_closed(tmp_path):
    skills = _make_kit(tmp_path)
    (skills.parent / "SKILL_RUNTIME.md").unlink()
    with pytest.raises(KitInventoryError):
        assemble_arm_profile("full", skills)


def test_real_kit_full_matches_current_bundle():
    bundle = assemble_arm_profile("full", DEFAULT_SKILLS_DIR)
    expected = {"AGENTS.md", "OPS.md", "SKILL_RUNTIME.md"} | {
        f"skills/{m['name']}/SKILL.md"
        for m in skill_manifest(DEFAULT_SKILLS_DIR)}
    assert set(bundle["files"]) == expected
    assert bundle["files"] == sorted(bundle["files"])
    policy = (len((ROOT / "AGENTS.md").read_bytes())
              + len((ROOT / "OPS.md").read_bytes())
              + len((ROOT / "SKILL_RUNTIME.md").read_bytes()))
    manifest = len(json.dumps(skill_manifest(DEFAULT_SKILLS_DIR),
                              sort_keys=True,
                              ensure_ascii=False).encode("utf-8"))
    assert bundle["policy_bytes"] == policy + manifest
    assert assemble_arm_profile("full", DEFAULT_SKILLS_DIR) == bundle


def test_real_kit_bare_and_thin_bounds():
    bare = assemble_arm_profile("bare", DEFAULT_SKILLS_DIR)
    thin = assemble_arm_profile("thin", DEFAULT_SKILLS_DIR)
    full = assemble_arm_profile("full", DEFAULT_SKILLS_DIR)
    assert bare["policy_bytes"] == 0
    assert 0 < thin["policy_bytes"] < full["policy_bytes"]
    assert thin["files"] == ["AGENTS.md", "OPS.md"]
