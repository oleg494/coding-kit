#!/usr/bin/env python3
"""lint_wiki.py — checks the integrity of the Wiki library (Karpathy LLM Wiki pattern).

For each post (all *.md except service files):
  - YAML frontmatter presence;
  - required fields: type, title, description, date, tags;
  - tags: lowercase, no spaces;
  - file name: kebab-case.

Prints an error report and tag statistics. Exit code 0 = clean, 1 = errors found.

Usage:
  python3 lint_wiki.py [path-to-Wiki]
"""
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

REQUIRED = ("type", "title", "description", "date", "tags")
SERVICE_FILES = {"README.md", "index.md", "log.md"}
SKIP_DIRS = {"_templates", "raw", "assets"}


def parse_frontmatter(text: str) -> dict | None:
    """Return a dict from the YAML frontmatter, or None if absent."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end].strip()
    if yaml is not None:
        try:
            data = yaml.safe_load(block)
            return data if isinstance(data, dict) else None
        except yaml.YAMLError as exc:
            print(f"  ⚠ YAML error in frontmatter: {exc}", file=sys.stderr)
            return None
    # fallback without yaml: top-level keys only
    data = {}
    for line in block.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            data[m.group(1)] = m.group(2)
    return data


def is_kebab(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*\.md", name))


def check_origin(fm: dict, rel: str, errors: list[str], warnings: list[str]):
    """ASI06 provenance rule (wave1 Task 3): every note declares where it
    came from — origin: web|session|subagent|manual; origin: web must cite
    source_url. Missing origin is a WARN (legacy notes predate the rule);
    a web note without source_url is an error (citable web claims are the
    whole point of provenance)."""
    origin = fm.get("origin")
    if origin in (None, ""):
        warnings.append(f"{rel}: WARN missing 'origin:' "
                        "(web|session|subagent|manual) — ASI06 provenance")
        return
    if origin == "web" and not fm.get("source_url"):
        errors.append(f"{rel}: origin: web requires 'source_url:'")


def stamp_origin(text: str) -> str:
    """Idempotently stamp `origin: manual` into a note's frontmatter —
    the legacy default (build.py calls this on notes that lack the key;
    existing origins are never touched)."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    block = text[3:end]
    if re.search(r"^origin:", block, re.MULTILINE):
        return text
    return text[:end] + "\norigin: manual" + text[end:]


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        root = Path(argv[0])
    else:
        from _compat import chulan_root
        root = chulan_root() / "Wiki"


    errors: list[str] = []
    warnings: list[str] = []
    posts: list[Path] = []
    tag_counter: Counter = Counter()

    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if path.name in SERVICE_FILES or rel.parts[0] in SKIP_DIRS:
            continue
        posts.append(path)
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm is None:
            errors.append(f"{rel}: no YAML frontmatter (starts with '---' and closed by '---')")
            continue
        for field in REQUIRED:
            value = fm.get(field)
            if value in (None, ""):
                errors.append(f"{rel}: missing required field '{field}'")
        check_origin(fm, rel, errors, warnings)
        tags = fm.get("tags") or []
        if not isinstance(tags, list):
            errors.append(f"{rel}: 'tags' must be a list [a, b]")
            tags = []
        for tag in tags:
            tag = str(tag)
            if tag != tag.lower() or " " in tag:
                errors.append(f"{rel}: tag '{tag}' — must be lowercase without spaces")
            tag_counter[tag] += 1
        if not is_kebab(path.name):
            errors.append(f"{rel}: file name is not kebab-case")

    print(f"Posts: {len(posts)}")
    if tag_counter:
        print("Tags: " + ", ".join(f"{t} ({n})" for t, n in tag_counter.most_common()))
    if warnings:
        print(f"\nWarnings: {len(warnings)}")
        for warn in warnings:
            print(f"  ⚠ {warn}")
    if errors:
        print(f"\nErrors: {len(errors)}")
        for err in errors:
            print(f"  ✗ {err}")
        return 1
    print("Errors: 0 — library clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
