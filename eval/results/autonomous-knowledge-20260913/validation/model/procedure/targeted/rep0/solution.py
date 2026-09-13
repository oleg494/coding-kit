"""Managed-file updater: preview / apply / restore for a workspace tree.

Implemented contract:

* Ownership -- ``apply`` creates/modifies/deletes ONLY the files named in
  ``updates``, plus its own recovery-state file ``.updater_recovery.json`` at
  the workspace root (and a ``.updater_recovery.json.tmp`` atomic-rename
  temporary that never survives an operation).  Every other file is foreign
  and stays byte-for-byte identical.
* Binary exactness -- all file I/O is binary; preimages are raw ``bytes``.
  Inside the JSON recovery state preimages are base64-encoded purely as a
  container encoding (never decoded/re-encoded as text and never passed
  through newline translation), so CRLF text and non-UTF-8 binary survive
  every round trip byte-exactly.
* preview -- strictly read-only; announces only files that would actually
  change.  No-ops (a write whose bytes already match, a delete of a missing
  file) are skipped so preview(), the recovery state and apply() all agree.
* apply -- performs exactly the announced plan, then persists the recovery
  state (preimage snapshot sufficient to undo the change) as the FINAL step,
  atomically via temp file + ``os.replace``.
* Handled failure -- if that final persistence fails (a real ``OSError`` or
  the simulated ``fail_recovery=True``), every mutation is undone
  byte-exactly (preimages rewritten, deleted files recreated, created files
  removed), no recovery state or temporary is left behind, and failure is
  reported honestly (``ok=False``, non-empty ``reason``, ``rolled_back=True``,
  ``applied=[]``).  Success is never claimed after failed persistence.
* restore -- rewrites the exact pre-apply bytes of every owned file
  (recreating deleted ones, removing created ones) and consumes the recovery
  state, leaving the tree exactly as it was before the last successful
  ``apply``.  A missing or corrupt state is reported as failure, never
  raised, and never reported as success.
"""

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

RECOVERY_NAME = ".updater_recovery.json"
RECOVERY_TMP_NAME = RECOVERY_NAME + ".tmp"

__all__ = ["preview", "apply", "restore"]


class _PersistenceFailure(Exception):
    """Raised when persisting the recovery state fails (real or simulated)."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _write_bytes(path, data):
    with open(path, "wb") as fh:
        fh.write(data)
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except OSError:
            pass


def _resolve(workspace, rel):
    """Map a relative POSIX update key onto a path inside the workspace."""
    if not isinstance(rel, str) or not rel:
        raise ValueError("update keys must be non-empty relative POSIX paths")
    posix = PurePosixPath(rel)
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError("update key escapes the workspace: %r" % (rel,))
    if not posix.parts:
        raise ValueError("update key does not name a file: %r" % (rel,))
    return workspace.joinpath(*posix.parts)


def _normalize(value):
    """Accept bytes-like new content (or None for delete); reject the rest."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    raise TypeError(
        "update values must be bytes-like or None, got %s" % type(value).__name__)


def _plan(workspace, updates):
    """Files apply() would really change, in the order given by ``updates``.

    No-ops are skipped: a write whose new bytes already equal the file's
    current bytes, and a delete of a file that does not exist.
    """
    plan = []
    for rel, value in updates.items():
        new_bytes = _normalize(value)
        target = _resolve(workspace, rel)
        if new_bytes is None:
            if not target.exists():
                continue  # deleting a missing file changes nothing
            old_bytes = _read_bytes(target)
            plan.append({
                "path": rel,
                "action": "delete",
                "old_sha256": _sha256_hex(old_bytes),
                "new_sha256": None,
                "target": target,
                "old_bytes": old_bytes,
                "new_bytes": None,
            })
            continue
        existed = target.is_file()
        old_bytes = _read_bytes(target) if existed else None
        if existed and old_bytes == new_bytes:
            continue  # identical content: no-op, not announced
        plan.append({
            "path": rel,
            "action": "write",
            "old_sha256": _sha256_hex(old_bytes) if existed else None,
            "new_sha256": _sha256_hex(new_bytes),
            "target": target,
            "old_bytes": old_bytes,
            "new_bytes": new_bytes,
        })
    return plan


def _encode_state(preimages):
    """Serialize the preimage snapshot to JSON bytes (binary-safe via base64)."""
    entries = []
    for rel, existed, old_bytes in preimages:
        entries.append({
            "path": rel,
            "existed": bool(existed),
            "old_sha256": _sha256_hex(old_bytes) if old_bytes is not None else None,
            "old_content_b64": (
                base64.b64encode(old_bytes).decode("ascii")
                if old_bytes is not None else None
            ),
        })
    state = {"version": 1, "entries": entries}
    return json.dumps(state, indent=2, sort_keys=True).encode("utf-8")


def _persist_recovery(workspace, data, fail):
    """Persist the recovery state atomically (temp file + os.replace)."""
    tmp = workspace / RECOVERY_TMP_NAME
    _write_bytes(tmp, data)
    if fail:
        # Simulated failure of the final persistence step: the temporary is
        # cleaned up and the caller must roll every mutation back.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise _PersistenceFailure(
            "simulated failure while persisting recovery state "
            "(fail_recovery=True)")
    os.replace(tmp, workspace / RECOVERY_NAME)


def _rollback(workspace, preimages, recovery_existed, old_recovery):
    """Undo every mutation; return a list of error strings ([] means clean)."""
    errors = []
    for rel, existed, old_bytes in reversed(preimages):
        try:
            target = _resolve(workspace, rel)
            if existed:
                _write_bytes(target, old_bytes)  # exact preimage bytes
            elif target.exists():
                os.unlink(target)                # remove a file we created
        except OSError as exc:
            errors.append("%s: %s" % (rel, exc))
    try:
        tmp = workspace / RECOVERY_TMP_NAME
        if tmp.exists():
            os.unlink(tmp)
        recovery = workspace / RECOVERY_NAME
        if recovery_existed and old_recovery is not None:
            # Restore whatever recovery state existed before this call.
            _write_bytes(tmp, old_recovery)
            os.replace(tmp, recovery)
        elif recovery.exists():
            os.unlink(recovery)  # leave no recovery state behind
    except OSError as exc:
        errors.append("recovery-state cleanup: %s" % (exc,))
    return errors


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def preview(workspace, updates):
    """Read-only plan of exactly what apply() would change."""
    workspace = Path(workspace)
    return [
        {
            "path": entry["path"],
            "action": entry["action"],
            "old_sha256": entry["old_sha256"],
            "new_sha256": entry["new_sha256"],
        }
        for entry in _plan(workspace, updates)
    ]


def apply(workspace, updates, *, fail_recovery=False):
    workspace = Path(workspace)
    recovery = workspace / RECOVERY_NAME
    plan = _plan(workspace, updates)

    recovery_existed = recovery.exists()
    old_recovery = _read_bytes(recovery) if recovery_existed else None

    # Phase 1: mutate only the planned (owned) files, recording preimages
    # BEFORE each mutation so any failure can be undone exactly.
    preimages = []
    try:
        for entry in plan:
            target = entry["target"]
            if entry["action"] == "delete":
                preimages.append((entry["path"], True, entry["old_bytes"]))
                os.unlink(target)
            else:
                existed = target.is_file()
                old_bytes = _read_bytes(target) if existed else None
                preimages.append((entry["path"], existed, old_bytes))
                parent = target.parent
                if not parent.exists():
                    os.makedirs(parent, exist_ok=True)
                _write_bytes(target, entry["new_bytes"])
    except OSError as exc:
        errors = _rollback(workspace, preimages, recovery_existed, old_recovery)
        reason = ("mutation failed before recovery persistence (%s); "
                  "all changes were rolled back" % (exc,))
        if errors:
            reason += "; rollback errors: " + "; ".join(errors)
        return {"ok": False, "reason": reason,
                "rolled_back": not errors, "applied": []}

    # Phase 2 (FINAL step): persist the recovery state.  Any failure here --
    # real or simulated -- must fully undo Phase 1.
    data = _encode_state(preimages)
    try:
        _persist_recovery(workspace, data, fail=bool(fail_recovery))
    except (_PersistenceFailure, OSError) as exc:
        errors = _rollback(workspace, preimages, recovery_existed, old_recovery)
        reason = ("failed to persist recovery state (%s); "
                  "all changes were rolled back" % (exc,))
        if errors:
            reason += "; rollback errors: " + "; ".join(errors)
        return {"ok": False, "reason": reason,
                "rolled_back": not errors, "applied": []}

    return {"ok": True, "applied": [entry["path"] for entry in plan]}


def restore(workspace):
    """Return every owned file of the last successful apply() to its exact
    pre-apply bytes; consume the recovery state.  Failures are reported,
    never raised and never reported as success."""
    workspace = Path(workspace)
    recovery = workspace / RECOVERY_NAME

    def fail_state(reason):
        return {"ok": False, "reason": reason, "restored": []}

    if not recovery.is_file():
        return fail_state(
            "no usable recovery state: %s not found in workspace" % RECOVERY_NAME)
    try:
        raw = _read_bytes(recovery)
        state = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return fail_state(
            "no usable recovery state: unreadable or corrupt (%s)" % (exc,))
    if not isinstance(state, dict) or not isinstance(state.get("entries"), list):
        return fail_state("no usable recovery state: malformed state document")

    preimages = []
    for index, entry in enumerate(state["entries"]):
        if not isinstance(entry, dict):
            return fail_state(
                "no usable recovery state: malformed entry #%d" % index)
        rel = entry.get("path")
        existed = entry.get("existed")
        content_b64 = entry.get("old_content_b64")
        if not isinstance(rel, str) or not rel:
            return fail_state(
                "no usable recovery state: entry #%d has no path" % index)
        if existed:
            if not isinstance(content_b64, str):
                return fail_state(
                    "no usable recovery state: entry %r lacks preimage content"
                    % rel)
            try:
                old_bytes = base64.b64decode(
                    content_b64.encode("ascii"), validate=True)
            except (ValueError, UnicodeEncodeError) as exc:
                return fail_state(
                    "no usable recovery state: entry %r preimage is corrupt (%s)"
                    % (rel, exc))
        else:
            old_bytes = None
        preimages.append((rel, bool(existed), old_bytes))

    errors = []
    for rel, existed, old_bytes in preimages:
        try:
            target = _resolve(workspace, rel)
            if existed:
                parent = target.parent
                if not parent.exists():
                    os.makedirs(parent, exist_ok=True)
                _write_bytes(target, old_bytes)  # exact preimage bytes
            elif target.exists():
                os.unlink(target)                # remove a file apply() created
        except (OSError, ValueError) as exc:
            errors.append("%s: %s" % (rel, exc))
    if errors:
        return {"ok": False,
                "reason": "failed to restore some files: " + "; ".join(errors),
                "restored": []}

    # The recovery state has been consumed: remove it (and any stray temp) so
    # the tree is exactly what it was before the last successful apply().
    try:
        os.unlink(recovery)
        tmp = workspace / RECOVERY_TMP_NAME
        if tmp.exists():
            os.unlink(tmp)
    except OSError as exc:
        return fail_state(
            "files restored but the recovery state could not be removed (%s)"
            % (exc,))

    return {"ok": True, "restored": [rel for rel, _, _ in preimages]}
