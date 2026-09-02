#!/usr/bin/env python3
"""deploy.py — one-shot coding-kit rollout to every harness on this machine.

Usage:
    python scripts/tools/deploy.py        (or double-click update-kit.bat)

Idempotent. Steps:
  1. Skills: sync KIT/skills -> ~/.claude/skills, ~/.agents/skills,
     ~/.zcode/skills (add / update / remove). Junctions on target dirs
     are detected and skipped — they track the master live.
     Local-only skill dirs are never touched: each target keeps a
     .kit-manifest.json naming the skills the kit owns; only manifest
     entries are eligible for removal.
  2. Routers: regenerate the uniform routers (omp, antigravity,
     zcode, codex, opencode) from the kit soul (AGENTS.md) — no drift.
     ~/.claude/CLAUDE.md keeps its machine-local triggers: only the
     version / date / skill-count line is bumped in place.
     An existing <!-- CODEGRAPH --> block is carried over verbatim.
  3. Verify: byte-compare every deployed skill against the master, check
     every router header, exit non-zero on any mismatch.
"""
import json
import re
import shutil
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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


def home(p):
    return Path(p).expanduser()


def is_link(p: Path) -> bool:
    """True for symlinks and Windows junctions."""
    return p.exists() and str(p.resolve()) != str(p.absolute())


def master_skill_names():
    return sorted(x.name for x in SKILLS.iterdir() if x.is_dir())


def load_manifest(dest: Path):
    f = dest / MANIFEST_NAME
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def sync_one_skill(src: Path, target: Path, log):
    """File-level sync of one skill dir; returns nothing, appends actions."""
    if not target.exists():
        shutil.copytree(src, target)
        log.append("add " + src.name)
        return
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        tf = target / rel
        if not tf.exists() or f.read_bytes() != tf.read_bytes():
            tf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, tf)
            log.append("upd " + src.name + "/" + str(rel))
    for f in target.rglob("*"):
        if f.is_file() and not (src / f.relative_to(target)).exists():
            f.unlink()
            log.append("del " + src.name + "/" + str(f.relative_to(target)))


def sync_skills():
    names = master_skill_names()
    report = []
    for d in SYNC_TARGETS:
        dest = home(d)
        if is_link(dest):
            report.append((d, ["skip (junction - always current)"], None))
            continue
        if not dest.exists():
            dest.mkdir(parents=True)
        log = []
        for name in names:
            sync_one_skill(SKILLS / name, dest / name, log)
        # Remove whole kit skills dropped from master (manifest-guarded).
        mani = load_manifest(dest)
        removed = []
        if mani:
            for name in mani.get("skills", []):
                if name not in names and (dest / name).exists():
                    shutil.rmtree(dest / name)
                    removed.append("rm-dir " + name)
        (dest / MANIFEST_NAME).write_text(
            json.dumps({"kit_version": VERSION, "skills": names}, indent=1),
            encoding="utf-8", newline="\n")
        report.append((d, log + removed, mani))
    return report


def soul_text():
    text = (KIT / "AGENTS.md").read_text(encoding="utf-8")
    if SOUL_MARKER not in text:
        sys.exit("FATAL: marker not found in kit AGENTS.md: " + SOUL_MARKER)
    return text[text.index(SOUL_MARKER):].rstrip() + "\n"


def codegraph_block(old: str):
    m = re.search(r"<!-- CODEGRAPH_START -->.*?<!-- CODEGRAPH_END -->",
                  old, re.S)
    return ("\n" + m.group(0) + "\n") if m else ""


def regen_routers():
    soul = soul_text()
    kit = KIT.as_posix()
    actions = []
    for h in HARNESSES:
        path = home(h["router"])
        old = path.read_text(encoding="utf-8") if path.exists() else ""
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
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new, encoding="utf-8")
            actions.append((str(path), "regenerated"))
    return actions


def bump_claude_md():
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
        CLAUDE_MD.write_text(t2, encoding="utf-8")
        return "bumped"
    return "unchanged"


def verify():
    ok = True
    names = master_skill_names()
    print("\n=== VERIFY ===")
    for d in SYNC_TARGETS:
        dest = home(d)
        bad = []
        for name in names:
            src, target = SKILLS / name, dest / name
            if not target.exists():
                bad.append("missing " + name)
                continue
            for f in src.rglob("*"):
                if f.is_file():
                    tf = target / f.relative_to(src)
                    if not tf.exists() or f.read_bytes() != tf.read_bytes():
                        bad.append("diff " + name + "/" + str(f.relative_to(src)))
        mani = load_manifest(dest) or {"skills": []}
        stale = [s for s in mani.get("skills", [])
                 if s not in names and (dest / s).exists()]
        tag = "OK  " if not (bad or stale) else "FAIL"
        ok = ok and not (bad or stale)
        print(f"{tag} {d} skills={len(names)}"
              + (f" problems={bad + stale}" if (bad or stale) else ""))
    for h in HARNESSES:
        first = home(h["router"]).read_text(encoding="utf-8").splitlines()[0]
        good = f"v{VERSION}" in first
        ok = ok and good
        print(("OK  " if good else "FAIL") + " " + str(h["router"]))
    first = CLAUDE_MD.read_text(encoding="utf-8").splitlines()[0]
    good = f"v{VERSION}" in first
    ok = ok and good
    print(("OK  " if good else "FAIL") + " " + str(CLAUDE_MD))
    print("\nVERDICT:", "ALL OK" if ok else "FAILED")
    return ok





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
    if dry:
        print("DRY RUN — no changes written")
        if not canon.exists():
            for n in master_skill_names():
                print(f"add .agents/skills/{n}")
        else:
            changed = False
            for n in master_skill_names():
                src, target = SKILLS / n, canon / n
                if not target.exists():
                    print(f"add .agents/skills/{n}")
                    changed = True
                    continue
                if target.resolve() == src.resolve():
                    continue
                for f in src.rglob("*"):
                    if f.is_file():
                        tf = target / f.relative_to(src)
                        if not tf.exists() \
                                or f.read_bytes() != tf.read_bytes():
                            print(f"upd {n}/{f.relative_to(src)}")
                            changed = True
            if not changed:
                print("no changes")
        return 0
    print(f"canonical: {canon}")
    if not canon.exists():
        canon.mkdir(parents=True)
    actions: list[str] = []
    names = master_skill_names()
    for name in names:
        sync_one_skill(SKILLS / name, canon / name, actions)
    # The repo .agents/skills copy is fully kit-owned (unlike the
    # home-dir deployments that keep local-only skills): anything not in
    # the master goes.
    for entry in sorted(canon.iterdir()):
        if entry.is_dir() and entry.name not in names:
            shutil.rmtree(entry)
            actions.append("rm-dir " + entry.name)
    (canon / MANIFEST_NAME).write_text(
        json.dumps({"kit_version": VERSION, "skills": names}, indent=1),
        encoding="utf-8", newline="\n")
    for a in actions:
        print(a)
    if not actions:
        print("no changes")
    print("canonical sync complete")
    return 0


def main():
    argv = sys.argv[1:]
    if "--canonical" in argv:
        return canonical_mode(argv)
    integrity_gate()
    print(f"coding-kit v{VERSION} -> all harnesses ({TODAY})")
    print("\n=== SKILLS ===")
    for d, log, _old_mani in sync_skills():
        print(f"{d}: " + (", ".join(log) if log else "no changes"))
    print("\n=== ROUTERS ===")
    for path, action in regen_routers():
        print(f"{action}: {path}")
    # the machine CLAUDE.md keeps its local triggers; only its version/
    # date/skill-count line is bumped in place (docstring promise — the
    # call was missing, so verify() failed on every VERSION bump)
    print(f"CLAUDE.md: {bump_claude_md()}")
    return 0 if verify() else 1


if __name__ == "__main__":
    sys.exit(main())
