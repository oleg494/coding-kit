#!/usr/bin/env python3
"""Independent behavioral verifier for the managed-file updater task.

Usage: python verify.py <candidate_dir> [<scenario_root>]

<candidate_dir> is a workspace containing `solution.py` (an alias such as
reference.py or a faulty control works identically). <scenario_root>
(optional, defaults to this script's directory) supplies
fixture/workspace_seed/. Observes only filesystem bytes and return values;
never inspects candidate source text. Emits JSON, exit 0 iff all pass.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile

RECOVERY = ".updater_recovery.json"
CRLF_TEXT = b"line one\r\nline two\r\nold tail\r\n"
BLOB = bytes(range(256)) + b"\r\n\xff\xfe\x00binary tail\r\n"
UPDATES = {
    # rewrite CRLF text with different content (not byte-identical)
    "notes/crlf_readme.txt": b"line one\r\nline two\r\nNEW tail\r\n",
    # rewrite binary blob
    "notes/blob.bin": bytes(range(128)) + b"\xff\x00NEW\r\n",
    # delete an owned existing file
    "notes/legacy_config.txt": None,
    # create a new owned file
    "notes/new_record.txt": b"created\r\nby updater\r\n",
    # no-op: identical bytes, must be excluded from preview/apply
    "notes/noop_guard.txt": CRLF_TEXT,
}


def seed_root(scenario_root):
    d = os.path.join(scenario_root, "fixture", "workspace_seed")
    if not os.path.isdir(d):
        raise SystemExit(f"missing seed directory: {d}")
    return d


def load_candidate(cand_dir):
    path = os.path.join(cand_dir, "solution.py")
    if not os.path.isfile(path):
        raise SystemExit(f"missing candidate: {path}")
    spec = importlib.util.spec_from_file_location("updater_candidate", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["updater_candidate"] = mod
    spec.loader.exec_module(mod)
    return mod


def tree(root):
    """relative posix path -> raw bytes for every regular file."""
    out = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = os.path.join(dirpath, name)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = \
                open(p, "rb").read()
    return out


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Checker:
    def __init__(self):
        self.results = []

    def check(self, name, passed, detail):
        self.results.append({"name": name, "pass": bool(passed),
                             "detail": detail})

    def verdict(self):
        ok = all(r["pass"] for r in self.results)
        print(json.dumps({"ok": ok, "checks": self.results}, indent=2))
        return 0 if ok else 1


def expected_plan(before):
    plan = []
    for rel in sorted(UPDATES):
        new = UPDATES[rel]
        old = before.get(rel)
        if new is None:
            if old is None:
                continue
            plan.append({"path": rel, "action": "delete",
                         "old_sha256": sha(old), "new_sha256": None})
        else:
            if old == new:
                continue
            plan.append({"path": rel, "action": "write",
                         "old_sha256": None if old is None else sha(old),
                         "new_sha256": sha(new)})
    return sorted(plan, key=lambda e: e["path"])


def same_plan(a, b):
    if len(a) != len(b):
        return False
    norm = lambda p: sorted(p, key=lambda e: e["path"])
    a, b = norm(a), norm(b)
    return all(ea["path"] == eb["path"] and ea["action"] == eb["action"]
               and ea["old_sha256"] == eb["old_sha256"]
               and ea["new_sha256"] == eb["new_sha256"]
               for ea, eb in zip(a, b))


def main():
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 2
    cand_dir = os.path.abspath(sys.argv[1])
    scenario_root = os.path.abspath(
        sys.argv[2]) if len(sys.argv) == 3 else os.path.dirname(
        os.path.abspath(__file__))
    seed = seed_root(scenario_root)
    mod = load_candidate(cand_dir)
    c = Checker()

    def fresh():
        tmp = tempfile.mkdtemp(prefix="updater_verify_")
        ws = os.path.join(tmp, "work")
        shutil.copytree(seed, ws)
        return tmp, ws

    # --- 1. preview: read-only and truthful -----------------------------
    tmp, ws = fresh()
    try:
        before = tree(ws)
        got = mod.preview(ws, UPDATES)
        c.check("preview_readonly", tree(ws) == before,
                "workspace bytes unchanged by preview()")
        want = expected_plan(before)
        c.check("preview_truthful", same_plan(got, want),
                f"expected {len(want)} entries matching independent "
                f"recomputation, got {len(got)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- 2. apply: owned mutation only, matches preview ------------------
    tmp, ws = fresh()
    try:
        before = tree(ws)
        plan = mod.preview(ws, UPDATES)
        res = mod.apply(ws, UPDATES)
        after = tree(ws)
        changed = sorted(p for p in before.keys() | after.keys()
                         if before.get(p) != after.get(p) and p != RECOVERY)
        announced = sorted(e["path"] for e in plan)
        c.check("apply_reports_success",
                isinstance(res, dict) and res.get("ok") is True
                and sorted(res.get("applied", [])) == announced,
                f"apply() return: {json.dumps(res, default=str)[:200]}")
        c.check("preview_matches_apply", changed == announced,
                f"bytes-changed={changed} announced={announced}")
        hashes_ok = all(after.get(e["path"]) == UPDATES[e["path"]]
                        for e in plan if e["action"] == "write")
        c.check("apply_new_content_exact", hashes_ok,
                "each write target now holds the exact update bytes")
        c.check("recovery_state_persisted", RECOVERY in after,
                ".updater_recovery.json present after successful apply")
        foreign_ok = all(
            after.get(f) == b for f, b in before.items()
            if f not in UPDATES and f != RECOVERY)
        c.check("foreign_preserved_after_apply", foreign_ok,
                "foreign files byte-identical after apply()")
        # --- 3. restore: exact preimage, CRLF + binary -------------------
        res = mod.restore(ws)
        c.check("restore_reports_success",
                isinstance(res, dict) and res.get("ok") is True,
                f"restore() return: {json.dumps(res, default=str)[:200]}")
        post = tree(ws)
        preimage = {p: b for p, b in before.items() if p != RECOVERY}
        post_clean = {p: b for p, b in post.items() if p != RECOVERY}
        c.check("restore_exact_preimage", post_clean == preimage,
                "every file (incl. CRLF text, binary, deleted, created) "
                "byte-identical to pre-apply snapshot")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- 4. handled failure: undo + honest report ------------------------
    tmp, ws = fresh()
    try:
        before = tree(ws)
        res = mod.apply(ws, UPDATES, fail_recovery=True)
        ok_false = isinstance(res, dict) and res.get("ok") is False
        reason = isinstance(res, dict) and isinstance(
            res.get("reason"), str) and res["reason"].strip() != ""
        rolled = isinstance(res, dict) and res.get("rolled_back") is True
        c.check("handled_failure_rolls_back", ok_false and reason and rolled
                and tree(ws) == before and RECOVERY not in tree(ws),
                f"apply(fail_recovery=True) return: "
                f"{json.dumps(res, default=str)[:200]}; tree equals "
                f"pre-call snapshot and no recovery state left")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- 5. restore without state: honest failure ------------------------
    tmp, ws = fresh()
    try:
        before = tree(ws)
        res = mod.restore(ws)
        ok_false = isinstance(res, dict) and res.get("ok") is False
        reason = isinstance(res, dict) and isinstance(
            res.get("reason"), str) and res["reason"].strip() != ""
        c.check("restore_without_state_fails",
                ok_false and reason and tree(ws) == before,
                f"restore() on pristine workspace return: "
                f"{json.dumps(res, default=str)[:200]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return c.verdict()


if __name__ == "__main__":
    sys.exit(main())
