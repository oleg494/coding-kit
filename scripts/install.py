#!/usr/bin/env python3
"""install.py — coding-kit bootstrap: private memory layout + engine link.

One clone -> one command -> a working kit with its own cross-chat memory.

Creates (idempotent, nothing personal is ever written by this script):
    ~/.memory/Wiki/<reference|howto|errors|decisions|ideas>/
    ~/.memory/db/                      (empty indexed DBs)
    ~/.memory/scripts/                 (memory-warmup.py + _compat.py)
    ~/.memory/VERSION                  (engine marker, schema 2.9)
    ~/.memory/db-tools  ->  <kit>/memory/db-tools   (junction on Windows,
                                                      symlink elsewhere)

Then builds empty indexes and smoke-tests the search. Safe to re-run.

Before writing, a link/reparse-aware preflight proves that MEMORY_ROOT
and every managed destination — including intermediate ancestors
(Wiki, db, scripts) and existing db/*.db entries — resolve inside the
root; escapes and unresolvable links fail closed before any mutation.
The db-tools engine link is the one intentional external link.

Usage:
    python scripts/install.py           # default root ~/.memory
    MEMORY_ROOT=/x/y python scripts/install.py   # custom root
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KIT = Path(__file__).resolve().parents[1]
ENGINE = KIT / "memory" / "db-tools"
WIKI_TYPES = ("reference", "howto", "errors", "decisions", "ideas")
ENGINE_VERSION = "2.9"

# Cycle files the dev-wiki contract (OPS §5, warmup --full integrity check)
# assumes exist. Seeded ONLY when absent — a re-run
# never overwrites a user's index/log (install philosophy: never
# destroy what may be data).
_WIKI_SEEDS = {
    "index.md": (
        "# Index — Wiki catalogue\n"
        "\n"
        "| Entry | Topic | Tags | Date | Folder |\n"
        "|-------|-------|------|------|--------|\n"
    ),
    "log.md": (
        "# Log — Wiki changelog\n"
        "\n"
        "Format: `YYYY-MM-DD HH:MM — action — file(s) — what was done`\n"
    ),
}


def memory_root() -> Path:
    env = os.environ.get("MEMORY_ROOT")
    if env:
        root = Path(env).expanduser()
        if not root.is_absolute():
            raise RuntimeError(
                f"MEMORY_ROOT must be an absolute path: {env!r}")
        return root
    return Path.home() / ".memory"


def check_python_environment(flags=None, executable=None) -> tuple[bool, str]:
    """Detect isolated or embedded Python environments early.

    Returns (True, "standard Python environment") if supported, or
    (False, remediation_message) if running under isolated mode or
    embedded ._pth distribution where site-packages / PYTHONPATH are disabled.
    """
    f = flags if flags is not None else sys.flags
    exe = Path(executable) if executable is not None else Path(sys.executable)

    if getattr(f, "isolated", 0):
        return (False, "isolated Python mode (sys.flags.isolated) is enabled; "
                       "isolated environments ignore PYTHONPATH and site-packages. "
                       "Please run install.py with a standard CPython interpreter or virtualenv.")
    if getattr(f, "no_site", 0):
        return (False, "no_site mode (sys.flags.no_site) is enabled; "
                       "site-packages are disabled. "
                       "Please run install.py with a standard CPython interpreter or virtualenv.")
    if exe.parent.is_dir():
        pth_files = sorted(exe.parent.glob("*._pth"))
        if pth_files:
            return (False, f"embedded Python distribution detected ({pth_files[0].name} "
                           f"present next to {exe.name}); embedded distributions restrict "
                           "module resolution and disable standard site-packages. "
                           "Please run install.py with a standard CPython interpreter or virtualenv.")

    return (True, "standard Python environment")

def _is_link(p: Path) -> bool:
    """True for symlinks and Windows junctions (is_symlink() misses
    the latter)."""
    if p.is_symlink():
        return True
    try:
        os.readlink(p)
        return True
    except OSError:
        return False


def _norm_real(p: Path) -> str:
    r"""Comparison key for a resolved path: strip the Windows extended
    path prefix and normalize case/separators, so paths from resolve()
    (\\?\-prefixed) compare equal to lexical paths (readlink targets,
    abspath)."""
    s = str(p)
    if s.startswith("\\\\?\\"):
        s = s[4:]
    return os.path.normcase(os.path.normpath(s))


def _resolve_managed(p: Path) -> Path | None:
    """Resolve a possibly linked managed path.

    Returns the path a write through p would land on, or None if p
    does not exist and is not a link (a path the installer would
    create cannot yet redirect a write). Path.resolve() (non-strict,
    Python 3.12) walks reparse points link-by-link, keeps resolving
    through DANGLING links to the real lexical target, and raises
    RuntimeError on link loops — exactly the fail-closed semantics
    the boundary check needs. Anything else that cannot be resolved
    — unreadable reparse point, permission error — raises
    RuntimeError: what cannot be proven safe is not accepted."""
    if not _is_link(p):
        if not p.exists():
            return None
    try:
        return p.resolve()
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(
            f"cannot resolve {p} ({exc}); an unresolvable path "
            "cannot be proven safe") from None


def _iter_managed_paths(root: Path) -> list[Path]:
    """All paths the installer or its engine (build.py, search/smoke,
    search logging) can write to under this root:
    layout dirs incl. every intermediate ancestor (Wiki, db, scripts),
    Wiki seed files, VERSION, copied scripts, and every *.db file in
    db/ (build writes db/wiki.db; search logging opens db/research.db
    read-write and sqlite follows file links — each *.db entry is a
    real write target). <root>/db-tools is absent: the engine link is
    the one intentional external link, handled by link_engine()."""
    paths = [root / "db", root / "scripts", root / "Wiki"]
    paths += [root / "Wiki" / t for t in WIKI_TYPES]
    paths += [root / "Wiki" / name for name in _WIKI_SEEDS]
    paths += [root / "VERSION",
              root / "scripts" / "memory-warmup.py",
              root / "scripts" / "_compat.py"]
    try:
        paths += [root / "db" / name for name in os.listdir(root / "db")]
    except OSError:
        pass  # no db/ dir yet (or unreadable): nothing to preflight
    return paths


def check_memory_boundary(root: Path) -> None:
    """Fail closed unless every managed path — including every
    intermediate ancestor and every db/*.db entry — provably resolves
    inside MEMORY_ROOT, and MEMORY_ROOT itself is not a link pointing
    at a different location (base-dir escape: writes would land in the
    link target, not the requested location).

    Existing links that stay inside the root are allowed. Links (or
    dangling descendants under them) that would send installer or
    engine writes outside the root are refused — including unresolvable
    paths: what cannot be proven safe is not accepted. The installer
    never writes where it was not asked to. This is a pre-mutation
    check, not a sandbox: it binds what the layout would be NOW (TOCTOU
    between check and write is accepted; bootstrap is not a crash-
    atomic transaction)."""
    try:
        root_real = root.resolve()
        root_is_link = _is_link(root)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(
            f"MEMORY_ROOT {root} cannot be resolved ({exc}); refusing "
            "to install into an unreadable path.") from None
    escapes = []

    if root_is_link and _norm_real(root_real) != _norm_real(
            Path(os.path.abspath(str(root)))):
        escapes.append(
            f"MEMORY_ROOT is a link: {root} -> {root_real} "
            "(writes would go to the link target, not the requested root)")
    for p in _iter_managed_paths(root):
        try:
            real = _resolve_managed(p)
        except RuntimeError as exc:
            escapes.append(str(exc))
            continue
        if real is None:
            continue
        if (_norm_real(real) != _norm_real(root_real)
                and _norm_real(root_real) not in
                [_norm_real(q) for q in real.parents]):
            rel = p.relative_to(root)
            escapes.append(
                f"{rel} is a link resolving outside MEMORY_ROOT: "
                f"{p} -> {real}")
    if escapes:
        raise RuntimeError(
            "Refusing to install: managed paths escape MEMORY_ROOT "
            f"({root}):\n  " + "\n  ".join(escapes) +
            "\nRemove or repoint the listed links, or choose a different "
            "MEMORY_ROOT, then re-run install.py.")


def link_engine(root: Path) -> bool:
    """Point <root>/db-tools at this kit's engine (the link follows the
    last installer). A pre-existing link is re-pointed; a real directory
    is left alone (never destroy what may be data).
    Returns True if engine is linked to this kit, False if a real directory
    conflicts and was preserved."""
    target = root / "db-tools"
    if _is_link(target):
        if target.resolve() == ENGINE.resolve():
            print("  db-tools already linked to this kit")
            return True
    elif target.exists():
        print(f"  NOTE: {target} is a real directory; replace it manually "
              f"to use this kit's engine.")
        return False
    if os.name == "nt" and not shutil.which("powershell"):
        raise RuntimeError(
            "PowerShell executable ('powershell') not found in PATH; "
            "PowerShell is required on Windows to create directory junctions. "
            "Please install/enable PowerShell or create the junction manually: "
            f"New-Item -ItemType Junction -Path '{target}' -Target '{ENGINE}'"
        )

    prev_target = None
    was_link = _is_link(target)
    if was_link:
        try:
            prev_target = target.resolve()
        except OSError:
            try:
                raw = os.readlink(target)
                if isinstance(raw, str) and raw.startswith("\\\\?\\"):
                    raw = raw[4:]
                prev_target = Path(raw)
            except OSError:
                prev_target = None
        if os.name == "nt":
            os.rmdir(target)  # junctions are directories on NT
        else:
            target.unlink()  # POSIX symlinks are not
    try:
        if os.name == "nt":
            # paths travel via env, not -Command text: no injection, and
            # $args is unavailable in -Command mode (script-only)
            env = dict(os.environ, KIT_LINK_PATH=str(target),
                       KIT_LINK_TARGET=str(ENGINE))
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "New-Item -ItemType Junction -Path $env:KIT_LINK_PATH "
                 "-Target $env:KIT_LINK_TARGET | Out-Null"],
                check=True, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
        else:
            target.symlink_to(ENGINE, target_is_directory=True)
    except Exception as exc:
        restored = False
        if was_link and prev_target:
            try:
                if os.name == "nt":
                    env = dict(os.environ, KIT_LINK_PATH=str(target),
                               KIT_LINK_TARGET=str(prev_target))
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         "New-Item -ItemType Junction -Path $env:KIT_LINK_PATH "
                         "-Target $env:KIT_LINK_TARGET | Out-Null"],
                        check=True, env=env, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                    )
                    restored = True
                else:
                    target.symlink_to(Path(prev_target), target_is_directory=True)
                    restored = True
            except Exception:
                pass
        msg = f"Failed to link engine ({target} -> {ENGINE}): {exc}."
        if restored:
            msg += f" Restored previous link to {prev_target}."
        msg += " Please re-run install or create the link manually."
        raise RuntimeError(msg) from None
    print(f"  linked {target} -> {ENGINE}")
    return True


def build_indexes(engine_dir: Path) -> None:
    build_script = engine_dir / "build.py"
    if not build_script.exists():
        print(f"  build.py WARN: {build_script} not found")
        return
    build = subprocess.run(
        [sys.executable, str(build_script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if build.returncode != 0:
        print("  build.py WARN:\n" + (build.stderr or build.stdout)[:500])

def main(argv: list = None) -> int:
    argv = list(sys.argv[1:]) if argv is None and \
        __name__ == "__main__" else list(argv or [])
    if argv in (["--help"], ["-h"]):
        print(__doc__)
        return 0
    if argv:
        # '--help' used to fall through and RUN the installer (v3.0
        # audit follow-up): arbitrary argv is never "yes, install"
        print(f"unexpected arguments: {' '.join(argv)}\n"
              "install.py takes no arguments; configure the root via the "
              "MEMORY_ROOT environment variable.\n"
              "Usage: python scripts/install.py [--help]", file=sys.stderr)
        return 2
    try:
        root = memory_root()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    try:
        # link/reparse-aware preflight: nothing below may mutate
        # anything before the boundary is proven safe
        check_memory_boundary(root)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    supported, env_msg = check_python_environment()
    if not supported:
        print(f"error: unsupported Python environment: {env_msg}", file=sys.stderr)
        return 1
    print(f"coding-kit install -> {root}")
    for d in [root / "db", root / "scripts"] + [
            root / "Wiki" / t for t in WIKI_TYPES]:
        d.mkdir(parents=True, exist_ok=True)
    for name, text in _WIKI_SEEDS.items():
        target = root / "Wiki" / name
        if not target.exists():
            target.write_text(text, encoding="utf-8", newline="\n")
            print(f"  seeded Wiki/{name}")
    (root / "VERSION").write_text(
        ENGINE_VERSION + "\n", encoding="utf-8", newline="\n")

    for name in ("memory-warmup.py", "_compat.py"):
        src = KIT / "memory" / "scripts" / name
        if src.exists():
            shutil.copy2(src, root / "scripts" / name)
    legacy = KIT.parent / "memory"
    if legacy.exists() and legacy.resolve() != root.resolve():
        # old layout: data next to the kit ("../memory") before the
        # ~/.memory convention — do not move user data silently
        print(f"  NOTE: legacy data found at {legacy}. Move its Wiki posts "
              f"into {root / 'Wiki'}/<type>/ or set MEMORY_ROOT={legacy}.")

    linked = False
    try:
        linked = link_engine(root)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not linked:
        print("\n---")
        print(f"Install INCOMPLETE: {root / 'db-tools'} is a real directory and was preserved.")
        print("To complete installation and use this kit's engine, back up or remove that directory")
        print("and re-run install.py.")
        return 1

    final_engine = root / "db-tools"
    build_indexes(final_engine)

    smoke_script = final_engine / "search_all.py"
    smoke = subprocess.run(
        # probe token from the root's own scripts (memory-warmup.py):
        # run against the final user-facing entry point
        [sys.executable, str(smoke_script), "warmup"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    ok = smoke.returncode == 0 and bool(smoke.stdout.strip())
    print("\n---")
    print("Install done. Layout:")
    print(f"  Wiki/: {root / 'Wiki'} (your knowledge — personal, never committed)")
    print(f"  db/  : {root / 'db'} (indexes, gitignored)")
    print(f"  engine: {final_engine} (linked to the kit)")
    print(f"  search smoke: {'OK' if ok else smoke.stderr[:300]}")
    print("\nNow follow README.md -> Install section for your environment "
          "(rules file + skills).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))