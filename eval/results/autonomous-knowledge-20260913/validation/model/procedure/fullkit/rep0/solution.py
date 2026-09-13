"""Managed-file updater: preview / apply / restore with rollback safety.

Public API (pure standard library, module-level functions):

    preview(workspace, updates) -> list[dict]
    apply(workspace, updates, *, fail_recovery=False) -> dict
    restore(workspace) -> dict

Why it is built this way:
- Every file read/write is BINARY, so CRLF text and non-UTF-8 binary survive
  byte-for-byte (no codec round trips, no newline translation).
- The recovery state keeps full preimage bytes (base64 inside JSON), because
  rollback/restore must reproduce exact original bytes, recreate deleted
  files and remove files the apply created.
- The recovery file is written under a temporary name and atomically renamed,
  so a torn ``.updater_recovery.json`` can never exist.
- Ownership is absolute: only files named in ``updates`` plus the recovery
  file (and its rename temporary) are ever touched.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

RECOVERY_FILENAME = ".updater_recovery.json"
RECOVERY_TEMP_FILENAME = RECOVERY_FILENAME + ".tmp"
STATE_VERSION = 1

__all__ = ["preview", "apply", "restore"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _target(workspace: Path, rel_path) -> Path:
    """Resolve a relative POSIX update path inside the workspace."""
    parts = [part for part in str(rel_path).split("/") if part not in ("", ".")]
    return workspace.joinpath(*parts)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_if_exists(path: Path):
    """Raw bytes of the file, or None when it does not exist."""
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _as_bytes(payload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, (bytearray, memoryview)):
        return bytes(payload)
    if isinstance(payload, str):  # tolerated convenience; contract says bytes
        return payload.encode("utf-8")
    raise TypeError(f"update payload must be bytes or None, got {type(payload).__name__}")


def _plan_changes(workspace: Path, updates):
    """Compute exactly what apply() would change, sorted by path.

    Each item is (rel_path, "write"|"delete", new_bytes|None, old_bytes|None).
    No-ops are skipped: identical bytes on write, or deleting a file that does
    not exist -- apply() would change nothing for them, so preview() must not
    report them either.
    """
    plan = []
    for raw_rel, payload in dict(updates).items():
        rel = str(raw_rel)
        target = _target(workspace, rel)
        old = _read_if_exists(target)  # binary read: byte-exact preimage
        if payload is None:
            if old is None:
                continue
            plan.append((rel, "delete", None, old))
        else:
            new = _as_bytes(payload)
            if old == new:
                continue
            plan.append((rel, "write", new, old))
    plan.sort(key=lambda item: item[0])
    return plan


def _rollback(workspace: Path, plan) -> None:
    """Undo a plan: restore preimage bytes, remove files the apply created."""
    for rel, _action, _new, old in reversed(plan):
        target = _target(workspace, rel)
        if old is None:
            try:
                target.unlink()  # we created it; make it gone again
            except FileNotFoundError:
                pass
        else:
            target.write_bytes(old)  # exact preimage; recreates deleted files


def _persist_recovery_state(workspace: Path, state: dict) -> None:
    """Write the recovery state atomically (temp file + os.replace)."""
    temp_path = workspace / RECOVERY_TEMP_FILENAME
    final_path = workspace / RECOVERY_FILENAME
    payload = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
    with open(temp_path, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, final_path)


def _discard_recovery_state(workspace: Path) -> None:
    """Leave no recovery state behind (best effort; never raises)."""
    for name in (RECOVERY_TEMP_FILENAME, RECOVERY_FILENAME):
        try:
            (workspace / name).unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preview(workspace, updates) -> list:
    """Read-only diff of what apply() would actually change."""
    workspace = Path(workspace)
    return [
        {
            "path": rel,
            "action": action,
            "old_sha256": None if old is None else _sha256_hex(old),
            "new_sha256": None if new is None else _sha256_hex(new),
        }
        for rel, action, new, old in _plan_changes(workspace, updates)
    ]


def apply(workspace, updates, *, fail_recovery: bool = False) -> dict:
    """Mutate owned files, then persist the recovery state as the FINAL step."""
    workspace = Path(workspace)
    plan = _plan_changes(workspace, updates)

    # Phase 1: mutate only the owned files.
    for rel, action, new, _old in plan:
        target = _target(workspace, rel)
        if action == "write":
            target.write_bytes(new)  # binary write: byte-exact
        else:
            target.unlink()

    # Phase 2 (final step): persist the preimage snapshot.
    if fail_recovery:
        # Simulated failure of the final persistence: undo every mutation,
        # leave no recovery state behind, report the failure honestly.
        _rollback(workspace, plan)
        _discard_recovery_state(workspace)
        return {
            "ok": False,
            "reason": "recovery-state persistence failed (simulated); all mutations were rolled back",
            "rolled_back": True,
            "applied": [],
        }

    state = {
        "version": STATE_VERSION,
        "entries": [
            {
                "path": rel,
                "existed": old is not None,
                "content_b64": None if old is None else base64.b64encode(old).decode("ascii"),
            }
            for rel, _action, _new, old in plan
        ],
    }
    try:
        _persist_recovery_state(workspace, state)
    except OSError as exc:
        # A real persistence failure gets the same handling as the simulated one.
        _rollback(workspace, plan)
        _discard_recovery_state(workspace)
        return {
            "ok": False,
            "reason": f"recovery-state persistence failed ({exc}); all mutations were rolled back",
            "rolled_back": True,
            "applied": [],
        }

    return {"ok": True, "applied": [rel for rel, _action, _new, _old in plan]}


def restore(workspace) -> dict:
    """Return every owned file to its exact pre-apply bytes."""
    workspace = Path(workspace)
    try:
        raw = (workspace / RECOVERY_FILENAME).read_bytes()
    except FileNotFoundError:
        return {
            "ok": False,
            "reason": "no recovery state found (.updater_recovery.json is absent)",
            "restored": [],
        }
    except OSError as exc:
        return {"ok": False, "reason": f"recovery state unreadable: {exc}", "restored": []}

    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return {"ok": False, "reason": f"recovery state is corrupt: {exc}", "restored": []}

    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return {"ok": False, "reason": "recovery state format not supported", "restored": []}
    entries = state.get("entries")
    if not isinstance(entries, list):
        return {"ok": False, "reason": "recovery state contains no usable entries", "restored": []}

    restored: list = []
    try:
        for entry in entries:
            if not isinstance(entry, dict) or "path" not in entry:
                return {
                    "ok": False,
                    "reason": "recovery state contains a malformed entry",
                    "restored": [],
                }
            rel = str(entry["path"])
            target = _target(workspace, rel)
            if entry.get("existed"):
                content_b64 = entry.get("content_b64")
                if not isinstance(content_b64, str):
                    content_b64 = ""
                try:
                    preimage = base64.b64decode(content_b64, validate=True)
                except (ValueError, TypeError) as exc:
                    return {
                        "ok": False,
                        "reason": f"recovery state entry {rel!r} is corrupt: {exc}",
                        "restored": [],
                    }
                target.write_bytes(preimage)
            else:
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
            restored.append(rel)
    except OSError as exc:
        return {"ok": False, "reason": f"restore failed: {exc}", "restored": []}

    return {"ok": True, "restored": restored}
