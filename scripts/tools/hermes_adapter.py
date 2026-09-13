#!/usr/bin/env python3
"""hermes_adapter.py — Hermes-only coding-kit integration (plan H2, 2026-09-12).

Three owned surfaces in a Hermes profile (HERMES_HOME):
  1. <home>/kit-skills/coding-kit/<skill>/   — generated projection of kit skills
  2. skills.external_dirs entry in <home>/config.yaml pointing at <home>/kit-skills
  3. a delimited kit block inside <home>/SOUL.md (routing only, not a soul copy)

Everything else in the profile is foreign and never touched. Default action is a
read-only preview; apply is explicit. Apply is idempotent, diff-driven, and rolls
back on handled failures (via the kit's DeployTransaction). restore reverses to
the exact prior state recorded at apply time.

Evidence behind the design: docs/research/2026-09-13-hermes-h1-evidence.md
(external root = full visibility + curator write protection; local copies are
archivable by the curator when their names are bundled; missing external roots
are silently skipped by Hermes, so this tool validates existence itself).

Usage:
    python hermes_adapter.py --kit <kit-root> --hermes-home <profile> preview
    python hermes_adapter.py --kit <kit-root> --hermes-home <profile> apply
    python hermes_adapter.py --kit <kit-root> --hermes-home <profile> apply --retire-legacy
    python hermes_adapter.py --kit <kit-root> --hermes-home <profile> restore

    --ext-root <dir> overrides the default <home>/kit-skills location.
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from ._deploy_fs import (is_link, has_link_ancestor, is_safe_under_boundary,
                             safe_write_text, safe_rmtree, safe_copytree)
    from ._deploy_tx import DeployTransaction
    from ._hermes_recovery import capture, restore_path, validate_image
except (ImportError, ValueError):
    import importlib.util

    _here = Path(__file__).resolve().parent
    for _name in ("_deploy_fs", "_deploy_tx", "_hermes_recovery"):
        _spec = importlib.util.spec_from_file_location(_name, _here / (_name + ".py"))
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        globals()[_name] = _mod
    is_link = _deploy_fs.is_link
    has_link_ancestor = _deploy_fs.has_link_ancestor
    is_safe_under_boundary = _deploy_fs.is_safe_under_boundary
    safe_write_text = _deploy_fs.safe_write_text
    safe_rmtree = _deploy_fs.safe_rmtree
    safe_copytree = _deploy_fs.safe_copytree
    capture = _hermes_recovery.capture
    restore_path = _hermes_recovery.restore_path
    validate_image = _hermes_recovery.validate_image
    DeployTransaction = _deploy_tx.DeployTransaction

CATEGORY = "coding-kit"
EXT_DIR_NAME = "kit-skills"
MARK_BEGIN = "<!-- kit:begin v{version} -->"
MARK_END = "<!-- kit:end -->"
STATE_NAME = ".kit-hermes-state.json"
RESTORE_NAME = ".kit-hermes-restore.json"

last_report_text = ""


def _report(text):
    global last_report_text
    last_report_text = text
    print(text)


SOUL_BLOCK = """{begin}
coding-kit {version}: methodology skills live under `{ext_root}/{category}/`
(load via `skill_view coding-kit/<name>`; bare names may collide with local skills).
Project memory: `python ~/.memory/db-tools/search_all.py "<topic>"` (findings/Wiki;
check [superseded]/[unverified] badges). Past conversations: `session_search`.
Native MEMORY.md is bounded (~2,200 chars): when full, offload durable facts with
`findings.py add`. Kit updates: python scripts/tools/hermes_adapter.py ... apply.
{end}"""


class Conflict(Exception):
    pass


def kit_version(kit: Path) -> str:
    v = kit / "VERSION"
    if not v.is_file():
        raise Conflict(f"kit VERSION not found: {v}")
    return v.read_text(encoding="utf-8").strip()


def kit_skills(kit: Path) -> list[Path]:
    root = kit / "skills"
    if not root.is_dir():
        raise Conflict(f"kit skills/ not found: {root}")
    return sorted((d for d in root.iterdir() if (d / "SKILL.md").is_file()),
                  key=lambda d: d.name)


def validate(kit: Path, home: Path, ext_root: Path):
    """Shared preflight for preview/apply/restore; raises Conflict."""
    if not home.is_dir():
        raise Conflict(f"hermes home not found: {home}")
    if has_link_ancestor(home, home.parent if home.parent != home else Path(home.anchor)):
        raise Conflict(f"hermes home path or ancestor is a link: {home}")
    version = kit_version(kit)
    skills = kit_skills(kit)
    if not skills:
        raise Conflict(f"no skills with SKILL.md under {kit / 'skills'}")
    if (ext_root == home or not ext_root.is_relative_to(home)
            or ext_root.is_relative_to(home / "skills")
            or kit.is_relative_to(ext_root) or ext_root.is_relative_to(kit)):
        raise Conflict("external root must be a separate directory inside the profile, outside skills/ and kit")
    for path in (ext_root, home / "config.yaml", home / "SOUL.md",
                 home / STATE_NAME, home / RESTORE_NAME, home / "skills" / CATEGORY):
        _check_path(path, home)
    for source in skills:
        _check_path(source, kit)
    state = _load_json(home / STATE_NAME)
    if state and state["after_apply"]["ext_root"] != ext_root.as_posix():
        raise Conflict("external root changed; restore the existing integration first")
    if bool(state) != (home / RESTORE_NAME).exists():
        raise Conflict("incomplete recovery state; preserve files and inspect recovery records")
    return version, skills


def bundled_names(home: Path) -> set:
    mf = home / "skills" / ".bundled_manifest"
    out = set()
    if mf.is_file():
        for line in mf.read_text(encoding="utf-8", errors="replace").splitlines():
            name = line.split(":", 1)[0].strip()
            if name:
                out.add(name)
    return out


def local_skill_names(home: Path) -> set:
    """Frontmatter-name set of LOCAL skills (excluding the legacy coding-kit copy)."""
    out = set()
    for md in (home / "skills").rglob("SKILL.md"):
        rel = md.relative_to(home / "skills")
        if rel.parts and rel.parts[0] == CATEGORY:
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            continue
        m = re.search(r"^name:\s*['\"]?([^'\"\n]+)", text, re.M)
        out.add((m.group(1).strip() if m else md.parent.name))
    return out


def _soul_block_version(soul_text: str) -> str:
    m = re.search(re.escape("<!-- kit:begin v") + r"([^ ]+)", soul_text)
    return m.group(1) if m else "?"


def plan(kit: Path, home: Path, ext_root: Path, retire_legacy: bool) -> dict:
    """Read-only planning: what apply would do + warnings. Raises Conflict on hard blocks."""
    version, skills = validate(kit, home, ext_root)
    cat_dir = ext_root / CATEGORY
    actions = []
    warnings = []

    legacy = home / "skills" / CATEGORY
    if legacy.exists():
        if retire_legacy:
            actions.append(f"retire legacy {legacy} (preimage stored outside discovery in {RESTORE_NAME})")
        else:
            raise Conflict(
                f"legacy local copy {legacy} exists: its skills are curator-archivable "
                f"(bundled names + prune_builtins). Re-run with --retire-legacy to move "
                f"it out of skills/ and adopt the external root layout")

    names = [d.name for d in skills]
    bundled = bundled_names(home) & set(names)
    if bundled:
        warnings.append(
            f"bundled-name overlap ({', '.join(sorted(bundled))}): curator eligibility "
            f"flag will read True, but archive_skill refuses EXTERNAL skills — no action "
            f"needed while the kit stays in the external root")
    local_dupes = local_skill_names(home) & set(names)
    if local_dupes:
        warnings.append(
            f"local same-name skills ({', '.join(sorted(local_dupes))}) will claim these "
            f"names in the prompt; load kit procedures via {CATEGORY}/<name>")

    # projection diff
    changed = removed = kept = 0
    for d in skills:
        tgt = cat_dir / d.name
        if not tgt.exists():
            changed += 1
            actions.append(f"install {CATEGORY}/{d.name}")
        elif not _dir_equal(d, tgt):
            changed += 1
            actions.append(f"update  {CATEGORY}/{d.name}")
        else:
            kept += 1
    if cat_dir.exists():
        owned = set(names)
        previous = _load_json(home / STATE_NAME) or {}
        previous_names = set(previous.get("after_apply", {}).get("names", []))
        for existing in cat_dir.iterdir():
            if existing.name in previous_names and existing.name not in owned:
                removed += 1
                actions.append(f"retire  {CATEGORY}/{existing.name} (not in kit {version})")

    # config entry
    cfg_path = home / "config.yaml"
    cfg = cfg_path.read_text(encoding="utf-8") if cfg_path.is_file() else ""
    ext_posix = ext_root.as_posix()
    if ext_posix in cfg:
        actions.append("config  external_dirs already contains kit root")
    else:
        actions.append(f"config  add external_dirs entry: {ext_posix}")
    # SOUL block
    soul = home / "SOUL.md"
    soul_text = soul.read_text(encoding="utf-8") if soul.is_file() else ""
    begin = MARK_BEGIN.format(version=version)
    if begin in soul_text:
        state_line = "present"
    elif MARK_END in soul_text:
        state_line = f"update ({_soul_block_version(soul_text)} -> {version})"
    else:
        state_line = "append"
    actions.append(f"SOUL    {state_line} kit block ({version})")

    return {"version": version, "names": names, "actions": actions,
            "warnings": warnings, "install_or_update": changed, "retired": removed,
            "kept": kept}


def _dir_equal(a: Path, b: Path) -> bool:
    """Exact bytes and empty directories matter for supporting assets."""
    def files(root: Path) -> dict:
        return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None
                for p in root.rglob("*")}
    return files(a) == files(b)

def _patch_config(cfg: str, ext_posix: str) -> str:
    """Add the kit root to skills.external_dirs, preserving all other content.

    Config files in the wild carry CRLF line endings; every pattern tolerates
    a trailing \r and inserted lines are LF (Hermes YAML parsers accept both).
    """
    if ext_posix in cfg:
        return cfg
    if re.search(r"(?m)^skills:\s*\r?$", cfg):
        m = re.search(r"(?ms)^skills:\s*?\r?\n((?:[ \t]+.*\r?\n?)*)", cfg)
        section = m.group(1) if m else ""
        if re.search(r"(?m)^([ \t]+)external_dirs:", section):
            em = re.search(
                r"(?ms)^([ \t]+)external_dirs:[ \t]*\r?\n((?:\1[ \t]+- [^\r\n]*\r?\n?)+)", cfg)
            if em:
                indent = em.group(1)
                new_entry = f"{indent}    - {ext_posix}\n"
                return cfg[:em.end(2)] + new_entry + cfg[em.end(2):]
            fm = re.search(r"(?m)^([ \t]+)external_dirs:[ \t]*(\[[^\r\n]*\])[ \t]*\r?$", cfg)
            if fm:
                inner = fm.group(2)[1:-1].strip()
                add = f"'{ext_posix}'"
                joined = f"{inner}, {add}" if inner else add
                return cfg[:fm.start(2)] + f"[{joined}]" + cfg[fm.end(2):]
            raise Conflict("cannot parse skills.external_dirs shape; edit config.yaml manually")
        m2 = re.search(r"(?m)^skills:\s*\r?$", cfg)
        insert = f"  external_dirs:\n    - {ext_posix}\n"
        return cfg[:m2.end()] + "\n" + insert + cfg[m2.end():]
    if not cfg.endswith("\n"):
        cfg += "\n"
    return cfg + f"\nskills:\n  external_dirs:\n    - {ext_posix}\n"


def _patch_soul(soul: str, version: str, ext_root: Path) -> str:
    """Replace/insert ONLY the delimited kit block; personal text stays untouched."""
    block = SOUL_BLOCK.format(
        begin=MARK_BEGIN.format(version=version), end=MARK_END,
        version=version, ext_root=ext_root.as_posix(), category=CATEGORY)
    # replace any older kit block regardless of its version marker
    pattern = re.compile(r"(?s)<!-- kit:begin v[^>]*-->\n?<!\[CDATA\[.*?\]\]>\n?<!-- kit:end -->"
                         r"|<!-- kit:begin v[^>]*-->.*?<!-- kit:end -->")
    if pattern.search(soul):
        return pattern.sub(lambda _m: block, soul, count=1)
    if soul and not soul.endswith("\n"):
        soul += "\n"
    return soul + ("\n" if soul else "") + block + "\n"


def _check_path(path: Path, home: Path):
    if not is_safe_under_boundary(path, home):
        raise Conflict(f"unsafe path or link: {path}")
    if path.is_dir():
        for child in path.rglob("*"):
            if is_link(child):
                raise Conflict(f"link inside managed tree: {child}")


def apply_adapter(kit: Path, home: Path, ext_root: Path, retire_legacy: bool,
                  plan_data: dict) -> int:
    version, names = plan_data["version"], plan_data["names"]
    state_path, anchor_path = home / STATE_NAME, home / RESTORE_NAME
    previous = _load_json(state_path) or {}
    prev_names = set(previous.get("after_apply", {}).get("names", []))
    anchor = _load_json(anchor_path) or {"format": 2, "paths": {}, "created_dirs": []}
    if anchor.get("format") != 2:
        raise Conflict("unsupported recovery format; preserve the original snapshot")
    cat_dir = ext_root / CATEGORY
    changed = [d for d in kit_skills(kit)
               if not (cat_dir / d.name).exists() or not _dir_equal(d, cat_dir / d.name)]
    retired = [cat_dir / n for n in sorted(prev_names - set(names)) if (cat_dir / n).exists()]
    legacy = home / "skills" / CATEGORY
    targets = [cat_dir / d.name for d in changed] + retired
    if legacy.exists() and retire_legacy:
        targets.append(legacy)
    texts = {}
    for name, patch in (("config.yaml", lambda s: _patch_config(s, ext_root.as_posix())),
                        ("SOUL.md", lambda s: _patch_soul(s, version, ext_root))):
        path = home / name
        old = path.read_bytes().decode("utf-8") if path.exists() else ""
        new = patch(old)
        if new != old:
            targets.append(path)
            texts[path] = new
    after = {"version": version, "names": names, "ext_root": ext_root.as_posix()}
    if not targets and previous.get("after_apply") == after:
        return 0
    for path in targets:
        rel = path.relative_to(home).as_posix()
        if rel not in anchor["paths"]:
            anchor["paths"][rel] = capture(path)
        parent = path.parent
        while parent != home and not parent.exists():
            rel_parent = parent.relative_to(home).as_posix()
            if rel_parent not in anchor["created_dirs"]:
                anchor["created_dirs"].append(rel_parent)
            parent = parent.parent
    with DeployTransaction() as tx:
        for path in targets + [state_path, anchor_path]:
            tx.record_absent_ancestors(path.parent)
            tx.snapshot_target(path)
        tx.mark_mutations_started()
        for source in changed:
            target = cat_dir / source.name
            if target.exists():
                safe_rmtree(target)
            safe_copytree(source, target, home)
        for path in retired + ([legacy] if legacy in targets else []):
            safe_rmtree(path)
        for path, content in texts.items():
            safe_write_text(path, content, boundary=home)
        safe_write_text(state_path, json_dumps({"after_apply": after}), boundary=home)
        safe_write_text(anchor_path, json_dumps(anchor), boundary=home)
        tx.commit()
    return 0


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _load_json(path: Path):
    if not path.exists():
        return None
    import json
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected object")
        return data
    except (ValueError, UnicodeError) as exc:
        raise Conflict(f"invalid recovery record {path}: {exc}") from exc


def restore(home: Path) -> int:
    """Restore recorded owned paths; preserve unrelated additions outside them."""
    anchor_path, state_path = home / RESTORE_NAME, home / STATE_NAME
    for path in (anchor_path, state_path):
        _check_path(path, home)
    snap = _load_json(anchor_path)
    if not snap:
        _report("nothing to restore: no prior apply recorded")
        return 1
    if snap.get("format") != 2:
        raise Conflict("unsupported recovery format; preserve the original snapshot")
    paths = []
    for rel, image in snap["paths"].items():
        path = home / rel
        if Path(rel).is_absolute() or ".." in Path(rel).parts or ":" in rel:
            raise Conflict(f"invalid recovery path: {rel}")
        _check_path(path, home)
        validate_image(image)
        paths.append((path, image))
    parents = [home / rel for rel in snap["created_dirs"]]
    for parent in parents:
        _check_path(parent, home)
    with DeployTransaction() as tx:
        for path, _ in paths:
            tx.snapshot_target(path)
        for path in (anchor_path, state_path):
            tx.snapshot_target(path)
        tx.mark_mutations_started()
        for path, image in paths:
            restore_path(path, image, safe_rmtree)
        for parent in sorted(parents, key=lambda p: len(p.parts), reverse=True):
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        for path in (state_path, anchor_path):
            if path.exists():
                path.unlink()
        tx.commit()
    _report(f"restored recorded owned paths in {home}; unrelated paths preserved")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:]) if argv is None and __name__ == "__main__" else list(argv or [])
    import argparse
    ap = argparse.ArgumentParser(
        description="Hermes-only coding-kit integration (preview/apply/restore)",
        epilog="Docs: adapters/hermes.md; evidence: docs/research/2026-09-13-hermes-h1-evidence.md")
    ap.add_argument("--kit", required=True, help="coding-kit repo root")
    ap.add_argument("--hermes-home", required=True,
                    help="Hermes profile dir (HERMES_HOME) — target of all changes")
    ap.add_argument("--ext-root", default=None,
                    help="external skills root (default: <home>/kit-skills)")
    ap.add_argument("command", choices=["preview", "apply", "restore"], nargs="?", default="preview")
    ap.add_argument("--retire-legacy", action="store_true",
                    help="apply: move legacy <home>/skills/coding-kit out of skills/")
    args = ap.parse_args(argv)

    kit = Path(args.kit).expanduser().resolve()
    home = Path(args.hermes_home).expanduser().resolve()
    ext_root = (Path(args.ext_root).expanduser().resolve() if args.ext_root
                else home / EXT_DIR_NAME)

    try:
        if args.command == "restore":
            return restore(home)
        data = plan(kit, home, ext_root, args.retire_legacy)
        if args.command == "preview":
            lines = [f"coding-kit {data['version']} -> hermes home {home}",
                     f"ext root: {ext_root.as_posix()}" + (
                         " (exists)" if ext_root.is_dir() else " (will be created)"),
                     ""]
            lines += [f"  {a}" for a in data["actions"]]
            if data["warnings"]:
                lines += ["", "warnings:"]
                lines += [f"  ! {w}" for w in data["warnings"]]
            _report("\n".join(lines))
            return 0
        # apply: print plan, then mutate under transaction
        lines = [f"apply coding-kit {data['version']} -> {home}", ""]
        lines += [f"  {a}" for a in data["actions"]]
        for w in data["warnings"]:
            lines.append(f"  ! {w}")
        rc = apply_adapter(kit, home, ext_root, args.retire_legacy, data)
        lines += ["", f"apply OK (rc=0); rollback snapshot: {home / RESTORE_NAME}"]
        _report("\n".join(lines))
        return rc
    except Conflict as e:
        _report(f"CONFLICT: {e}")
        return 1
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as e:
        _report(f"FAILED: {e}; handled mutation failures attempt rollback; inspect recovery diagnostics")
        return 1


if __name__ == "__main__":
    sys.exit(main())
