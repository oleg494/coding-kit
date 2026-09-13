"""Faulty control: restore() round-trips preimage bytes as UTF-8 text
with universal-newline translation, corrupting CRLF endings and binary."""
import base64
import hashlib
import json
import os
import tempfile

RECOVERY_NAME = ".updater_recovery.json"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _root(workspace):
    return os.fspath(workspace)


def _snapshots(root, relpaths):
    """Capture exact preimage bytes of owned files that exist."""
    snap = {}
    for rel in relpaths:
        p = os.path.join(root, *rel.split("/"))
        snap[rel] = open(p, "rb").read() if os.path.isfile(p) else None
    return snap


def _encode(snap):
    """base64-wrap raw bytes so the recovery JSON stays portable."""
    return {rel: None if data is None else
            base64.b64encode(data).decode("ascii")
            for rel, data in snap.items()}


def _decode(enc):
    return {rel: None if data is None else base64.b64decode(data)
            for rel, data in enc.items()}


def preview(workspace, updates):
    root = _root(workspace)
    plan = []
    for rel, new_bytes in sorted(updates.items()):
        p = os.path.join(root, *rel.split("/"))
        old = open(p, "rb").read() if os.path.isfile(p) else None
        if new_bytes is None:
            if old is None:
                continue  # deleting a missing file is a no-op
            plan.append({"path": rel, "action": "delete",
                         "old_sha256": _sha256(old), "new_sha256": None})
        else:
            if old == new_bytes:
                continue  # identical content is a no-op
            plan.append({"path": rel, "action": "write",
                         "old_sha256": None if old is None else _sha256(old),
                         "new_sha256": _sha256(new_bytes)})
    return plan


def _write_recovery(root, snap):
    tmp = tempfile.NamedTemporaryFile(
        mode="w", dir=root, prefix=".updater_recovery.", delete=False)
    try:
        json.dump({"preimage": _encode(snap)}, tmp)
        tmp.close()
        os.replace(tmp.name, os.path.join(root, RECOVERY_NAME))
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def apply(workspace, updates, *, fail_recovery=False):
    root = _root(workspace)
    snap = _snapshots(root, updates.keys())
    created, deleted, modified, changed = [], [], [], []

    def undo():
        for rel in created:
            try:
                os.unlink(os.path.join(root, *rel.split("/")))
            except OSError:
                pass
        for rel in deleted:
            p = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(snap[rel])
        for rel in modified:
            with open(os.path.join(root, *rel.split("/")), "wb") as f:
                f.write(snap[rel])
        try:
            os.unlink(os.path.join(root, RECOVERY_NAME))
        except OSError:
            pass

    try:
        for rel, new_bytes in sorted(updates.items()):
            p = os.path.join(root, *rel.split("/"))
            if new_bytes is None:
                if snap[rel] is not None:
                    os.unlink(p)
                    deleted.append(rel)
                    changed.append(rel)
            elif snap[rel] != new_bytes:
                with open(p, "wb") as f:
                    f.write(new_bytes)
                changed.append(rel)
                if snap[rel] is None:
                    created.append(rel)
                else:
                    modified.append(rel)
    except OSError as exc:
        undo()
        return {"ok": False, "reason": f"mutation failed: {exc}",
                "rolled_back": True, "applied": []}

    if fail_recovery:
        undo()
        return {"ok": False,
                "reason": "recovery-state persistence failed (injected)",
                "rolled_back": True, "applied": []}

    try:
        _write_recovery(root, snap)
    except OSError as exc:
        undo()
        return {"ok": False, "reason": f"recovery-state persistence failed: "
                f"{exc}", "rolled_back": True, "applied": []}

    return {"ok": True, "applied": sorted(changed)}


def restore(workspace):
    root = _root(workspace)
    rec_path = os.path.join(root, RECOVERY_NAME)
    try:
        with open(rec_path, "rb") as f:
            snap = _decode(json.load(f)["preimage"])
    except (OSError, ValueError, KeyError):
        return {"ok": False, "reason": "no usable recovery state",
                "restored": []}
    for rel, data in snap.items():
        p = os.path.join(root, *rel.split("/"))
        if data is None:
            try:
                os.unlink(p)
            except OSError:
                pass
        else:
            # FAULT: decode/encode with newline translation instead of
            # writing raw preimage bytes back.
            text = data.decode("utf-8", errors="replace")
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(normalized)
    try:
        os.unlink(rec_path)
    except OSError:
        pass
    return {"ok": True, "restored": sorted(snap)}
