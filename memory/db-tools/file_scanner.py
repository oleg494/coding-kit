"""memory/db-tools/file_scanner.py — file discovery, filtering, hashing."""
import fnmatch
import hashlib
import os

DEFAULT_SKIP_DIRS = {
    "db", ".venv", "venv", ".git", "__pycache__",
    "backups", "indexes", "eval-archive",
}
DEFAULT_SKIP_FILES = {".env", "wiki.db", "skip.local"}

_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp",
    ".exe", ".dll", ".so", ".bin", ".pdf", ".zip", ".tar", ".gz",
    ".7z", ".rar", ".jar", ".docx", ".xlsx", ".pptx"
}


def load_local_skip(root):
    """Per-machine extras: <root>/skip.local — one name per line (# = comment)."""
    dirs, files = set(), set()
    try:
        text = open(os.path.join(root, "skip.local"), encoding="utf-8-sig").read()
    except OSError:
        return dirs, files
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.endswith("/"):
            dirs.add(line.rstrip("/"))
        elif line.startswith("file:"):
            files.add(line[5:].strip())
        elif os.path.splitext(line)[1]:
            files.add(line)
        else:
            dirs.add(line)
    return dirs, files


def read_hashed(full):
    """Read a file: (sha256, content). Hash is the change authority."""
    with open(full, "rb") as f:
        data = f.read()
    return hashlib.sha256(data).hexdigest(), data.decode("utf-8", errors="replace")


def is_artifact(fn):
    """Service sqlite files, backups and images — not put into the text database."""
    low = fn.lower()
    return low.endswith((".db", ".db-shm", ".db-wal", ".db-journal",
                         ".sqlite", ".sqlite3", ".db3",
                         ".sqlite-shm", ".sqlite-wal", ".sqlite-journal",
                         ".sqlite3-shm", ".sqlite3-wal", ".sqlite3-journal",
                         ".bak", ".orig", ".pyc")) or \
        os.path.splitext(low)[1] in _BINARY_EXTS


def load_gitignore(root):
    """Minimal .gitignore parser: folder names and fnmatch patterns."""
    ignore_dirs, ignore_files = set(), []
    p = os.path.join(root, ".gitignore")
    if not os.path.isfile(p):
        return ignore_dirs, ignore_files
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(("#", "!")):
                    continue
                pat = line.rstrip("/")
                if "*" not in pat and "?" not in pat and "[" not in pat:
                    ignore_dirs.add(pat.lstrip("/"))
                else:
                    ignore_files.append(pat)
    except OSError:
        pass
    return ignore_dirs, ignore_files


def scan_files(root, skip_dirs, skip_files, use_gitignore=False):
    """Fast pass without reading content: rel -> (mtime, size)."""
    out = {}
    gi_dirs, gi_files = load_gitignore(root) if use_gitignore else (set(), [])
    skip = set(skip_dirs) | gi_dirs
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in sorted(filenames):
            if fn in skip_files or is_artifact(fn):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            rel_posix = rel.replace(os.sep, "/")
            if gi_files and any(
                    fnmatch.fnmatch(rel_posix, p)
                    or fnmatch.fnmatch(rel_posix, p.lstrip("/"))
                    for p in gi_files):
                continue
            out[rel] = (os.path.getmtime(full), os.path.getsize(full))
    return out


def collect_extra(extra_files):
    """External files outside root (e.g. transcript history)."""
    out = {}
    for p in (extra_files or []):
        full = os.path.abspath(os.path.expanduser(p))
        if os.path.isfile(full):
            out[full] = (os.path.getmtime(full), os.path.getsize(full))
    return out
