"""Managed-file updater: preview / apply / restore with rollback safety.

Module-level API (pure standard library)::

    preview(workspace, updates)                  -> list[dict]
    apply(workspace, updates, *, fail_recovery)  -> dict
    restore(workspace)                           -> dict

Design notes
------------
* All user-file I/O is binary, so preimage bytes (CRLF text, non-UTF-8
  blobs) survive byte-for-byte: no newline translation and no encode/decode
  round trips of user content.
* ``apply`` touches only the files named in ``updates`` plus its own
  recovery-state file ``.updater_recovery.json`` at the workspace root (and
  a transient ``.updater_recovery.json.tmp`` used for an atomic rename).
  Every other file in the workspace is foreign and stays untouched.
* The recovery state stores the exact preimage (base64) of every changed
  file, which is sufficient to undo a whole apply: modified/deleted files
  are rewritten with their original bytes, created files are removed.
* If the FINAL persistence of the recovery state fails (a real error or the
  simulated ``fail_recovery=True``), every mutation is rolled back, no
  recovery state or temporary is left behind, and a failure result with
  ``rolled_back: True`` is returned.  A pre-existing recovery state from an
  earlier *successful* apply is never damaged by a failed one.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

__all__ = ["preview", "apply", "restore"]

RECOVERY_STATE_NAME = ".updater_recovery.json"
RECOVERY_TEMP_NAME = RECOVERY_STATE_NAME + ".tmp"


class _RecoveryPersistenceError(Exception):
    """The final persistence of the recovery state failed (real or simulated)."""


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_or_none(path: Path):
    """Return a file's raw bytes, or None if no file exists at ``path``."""
    try:
        return path.read_bytes()  # binary mode: byte-exact, no translation
    except (FileNotFoundError, NotADirectoryError):
        return None


def _workspace_path(workspace: Path, relpath: str) -> Path:
    """Map a relative POSIX path onto a concrete path inside ``workspace``."""
    if relpath.startswith("/"):
        raise ValueError(f"update path must be relative: {relpath!r}")
    parts = []
    for part in relpath.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"update path escapes the workspace: {relpath!r}")
        parts.append(part)
    if not parts:
        raise ValueError(f"update path does not name a file: {relpath!r}")
    target = workspace.joinpath(*parts)
    try:
        target.relative_to(workspace)
    except ValueError:
        raise ValueError(f"update path escapes the workspace: {relpath!r}") from None
    return target


def _normalized_update_items(updates):
    """Validate the updates mapping; return sorted (path, spec) pairs."""
    if not isinstance(updates, Mapping):
        raise TypeError(
            "updates must be a mapping of relative POSIX path -> bytes | None"
        )
    items = []
    for key, spec in updates.items():
        if isinstance(key, os.PathLike):
            key = os.fspath(key)
        if not isinstance(key, str):
            raise TypeError(f"update path must be a str, got {type(key).__name__}")
        items.append((key, spec))
    items.sort(key=lambda pair: pair[0])
    return items


def _build_plan(workspace: Path, updates) -> list:
    """Read-only computation of the changes ``apply`` would actually make.

    A write whose bytes already match and a delete of a missing file are
    no-ops and are excluded from the plan.
    """
    plan = []
    for key, spec in _normalized_update_items(updates):
        target = _workspace_path(workspace, key)
        old = _read_or_none(target)
        if spec is None:
            if old is None:
                continue  # deleting a missing file changes nothing
            plan.append(
                {"path": key, "target": target, "action": "delete",
                 "old": old, "new": None}
            )
            continue
        if not isinstance(spec, (bytes, bytearray, memoryview)):
            raise TypeError(
                f"update for {key!r} must be bytes or None, "
                f"got {type(spec).__name__}"
            )
        new = bytes(spec)
        if old == new:
            continue  # no-op write: content already byte-identical
        plan.append(
            {"path": key, "target": target, "action": "write",
             "old": old, "new": new}
        )
    return plan


def _failure(reason: str) -> dict:
    return {
        "ok": False,
        "reason": reason or "unknown failure",
        "rolled_back": True,
        "applied": [],
    }


def _ensure_parent(parent: Path, created_dirs: list) -> None:
    """Create missing parent directories, remembering them for rollback.

    Per the contract parents already exist, so this is defensive only.
    """
    missing = []
    cur = parent
    while not cur.exists():
        missing.append(cur)
        if cur == cur.parent:
            break
        cur = cur.parent
    for directory in reversed(missing):
        directory.mkdir()
        created_dirs.append(directory)


def _mutate(item: dict, created_dirs: list) -> None:
    target = item["target"]
    if item["action"] == "write":
        _ensure_parent(target.parent, created_dirs)
        target.write_bytes(item["new"])  # binary mode: byte-exact write
    else:  # delete
        try:
            os.remove(target)
        except FileNotFoundError:
            pass


def _rollback(executed: list, created_dirs: list) -> None:
    """Undo executed mutations: restore preimage bytes / remove creations."""
    for item in reversed(executed):
        target = item["target"]
        old = item["old"]
        try:
            if old is None:
                # The file was created by this apply: remove it again.
                try:
                    os.remove(target)
                except FileNotFoundError:
                    pass
            else:
                # Modified or deleted by this apply: restore exact bytes.
                target.write_bytes(old)
        except OSError:
            pass  # best effort: keep undoing the remaining items
    for directory in reversed(created_dirs):
        try:
            os.rmdir(directory)  # only removes dirs we created, if now empty
        except OSError:
            pass


def _state_entry(item: dict) -> dict:
    old = item["old"]
    if old is None:
        return {
            "path": item["path"],
            "action": item["action"],
            "existed": False,
            "content_b64": None,
            "sha256": None,
        }
    return {
        "path": item["path"],
        "action": item["action"],
        "existed": True,
        "content_b64": base64.b64encode(old).decode("ascii"),
        "sha256": _sha256_hex(old),
    }


def _persist_recovery_state(workspace: Path, plan: list, *, fail_recovery: bool) -> None:
    """Write the recovery state atomically.  Raises on (simulated) failure
    and never leaves a temporary or partial state file behind."""
    state = {"version": 1, "files": [_state_entry(item) for item in plan]}
    payload = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
    tmp = workspace / RECOVERY_TEMP_NAME
    final = workspace / RECOVERY_STATE_NAME
    try:
        with open(tmp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        if fail_recovery:
            # Simulated failure of the final persistence step: the rename
            # never happens, so no recovery state is left behind.
            raise _RecoveryPersistenceError(
                "simulated failure while persisting recovery state "
                "(fail_recovery=True)"
            )
        os.replace(tmp, final)  # atomic publish of the recovery state
    finally:
        try:
            os.remove(tmp)  # no-op once the rename succeeded
        except OSError:
            pass


def _load_recovery_state(workspace: Path):
    """Return (entries, None) when a usable state exists, else (None, reason)."""
    path = workspace / RECOVERY_STATE_NAME
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, f"no usable recovery state: {RECOVERY_STATE_NAME} is missing"
    except OSError as exc:
        return None, f"cannot read recovery state {RECOVERY_STATE_NAME}: {exc}"
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return None, f"recovery state is not valid JSON: {exc}"
    if not isinstance(state, dict) or not isinstance(state.get("files"), list):
        return None, "recovery state is malformed: expected an object with a 'files' list"

    entries = []
    for index, entry in enumerate(state["files"]):
        if not isinstance(entry, dict):
            return None, f"recovery state entry #{index} is malformed"
        relpath = entry.get("path")
        if not isinstance(relpath, str) or not relpath:
            return None, f"recovery state entry #{index} has no valid 'path'"
        existed = entry.get("existed")
        if not isinstance(existed, bool):
            return None, f"recovery state entry for {relpath!r} has no valid 'existed' flag"
        data = None
        if existed:
            content = entry.get("content_b64")
            if not isinstance(content, str):
                return None, f"recovery state entry for {relpath!r} lacks preimage content"
            try:
                data = base64.b64decode(content.encode("ascii"), validate=True)
            except (ValueError, UnicodeEncodeError):
                return None, f"recovery state entry for {relpath!r} has undecodable preimage content"
        try:
            target = _workspace_path(workspace, relpath)
        except ValueError as exc:
            return None, f"recovery state entry for {relpath!r} is invalid: {exc}"
        entries.append({"path": relpath, "target": target, "existed": existed, "data": data})
    return entries, None


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def preview(workspace, updates) -> list:
    """Read-only plan of what ``apply`` would actually change.

    Returns one entry per file that would really change (no-op updates are
    skipped)::
        {"path": str, "action": "write" | "delete",
         "old_sha256": hex | None, "new_sha256": hex | None}
    """
    plan = _build_plan(Path(workspace), updates)
    entries = []
    for item in plan:
        entries.append(
            {
                "path": item["path"],
                "action": item["action"],
                "old_sha256": None if item["old"] is None else _sha256_hex(item["old"]),
                "new_sha256": None if item["new"] is None else _sha256_hex(item["new"]),
            }
        )
    return entries


def apply(workspace, updates, *, fail_recovery: bool = False) -> dict:
    """Mutate only the owned files, then persist the recovery state last.

    On success: ``{"ok": True, "applied": [changed paths]}``.
    If the final recovery-state persistence fails (simulated with
    ``fail_recovery=True`` or a genuine I/O error), every mutation is undone
    and ``{"ok": False, "reason": ..., "rolled_back": True, "applied": []}``
    is returned with no recovery state left behind.
    """
    ws = Path(workspace)
    if not ws.is_dir():
        return _failure(f"workspace directory does not exist: {ws}")

    try:
        plan = _build_plan(ws, updates)
    except Exception as exc:
        return _failure(f"invalid updates: {type(exc).__name__}: {exc}")

    executed = []
    created_dirs = []
    try:
        for item in plan:
            _mutate(item, created_dirs)
            executed.append(item)
    except Exception as exc:
        _rollback(executed, created_dirs)
        return _failure(f"failed while applying updates: {type(exc).__name__}: {exc}")

    # The recovery state is persisted as the FINAL step, after all mutations.
    try:
        _persist_recovery_state(ws, plan, fail_recovery=fail_recovery)
    except Exception as exc:
        # Persistence failed: undo everything, leave no state or temp behind.
        _rollback(executed, created_dirs)
        return _failure(
            "recovery-state persistence failed; every mutation was rolled "
            f"back: {type(exc).__name__}: {exc}"
        )

    return {"ok": True, "applied": [item["path"] for item in plan]}


def restore(workspace) -> dict:
    """Undo the last successful apply using its recovery state.

    Returns ``{"ok": True, "restored": [paths]}`` on success, or
    ``{"ok": False, "reason": ..., "restored": []}`` when no usable
    recovery state exists.
    """
    ws = Path(workspace)
    entries, reason = _load_recovery_state(ws)
    if entries is None:
        return {"ok": False, "reason": reason, "restored": []}

    restored = []
    try:
        for entry in entries:
            target = entry["target"]
            if entry["existed"]:
                parent = target.parent
                if not parent.exists():
                    parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(entry["data"])  # byte-exact preimage
            else:
                try:
                    os.remove(target)  # file was created by that apply
                except FileNotFoundError:
                    pass
            restored.append(entry["path"])
    except Exception as exc:
        return {"ok": False, "reason": f"failed to restore preimage: {exc}", "restored": []}

    return {"ok": True, "restored": restored}
