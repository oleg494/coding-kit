"""Managed-file updater.

Module-level API (pure standard library):

    preview(workspace, updates) -> list[dict]
    apply(workspace, updates, *, fail_recovery=False) -> dict
    restore(workspace) -> dict

How this implementation maps to the contract:

* Ownership: ``apply`` mutates only the files named in ``updates`` plus its own
  recovery state ``.updater_recovery.json`` at the workspace root (written via
  a same-directory temporary ``.updater_recovery.json.tmp`` that is atomically
  renamed onto the final name and never left behind).
* Binary exactness: every read/write uses binary mode.  Preimages are stored
  in the JSON recovery state as base64 text, so CRLF line endings and
  non-UTF-8 bytes round-trip byte-for-byte; no decode/encode or newline
  translation is ever performed on file content.
* ``preview`` is read-only and reports exactly the entries ``apply`` would
  change; no-op updates (identical bytes, or deleting a missing file) are
  excluded.
* ``apply`` mutates the owned files first and persists the recovery state as
  the FINAL step.  With ``fail_recovery=True`` that persistence fails by
  simulation: every mutation is undone byte-for-byte (deleted files recreated,
  created files removed), no recovery state is left behind, and the failure is
  reported honestly with ``rolled_back=True``.
* ``restore`` rebuilds the exact pre-apply bytes recorded by the last
  successful apply, then removes the recovery state.  With no usable state it
  returns ``ok=False`` without raising.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import NamedTuple, Optional, Union

__all__ = ["preview", "apply", "restore"]

RECOVERY_NAME = ".updater_recovery.json"
RECOVERY_TMP_NAME = ".updater_recovery.json.tmp"

_BYTES_LIKE = (bytes, bytearray, memoryview)


class _Change(NamedTuple):
    """One planned, non-no-op change to an owned file."""

    path: str
    action: str  # "write" | "delete"
    existed: bool
    old_bytes: Optional[bytes]
    old_sha256: Optional[str]
    new_bytes: Optional[bytes]
    new_sha256: Optional[str]


class _RestoreEntry(NamedTuple):
    """One entry parsed from the recovery state (enough to undo a change)."""

    path: str
    existed: bool
    old_bytes: Optional[bytes]


# --------------------------------------------------------------------------
# small binary-exact I/O helpers
# --------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_regular_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _read_bytes(path: Path) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def _write_bytes(path: Path, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)


def _remove_file(path: Path) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _validate_rel(rel: object) -> str:
    """Return the update path as a str, rejecting paths outside the workspace."""
    if isinstance(rel, os.PathLike):
        rel = os.fspath(rel)
    if not isinstance(rel, str):
        raise TypeError(f"update path must be a str, got {type(rel).__name__}")
    if not rel:
        raise ValueError("update path must be non-empty")
    pure = PurePosixPath(rel)
    if not pure.parts or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"update path must stay inside the workspace: {rel!r}")
    return rel


def _target_for(ws: Path, rel: str) -> Path:
    return ws.joinpath(*PurePosixPath(rel).parts)


# --------------------------------------------------------------------------
# planning (shared by preview and apply so both always agree)
# --------------------------------------------------------------------------

def _compute_plan(ws: Path, updates: Mapping) -> list:
    if not isinstance(updates, Mapping):
        raise TypeError("updates must be a mapping of relative path -> bytes | None")
    plan: list = []
    for raw_rel, new_value in updates.items():
        rel = _validate_rel(raw_rel)
        target = _target_for(ws, rel)
        if new_value is None:
            if not _is_regular_file(target):
                continue  # deleting a file that is not there is a no-op
            old = _read_bytes(target)
            plan.append(
                _Change(rel, "delete", True, old, _sha256(old), None, None)
            )
            continue
        if not isinstance(new_value, _BYTES_LIKE):
            raise TypeError(
                f"update content for {rel!r} must be bytes-like or None, "
                f"got {type(new_value).__name__}"
            )
        new = bytes(new_value)
        if _is_regular_file(target):
            old = _read_bytes(target)
            if old == new:
                continue  # no-op: content already identical
            plan.append(
                _Change(rel, "write", True, old, _sha256(old), new, _sha256(new))
            )
        else:
            plan.append(
                _Change(rel, "write", False, None, None, new, _sha256(new))
            )
    return plan


# --------------------------------------------------------------------------
# recovery state persistence / parsing
# --------------------------------------------------------------------------

def _persist_recovery_state(ws: Path, plan: Sequence) -> None:
    entries = [
        {
            "path": change.path,
            "action": change.action,
            "existed": change.existed,
            "old_b64": (
                base64.b64encode(change.old_bytes).decode("ascii")
                if change.old_bytes is not None
                else None
            ),
            "old_sha256": change.old_sha256,
            "new_sha256": change.new_sha256,
        }
        for change in plan
    ]
    payload = json.dumps(
        {"version": 1, "entries": entries}, indent=2, sort_keys=True
    ).encode("utf-8")
    tmp_path = ws / RECOVERY_TMP_NAME
    final_path = ws / RECOVERY_NAME
    try:
        with open(tmp_path, "wb") as handle:
            handle.write(payload)
            try:
                handle.flush()
                os.fsync(handle.fileno())
            except OSError:
                pass  # best effort durability; the rename below still commits
        os.replace(tmp_path, final_path)
    except BaseException:
        _remove_file(tmp_path)  # never leave the atomic-rename temp behind
        raise


def _parse_recovery_document(document: object) -> list:
    if not isinstance(document, dict):
        raise ValueError("recovery state must be a JSON object")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("recovery state must contain an 'entries' list")
    entries: list = []
    seen: set = set()
    for item in raw_entries:
        if not isinstance(item, dict):
            raise ValueError("each recovery entry must be an object")
        path = item.get("path")
        if not isinstance(path, str):
            raise ValueError("recovery entry 'path' must be a string")
        _validate_rel(path)
        existed = item.get("existed")
        if not isinstance(existed, bool):
            raise ValueError("recovery entry 'existed' must be a boolean")
        old_b64 = item.get("old_b64")
        if existed:
            if not isinstance(old_b64, str):
                raise ValueError(f"recovery entry for {path!r} lacks base64 preimage")
            try:
                old_bytes = base64.b64decode(old_b64.encode("ascii"), validate=True)
            except (ValueError, UnicodeEncodeError) as exc:
                raise ValueError(
                    f"recovery entry for {path!r} has invalid base64 preimage: {exc}"
                ) from exc
        else:
            if old_b64 is not None:
                raise ValueError(
                    f"recovery entry for created file {path!r} must not carry a preimage"
                )
            old_bytes = None
        if path in seen:
            raise ValueError(f"duplicate recovery entry for {path!r}")
        seen.add(path)
        entries.append(_RestoreEntry(path, existed, old_bytes))
    return entries


def _roll_back(ws: Path, plan: Sequence) -> bool:
    """Undo every planned mutation using the in-memory preimages."""
    fully_undone = True
    for change in reversed(plan):
        target = _target_for(ws, change.path)
        try:
            if change.existed:
                _write_bytes(target, change.old_bytes)
            else:
                _remove_file(target)
        except Exception:
            fully_undone = False
    return fully_undone


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def preview(
    workspace: Union[str, "os.PathLike"],
    updates: Mapping,
) -> list:
    """Read-only plan of what apply() would change. Never mutates anything."""
    ws = Path(workspace)
    plan = _compute_plan(ws, updates)
    return [
        {
            "path": change.path,
            "action": change.action,
            "old_sha256": change.old_sha256,
            "new_sha256": change.new_sha256,
        }
        for change in plan
    ]


def apply(
    workspace: Union[str, "os.PathLike"],
    updates: Mapping,
    *,
    fail_recovery: bool = False,
) -> dict:
    """Apply the owned updates, then persist the recovery state as the final step."""
    ws = Path(workspace)
    try:
        plan = _compute_plan(ws, updates)
    except (OSError, TypeError, ValueError) as exc:
        return {
            "ok": False,
            "reason": f"planning failed, nothing was changed: {exc}",
            "rolled_back": True,
            "applied": [],
        }

    # --- mutate the owned files exactly as planned -----------------------
    applied: list = []
    try:
        for change in plan:
            target = _target_for(ws, change.path)
            if change.action == "delete":
                os.unlink(target)
            else:
                _write_bytes(target, change.new_bytes)
            applied.append(change.path)
    except Exception as exc:
        rolled_back = _roll_back(ws, plan)
        return {
            "ok": False,
            "reason": f"failed to update owned files, changes undone: {exc}",
            "rolled_back": rolled_back,
            "applied": [],
        }

    # --- final step: persist the recovery state --------------------------
    if fail_recovery:
        # Simulated persistence failure: undo everything, leave no state.
        rolled_back = _roll_back(ws, plan)
        return {
            "ok": False,
            "reason": "failed to persist recovery state; all changes were rolled back",
            "rolled_back": rolled_back,
            "applied": [],
        }
    try:
        _persist_recovery_state(ws, plan)
    except Exception as exc:
        rolled_back = _roll_back(ws, plan)
        return {
            "ok": False,
            "reason": (
                "failed to persist recovery state; all changes were rolled back: "
                f"{exc}"
            ),
            "rolled_back": rolled_back,
            "applied": [],
        }

    return {"ok": True, "applied": applied}


def restore(workspace: Union[str, "os.PathLike"]) -> dict:
    """Return owned files to their exact pre-apply bytes using the recovery state."""
    ws = Path(workspace)
    state_path = ws / RECOVERY_NAME
    if not _is_regular_file(state_path):
        return {
            "ok": False,
            "reason": f"no usable recovery state ({RECOVERY_NAME}) in workspace",
            "restored": [],
        }
    try:
        document = json.loads(_read_bytes(state_path).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "reason": f"recovery state is unreadable: {exc}",
            "restored": [],
        }
    try:
        entries = _parse_recovery_document(document)
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "reason": f"recovery state is malformed: {exc}",
            "restored": [],
        }

    restored: list = []
    try:
        for entry in entries:
            target = _target_for(ws, entry.path)
            if entry.existed:
                _write_bytes(target, entry.old_bytes)
            else:
                _remove_file(target)
            restored.append(entry.path)
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"restore failed part-way: {exc}",
            "restored": [],
        }

    try:
        _remove_file(state_path)
    except OSError as exc:
        return {
            "ok": False,
            "reason": f"restored files but failed to drop recovery state: {exc}",
            "restored": [],
        }

    return {"ok": True, "restored": restored}
