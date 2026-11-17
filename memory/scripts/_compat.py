#!/usr/bin/env python3

"""Shared cross-platform module for memory: stdout encoding, venv paths,
platform helpers. A single place instead of copying into every script
(recommendation from the Windows bug report: "put it in a shared module,
not copied into 6 files").

Usage:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    import _compat
    _compat.fix_encoding()          # stdout/stderr -> UTF-8 (Windows cp1251)
    py = _compat.venv_python()      # path to project python (bin/ vs Scripts/)
"""

import os
import subprocess
import sys
from pathlib import Path


IS_NT = os.name == "nt"
IS_CI = os.environ.get("CI") == "true"


def fix_encoding():
    """Windows console defaults to cp1251 — Russian output (✓/✗/Cyrillic)
    crashes with UnicodeEncodeError. Switching to UTF-8 (Python 3.7+).
    Call at the start of every CLI script."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: S110,BLE001 — reconfigure is optional, fine without it
        pass


def run(cmd, *, timeout=None, cwd=None, env=None, check=False,
        shell=False):
    """subprocess.run for CLI scripts: cross-platform encoding.

    Windows gotcha (bug report v2.4 BUG-1/4): text=True without an explicit
    encoding picks the ANSI code page (locale.getencoding — cp1251), while
    console children write in OEM (cp866) — UnicodeDecodeError in reader
    streams or mojibake (CPython issue #105312). Fix on both sides:
    (1) python children get PYTHONUTF8=1 — they write UTF-8;
    (2) output is decoded as utf-8 + errors="replace" — we never crash on
    a foreign encoding (PowerShell children switch themselves via
    [Console]::OutputEncoding).
    """
    child_env = os.environ.copy() if env is None else {**os.environ, **env}
    if IS_NT:
        child_env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=cwd, env=child_env,
                          check=check, shell=shell)


# Memory root markers: files/folders present ONLY in the workspace root
# (VERSION is unique — projects don't have it; db-tools/ and
# scripts/_compat.py are part of the root). Used to validate the found root.
ROOT_MARKERS = ("VERSION", "db-tools", "scripts/_compat.py")


def chulan_root():
    """Memory root. Industry pattern (jayqi/python-find-project-root-
    cookbook, R here): chain — (1) explicit $MEMORY_ROOT override, (2)
    VERSION marker file when climbing up, (3) __file__-based fallback.
    No hardcoded paths: the root can live anywhere (any OS, any mount
    point, an unpacked archive) — it is found automatically. Fails if the
    found place does not look like a root (renamed, script moved) — instead
    of silently working from the wrong directory.
    """
    env = os.environ.get("MEMORY_ROOT")
    if env:
        root = Path(env).expanduser()
        if not root.is_absolute():
            raise RuntimeError(
                f"MEMORY_ROOT must be an absolute path: {env!r}")
        _validate_root(root, source="MEMORY_ROOT")
        return root
    home = Path.home() / ".memory"
    try:  # kit-hosted engine (junction): default root = ~/.memory
        _validate_root(home, source="~/.memory")
        return home
    except RuntimeError:
        pass
    here = Path(__file__).resolve().parent.parent  # memory-repo layout
    _validate_root(here, source="__file__")
    return here


def _validate_root(root, source):
    """Check that the directory is really the memory root (markers in place)."""
    missing = [m for m in ROOT_MARKERS if not (root / m).exists()]
    if missing:
        raise RuntimeError(
            f"memory root ({source}) does not look like a root: {root} — "
            f"missing markers: {', '.join(missing)}. Set MEMORY_ROOT or "
            f"place a VERSION file at the workspace root.")


def venv_dir():
    """Shared workspace venv: ~/.venvs/memory (kept outside the folder so
    the project can be shared cleanly). Created by setup.py (ensure_env)."""
    return Path.home() / ".venvs" / "memory"


def venv_python():
    """Path to python in the project venv (bin/python vs Scripts/python.exe)."""
    d = venv_dir()
    if IS_NT:
        return d / "Scripts" / "python.exe"
    return d / "bin" / "python"


def ro_uri(path):
    """Build an escaped SQLite read-only URI (handles PurePath, UNC, #, %, spaces)."""
    from pathlib import PurePath
    from urllib.parse import quote
    if isinstance(path, PurePath) and not isinstance(path, Path):
        posix = path.as_posix()
    else:
        p = Path(path)
        posix = (p if p.is_absolute() else Path(os.path.abspath(p))).as_posix()
    if posix.startswith("/") and not posix.startswith("//"):
        return "file://" + quote(posix, safe="/:") + "?mode=ro"
    return "file:" + quote(posix, safe="/:") + "?mode=ro"
