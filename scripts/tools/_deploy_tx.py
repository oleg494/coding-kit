import shutil
import tempfile
from pathlib import Path
from typing import Optional


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
                if action == "remove_on_failure":
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                elif action == "restore" and snap and snap.exists():
                    if is_dir:
                        if target.exists():
                            shutil.rmtree(target)
                        shutil.copytree(snap, target)
                    else:
                        if target.exists():
                            target.unlink()
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(snap, target)
            except Exception as e:
                rollback_errors.append(f"Failed to restore {target}: {e}")

        # Clean up empty recorded newly-created parent directories
        for parent in reversed(self._created_parents):
            try:
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
