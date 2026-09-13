"""Path-safety primitives for deploy.py (link/junction-aware filesystem I/O).

Split out of deploy.py for the file-size gate: the deploy orchestration grew
past the hard limit, and these primitives are a self-contained concern — every
write in the deploy path goes through them and fails closed when a symlink,
junction or escape is in the way.
"""
import os
import shutil
import stat
from pathlib import Path


def is_link(p: Path) -> bool:
    """True for symlinks and Windows junctions/reparse points, including dangling links."""
    try:
        st = p.lstat()
        if bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            return True
        return p.is_symlink()
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True


def has_link_ancestor(p: Path, boundary: Path) -> bool:
    """True if any path element from p up to (but excluding) boundary is a symlink/junction."""
    curr = p
    while True:
        if is_link(curr):
            return True
        if curr == boundary or curr.parent == curr:
            break
        try:
            if curr.resolve() == boundary.resolve():
                break
        except Exception:
            pass
        curr = curr.parent
    return False


def is_safe_under_boundary(p: Path, boundary: Path) -> bool:
    """Check that p has no link in hierarchy up to boundary and resolves inside boundary."""
    try:
        boundary_res = boundary.resolve()
    except Exception:
        boundary_res = boundary
    if has_link_ancestor(p, boundary):
        return False
    curr = p
    while not curr.exists() and curr != boundary and curr.parent != curr:
        curr = curr.parent
    try:
        if not curr.resolve().is_relative_to(boundary_res):
            return False
    except Exception:
        return False
    return True


def safe_write_text(path: Path, content: str, boundary: Path | None = None, encoding: str = "utf-8") -> None:
    """Write text failing closed if target or any parent up to boundary is a symlink/junction."""
    if is_link(path):
        raise RuntimeError(f"Refusing to write to link {path}")
    if boundary is not None and not is_safe_under_boundary(path, boundary):
        raise RuntimeError(f"Refusing to write to link/escape under {boundary}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding, newline="\n")


def safe_copytree(src: Path, target: Path, boundary: Path) -> None:
    """Copy directory tree verifying neither source nor destination contains links/escapes."""
    if is_link(target):
        raise RuntimeError(f"Refusing to copytree to link {target}")
    if not is_safe_under_boundary(target, boundary):
        raise RuntimeError(f"Refusing to copytree outside boundary {boundary}: {target}")
    target.mkdir(parents=True, exist_ok=True)
    for root_dir, dirs, files in os.walk(src, topdown=True, followlinks=False):
        rel = Path(root_dir).relative_to(src)
        dest_dir = target / rel
        if is_link(dest_dir):
            raise RuntimeError(f"Refusing to copy into link directory {dest_dir}")
        for d in dirs:
            sd = Path(root_dir) / d
            td = dest_dir / d
            if is_link(sd):
                raise RuntimeError(f"Refusing to copy from link source directory {sd}")
            if is_link(td):
                raise RuntimeError(f"Refusing to copy into link target directory {td}")
            td.mkdir(parents=True, exist_ok=True)
        for f in files:
            sf = Path(root_dir) / f
            tf = dest_dir / f
            if is_link(sf):
                raise RuntimeError(f"Refusing to copy from link source file {sf}")
            if is_link(tf):
                raise RuntimeError(f"Refusing to copy into link target file {tf}")
            shutil.copy2(sf, tf)


def safe_rmtree(target: Path) -> None:
    """Remove directory tree failing closed without traversing any symlinks/junctions."""
    if is_link(target):
        raise RuntimeError(f"Refusing to rmtree link {target}")
    for root_dir, dirs, files in os.walk(target, topdown=True, followlinks=False):
        for d in list(dirs):
            dp = Path(root_dir) / d
            if is_link(dp):
                raise RuntimeError(f"Refusing to recurse into link dir {dp}")
        for f in files:
            fp = Path(root_dir) / f
            if is_link(fp):
                raise RuntimeError(f"Refusing to delete link file {fp}")
    for root_dir, dirs, files in os.walk(target, topdown=False, followlinks=False):
        for f in files:
            (Path(root_dir) / f).unlink()
        for d in dirs:
            (Path(root_dir) / d).rmdir()
    target.rmdir()


def scan_skill_links(dest: Path, skill_dir: Path) -> list:
    """Scan an existing skill dir for symlinks/junctions or escapes outside dest.

    Returns list of problem descriptions (empty if clean).
    """
    bad = []
    if is_link(skill_dir):
        bad.append(f"{skill_dir.name} (root link)")
        return bad
    if not skill_dir.exists():
        return bad
    dest_res = dest.resolve()
    try:
        if not skill_dir.resolve().is_relative_to(dest_res):
            bad.append(f"{skill_dir.name} (escapes destination)")
            return bad
    except Exception as e:
        bad.append(f"{skill_dir.name} (resolution error: {e})")
        return bad
    for p in skill_dir.rglob("*"):
        if is_link(p):
            bad.append(f"{p.relative_to(dest)} (link)")
            continue
        try:
            if not p.resolve().is_relative_to(dest_res):
                bad.append(f"{p.relative_to(dest)} (resolves outside destination)")
        except Exception as e:
            bad.append(f"{p.relative_to(dest)} (resolution error: {e})")
    return bad
