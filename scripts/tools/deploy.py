#!/usr/bin/env python3
"""deploy.py — one-shot coding-kit rollout to every harness on this machine.

Usage:
    python scripts/tools/deploy.py        (or double-click update-kit.bat)
    python scripts/tools/deploy.py --dry-run   (read-only full-deploy preview)

Idempotent. Steps:
  1. Skills: sync KIT/skills -> ~/.claude/skills, ~/.agents/skills,
     ~/.zcode/skills (add / update / remove). Destinations junctioned directly
     to KIT/skills (e.g. ~/.zcode/skills) track master live and are skipped
     with zero writes. Foreign or dangling linked destinations/ancestors
     fail closed during preflight to prevent escapes.
     Local-only skill dirs are never touched: each target keeps a
     .kit-manifest.json naming the skills the kit owns; only manifest
     entries are eligible for removal.
     ~/.claude/CLAUDE.md keeps its machine-local triggers: only the
     version / date / skill-count line is bumped in place.
     An existing <!-- CODEGRAPH --> block is carried over verbatim.
  3. Verify: byte-compare every deployed skill against the master, check
     every router header, exit non-zero on any mismatch.
"""
import argparse
import json
import os
import re
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from ._deploy_tx import DeployTransaction
except (ImportError, ValueError):
    try:
        from _deploy_tx import DeployTransaction
    except ImportError:
        # Fallback when running directly or dynamically loaded from other paths
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_deploy_tx", Path(__file__).resolve().parent / "_deploy_tx.py"
        )
        _tx_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_tx_mod)
        DeployTransaction = _tx_mod.DeployTransaction

KIT = Path(__file__).resolve().parents[2]
SKILLS = KIT / "skills"
SOUL_MARKER = "# coding-kit — Agent Soul"
MANIFEST_NAME = ".kit-manifest.json"
TODAY = time.strftime("%Y-%m-%d")
VERSION = (KIT / "VERSION").read_text(encoding="utf-8").strip()

# Harnesses with a uniform regenerable router.
# skills_dir None = harness has no own kit skills copy (omp auto-discovers
# ~/.claude/skills; codex/opencode use none). skills_line None = omit line.
HARNESSES = [
    {"id": "omp", "router": "~/.omp/agent/AGENTS.md", "name": "OMP",
     "skills_line": "# Skills: auto-discovered (kit skills synced to ~/.claude/skills)",
     "skills_dir": None},
    # Gemini CLI was retired by Google on 2026-06-18 (Antigravity CLI is
    # the successor and has its own target above); the chat-JSON reader
    # (eval/transcript_normalize.py) stays for historical archives.
    {"id": "antigravity", "router": "~/AGENTS.md", "name": "Antigravity",
     "skills_line": "# Skills: ~/.agents/skills/",
     "skills_dir": "~/.agents/skills"},
    {"id": "zcode", "router": "~/.zcode/AGENTS.md", "name": "ZCode",
     "skills_line": "# Skills: ~/.zcode/skills/",
     "skills_dir": "~/.zcode/skills"},
    {"id": "codex", "router": "~/.codex/AGENTS.md", "name": "Codex",
     "skills_line": None, "skills_dir": None},
    {"id": "opencode", "router": "~/.config/opencode/AGENTS.md", "name": "OpenCode",
     "skills_line": None, "skills_dir": None},
]
CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
SYNC_TARGETS = ["~/.claude/skills", "~/.agents/skills", "~/.zcode/skills"]

def integrity_gate():
    """CBSE pre-copy gate (wave1 Task 2): refuse to roll out a kit tree
    whose control plane has drifted from integrity-manifest.json. Exit 3
    = integrity failure (distinct from deploy's own exit 1 = verify
    failure). Detects drift; a harness-level hook compromise is out of
    scope (Cymulate caveat)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "integrity_manifest",
        KIT / "scripts" / "tools" / "integrity_manifest.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    data = m.load_manifest(KIT)
    if data is None:
        print(f"INTEGRITY FAIL: no readable {m.MANIFEST_NAME} in {KIT} — "
              "run integrity_manifest.py --update first")
        raise SystemExit(3)
    problems = m.check(KIT, data["files"])
    if problems:
        for p in problems[:10]:
            print("INTEGRITY FAIL:", p)
        if len(problems) > 10:
            print(f"INTEGRITY FAIL: +{len(problems) - 10} more")
        raise SystemExit(3)
    print(f"integrity OK: {len(data['files'])} control-plane files verified")


try:
    from ._deploy_fs import (is_link, has_link_ancestor, is_safe_under_boundary,
                             safe_write_text, safe_copytree, safe_rmtree,
                             scan_skill_links)
except (ImportError, ValueError):
    try:
        from _deploy_fs import (is_link, has_link_ancestor, is_safe_under_boundary,
                                safe_write_text, safe_copytree, safe_rmtree,
                                scan_skill_links)
    except ImportError:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "_deploy_fs", Path(__file__).resolve().parent / "_deploy_fs.py")
        _fs = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_fs)
        (is_link, has_link_ancestor, is_safe_under_boundary, safe_write_text,
         safe_copytree, safe_rmtree, scan_skill_links) = (
            _fs.is_link, _fs.has_link_ancestor, _fs.is_safe_under_boundary,
            _fs.safe_write_text, _fs.safe_copytree, _fs.safe_rmtree,
            _fs.scan_skill_links)


def home(p):
    return Path(p).expanduser()


def master_skill_names():
    return sorted(x.name for x in SKILLS.iterdir() if x.is_dir())


def validate_manifest(dest: Path, mani: object) -> tuple[bool, str | None]:
    """CR-02: validate the ENTIRE manifest BEFORE any mutation of that destination:
    JSON object with skills: list of single-component names (no path separators,
    no absolute paths, no "." / "..", must resolve inside dest, entry must not be a symlink/junction).
    Malformed manifest -> fail closed for that dest BEFORE sync starts (no writes), clear error.
    """
    if not isinstance(mani, dict):
        return False, f"manifest must be a JSON object, got {type(mani).__name__}"
    if "skills" not in mani or not isinstance(mani["skills"], list):
        return False, "manifest missing required 'skills' list"
    dest_resolved = dest.resolve()
    for item in mani["skills"]:
        if not isinstance(item, str) or not item.strip():
            return False, f"invalid skill name entry in manifest: {item!r}"
        if item in (".", "..") or "/" in item or "\\" in item or Path(item).is_absolute():
            return False, f"traversal or non-single-component skill name in manifest: {item!r}"
        target = dest / item
        if is_link(target):
            return False, f"manifest skill entry is a symlink or junction: {item!r}"
        try:
            # Must resolve strictly inside dest
            target_resolved = target.resolve()
            if target.exists() and not str(target_resolved).startswith(str(dest_resolved)):
                return False, f"manifest entry resolves outside destination: {item!r}"
        except Exception as e:
            return False, f"error resolving manifest entry {item!r}: {e}"
    return True, None


def load_manifest(dest: Path):
    f = dest / MANIFEST_NAME
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def dirs_byte_identical(src: Path, target: Path) -> bool:
    """Check whether all files in src and target are byte-identical and have identical layout."""
    if not target.exists() or not target.is_dir() or is_link(target):
        return False
    if scan_skill_links(target.parent, target):
        return False
    src_files = {f.relative_to(src): f for f in src.rglob("*") if f.is_file()}
    target_files = {f.relative_to(target): f for f in target.rglob("*") if f.is_file()}
    if set(src_files.keys()) != set(target_files.keys()):
        return False
    for rel, sf in src_files.items():
        tf = target_files[rel]
        if is_link(tf) or sf.read_bytes() != tf.read_bytes():
            return False
    return True

def sync_one_skill(src: Path, target: Path, log, dest: Path | None = None,
                   dry: bool = False):
    """File-level sync of one skill dir; appends the action list.

    dry=True computes the identical action list without writing anything.
    Validation (links/escapes) still raises in both modes.
    """
    root_dest = dest or target.parent
    if is_link(target):
        raise RuntimeError(f"Refusing to sync to link {target}")
    if not target.exists():
        if not dry:
            safe_copytree(src, target, boundary=root_dest)
        log.append("add " + src.name)
        return
    dest_res = root_dest.resolve()
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        tf = target / rel
        if is_link(tf):
            raise RuntimeError(f"Refusing to write to link {tf}")
        if tf.exists() and not tf.resolve().is_relative_to(dest_res):
            raise RuntimeError(f"Refusing to write outside destination {tf}")
        if not tf.exists() or f.read_bytes() != tf.read_bytes():
            if not dry:
                tf.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, tf)
            log.append("upd " + src.name + "/" + str(rel))
    for f in target.rglob("*"):
        if f.is_file() and not (src / f.relative_to(target)).exists():
            if is_link(f):
                raise RuntimeError(f"Refusing to unlink link {f}")
            if not dry:
                f.unlink()
            log.append("del " + src.name + "/" + str(f.relative_to(target)))
@dataclass
class SkillsReport:
    target: str
    actions: list[str]
    manifest: dict | None
    ok: bool = True
def preflight_skills() -> tuple[bool, list[dict], list[SkillsReport]]:
    names = master_skill_names()
    preflight = []
    any_failure = False
    # Preflight master skills for links first
    for name in names:
        src = SKILLS / name
        if is_link(src) or scan_skill_links(SKILLS, src):
            err_report = [SkillsReport(str(SKILLS), [f"ERROR: master skill {name} contains links/escapes"], None, ok=False)]
            return False, [], err_report

    for d in SYNC_TARGETS:
        dest = home(d)
        # Supported master alias: exact destination resolves to SKILLS
        if is_link(dest):
            try:
                if dest.resolve() == SKILLS.resolve():
                    preflight.append({"d": d, "dest": dest, "kind": "master_alias", "ok": True})
                    continue
            except Exception:
                pass
            preflight.append({
                "d": d, "dest": dest, "kind": "error", "ok": False,
                "errors": [f"ERROR: destination {dest} is a foreign or broken symlink/junction (rejected)"],
            })
            any_failure = True
            continue
        if has_link_ancestor(dest, Path.home()):
            preflight.append({
                "d": d, "dest": dest, "kind": "error", "ok": False,
                "errors": [f"ERROR: destination {dest} ancestor is a symlink/junction (rejected)"],
            })
            any_failure = True
            continue
        mani_file = dest / MANIFEST_NAME
        if is_link(mani_file):
            preflight.append({
                "d": d, "dest": dest, "kind": "error", "ok": False,
                "errors": [f"ERROR: manifest {mani_file} is a symlink/junction (wrong type or escape)"],
            })
            any_failure = True
            continue
        mani = None
        if mani_file.exists():
            if not mani_file.is_file():
                preflight.append({
                    "d": d, "dest": dest, "kind": "error", "ok": False,
                    "errors": [f"ERROR: manifest {mani_file} exists but is not a regular file"],
                })
                any_failure = True
                continue
            try:
                raw_mani = json.loads(mani_file.read_text(encoding="utf-8"))
            except Exception as e:
                preflight.append({"d": d, "dest": dest, "kind": "error", "ok": False, "errors": [f"ERROR: malformed manifest JSON: {e}"]})
                any_failure = True
                continue
            valid, err = validate_manifest(dest, raw_mani)
            if not valid:
                preflight.append({"d": d, "dest": dest, "kind": "error", "ok": False, "errors": [f"ERROR: malformed manifest ({err})"]})
                any_failure = True
                continue
            mani = raw_mani

        manifest_skills = set(mani.get("skills", [])) if mani else set()
        conflicts = []
        owned_skills = []
        for name in names:
            target = dest / name
            if is_link(target):
                conflicts.append(f"skill {name} is a symlink/junction")
                continue
            if not target.exists():
                owned_skills.append(name)
                continue
            bad_links = scan_skill_links(dest, target)
            if bad_links:
                conflicts.append(f"skill {name} contains symlink/junction/escape: {', '.join(bad_links)}")
            elif name in manifest_skills:
                owned_skills.append(name)
            elif dirs_byte_identical(SKILLS / name, target):
                owned_skills.append(name)
            else:
                conflicts.append(f"unowned skill {name} exists with differing content")

        # Preflight stale removal candidates for nested links BEFORE any writes
        if mani:
            for stale_name in mani.get("skills", []):
                if stale_name not in names:
                    stale_dir = dest / stale_name
                    if is_link(stale_dir):
                        conflicts.append(f"stale skill {stale_name} is a symlink/junction")
                    elif stale_dir.exists():
                        bad_stale_links = scan_skill_links(dest, stale_dir)
                        if bad_stale_links:
                            conflicts.append(f"stale skill {stale_name} contains symlink/junction/escape: {', '.join(bad_stale_links)}")

        if conflicts:
            preflight.append({
                "d": d, "dest": dest, "kind": "conflict", "ok": False,
                "mani": mani,
                "conflicts": [f"CONFLICT: {c} (skipping)" for c in conflicts],
            })
            any_failure = True
        else:
            preflight.append({
                "d": d, "dest": dest, "kind": "ok", "ok": True,
                "mani": mani,
                "manifest_skills": manifest_skills,
                "owned_skills": owned_skills,
            })

    report = []
    for item in preflight:
        kind = item["kind"]
        if kind == "master_alias":
            report.append(SkillsReport(item["d"], ["skip (master junction - always current)"], None, ok=True))
        elif kind == "error":
            report.append(SkillsReport(item["d"], item["errors"], None, ok=False))
        elif kind == "conflict":
            report.append(SkillsReport(item["d"], item["conflicts"], item["mani"], ok=False))
        elif any_failure:
            report.append(SkillsReport(item["d"], ["aborted (prior destination had conflicts/errors)"], item["mani"], ok=False))
    return (not any_failure), preflight, report


def execute_skills(preflight: list[dict], dry: bool = False) -> list[SkillsReport]:
    """Sync owned skills, remove stale manifest entries, refresh the manifest.

    dry=True performs the identical computation (same action list, same
    validation) and writes nothing.
    """
    names = master_skill_names()
    report = []
    for item in preflight:
        d, dest, kind = item["d"], item["dest"], item["kind"]
        if kind == "master_alias":
            report.append(SkillsReport(d, ["skip (master junction - always current)"], None, ok=True))
            continue
        if not dest.exists() and not dry:
            dest.mkdir(parents=True)

        log = []
        owned_skills = item["owned_skills"]
        for name in owned_skills:
            sync_one_skill(SKILLS / name, dest / name, log, dest=dest, dry=dry)

        mani = item["mani"]
        removed = []
        if mani:
            for name in mani.get("skills", []):
                if name not in names and (dest / name).exists():
                    if not dry:
                        safe_rmtree(dest / name)
                    removed.append("rm-dir " + name)

        persisted_skills = sorted(list((item["manifest_skills"] | set(owned_skills)) & set(names)))
        manifest_text = json.dumps({"kit_version": VERSION, "skills": persisted_skills}, indent=1)
        mani_path = dest / MANIFEST_NAME
        if not mani_path.exists():
            log.append("add " + MANIFEST_NAME)
        elif mani_path.read_text(encoding="utf-8", errors="replace") != manifest_text:
            log.append("upd " + MANIFEST_NAME)
        if not dry:
            safe_write_text(mani_path, manifest_text, boundary=dest)
        report.append(SkillsReport(d, log + removed, mani, ok=True))
    return report


def sync_skills() -> list[SkillsReport]:
    """Convenience wrapper for callers running preflight + execute together."""
    ok, plan, report = preflight_skills()
    if not ok:
        return report
    return execute_skills(plan)


def soul_text():
    text = (KIT / "AGENTS.md").read_text(encoding="utf-8")
    if SOUL_MARKER not in text:
        sys.exit("FATAL: marker not found in kit AGENTS.md: " + SOUL_MARKER)
    return text[text.index(SOUL_MARKER):].rstrip() + "\n"


def codegraph_block(old: str):
    m = re.search(r"<!-- CODEGRAPH_START -->.*?<!-- CODEGRAPH_END -->",
                  old, re.S)
    return ("\n" + m.group(0) + "\n") if m else ""


def is_router_kit_owned(old_content: str) -> bool:
    """A router file is kit-owned iff it carries the kit header marker or soul marker."""
    return ("# Coding Agent Router" in old_content) or (SOUL_MARKER in old_content)


def preflight_routers_and_claude() -> tuple[bool, list[str]]:
    """Preflight all router targets and CLAUDE.md before any filesystem mutations."""
    errors = []
    for h in HARNESSES:
        path = home(h["router"])
        if has_link_ancestor(path, Path.home()):
            errors.append(f"router {path} or ancestor up to home is a symlink/junction")
            continue
        if path.exists():
            if not path.is_file():
                errors.append(f"router {path} exists but is not a regular file")
                continue
            old = path.read_text(encoding="utf-8")
            if not is_router_kit_owned(old):
                errors.append(f"router {path} is foreign (missing kit marker)")
                continue
            backup_path = Path(str(path) + ".kit-bak")
            if is_link(backup_path) or (backup_path.exists() and not backup_path.is_file()):
                errors.append(f"router backup path {backup_path} is a symlink/junction or not a regular file")
    if is_link(CLAUDE_MD) or has_link_ancestor(CLAUDE_MD, Path.home()):
        errors.append(f"CLAUDE.md {CLAUDE_MD} or ancestor is a symlink/junction")
    elif CLAUDE_MD.exists() and not CLAUDE_MD.is_file():
        errors.append(f"CLAUDE.md {CLAUDE_MD} exists but is not a regular file")
    return (len(errors) == 0), errors


def regen_routers(dry: bool = False):
    """Regenerate kit-owned routers. dry=True reports planned actions only."""
    soul = soul_text()
    kit = KIT.as_posix()
    actions = []
    for h in HARNESSES:
        path = home(h["router"])
        if has_link_ancestor(path, Path.home()):
            actions.append((str(path), "CONFLICT: router path or ancestor is a link (preserved)"))
            continue
        if path.exists():
            old = path.read_text(encoding="utf-8")
            if not is_router_kit_owned(old):
                actions.append((str(path), "CONFLICT: foreign router without kit marker (preserved)"))
                continue
        else:
            old = ""

        lines = [
            f"# Coding Agent Router ({h['name']}) - coding-kit v{VERSION}"
            f" (installed {TODAY}, machine-adapted)",
            f"# Kit core: {kit} - soul: {kit}/AGENTS.md,"
            f" contract: {kit}/OPS.md",
            "# Memory root: ~/.memory (env MEMORY_ROOT overrides)",
        ]
        if h["skills_line"]:
            lines.append(h["skills_line"])
        lines += [
            "## STARTUP (once per session)",
            f"1. read {kit}/OPS.md",
            "2. python ~/.memory/scripts/memory-warmup.py",
            "",
        ]
        new = "\n".join(lines) + "\n" + soul + codegraph_block(old)
        if new == old.rstrip() + ("\n" if old else "") or new == old:
            actions.append((str(path), "unchanged"))
        elif dry:
            actions.append((str(path), "would regenerate"))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                # CR-01: Cheap one-file backup before replacing an owned router
                backup_path = Path(str(path) + ".kit-bak")
                safe_write_text(backup_path, old)
            safe_write_text(path, new)
            actions.append((str(path), "regenerated"))
    return actions


def bump_claude_md(dry: bool = False):
    """Bump the machine CLAUDE.md version line. dry=True writes nothing."""
    if is_link(CLAUDE_MD) or has_link_ancestor(CLAUDE_MD, Path.home()):
        return "skipped (link target or ancestor)"
    if not CLAUDE_MD.exists():
        return "skipped (not present)"
    n = len(master_skill_names())
    t = CLAUDE_MD.read_text(encoding="utf-8")
    t2 = re.sub(
        r"coding-kit v\d+\.\d+\.\d+ \(repo master; machine CLAUDE\.md"
        r" refreshed \d{4}-\d{2}-\d{2}\)*",
        f"coding-kit v{VERSION} (repo master; machine CLAUDE.md"
        f" refreshed {TODAY})",
        t, count=1)
    t2 = re.sub(r"\(\d+, English\)", f"({n}, English)", t2, count=1)
    if t2 != t:
        if dry:
            return "would bump"
        safe_write_text(CLAUDE_MD, t2)
        return "bumped"
    return "unchanged"


def verify():
    ok = True
    names = master_skill_names()
    print("\n=== VERIFY ===")
    for d in SYNC_TARGETS:
        dest = home(d)
        if is_link(dest):
            try:
                if dest.resolve() == SKILLS.resolve():
                    print(f"OK   {d} (master junction)")
                    continue
            except Exception:
                pass
            print(f"FAIL {d} (foreign or broken symlink/junction rejected)")
            ok = False
            continue
        if has_link_ancestor(dest, Path.home()):
            print(f"FAIL {d} (ancestor is symlink/junction)")
            ok = False
            continue
        if not dest.exists():
            print(f"FAIL {d} (missing)")
            ok = False
            continue
        mani = load_manifest(dest)
        if not mani:
            print(f"FAIL {d} (missing or invalid manifest)")
            ok = False
            continue
        valid, _ = validate_manifest(dest, mani)
        if not valid:
            print(f"FAIL {d} (invalid manifest)")
            ok = False
            continue
        manifest_skills = set(mani.get("skills", []))
        bad = []
        for name in names:
            if name not in manifest_skills:
                bad.append("unowned/missing-from-manifest " + name)
                continue
            src, target = SKILLS / name, dest / name
            if not target.exists():
                bad.append("missing " + name)
                continue
            bad_links = scan_skill_links(dest, target)
            if bad_links:
                bad.append(f"links in {name}: {', '.join(bad_links)}")
                continue
            for f in src.rglob("*"):
                if f.is_file():
                    tf = target / f.relative_to(src)
                    if is_link(tf) or not tf.exists() or f.read_bytes() != tf.read_bytes():
                        bad.append("diff " + name + "/" + str(f.relative_to(src)))
        stale = [s for s in manifest_skills
                 if s not in names and (dest / s).exists()]
        tag = "OK  " if not (bad or stale) else "FAIL"
        ok = ok and not (bad or stale)
        print(f"{tag} {d} skills={len(names)}"
              + (f" problems={bad + stale}" if (bad or stale) else ""))
    for h in HARNESSES:
        router_path = home(h["router"])
        if not router_path.exists():
            print(f"FAIL {h['router']} (missing)")
            ok = False
            continue
        old = router_path.read_text(encoding="utf-8")
        if not is_router_kit_owned(old):
            print(f"FAIL {h['router']} (foreign conflict)")
            ok = False
            continue
        first = old.splitlines()[0] if old.splitlines() else ""
        good = f"v{VERSION}" in first
        ok = ok and good
        print(("OK  " if good else "FAIL") + " " + str(h["router"]))
    if CLAUDE_MD.exists():
        first = CLAUDE_MD.read_text(encoding="utf-8").splitlines()[0]
        good = f"v{VERSION}" in first
        ok = ok and good
        print(("OK  " if good else "FAIL") + " " + str(CLAUDE_MD))
    else:
        print(f"SKIP {CLAUDE_MD} (not present)")
    print("\nVERDICT:", "ALL OK" if ok else "FAILED")
    return ok





def plan_canonical_sync(canon: Path) -> list[dict]:
    """CR-04: Compute ONE unified change plan for canonical sync (including manifest)."""
    names = master_skill_names()
    plan = []
    if is_link(canon) or has_link_ancestor(canon, KIT):
        return [{"op": "error", "target": canon, "desc": f"ERROR: canonical target {canon} or ancestor is a link"}]
    if not canon.exists():
        for n in names:
            plan.append({"op": "add-skill", "skill": n, "src": SKILLS / n, "target": canon / n, "desc": f"add .agents/skills/{n}"})
        plan.append({"op": "upd-manifest", "target": canon / MANIFEST_NAME, "desc": f"add {MANIFEST_NAME}"})
        return plan

    for n in names:
        src, target = SKILLS / n, canon / n
        if is_link(target):
            try:
                if target.resolve() == src.resolve():
                    continue
            except Exception:
                pass
            plan.append({"op": "error", "skill": n, "target": target, "desc": f"ERROR: skill {n} is a link: {target}"})
            continue
        if not target.exists():
            plan.append({"op": "add-skill", "skill": n, "src": src, "target": target, "desc": f"add .agents/skills/{n}"})
            continue
        bad_links = scan_skill_links(canon, target)
        if bad_links:
            plan.append({"op": "error", "skill": n, "target": target, "desc": f"ERROR: skill {n} contains link/escape: {', '.join(bad_links)}"})
            continue
        if target.resolve() == src.resolve():
            continue
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                tf = target / rel
                if not tf.exists() or f.read_bytes() != tf.read_bytes():
                    plan.append({"op": "upd-file", "src": f, "target": tf, "desc": f"upd {n}/{rel}"})
        for f in target.rglob("*"):
            if f.is_file() and not (src / f.relative_to(target)).exists():
                plan.append({"op": "del-file", "target": f, "desc": f"del {n}/{f.relative_to(target)}"})
    for entry in sorted(canon.iterdir()):
        if entry.is_dir() and entry.name not in names:
            bad_links = scan_skill_links(canon, entry)
            if bad_links:
                plan.append({"op": "error", "target": entry, "desc": f"ERROR: stale dir {entry.name} contains link/escape: {', '.join(bad_links)}"})
            else:
                plan.append({"op": "rm-dir", "target": entry, "desc": f"rm-dir {entry.name}"})

    # Manifest check
    mani_file = canon / MANIFEST_NAME
    if is_link(mani_file):
        plan.append({"op": "error", "target": mani_file, "desc": f"ERROR: manifest {mani_file} is a link"})
    elif not mani_file.exists():
        plan.append({"op": "upd-manifest", "target": mani_file, "desc": f"add {MANIFEST_NAME}"})
    else:
        try:
            curr_mani = json.loads(mani_file.read_text(encoding="utf-8"))
            if curr_mani.get("kit_version") != VERSION or curr_mani.get("skills") != names:
                plan.append({"op": "upd-manifest", "target": mani_file, "desc": f"upd {MANIFEST_NAME}"})
        except Exception:
            plan.append({"op": "upd-manifest", "target": mani_file, "desc": f"upd {MANIFEST_NAME}"})

    return plan


def canonical_mode(argv=None):
    """--canonical (wave3 Task 10): sync KIT/skills -> the repo's
    .agents/skills/ — the copy harnesses read (agentskills.io canonical
    location). --dry-run lists actions
    without writing. Per-adapter opt-in lives in profile.yml
    adapters[].canonical (default false — enable only for harnesses
    proven to read the alias)."""
    argv = list(sys.argv[1:]) if argv is None else argv
    dry = "--dry-run" in argv
    canon = KIT / ".agents" / "skills"
    plan = plan_canonical_sync(canon)
    has_errors = any(item.get("op") == "error" for item in plan)
    if dry:
        print("DRY RUN — no changes written")
        if not plan:
            print("no changes")
        else:
            for item in plan:
                print(item["desc"])
        return 1 if has_errors else 0

    if has_errors:
        for item in plan:
            if item.get("op") == "error":
                print(item["desc"])
        print("canonical sync aborted due to errors/links")
        return 1

    print(f"canonical: {canon}")
    actions: list[str] = []
    tx = DeployTransaction()
    with tx:
        for item in plan:
            op = item["op"]
            if op in ("add-skill", "upd-file", "del-file", "rm-dir"):
                skill_name = item.get("skill")
                target_path = canon / skill_name if skill_name else item["target"]
                tx.record_absent_ancestors(target_path)
                tx.snapshot_target(target_path)
            elif op == "upd-manifest":
                tx.record_absent_ancestors(item["target"])
                tx.snapshot_target(item["target"])

        tx.mark_mutations_started()
        if not canon.exists():
            canon.mkdir(parents=True)

        try:
            for item in plan:
                op = item["op"]
                if op == "add-skill":
                    safe_copytree(item["src"], item["target"], boundary=canon)
                    actions.append(item["desc"])
                elif op == "upd-file":
                    if not is_safe_under_boundary(item["target"], canon):
                        print(f"ERROR: unsafe upd file target {item['target']}")
                        tx.rollback("unsafe upd file target")
                        return 1
                    item["target"].parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item["src"], item["target"])
                    actions.append(item["desc"])
                elif op == "del-file":
                    if not is_safe_under_boundary(item["target"], canon):
                        print(f"ERROR: unsafe del file target {item['target']}")
                        tx.rollback("unsafe del file target")
                        return 1
                    item["target"].unlink()
                    actions.append(item["desc"])
                elif op == "rm-dir":
                    safe_rmtree(item["target"])
                    actions.append(item["desc"])
                elif op == "upd-manifest":
                    names = master_skill_names()
                    safe_write_text(
                        item["target"],
                        json.dumps({"kit_version": VERSION, "skills": names}, indent=1),
                        boundary=canon,
                    )
                    actions.append(item["desc"])
                elif op == "error":
                    print(item["desc"])
                    tx.rollback(item["desc"])
                    return 1
        except Exception as e:
            tx.rollback(str(e))
            return 1

        tx.commit()

    for a in actions:
        print(a)
    if not actions:
        print("no changes")
    print("canonical sync complete")
    return 0


def deploy_preview() -> int:
    """CK-01: read-only full-deploy preview.

    Runs the same gates and computes the same plan as the apply path, printing
    affected paths and actions without writing anything: no transaction dir,
    no directory creation, no snapshots. Exit 0 = clean plan, 1 = preflight
    conflict/plan error, 3 = integrity drift (as in apply).
    """
    integrity_gate()
    print(f"DRY RUN — no changes written (coding-kit v{VERSION} full-deploy preview)")
    routers_ok, router_errs = preflight_routers_and_claude()
    skills_ok, skills_plan, skills_reports = preflight_skills()
    for err in router_errs:
        print("  " + err)
    if not routers_ok or not skills_ok:
        for r in skills_reports:
            print(f"{r.target}: " + (", ".join(r.actions) if r.actions else "no changes"))
        print("\nPREVIEW ABORTED: conflicts must be resolved before a real deploy.")
        return 1
    try:
        reports = execute_skills(skills_plan, dry=True)
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    for r in reports:
        print(f"{r.target}: " + (", ".join(r.actions) if r.actions else "no changes"))
    print("\n=== ROUTERS ===")
    for path, action in regen_routers(dry=True):
        print(f"{action}: {path}")
    print(f"CLAUDE.md: {bump_claude_md(dry=True)}")
    print("\npreview complete — no changes written")
    return 0


def main():
    argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        description=f"Deploy coding-kit v{VERSION} to local agent harnesses."
    )
    parser.add_argument(
        "--canonical", action="store_true",
        help="Sync master skills to the repo's .agents/skills/ directory."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview planned changes without writing (full deploy; with "
             "--canonical, list canonical actions)."
    )
    args = parser.parse_args(argv)

    if args.canonical:
        return canonical_mode(argv)
    if args.dry_run:
        return deploy_preview()
    integrity_gate()
    print(f"coding-kit v{VERSION} -> all harnesses ({TODAY})")
    routers_ok, router_errs = preflight_routers_and_claude()
    if not routers_ok:
        print("\nDEPLOY ABORTED: router or CLAUDE.md preflight encountered conflicts:")
        for err in router_errs:
            print("  " + err)
        return 1

    # Preflight skills
    skills_ok, skills_plan, skills_reports = preflight_skills()
    has_skill_failure = any(not r.ok for r in skills_reports)
    for r in skills_reports:
        print(f"{r.target}: " + (", ".join(r.actions) if r.actions else "no changes"))
    if not skills_ok or has_skill_failure:
        print("\nDEPLOY ABORTED: skill preflight encountered conflicts or errors.")
        return 1
    names_set = set(master_skill_names())
    tx = DeployTransaction()
    with tx:
        # Snapshot validated targets from skills_plan
        for item in skills_plan:
            if item["kind"] == "master_alias":
                continue
            dest: Path = item["dest"]
            tx.record_absent_ancestors(dest / MANIFEST_NAME)
            tx.snapshot_target(dest / MANIFEST_NAME)
            for name in item.get("owned_skills", []):
                t = dest / name
                tx.record_absent_ancestors(t)
                tx.snapshot_target(t)
            mani = item.get("mani")
            if mani:
                for stale_name in mani.get("skills", []):
                    if stale_name not in names_set:
                        stale_t = dest / stale_name
                        if stale_t.exists():
                            tx.record_absent_ancestors(stale_t)
                            tx.snapshot_target(stale_t)

        for h in HARNESSES:
            r_path = home(h["router"])
            tx.record_absent_ancestors(r_path)
            tx.snapshot_target(r_path)
            bak_p = Path(str(r_path) + ".kit-bak")
            tx.record_absent_ancestors(bak_p)
            tx.snapshot_target(bak_p)
        tx.record_absent_ancestors(CLAUDE_MD)
        tx.snapshot_target(CLAUDE_MD)

        tx.mark_mutations_started()
        try:
            execute_skills(skills_plan)
            print("\n=== ROUTERS ===")
            for path, action in regen_routers():
                print(f"{action}: {path}")
            print(f"CLAUDE.md: {bump_claude_md()}")
            if not verify():
                tx.rollback("verify returned False")
                return 1
            tx.commit()
            return 0
        except Exception as e:
            tx.rollback(str(e))
            return 1
if __name__ == "__main__":
    sys.exit(main())
