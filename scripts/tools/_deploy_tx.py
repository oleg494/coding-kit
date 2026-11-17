import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Optional

try:
    from ._deploy_fs import is_link as _is_link
except (ImportError, ValueError):
    try:
        from _deploy_fs import is_link as _is_link
    except ImportError:
        import importlib.util as _ilu
        _fs_spec = _ilu.spec_from_file_location(
            "_deploy_fs", Path(__file__).resolve().parent / "_deploy_fs.py")
        _fs_mod = _ilu.module_from_spec(_fs_spec)
        _fs_spec.loader.exec_module(_fs_mod)
        _is_link = _fs_mod.is_link


def _assert_no_links(root: Path) -> None:
    """Fail closed if root or any nested child is a symlink/junction."""
    if _is_link(root):
        raise RuntimeError(f"Refusing to rmtree link {root}")
    for dirpath, dirs, files in os.walk(root, topdown=True, followlinks=False):
        for name in dirs + files:
            p = Path(dirpath) / name
            if _is_link(p):
                raise RuntimeError(f"Refusing to traverse/unlink link {p}")


def _rmtree_readonly_safe(path: Path) -> None:
    """Link-safe shutil.rmtree clearing read-only bits on Windows PermissionError."""
    _assert_no_links(path)

    def _clear_ro_and_retry(func, fpath, _exc):
        try:
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        except Exception:
            raise

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_clear_ro_and_retry)
    else:
        def _onerror(func, fpath, _exc_info):
            _clear_ro_and_retry(func, fpath, None)
        shutil.rmtree(path, onerror=_onerror)


def _unlink_force(path: Path) -> None:
    if _is_link(path):
        raise RuntimeError(f"Refusing to unlink link {path}")
    try:
        path.unlink()
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        path.unlink()


class DeployTransaction:
    """Manages handled-I/O rollback snapshots for planned touched deployment targets.

    Explicit Non-Goals:
      1. Durability across sudden process termination or power loss (no WAL fsync engine).
      2. Concurrent filesystem swaps or races during multi-second syncs.
    Bounded Scope:
      Handled Python runtime I/O exceptions and verification failures during deployment execution.
    """

    def __init__(self):
        self.tx_dir: Optional[Path] = None
        self._entries: list[dict] = []  # list of {target, action, snapshot_path, is_dir}
        self._created_parents: list[Path] = []  # directories created by transaction that were absent
        self._mutations_started = False
        self._committed = False

    def __enter__(self):
        self.tx_dir = Path(tempfile.mkdtemp(prefix="kit-deploy-tx-"))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and not self._committed:
            self.rollback(initial_error=str(exc_val))
            return False
        if self._committed and self.tx_dir and self.tx_dir.exists():
            shutil.rmtree(self.tx_dir, ignore_errors=True)
        return False

    def record_absent_ancestors(self, path: Path):
        """Record any absent ancestor directories above path that would be created."""
        curr = path if not path.exists() else path.parent
        missing = []
        while not curr.exists() and curr != curr.parent:
            missing.append(curr)
            curr = curr.parent
        # Append in root-to-leaf order so rollback removes leaf-to-root
        for m in reversed(missing):
            if m not in self._created_parents:
                self._created_parents.append(m)
    def mark_mutations_started(self):
        """Call when preflight and snapshotting finish and actual mutation starts."""
        self._mutations_started = True

    def snapshot_target(self, target: Path):
        """Snapshot a specific target file or directory before it is touched."""
        if not self.tx_dir:
            return
        # If already tracked, skip duplicate snapshot
        for entry in self._entries:
            if entry["target"] == target:
                return

        if _is_link(target):
            raise RuntimeError(f"Refusing to snapshot symlink/junction target {target}")
        if not target.exists():
            self._entries.append({
                "target": target,
                "action": "remove_on_failure",
                "snapshot_path": None,
                "is_dir": False,
            })
            return

        idx = len(self._entries)
        if target.is_dir():
            snap = self.tx_dir / f"snap_dir_{idx}"
            shutil.copytree(target, snap)
            self._entries.append({
                "target": target,
                "action": "restore",
                "snapshot_path": snap,
                "is_dir": True,
            })
        else:
            snap = self.tx_dir / f"snap_file_{idx}"
            shutil.copy2(target, snap)
            self._entries.append({
                "target": target,
                "action": "restore",
                "snapshot_path": snap,
                "is_dir": False,
            })

    def rollback(self, initial_error: Optional[str] = None) -> bool:
        """Rollback all recorded targets in reverse order."""
        if not self.tx_dir or self._committed:
            return True

        # If mutations never started (e.g. failure during snapshotting/preflight),
        # do NOT perform destructive restore; simply clean up tx_dir
        if not self._mutations_started:
            if self.tx_dir.exists():
                shutil.rmtree(self.tx_dir, ignore_errors=True)
            return True

        rollback_errors = []
        # Rollback targets in reverse order
        for entry in reversed(self._entries):
            target: Path = entry["target"]
            action = entry["action"]
            snap: Optional[Path] = entry["snapshot_path"]
            is_dir = entry["is_dir"]

            try:
                if _is_link(target):
                    raise RuntimeError(f"Refusing rollback across link {target}")
                if action == "remove_on_failure":
                    if target.exists():
                        if target.is_dir():
                            _rmtree_readonly_safe(target)
                        else:
                            _unlink_force(target)
                elif action == "restore" and snap and snap.exists():
                    if is_dir:
                        if target.exists():
                            _rmtree_readonly_safe(target)
                        shutil.copytree(snap, target)
                    else:
                        if target.exists():
                            _unlink_force(target)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(snap, target)
            except Exception as e:
                rollback_errors.append(f"Failed to restore {target}: {e}")

        # Clean up empty recorded newly-created parent directories (leaf-to-root)
        for parent in sorted(set(self._created_parents), key=lambda p: len(p.parts), reverse=True):
            try:
                if _is_link(parent):
                    continue
                if parent.exists() and parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
            except Exception as e:
                rollback_errors.append(f"Failed to remove created parent {parent}: {e}")

        if rollback_errors:
            print(f"\nFATAL: Deployment failed and rollback encountered secondary errors!")
            if initial_error:
                print(f"Initial failure: {initial_error}")
            for err in rollback_errors:
                print(f"Rollback error: {err}")
            print(f"Recovery snapshot preserved at: {self.tx_dir}\n")
            return False

        # If rollback succeeded cleanly, remove tx_dir
        if self.tx_dir.exists():
            shutil.rmtree(self.tx_dir, ignore_errors=True)
        return True

    def commit(self):
        """Commit deployment, permanently removing transaction directory."""
        self._committed = True
        if self.tx_dir and self.tx_dir.exists():
            shutil.rmtree(self.tx_dir, ignore_errors=True)
