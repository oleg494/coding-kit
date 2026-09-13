"""Managed-file updater: preview / apply / restore of byte-exact file updates.

API (module level, pure standard library)::

    preview(workspace, updates)                       -> list[dict]
    apply(workspace, updates, *, fail_recovery=False) -> dict
    restore(workspace)                                -> dict

Guarantees implemented here:

* Ownership -- ``apply`` only creates/modifies/deletes the files named in
  ``updates`` plus its own recovery-state file ``.updater_recovery.json`` at
  the workspace root (and the temporary file used to atomically rename it
  into place).  Every other file is foreign and is never opened for writing.
* Binary exactness -- every read/write uses binary mode; preimages are kept
  as raw ``bytes`` in memory and base64-encoded inside the JSON recovery
  state, so content round-trips with no newline translation and no text
  encoding/decoding of file content.
* Ordering -- ``apply`` mutates the owned files first and persists the
  recovery state as its FINAL step.  If that final step fails
  (``fail_recovery=True`` simulates the failure), every mutation is undone
  from the in-memory preimage, the temporary state file is removed, and a
  failure result is returned -- success is never reported after a failed
  persistence.  A recovery state written by an *earlier* successful apply is
  pre-existing workspace data and is left exactly as it was (the failed
  attempt itself leaves no recovery state behind).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import posixpath
from pathlib import Path, PurePath

__all__ = ["preview", "apply", "restore"]

#: Own recovery-state file at the workspace root.
RECOVERY_FILE = ".updater_recovery.json"
#: Atomic-rename temporary for the recovery state (same directory => same fs).
RECOVERY_TMP = ".updater_recovery.json.tmp"
#: On-disk layout version of the recovery state.
STATE_VERSION = 1


class _UpdaterError(Exception):
    """Internal control-flow error carrying a user-facing reason string."""


class _SimulatedFailure(_UpdaterError):
    """Simulates the failure of the final recovery-state persistence step."""


# ---------------------------------------------------------------------------
# path + byte helpers
# ---------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_rel(key: object) -> str:
    """Normalise an update key to a clean relative POSIX path string.

    Rejects empty, absolute, or workspace-escaping paths so the updater can
    never touch files outside the workspace.
    """
    raw = key.as_posix() if isinstance(key, PurePath) else str(key)
    if not raw:
        raise _UpdaterError("update path must be a non-empty relative POSIX path")
    norm = posixpath.normpath(raw)
    if (
        posixpath.isabs(raw)
        or posixpath.isabs(norm)
        or norm in (".", "..")
        or norm.startswith("../")
    ):
        raise _UpdaterError(f"update path escapes the workspace: {raw!r}")
    return norm


def _target_path(ws: Path, rel: str) -> Path:
    return ws.joinpath(*rel.split("/"))


def _read_bytes(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _write_bytes(path: Path, data: bytes) -> None:
    parent = path.parent
    if not parent.exists():
        # Defensive only: the contract guarantees parent directories exist.
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def _remove_quietly(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _failure(reason: str, *, rolled_back: bool) -> dict:
    return {
        "ok": False,
        "reason": reason or "unknown failure",
        "rolled_back": rolled_back,
        "applied": [],
    }


# ---------------------------------------------------------------------------
# planning (read-only)
# ---------------------------------------------------------------------------

def _plan(ws: Path, updates, strict: bool = True):
    """Compute the change plan and the full preimage snapshot.

    Returns ``(plan, snapshot)`` where *plan* contains only the updates that
    would really change something (no-op writes and deletes of missing files
    are skipped) and *snapshot* contains ``(rel_path, preimage_bytes_or_None)``
    for **every** owned target (``None`` means the file does not exist now).
    """
    if not hasattr(updates, "items"):
        raise _UpdaterError("updates must be a mapping of relative path -> bytes | None")

    owned = {}
    for key, payload in updates.items():
        rel = _normalize_rel(key)
        if payload is None:
            data = None
        elif isinstance(payload, (bytes, bytearray, memoryview)):
            data = bytes(payload)
        else:
            raise _UpdaterError(
                f"update for {key!r} must be bytes or None, got {type(payload).__name__}"
            )
        owned[rel] = data

    plan = []
    snapshot = []
    for rel in sorted(owned):
        path = _target_path(ws, rel)
        if os.path.lexists(path) and not os.path.isfile(path):
            if strict:
                raise _UpdaterError(f"update target is not a regular file: {rel}")
            old = None
        else:
            try:
                old = _read_bytes(path)
            except FileNotFoundError:
                old = None
        snapshot.append((rel, old))

        payload = owned[rel]
        if payload is None:
            if old is not None:  # deleting a missing file is a no-op
                plan.append({"path": rel, "action": "delete", "old": old, "new": None})
        elif old != payload:  # identical bytes => no-op, must not appear
            plan.append({"path": rel, "action": "write", "old": old, "new": payload})
    return plan, snapshot


# ---------------------------------------------------------------------------
# recovery state (encode / persist / decode)
# ---------------------------------------------------------------------------

def _encode_state(applied, snapshot) -> bytes:
    entries = [
        {
            "path": rel,
            "existed": old is not None,
            "sha256": None if old is None else _sha256_hex(old),
            "preimage_b64": None if old is None else base64.b64encode(old).decode("ascii"),
        }
        for rel, old in snapshot
    ]
    state = {"version": STATE_VERSION, "applied": list(applied), "entries": entries}
    return json.dumps(state, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _persist_state(tmp_path: Path, final_path: Path, blob: bytes, *, simulate_failure: bool) -> None:
    """Atomically publish the recovery state (write temp, fsync, rename)."""
    _remove_quietly(tmp_path)  # clear any stale temporary from an earlier crashed run
    with open(tmp_path, "wb") as fh:
        fh.write(blob)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    if simulate_failure:
        # The contract-mandated simulated failure of the FINAL step: the state
        # was never published (no rename happened).
        raise _SimulatedFailure("simulated failure while persisting the recovery state")
    os.replace(tmp_path, final_path)  # atomic publish


def _decode_state(state) -> tuple:
    if not isinstance(state, dict):
        raise _UpdaterError("recovery state is malformed (not a JSON object)")
    if state.get("version") != STATE_VERSION:
        raise _UpdaterError(f"unsupported recovery-state version: {state.get('version')!r}")
    applied = state.get("applied")
    if not isinstance(applied, list) or not all(isinstance(p, str) for p in applied):
        raise _UpdaterError("recovery state is malformed ('applied' is not a list of paths)")
    raw_entries = state.get("entries")
    if not isinstance(raw_entries, list):
        raise _UpdaterError("recovery state is malformed ('entries' is not a list)")

    entries = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise _UpdaterError("recovery state is malformed (entry is not an object)")
        rel = raw.get("path")
        if not isinstance(rel, str):
            raise _UpdaterError("recovery state is malformed (entry has no path)")
        rel = _normalize_rel(rel)  # refuse to write outside the workspace
        existed = raw.get("existed")
        if not isinstance(existed, bool):
            raise _UpdaterError(f"recovery state is malformed (bad 'existed' for {rel!r})")
        if existed:
            b64 = raw.get("preimage_b64")
            if not isinstance(b64, str):
                raise _UpdaterError(f"recovery state is malformed (no preimage for {rel!r})")
            try:
                data = base64.b64decode(b64.encode("ascii"), validate=True)
            except (ValueError, UnicodeEncodeError) as exc:
                raise _UpdaterError(
                    f"recovery state for {rel!r} has an invalid base64 preimage"
                ) from exc
            expected = raw.get("sha256")
            if isinstance(expected, str) and _sha256_hex(data) != expected:
                raise _UpdaterError(f"recovery state for {rel!r} failed its integrity check")
            entries.append({"path": rel, "existed": True, "bytes": data})
        else:
            entries.append({"path": rel, "existed": False, "bytes": None})
    return applied, entries


def _rollback(ws: Path, plan) -> bool:
    """Undo every mutation in *plan* from the in-memory preimage.

    Returns True when the preimage was fully restored.
    """
    undone = True
    for item in reversed(plan):
        path = _target_path(ws, item["path"])
        old = item["old"]
        try:
            if old is None:
                try:
                    os.remove(path)  # we created it -> remove it
                except FileNotFoundError:
                    pass
            else:
                _write_bytes(path, old)  # modified/deleted -> exact preimage bytes
        except OSError:
            undone = False
    return undone


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def preview(workspace, updates) -> list:
    """Read-only plan of what ``apply`` would change (no-op updates omitted)."""
    ws = Path(workspace)
    plan, _snapshot = _plan(ws, updates)
    return [
        {
            "path": item["path"],
            "action": item["action"],
            "old_sha256": None if item["old"] is None else _sha256_hex(item["old"]),
            "new_sha256": None if item["new"] is None else _sha256_hex(item["new"]),
        }
        for item in plan
    ]


def apply(workspace, updates, *, fail_recovery: bool = False) -> dict:
    """Mutate the owned files, then persist the recovery state as the final step."""
    ws = Path(workspace)

    # 1) Plan (read-only; nothing has been mutated yet).
    try:
        plan, snapshot = _plan(ws, updates)
    except _UpdaterError as exc:
        return _failure(str(exc), rolled_back=True)
    except OSError as exc:
        return _failure(f"failed to inspect the workspace: {exc}", rolled_back=True)

    applied = [item["path"] for item in plan]
    state_path = ws / RECOVERY_FILE
    tmp_path = ws / RECOVERY_TMP

    # 2) Mutate owned files exactly as planned, then 3) persist state (FINAL).
    try:
        for item in plan:
            path = _target_path(ws, item["path"])
            if item["action"] == "write":
                _write_bytes(path, item["new"])
            else:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass  # vanished between plan and mutate: target state reached
        _persist_state(
            tmp_path, state_path, _encode_state(applied, snapshot),
            simulate_failure=fail_recovery,
        )
    except Exception as exc:  # every failure must be handled, never report success
        reason = str(exc) if isinstance(exc, _UpdaterError) else f"apply failed: {exc}"
        if not reason:
            reason = f"apply failed: {exc!r}"
        undone = _rollback(ws, plan)
        _remove_quietly(tmp_path)  # no recovery state (nor temp) left behind by us
        if not undone:
            reason += " (rollback could not fully restore the preimage)"
        return _failure(reason, rolled_back=undone)

    return {"ok": True, "applied": list(applied)}


def restore(workspace) -> dict:
    """Return every owned file of the last successful apply to its preimage."""
    ws = Path(workspace)
    state_path = ws / RECOVERY_FILE

    try:
        raw = _read_bytes(state_path)
    except FileNotFoundError:
        return {
            "ok": False,
            "reason": f"no usable recovery state: {RECOVERY_FILE} does not exist",
            "restored": [],
        }
    except OSError as exc:
        return {"ok": False, "reason": f"cannot read the recovery state: {exc}", "restored": []}

    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return {"ok": False, "reason": f"recovery state is not valid JSON: {exc}", "restored": []}

    try:
        applied, entries = _decode_state(state)
    except _UpdaterError as exc:
        return {"ok": False, "reason": str(exc), "restored": []}

    try:
        for entry in entries:
            path = _target_path(ws, entry["path"])
            if entry["existed"]:
                _write_bytes(path, entry["bytes"])  # recreate/rewrite exact preimage
                if _read_bytes(path) != entry["bytes"]:
                    return {
                        "ok": False,
                        "reason": f"post-restore verification failed for {entry['path']!r}",
                        "restored": [],
                    }
            else:
                try:
                    os.remove(path)  # file was created by apply -> remove it
                except FileNotFoundError:
                    pass
    except OSError as exc:
        return {"ok": False, "reason": f"failed to restore the preimage: {exc}", "restored": []}

    return {"ok": True, "restored": list(applied)}


# ---------------------------------------------------------------------------
# manual smoke check (not executed on import)
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import shutil
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="updater-smoke-"))
    try:
        (root / "app").mkdir()
        (root / "app" / "data.bin").write_bytes(b"\x00\xff\r\nkeep")
        (root / "foreign.txt").write_bytes(b"foreign\r\n")
        (root / "gone.txt").write_bytes(b"bye")

        updates = {"app/data.bin": b"new\r\nbytes", "made.txt": b"hello", "gone.txt": None}
        print(preview(root, updates))

        before = (root / "foreign.txt").read_bytes()
        assert apply(root, updates)["ok"] is True
        assert (root / "app" / "data.bin").read_bytes() == b"new\r\nbytes"
        assert (root / "made.txt").read_bytes() == b"hello"
        assert not (root / "gone.txt").exists()
        assert (root / "foreign.txt").read_bytes() == before

        res = restore(root)
        assert res["ok"] is True, res
        assert (root / "app" / "data.bin").read_bytes() == b"\x00\xff\r\nkeep"
        assert not (root / "made.txt").exists()
        assert (root / "gone.txt").read_bytes() == b"bye"

        bad = apply(root, {"x.txt": b"v"}, fail_recovery=True)
        assert bad["ok"] is False and bad["rolled_back"] is True and bad["applied"] == []
        assert not (root / "x.txt").exists()
        assert not (root / RECOVERY_TMP).exists()
        print("smoke ok")
    finally:
        shutil.rmtree(root, ignore_errors=True)
