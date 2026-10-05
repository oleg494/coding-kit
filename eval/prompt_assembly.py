"""Controlled inlined-prompt assembly for the kit's eval executors.

`assemble_prompt` builds `<skill manifest>\n\n<task body>` so the kit itself
injects skill name/description lines plus one fully-inlined active skill into
a subprocess executor prompt. Ambient CLI skills (those already loaded by the
host harness) remain outside this module's purview.
"""
import re
from pathlib import Path

try:
    from kit_inventory import KitInventoryError, load_owned_skills
except ImportError:  # direct execution: resolve the sibling module file
    import importlib.util as _ilu
    _inv = _ilu.spec_from_file_location(
        "kit_inventory",
        Path(__file__).resolve().parents[1] / "scripts" / "tools"
        / "kit_inventory.py")
    _inv_mod = _ilu.module_from_spec(_inv)
    _inv.loader.exec_module(_inv_mod)
    KitInventoryError = _inv_mod.KitInventoryError
    load_owned_skills = _inv_mod.load_owned_skills

_InventoryError = KitInventoryError  # re-export for consumers/tests

KIT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS_DIR = KIT_ROOT / "skills"


def skill_manifest_names(skills_root: Path, *,
                          profile_path: Path | None = None) -> frozenset[str]:
    """Kit-owned skill slugs for the kit owning `skills_root`.

    Resolves the kit root from the default (in-kit) skills directory;
    for out-of-tree skills roots WITHOUT a sibling profile.yml the
    whole directory is owned (synthetic eval fixtures, standalone
    temp copies). A present-but-invalid profile raises
    KitInventoryError — explicit failure, never silent adoption.
    """
    root = Path(skills_root)
    if profile_path is None:
        if root == DEFAULT_SKILLS_DIR:
            profile_path = KIT_ROOT / "profile.yml"
        else:
            sibling = root.parent / "profile.yml"
            profile_path = sibling if sibling.is_file() else None
    if profile_path is None:
        return frozenset(
            d.name for d in root.iterdir() if d.is_dir())
    return frozenset(load_owned_skills(
        profile_path.parent, profile_path=profile_path))

_FRONTMATTER = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def parse_frontmatter(text: str) -> dict:
    """`{name, description, ...}` from a `---`-delimited SKILL.md head.

    Returns `{}` when the head is missing or malformed.
    """
    m = _FRONTMATTER.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        out[key] = val
    return out


def _read_skill(skills_root: Path, name: str) -> str | None:
    try:
        return (skills_root / name / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return None


def _body_of(text: str) -> str:
    m = _FRONTMATTER.match(text)
    return text[m.end():].strip() if m else text.strip()


def skill_manifest(skills_root: Path, *,
                   disable: frozenset = frozenset(),
                   profile_path: Path | None = None) -> list[dict]:
    """`[{name, description}]` sorted by name, excluding `disable` names.

    Only kit-owned skills (profile.yml inventory, v4.7.0) are listed;
    foreign directories under skills_root are ignored. Malformed or
    missing SKILL.md files are skipped, never raised. A present-but-
    invalid inventory raises KitInventoryError.
    """
    skills_root = Path(skills_root)
    owned = skill_manifest_names(skills_root, profile_path=profile_path)
    entries: list[dict] = []
    for d in sorted(owned):
        content = _read_skill(skills_root, d)
        if content is None:
            continue
        fm = parse_frontmatter(content)
        name = fm.get("name")
        description = fm.get("description", "")
        if not name or not description or name in disable:
            continue
        entries.append({"name": name, "description": description})
    entries.sort(key=lambda e: e["name"])
    return entries


def assemble_prompt(body: str, skills_root: Path, *,
                    active_skill: str | None = None,
                    disable: frozenset = frozenset()) -> str:
    """Manifest block + task `body`; only the enabled `active_skill` body is
    inlined (following its description line). A disabled active skill has
    neither descriptor nor body."""
    lines = ["Available skills:"]
    for item in skill_manifest(skills_root, disable=disable):
        lines.append(f"- {item['name']}: {item['description']}")
        if item["name"] == active_skill:
            active_text = _read_skill(skills_root, item["name"])
            if active_text is not None:
                lines.append(_body_of(active_text))
    return "\n".join(lines) + "\n\n" + body