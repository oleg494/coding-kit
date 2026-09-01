#!/usr/bin/env python3
"""doctor.py — kit self-diagnostic: one command, full health picture.

Checks:
  1.  manifest sync      profile.yml skill lists == skills/ dirs (both ways)
  2.  version sync       VERSION == profile.yml version
  3.  skill frontmatter  name/description present, description non-empty
  4.  file-size gate     scripts/tools/check_file_sizes.py --ci
  5.  memory             ~/.memory root + SQLite integrity of every db/*.db
  6.  adapters           every adapter file named in profile.yml exists
  7.  override           .override.md mode validity
  8.  engine sync        the two shipped _compat.py copies are identical
 10.  integrity         CBSE manifest over the kit control plane (hash-pinned)
 11.  supply chain      WARN: skills with inconsistent license: frontmatter

Usage:
    python scripts/doctor.py          # table + exit 1 on any failure
"""
import os
import re
from datetime import datetime
import sqlite3
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KIT = Path(__file__).resolve().parents[1]


def check_manifest() -> tuple[bool, str]:
    text = (KIT / "profile.yml").read_text(encoding="utf-8")
    sec = text.split("always_on:")[-1].split("adapters:")[0]
    declared = set(re.findall(r"^\s*-\s+([a-z0-9-]+)", sec, re.M))
    on_disk = {d.name for d in (KIT / "skills").iterdir() if d.is_dir()}
    missing = sorted(declared - on_disk)
    extra = sorted(on_disk - declared)
    if not missing and not extra:
        return (True, f"{len(on_disk)} skills in sync")
    return (False, " ".join(
        ([f"profile-no-dirs: {missing}"] if missing else [])
        + ([f"dirs-not-in-profile: {extra}"] if extra else [])))


def check_versions() -> tuple[bool, str]:
    ver = (KIT / "VERSION").read_text(encoding="utf-8").strip()
    m = re.search(r'^version:\s*"([^"]+)"', 
                  (KIT / "profile.yml").read_text(encoding="utf-8"), re.M)
    prof = m.group(1) if m else "?"
    ok = ver == prof
    return (ok, f"VERSION {ver} == profile {prof}" if ok
            else f"VERSION {ver} != profile {prof}")


def check_frontmatter() -> tuple[bool, str]:
    bad = []
    for sk in sorted((KIT / "skills").iterdir()):
        md = sk / "SKILL.md"
        if not md.is_file():
            bad.append(f"{sk.name}: no SKILL.md")
            continue
        head = md.read_text(encoding="utf-8", errors="replace").split("---")
        if len(head) < 3:
            bad.append(f"{sk.name}: no frontmatter")
            continue
        fm = head[1]
        if yaml is not None:
            try:
                fm_yaml = yaml.safe_load(fm)
            except Exception as exc:
                bad.append(f"{sk.name}: invalid yaml ({str(exc).splitlines()[0]})")
                continue
            if not isinstance(fm_yaml, dict) or not fm_yaml.get("name"):
                bad.append(f"{sk.name}: name missing")
            if not isinstance(fm_yaml, dict) or not fm_yaml.get("description"):
                bad.append(f"{sk.name}: description missing")
            continue
        if not re.search(r"^name:\s*\S+", fm, re.M):
            bad.append(f"{sk.name}: name missing")
        if not re.search(r"^description:\s*\S+", fm, re.M):
            bad.append(f"{sk.name}: description missing")
    return (not bad, f"{len(bad)} bad" if bad else "all present")


# Agent Skills spec rules as data (wave3 Task 8, agentskills.io spec):
# - name: 1-64 chars, ^[a-z0-9]+(-[a-z0-9]+)*$ (no lead/trail/consecutive
#   hyphens); MUST equal the parent dir name (WARN — harnesses tolerate
#   drift; a hard fail here would break 4-harness reality).
# - description: 1-1024 chars (hard FAIL: the trigger path is dead without
#   it, and >1024 is out of spec).
# - compatibility: <= 500 chars when present (WARN — current harnesses
#   truncate silently).
# - metadata: str->str map, allowed-tools: space-separated (hard FAIL on
#   wrong types).
_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def frontmatter_spec_problems(slug: str, fm_text: str,
                               fm_yaml) -> tuple[list[str], list[str]]:
    """Spec problems for one skill's frontmatter.

    fm_yaml is the parsed dict (None when PyYAML is unavailable or the
    frontmatter does not parse). Returns (hard, warn) problem lists; each
    problem string is prefixed with the slug. Type rules need the parsed
    dict, so they only run on the yaml path (CI installs pytest only —
    the regex fallback still covers every string-level rule)."""
    hard: list[str] = []
    warn: list[str] = []

    def note(msg: str) -> None:
        (hard if not msg.startswith("WARN") else warn).append(f"{slug}: {msg}")

    m = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
    name = m.group(1).strip().strip("'\"") if m else None
    if name is None:
        note("name missing")
    else:
        if not name or len(name) > 64:
            note(f"name length {len(name)} outside 1-64")
        elif not _NAME_RE.fullmatch(name):
            note("name charset (want ^[a-z0-9]+(-[a-z0-9]+)*$)")
        elif name != slug:
            note(f"WARN name != dir ({name!r})")

    m = re.search(r"^description:\s*(.+)$", fm_text, re.MULTILINE)
    desc = m.group(1).strip() if m else None
    if not desc:
        note("description missing")
    else:
        if fm_yaml is not None:
            y = fm_yaml.get("description") if isinstance(fm_yaml, dict) else None
            if isinstance(y, str) and len(y) > 1024:
                note(f"description length {len(y)} > 1024")
        elif len(desc) > 1024 + 2:  # regex path: allow for the quotes
            note(f"description length {len(desc) - 2} > 1024")

    m = re.search(r"^compatibility:\s*(.+)$", fm_text, re.MULTILINE)
    if m and fm_yaml is None:
        raw = m.group(1).strip().strip("'\"")
        if len(raw) > 500:
            note(f"WARN compatibility length {len(raw)} > 500")

    if isinstance(fm_yaml, dict):
        compat = fm_yaml.get("compatibility")
        if compat is not None:
            if not isinstance(compat, str):
                note("compatibility must be a string")
            elif len(compat) > 500:
                note(f"WARN compatibility length {len(compat)} > 500")
        meta = fm_yaml.get("metadata")
        if meta is None:
            note("WARN metadata.version missing (skill lifecycle, "
                 "wave3 Task 11)")
        elif not isinstance(meta, dict) \
                or not all(isinstance(k, str) and isinstance(v, str)
                           for k, v in meta.items()):
            note("metadata must be a str->str map")
        elif not meta.get("version"):
            note("WARN metadata.version missing (skill lifecycle, "
                 "wave3 Task 11)")
        tools = fm_yaml.get("allowed-tools")
        if tools is not None and not (isinstance(tools, str)
                                      and tools.strip()
                                      and "  " not in tools):
            note("allowed-tools must be a space-separated string")
    return hard, warn


def check_frontmatter_spec() -> tuple[bool, str]:
    """agentskills.io spec conformance (wave3 Task 8). Hard violations
    FAIL the doctor; WARN tier (name != dir, compat > 500, version-less
    metadata) names slugs but keeps the kit green."""
    bad: list[str] = []
    warned: list[str] = []
    total = 0
    for sk in sorted((KIT / "skills").iterdir()):
        if not sk.is_dir():
            continue
        md = sk / "SKILL.md"
        if not md.is_file():
            bad.append(f"{sk.name}: no SKILL.md")
            continue
        total += 1
        parts = md.read_text(encoding="utf-8", errors="replace").split("---")
        if len(parts) < 3:
            bad.append(f"{sk.name}: no frontmatter")
            continue
        fm_text = parts[1]
        fm_yaml = None
        if yaml is not None:
            try:
                fm_yaml = yaml.safe_load(fm_text)
            except yaml.YAMLError:
                fm_yaml = None  # parse errors are check_frontmatter's turf
        hard, warn = frontmatter_spec_problems(sk.name, fm_text, fm_yaml)
        bad.extend(hard)
        warned.extend(warn)
    if bad:
        return (False, "; ".join(bad[:5])
                + (f" (+{len(bad) - 5} more)" if len(bad) > 5 else ""))
    if warned:
        return (True, f"{total} skills, spec OK; WARN: "
                + "; ".join(warned[:5])
                + (f" (+{len(warned) - 5} more)" if len(warned) > 5 else ""))
    return (True, f"{total} skills, spec OK")


def check_gate() -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable,
         str(KIT / "scripts" / "tools" / "check_file_sizes.py"), "--ci"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    last = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-1] \
        if (r.stdout or r.stderr) else f"rc={r.returncode}"
    return (r.returncode == 0, last)


def check_memory() -> tuple[bool, str]:
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_compat", KIT / "memory" / "db-tools" / "_compat.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        root = m.chulan_root()
    except Exception as e:
        return (False, f"memory root: {e}")
    dbs = sorted((root / "db").glob("*.db"))
    for db in dbs:
        try:
            con = sqlite3.connect(db)
            row = con.execute("PRAGMA integrity_check").fetchone()
            con.close()
            if row and row[0] != "ok":
                return (False, f"{db.name}: {row[0]}")
        except sqlite3.Error as e:
            return (False, f"{db.name}: {e}")
    return (True, f"{root} ok, {len(dbs)} db healthy")


def check_adapters() -> tuple[bool, str]:
    missing = [
        f"adapters/{m.group(1)}" for m in re.finditer(
            r"adapters/([\w./-]+\.md)",
            (KIT / "profile.yml").read_text(encoding="utf-8"))
        if not (KIT / "adapters" / m.group(1)).exists()]
    return (not missing, "all targets exist" if not missing
            else "; ".join(missing))

def check_override() -> tuple[bool, str]:
    ov = KIT / ".override.md"
    if not ov.exists():
        return (True, "no .override.md")
    m = re.search(r"^\s*MODE:\s*(\S+)",
                  ov.read_text(encoding="utf-8"), re.M)
    if not m:
        return (False, ".override.md present but no MODE: line")
    mode = m.group(1).strip()
    if mode in ("EXPLORATORY_PROTOTYPE", "STRICT_AUDIT"):
        return (True, f"{mode} (valid)")
    return (False, f"unknown mode {mode!r} — allowed: "
                   "EXPLORATORY_PROTOTYPE, STRICT_AUDIT. Typo?")


def check_engine_sync() -> tuple[bool, str]:
    """Check that the two shipped _compat.py copies in the repository
    (memory/db-tools/ and memory/scripts/) are identical to prevent drift
    between the engine and the bootstrap script."""
    a = KIT / "memory" / "db-tools" / "_compat.py"
    b = KIT / "memory" / "scripts" / "_compat.py"
    if a.read_bytes() == b.read_bytes():
        return (True, "_compat copies identical")
    return (False, "memory/db-tools/_compat.py != memory/scripts/_compat.py")


def check_skill_supply_chain() -> tuple[bool, str]:
    """AST02 supply-chain hygiene seed: optional `license:` frontmatter
    across skills must be consistent. WARN tier (FILE-SIZE soft-gate
    semantics): ok=True — the doctor stays green, the detail names the
    unlicensed skills. Skills are local-authored (no third-party installs),
    so licensing is a hygiene signal, not a gate (wave1 Task 1)."""
    unlicensed = []
    total = 0
    for sk in sorted((KIT / "skills").iterdir()):
        md = sk / "SKILL.md"
        if not md.is_file():
            continue
        total += 1
        head = md.read_text(encoding="utf-8", errors="replace").split("---")
        if len(head) >= 3 and not re.search(r"^license:\s*\S+", head[1], re.M):
            unlicensed.append(sk.name)
    if not unlicensed:
        return (True, f"{total} skills, all licensed" if total else "no skills")
    return (True, f"WARN: {len(unlicensed)}/{total} skills lack license: "
                  + ", ".join(unlicensed[:5])
                  + ("…" if len(unlicensed) > 5 else ""))


def check_integrity() -> tuple[bool, str]:
    """CBSE integrity manifest over the kit control plane (wave1 Task 2):
    every file that executes or steers is hash-pinned in
    integrity-manifest.json; any drift/added/removed file FAILs the kit."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location(
        "integrity_manifest",
        KIT / "scripts" / "tools" / "integrity_manifest.py")
    m = _ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    data = m.load_manifest(KIT)
    if data is None:
        return (False, f"no readable {m.MANIFEST_NAME} — run --update")
    problems = m.check(KIT, data["files"])
    if problems:
        return (False, "; ".join(problems[:5])
                + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""))
    return (True, f"{len(data['files'])} control-plane files verified")


def find_bare_text_true(source: str) -> list[int]:
    """Line numbers of subprocess.* calls whose text=True keyword has no
    encoding= sibling. The v2.4 BUG-1/4 class: text=True decodes child
    output with the ANSI code page on Windows (cp1251) — mojibake or
    UnicodeDecodeError on Cyrillic (audit 2026-08-22 M3). AST-based:
    docstrings/strings mentioning the pattern never match."""
    try:
        import ast
        tree = ast.parse(source)
    except SyntaxError:
        return []  # unparsable files are another gate's problem
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", "")
        if name not in ("run", "Popen", "check_output", "check_call"):
            continue
        has_text_true = any(
            k.arg == "text" and getattr(k.value, "value", None) is True
            for k in node.keywords)
        has_encoding = any(k.arg == "encoding" for k in node.keywords)
        if has_text_true and not has_encoding:
            hits.append(node.lineno)
    return sorted(hits)


def check_encoding_discipline() -> tuple[bool, str]:
    """No bare text=True subprocess calls in engine/script code — each one
    is a latent cp1251 mojibake bug on Windows (use _compat.run, or pass
    encoding='utf-8', errors='replace')."""
    bad = []
    patterns = ("memory/db-tools/*.py", "memory/scripts/*.py",
                "scripts/*.py", "scripts/tools/*.py", "eval/*.py")
    for pattern in patterns:
        for p in sorted(KIT.glob(pattern)):
            for ln in find_bare_text_true(
                    p.read_text(encoding="utf-8", errors="replace")):
                bad.append(f"{p.relative_to(KIT).as_posix()}:{ln}")
    return (not bad, "no bare text=True" if not bad else "; ".join(bad[:5]))

def check_backup_freshness() -> tuple[bool, str]:
    """Backup/DR freshness (wave1 Task 4): WARN when the newest memory
    backup is older than 14 days or none exists. WARN-tier: doctor stays
    green (ok=True) — a stale backup must not block work, only nag."""
    root = Path(os.environ.get("MEMORY_ROOT") or Path.home() / ".memory")
    backups = root / "backups"
    if not backups.is_dir():
        return (True, "no backups yet (WARN: run scripts/tools/backup_memory.py)")
    stamps = sorted(e.name for e in backups.iterdir()
                    if e.is_dir() and re.fullmatch(r"\d{8}T\d{6}", e.name))
    if not stamps:
        return (True, "backups dir has no YYYYMMDDTHHMMSS entries (WARN)")
    try:
        age_days = (datetime.now()
                    - datetime.strptime(stamps[-1], "%Y%m%dT%H%M%S")
                    ).total_seconds() / 86400
    except ValueError:
        return (True, f"unparseable backup name: {stamps[-1]}")
    if age_days > 14:
        return (True, f"newest backup {int(age_days)}d old (WARN: refresh)")
    return (True, f"newest backup {int(age_days)}d old")



# Deployed kit-skills copies the drift check knows about (wave3 Task 10).
# ~/.gemini/skills and ~/.zcode/skills are junctions to the kit master on
# this machine — resolve-equal targets are skipped, real copies are
# byte-compared. Extend the list when a new adapter starts copying.
_DEPLOYED_SKILL_DIRS = (
    Path.home() / ".agents" / "skills",
    Path.home() / ".claude" / "skills",
    KIT / ".agents" / "skills",
)


def check_skills_sync() -> tuple[bool, str]:
    """Canonical-skills drift (wave3 Task 10): byte-compare every deployed
    copy of the kit skills tree against skills/ (pattern:
    check_engine_sync). Only copies that exist are compared; junctions
    (resolve() == master) track the master live and are skipped. No
    deployed copy at all = WARN (backup-freshness semantics: a missing
    copy must not block work, only nag). FAIL names the drifted slugs."""
    names = sorted(d.name for d in (KIT / "skills").iterdir()
                   if d.is_dir())
    candidates = [d for d in _DEPLOYED_SKILL_DIRS if d.is_dir()]
    if not candidates:
        return (True, ("WARN: no deployed skills copy found "
                       "(run deploy.py --canonical)"))
    bad: list[str] = []
    for dest in candidates:
        for name in names:
            src, target = KIT / "skills" / name, dest / name
            if not target.exists():
                bad.append(f"{dest.parent.name}/{name}: missing")
                continue
            try:
                linked = target.resolve() == src.resolve()
            except OSError:
                linked = False
            if linked:
                continue
            for f in src.rglob("*"):
                if not f.is_file():
                    continue
                tf = target / f.relative_to(src)
                if not tf.exists():
                    bad.append(f"{dest.parent.name}/{name}/"
                               f"{f.relative_to(src)}: missing")
                elif f.read_bytes() != tf.read_bytes():
                    bad.append(f"{dest.parent.name}/{name}/"
                               f"{f.relative_to(src)}: diff")
            for f in target.rglob("*"):
                if f.is_file() and not (src / f.relative_to(target)).exists():
                    bad.append(f"{dest.parent.name}/{name}/"
                               f"{f.relative_to(target)}: extra")
    if bad:
        return (False, "; ".join(bad[:5])
                + (f" (+{len(bad) - 5} more)" if len(bad) > 5 else ""))
    label = ", ".join(
        ("repo .agents/skills" if d == KIT / ".agents" / "skills"
         else str(d.parent).replace(str(Path.home()), "~"))
        for d in candidates)
    return (True, f"{len(names)} skills in sync ({label})")

def main() -> int:
    checks = [
        ("manifest", check_manifest()),
        ("versions", check_versions()),
        ("frontmatter", check_frontmatter()),
        ("file-size gate", check_gate()),
        ("memory+db", check_memory()),
        ("adapters", check_adapters()),
        ("override", check_override()),
        ("engine sync", check_engine_sync()),
        ("integrity", check_integrity()),
        ("supply chain", check_skill_supply_chain()),
        ("frontmatter-spec", check_frontmatter_spec()),
        ("skills-sync", check_skills_sync()),
        ("backup freshness", check_backup_freshness()),
        ("encoding discipline", check_encoding_discipline()),
    ]
    fails = 0
    print(f"{'CHECK':<16} {'RESULT':<6} DETAIL")
    for name, (ok, detail) in checks:
        fails += 0 if ok else 1
        print(f"{name:<16} {'OK' if ok else 'FAIL':<6} {detail}")
    print(f"\n== {'All systems GREEN' if not fails else str(fails) + ' FAILURES'}"
          f" ({len(checks)} checks) ==")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())