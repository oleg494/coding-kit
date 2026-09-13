"""Managed-file updater: byte-exact preview / apply / restore.

Public API (pure standard library, module-level functions):

    preview(workspace, updates) -> list[dict]
    apply(workspace, updates, *, fail_recovery=False) -> dict
    restore(workspace) -> dict

``updates`` maps a relative POSIX path to either bytes (create/overwrite with
exactly those bytes) or None (delete that file).  The paths named in
``updates`` are the files owned for that call; every other workspace file is
foreign and remains byte-for-byte untouched.  The only extra file ``apply``
may touch is its own recovery state ``.updater_recovery.json`` at the
workspace root (plus an atomic-rename temporary for it).  All file I/O is
binary, so CRLF text and non-UTF-8 binary preimages survive exactly.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

__all__ = ["preview", "apply", "restore"]

RECOVERY_NAME = ".updater_recovery.json"
RECOVERY_TMP_NAME = RECOVERY_NAME + ".tmp"
STATE_FORMAT = 1


class _PersistenceFailure(RuntimeError):
    """Simulated failure of the final recovery-state persistence step."""


class _Planned:
    """One change ``apply`` will really make (no-op updates are dropped)."""

    __slots__ = ("rel", "path", "action", "old", "new")

    def __init__(self, rel, path, action, old, new):
        self.rel = rel        # original updates key as a str (POSIX form)
        self.path = path      # concrete path inside the workspace
        self.action = action  # "write" | "delete"
        self.old = old        # preimage bytes, or None if the file was absent
        self.new = new        # replacement bytes, or None for a deletion

    def perform(self) -> None:
        if self.action == "write":
            _write_bytes(self.path, self.new)
        else:
            self.path.unlink()

    def undo(self) -> None:
        if self.old is None:
            # The file was created by this apply: removing it restores the
            # pre-apply state.
            self.path.unlink(missing_ok=True)
        else:
            _write_bytes(self.path, self.old)


# --- small I/O helpers (binary only; never any newline/encoding mangling) ---


def _resolve(ws: Path, rel: str) -> Path:
    return ws.joinpath(*PurePosixPath(rel).parts)


def _read_bytes(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _write_bytes(path: Path, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rollback(performed) -> None:
    """Best-effort undo of already-performed operations, newest first."""
    for op in reversed(performed):
        try:
            op.undo()
        except OSError:
            # Best effort only: the overall result is still reported as a
            # failed, rolled-back apply.
            pass


def _plan(ws: Path, updates) -> list:
    """Compute exactly the changes ``apply`` would make, with preimages.

    No-ops are dropped: a write whose bytes already match, and a delete of
    an absent file, change nothing and must not be reported or applied.
    """
    plan = []
    for key, value in updates.items():
        rel = str(key)
        if value is None:
            new = None
        elif isinstance(value, (bytes, bytearray, memoryview)):
            new = bytes(value)
        else:
            raise TypeError(
                "update for %r must be bytes or None, got %s"
                % (rel, type(value).__name__)
            )
        target = _resolve(ws, rel)
        old = _read_bytes(target) if target.is_file() else None
        if new is None:
            if old is None:
                continue  # deleting an absent file changes nothing
            plan.append(_Planned(rel, target, "delete", old, None))
        elif old == new:
            continue  # bytes already match: a no-op, not a change
        else:
            plan.append(_Planned(rel, target, "write", old, new))
    return plan


# --- public API --------------------------------------------------------------


def preview(workspace, updates) -> list:
    """Read-only plan of what ``apply`` would change. Touches nothing."""
    plan = _plan(Path(workspace), updates)
    return [
        {
            "path": op.rel,
            "action": op.action,
            "old_sha256": None if op.old is None else _sha256_hex(op.old),
            "new_sha256": None if op.new is None else _sha256_hex(op.new),
        }
        for op in plan
    ]


def apply(workspace, updates, *, fail_recovery: bool = False) -> dict:
    """Mutate the owned files, then persist the recovery state (final step)."""
    ws = Path(workspace)

    try:
        plan = _plan(ws, updates)
    except Exception as exc:
        # Planning failed before anything was mutated.
        return _apply_failure("failed to plan updates: %s" % (exc,))

    performed = []
    try:
        for op in plan:
            op.perform()
            performed.append(op)
    except Exception as exc:
        _rollback(performed)
        _remove_quietly(ws / RECOVERY_TMP_NAME)
        return _apply_failure("failed to apply update: %s" % (exc,))

    try:
        if fail_recovery:
            # Contract: the FINAL persistence step fails (simulated). The
            # mutations above must be undone and no recovery state may
            # remain behind.
            raise _PersistenceFailure(
                "simulated persistence failure (fail_recovery=True)"
            )
        _persist_recovery_state(ws, plan)
    except Exception as exc:
        _rollback(performed)
        _remove_quietly(ws / RECOVERY_TMP_NAME)
        if fail_recovery:
            # A handled failure must leave no recovery state behind.
            _remove_quietly(ws / RECOVERY_NAME)
        return _apply_failure("recovery-state persistence failed: %s" % (exc,))

    return {"ok": True, "applied": [op.rel for op in plan]}


def restore(workspace) -> dict:
    """Undo the last successful apply from its persisted recovery state."""
    ws = Path(workspace)
    try:
        raw = _read_bytes(ws / RECOVERY_NAME)
    except FileNotFoundError:
        return _restore_failure("no recovery state exists in this workspace")
    except OSError as exc:
        return _restore_failure("cannot read recovery state: %s" % (exc,))

    entries = _parse_recovery_state(raw)
    if entries is None:
        return _restore_failure("recovery state is corrupt or unusable")

    restored = []
    try:
        for rel, preimage in entries:
            target = _resolve(ws, rel)
            if preimage is None:
                # The apply created this file: removing it restores the
                # pre-apply state.
                target.unlink(missing_ok=True)
            else:
                _write_bytes(target, preimage)
            restored.append(rel)
    except Exception as exc:
        return _restore_failure("failed to restore preimage: %s" % (exc,))

    return {"ok": True, "restored": restored}


# --- recovery-state persistence ----------------------------------------------


def _apply_failure(reason) -> dict:
    return {
        "ok": False,
        "reason": str(reason) or "apply failed",
        "rolled_back": True,
        "applied": [],
    }


def _restore_failure(reason) -> dict:
    return {
        "ok": False,
        "reason": str(reason) or "restore failed",
        "restored": [],
    }


def _persist_recovery_state(ws: Path, plan) -> None:
    """Atomically write ``.updater_recovery.json`` (temp file + os.replace)."""
    entries = [
        {
            "path": op.rel,
            "action": op.action,
            "existed": op.old is not None,
            "preimage_b64": (
                base64.b64encode(op.old).decode("ascii")
                if op.old is not None
                else None
            ),
        }
        for op in plan
    ]
    payload = json.dumps(
        {"format": STATE_FORMAT, "entries": entries}, indent=2
    ).encode("utf-8")
    tmp = ws / RECOVERY_TMP_NAME
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ws / RECOVERY_NAME)  # atomic rename within one directory


def _parse_recovery_state(raw: bytes):
    """Return [(rel, preimage_bytes_or_None), ...] or None if unusable."""
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(state, dict) or state.get("format") != STATE_FORMAT:
        return None
    raw_entries = state.get("entries")
    if not isinstance(raw_entries, list):
        return None
    entries = []
    for item in raw_entries:
        if not isinstance(item, dict):
            return None
        rel = item.get("path")
        existed = item.get("existed")
        if not isinstance(rel, str) or not rel or not isinstance(existed, bool):
            return None
        if existed:
            b64 = item.get("preimage_b64")
            if not isinstance(b64, str):
                return None
            try:
                preimage = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError):
                return None
        else:
            preimage = None
        entries.append((rel, preimage))
    return entries
