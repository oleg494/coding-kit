#!/usr/bin/env python3
"""kit_inventory.py — stdlib-only kit-owned skill inventory (v4.7.0).

Single source of truth for "which skills does the kit own": the
profile.yml skills.always_on + skills.domain lists. Everything else under
skills/ (e.g. third-party firecrawl sources the user dropped in) is
FOREIGN: never copied, never deleted, never validated by the kit's own
doctor/integrity/sync consumers.

Contract:
- owned_skill_names(profile_path) -> sorted list[str] of slugs declared
  in skills.always_on and skills.domain.
- load_owned_skills(kit_root, profile_path=None) -> same list for a kit
  root (reads <root>/profile.yml; explicit non-None profile_path wins).
- A missing, unreadable, or structurally invalid profile (no skills map,
  non-list always_on/domain, non-slug entries, unknown duplicate) raises
  KitInventoryError — the caller turns that into an explicit failure.
  An explicit error, never a silent fallback to "every directory on disk".
- Foreign directories under skills/ are ignored: the kit does not own
  them and MUST NOT copy, delete, or hash them.

Parsing is stdlib-only (re over the skills block); PyYAML is optional
elsewhere, never required here. Duplicate declarations across always_on
and domain are deduplicated.
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001,S110 — optional console nicety
    pass

PROFILE_NAME = "profile.yml"
_SKILL_LINE_RE = re.compile(
    r"^\s*-\s+([a-z0-9_]+(?:-[a-z0-9_]+)*)"
    r"(?:\s+#.*)?$"
)
_LIST_KEY_RE = re.compile(
    r"^\s{2}(always_on|domain):\s*(?:\[\s*\])?\s*$"
)


class KitInventoryError(Exception):
    """profile.yml skills inventory missing or invalid."""


def _parse_list_items(block_lines: list[tuple[str, str]]) -> list[str]:
    """Slugs in file order; raises on an unparsable entry or a duplicate
    within one list. The same slug in both always_on and domain is
    tolerated (deduplicated by the caller)."""
    names: list[str] = []
    seen: dict[str, str] = {}
    for key, line in block_lines:
        m = _SKILL_LINE_RE.match(line)
        if not m:
            raise KitInventoryError(
                f"profile.yml skills.{key}: unparsable entry: {line.strip()!r}")
        name = m.group(1)
        if name in seen and seen[name] == key:
            raise KitInventoryError(
                f"profile.yml skills.{key}: duplicate entry: {name}")
        seen[name] = key
        names.append(name)
    return names


def owned_skill_names(profile_path: Path) -> list[str]:
    """Kit-owned skill slugs from profile.yml (sorted, deduplicated).

    profile_path: Path to the profile.yml to parse.
    Raises KitInventoryError on missing/unreadable/invalid inventory.
    """
    profile_path = Path(profile_path)
    if not profile_path.is_file():
        raise KitInventoryError(
            f"kit inventory missing: no {PROFILE_NAME} at {profile_path}")
    try:
        text = profile_path.read_text(encoding="utf-8")
    except OSError as e:
        raise KitInventoryError(
            f"kit inventory unreadable: {profile_path}: {e}") from e

    # Extract the `skills:` map (top-level, 2-space indented keys) with
    # its always_on / domain sublists. Only line-level structure; no
    # PyYAML dependency.
    lines = text.splitlines()
    in_skills = False
    block: list[tuple[str, str]] = []
    current_list: str | None = None
    found_lists: set[str] = set()
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")) and line.rstrip().endswith(":"):
            in_skills = line.split(":", 1)[0].strip() == "skills"
            current_list = None
            continue
        if not in_skills:
            continue
        m = _LIST_KEY_RE.match(line)
        if m:
            current_list = m.group(1)
            found_lists.add(current_list)
            continue
        if current_list and line.lstrip().startswith("- "):
            block.append((current_list, line))
        elif current_list and line.startswith((" ", "\t")):
            # continuation of a list item (comment text after the entry
            # is already captured; deeper keys are not part of the slug)
            continue
        else:
            current_list = None
    for required in ("always_on", "domain"):
        if required not in found_lists:
            raise KitInventoryError(
                f"profile.yml skills: missing required list '{required}'")
    if not any(_SKILL_LINE_RE.match(l) for _, l in block):
        raise KitInventoryError(
            "profile.yml skills: empty inventory (no owned skills declared)")
    return sorted(set(_parse_list_items(block)))


def load_owned_skills(kit_root: Path, profile_path: Path | None = None) -> list[str]:
    """Kit-owned skill slugs for a kit root directory.

    kit_root: directory containing profile.yml (and skills/).
    profile_path: explicit override; defaults to <kit_root>/profile.yml.
    Raises KitInventoryError on missing/invalid inventory.
    """
    root = Path(kit_root)
    pp = Path(profile_path) if profile_path is not None else root / PROFILE_NAME
    return owned_skill_names(pp)
