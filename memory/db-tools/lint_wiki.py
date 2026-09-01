#!/usr/bin/env python3
"""lint_wiki.py — checks the integrity of the Wiki library (Karpathy LLM Wiki pattern).

For each post (all *.md except service files):
  - YAML frontmatter presence;
  - required fields: type, title, description, date, tags;
  - type hygiene (wave4 Task 14): `type` in {user, feedback, project,
    reference}; other values are WARN-tier legacy (errors/howto/decisions/...
    keep working, they just nag) — missing `type` also WARNs;
  - `modified` ISO-8601 stamp, auto-maintained by writers; malformed = WARN;
  - freshness: note older than 180 days (by `modified`, else `date`) WARNs;
  - tags: lowercase, no spaces;
  - file name: kebab-case;
  - `Wiki/index.md` is hard-capped at INDEX_MAX_LINES (Anthropic memory-tool
    cap): over-cap is an ERROR demanding consolidation — the tail is never
    silently dropped, and an over-limit write must return an error.

Prints an error report and tag statistics. Exit code 0 = clean, 1 = errors found.

Usage:
  python3 lint_wiki.py [path-to-Wiki]
"""
import datetime
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

# wave4 Task 14: the hygiene taxonomy.
TAXONOMY_TYPES = {"user", "feedback", "project", "reference"}
FRESHNESS_DAYS = 180
INDEX_MAX_LINES = 200  # Anthropic memory-tool cap
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_ISO_STAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?([+-]\d{2}:?\d{2}|Z)?)?$")


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




def _note_date(value) -> datetime.date | None:
    """Parse a frontmatter date/modified value into a date, or None."""
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    s = str(value).strip()
    if not _ISO_DATE_RE.match(s):
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        return None


def check_taxonomy(fm: dict, rel: str, warnings: list[str]):
    """wave4 Task 14: `type` in {user, feedback, project, reference}.
    Legacy values (errors/howto/decisions/ideas/notes/...) and missing
    type are WARN-tier — they never fail the lint, they nudge migration."""
    t = fm.get("type")
    if t in (None, ""):
        warnings.append(f"{rel}: WARN missing 'type:' — taxonomy is "
                        f"{sorted(TAXONOMY_TYPES)} (+legacy at WARN)")
        return
    if str(t).strip().lower() not in TAXONOMY_TYPES:
        warnings.append(f"{rel}: WARN legacy type '{t}' — taxonomy is "
                        f"{sorted(TAXONOMY_TYPES)}")


def check_modified(fm: dict, rel: str, warnings: list[str]):
    """wave4 Task 14: `modified` is an ISO-8601 stamp auto-maintained by
    writers (build.py stamps it into the indexed copy). Present but
    malformed = WARN; absent = fine (writers backfill)."""
    m = fm.get("modified")
    if m in (None, ""):
        return
    s = str(m).strip()
    if isinstance(m, str) and not _ISO_STAMP_RE.match(s):
        warnings.append(f"{rel}: WARN malformed 'modified:' stamp "
                        f"({s!r}) — must be ISO-8601")


def check_freshness(fm: dict, rel: str, warnings: list[str]):
    """wave4 Task 14: note older than FRESHNESS_DAYS (by `modified` when
    present, else `date`) WARNs — candidates for review or archival."""
    d = _note_date(fm.get("modified")) or _note_date(fm.get("date"))
    if d is None:
        return
    age = (datetime.date.today() - d).days  # noqa: DTZ011 — local day is the contract
    if age > FRESHNESS_DAYS:
        warnings.append(f"{rel}: WARN stale — {age}d old (> {FRESHNESS_DAYS}) "
                        "without edit; review or archive")


def check_index_cap(root: Path, errors: list[str]):
    """wave4 Task 14: Wiki/index.md is hard-capped at INDEX_MAX_LINES
    (Anthropic memory-tool cap). Over cap = ERROR demanding consolidation;
    the tail is never silently dropped — the writer refuses and asks the
    agent to consolidate rows instead."""
    index = root / "index.md"
    if not index.is_file():
        return
    n = index.read_text(encoding="utf-8", errors="replace").count("\n")
    if n > INDEX_MAX_LINES:
        errors.append(
            f"index.md: {n} lines exceeds the {INDEX_MAX_LINES}-line cap — "
            "consolidate rows (merge/archive) before adding more; the tail "
            "is never silently dropped")

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

def stamp_modified(text: str, today: str | None = None) -> str:
    """Idempotently stamp `modified: <ISO-8601 date>` into a note's
    frontmatter — the writer-maintained freshness stamp (wave4 Task 14;
    build.py calls this on notes lacking the key, indexed copy only).
    An existing `modified:` is never touched."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    block = text[3:end]
    if re.search(r"^modified:", block, re.MULTILINE):
        return text
    stamp = today or datetime.date.today().isoformat()  # noqa: DTZ011 — local day is the contract
    return text[:end] + f"\nmodified: {stamp}" + text[end:]


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
            if field == "type":
                continue  # check_taxonomy owns the type tier (WARN, legacy ok)
            value = fm.get(field)
            if value in (None, ""):
                errors.append(f"{rel}: missing required field '{field}'")
        check_origin(fm, rel, errors, warnings)
        check_taxonomy(fm, rel, warnings)
        check_modified(fm, rel, warnings)
        check_freshness(fm, rel, warnings)
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

    check_index_cap(root, errors)

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
