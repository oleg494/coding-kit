#!/usr/bin/env python3
"""scripts/tools/handoff.py — portable evidence-bound session handoff.

capture(workspace, brief_path, output) -> dict
    Validates a task brief, snapshots sha256 of the union of the brief's
    observation paths, and writes a version-1 manifest atomically
    (refusing to overwrite an existing output).

resume(workspace, handoff_path) -> dict
    Read-only. Strictly revalidates the manifest under the same canonical
    workspace, compares the snapshot against live files, and returns a
    drift report (observations unchanged|stale, files
    unchanged|modified|missing|unsafe).

render(report) -> str
    Human-readable rendering of a resume report: complete task context
    with stale evidence marked prominently.

Guarantees (.autonomous/continuity-contract.json):
- explicit allow-list only: no workspace scan, no file contents stored;
- static path checks reject symlinks/junctions on every observed component
  (lstat, plus fstat identity on the opened handle). This is not a sandbox:
  a hostile concurrent writer can still race a parent swap between checks.
  Drift reports, not security isolation, are the contract;
- brief and manifest are capped at 1 MiB and strictly schema-checked
  (version type, sha256 shape, missing and extra fields);
- 'unchanged' means byte-identical only — never truth, correctness,
  passing tests, or authorization;
- nothing from a handoff is ever executed; no commands exist in the format.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

VERSION = 1
MAX_BYTES = 1 << 20            # brief and manifest size cap (1 MiB)
CHUNK = 1 << 20                # streaming hash chunk (memory-bounded)
RESERVED_DIRS = frozenset({".git", ".autonomous"})
_MANIFEST_KEYS = frozenset({"version", "workspace", "brief", "files"})
_BRIEF_KEYS = frozenset(
    {"goal", "acceptance", "constraints", "pending", "observations"})
_FORBIDDEN_CHARS = (frozenset('<>:"|?*\\')
                    | {chr(i) for i in range(0x20)} | {"\x7f"})
_HEX = frozenset("0123456789abcdef")


def _fail(msg: str) -> None:
    raise ValueError(msg)


# --- workspace and path validation --------------------------------------

def _canonical_workspace(workspace: Path) -> Path:
    """Resolve to an absolute existing directory."""
    ws = Path(workspace).resolve()
    if not ws.is_dir():
        _fail(f"workspace is not an existing directory: {ws}")
    return ws


def _validate_rel_path(p) -> str:
    """Require the canonical workspace-relative form: POSIX separators,
    no traversal/dots, no drive/UNC/NTFS-stream syntax, no reserved
    components. Rejects before any filesystem access."""
    if not isinstance(p, str) or not p:
        _fail("observation path must be a nonempty string")
    if "\\" in p:
        _fail(f"noncanonical path (use '/' separators): {p!r}")
    if p.startswith("/"):
        _fail(f"path must be workspace-relative, not absolute: {p!r}")
    for ch in p:
        if ch in _FORBIDDEN_CHARS:
            _fail(f"forbidden character {ch!r} in path "
                  f"(drives, UNC and NTFS streams are rejected): {p!r}")
    for part in p.split("/"):
        if part == "":
            _fail(f"empty path component: {p!r}")
        if part in (".", ".."):
            _fail(f"path traversal component is rejected: {p!r}")
        if part.lower() in RESERVED_DIRS:
            _fail(f"reserved path component is rejected: {p!r}")
        if part.endswith(".") or part.endswith(" "):
            _fail(f"Windows-invalid path component: {p!r}")
    return p


# --- brief validation ----------------------------------------------------

def _require_str_list(value, field: str, nonempty_items: bool) -> list:
    if not isinstance(value, list):
        _fail(f"brief.{field} must be a list")
    for item in value:
        if not isinstance(item, str):
            _fail(f"brief.{field} entries must be strings")
        if nonempty_items and not item.strip():
            _fail(f"brief.{field} entries must be nonempty strings")
    return list(value)


def _validate_brief(brief) -> dict:
    if not isinstance(brief, dict):
        _fail("brief must be a JSON object")
    keys = set(brief)
    if keys != set(_BRIEF_KEYS):
        missing = sorted(set(_BRIEF_KEYS) - keys)
        extra = sorted(keys - set(_BRIEF_KEYS))
        _fail(f"brief keys invalid (missing: {missing}, unexpected: {extra})")
    if not isinstance(brief["goal"], str) or not brief["goal"].strip():
        _fail("brief.goal must be a nonempty string")
    _require_str_list(brief["acceptance"], "acceptance", True)
    _require_str_list(brief["constraints"], "constraints", False)
    _require_str_list(brief["pending"], "pending", True)
    observations = brief["observations"]
    if not isinstance(observations, list):
        _fail("brief.observations must be a list")
    for entry in observations:
        if not isinstance(entry, dict) or set(entry) != {"claim", "paths"}:
            _fail("each observation must have exactly 'claim' and 'paths'")
        if not isinstance(entry["claim"], str) or not entry["claim"].strip():
            _fail("observation.claim must be a nonempty string")
        paths = entry["paths"]
        if not isinstance(paths, list) or not paths:
            _fail("observation.paths must be a nonempty list")
        seen: set[str] = set()
        for p in paths:
            _validate_rel_path(p)
            key = os.path.normcase(p)
            if key in seen:
                _fail(f"duplicate path within one observation: {p!r}")
            seen.add(key)
    return brief


def _union_paths(brief: dict) -> list[str]:
    """Ordered union of observation paths. The same file may back
    multiple claims (one entry each in the files map); duplicates are
    case-insensitive on Windows."""
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in brief["observations"]:
        for p in entry["paths"]:
            key = os.path.normcase(p)
            if key not in seen:
                seen.add(key)
                ordered.append(p)
    return ordered


# --- serialized data load and manifest validation ------------------------

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _load_json(path: Path, what: str) -> dict:
    try:
        size = path.stat().st_size
    except OSError as e:
        raise ValueError(f"{what} is not readable: {path}") from e
    if size > MAX_BYTES:
        _fail(f"{what} exceeds the 1 MiB limit: {path}")
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            _fail(f"{what} exceeds the 1 MiB limit: {path}")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, OSError, RecursionError) as e:
        raise ValueError(f"{what} is not valid UTF-8 JSON: {path}") from e
    if not isinstance(data, dict):
        _fail(f"{what} must be a JSON object: {path}")
    return data


def _validate_manifest(manifest, ws: Path) -> None:
    if not isinstance(manifest, dict):
        _fail("handoff must be a JSON object")
    keys = set(manifest)
    if keys != set(_MANIFEST_KEYS):
        missing = sorted(set(_MANIFEST_KEYS) - keys)
        extra = sorted(keys - set(_MANIFEST_KEYS))
        _fail(f"handoff keys invalid (missing: {missing}, unexpected: {extra})")
    version = manifest["version"]
    if type(version) is not int or version != VERSION:
        _fail(f"unsupported handoff version: {version!r}")
    ws_field = manifest["workspace"]
    if not isinstance(ws_field, str) or not ws_field:
        _fail("handoff.workspace must be a nonempty string")
    if not Path(ws_field).is_absolute() or str(Path(ws_field).resolve()) != ws_field:
        _fail("handoff.workspace must be an absolute canonical path")
    if Path(ws_field).resolve() != ws:
        _fail(f"handoff belongs to a different workspace: {ws_field}")
    _validate_brief(manifest["brief"])
    files = manifest["files"]
    if not isinstance(files, dict):
        _fail("handoff.files must be an object mapping paths to sha256")
    seen: set[str] = set()
    for rel, digest in files.items():
        _validate_rel_path(rel)
        key = os.path.normcase(rel)
        if key in seen:
            _fail(f"duplicate file entry: {rel!r}")
        seen.add(key)
        if (not isinstance(digest, str) or len(digest) != 64
                or not set(digest) <= _HEX):
            _fail(f"invalid sha256 digest for {rel!r}")
    union = {os.path.normcase(p) for p in _union_paths(manifest["brief"])}
    if union != seen:
        _fail("handoff.files does not match the union of observation paths")


# --- live filesystem inspection ------------------------------------------

def _reparse_or_link(st) -> bool:
    """True for symlinks, junctions and any other reparse point."""
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _file_state(ws: Path, rel: str,
                expected: str | None) -> tuple[str, str | None]:
    """Classify one allow-listed path under ws without following any
    symlink/junction parent. With expected=None (capture) returns
    ('ok', sha) or the blocking status; otherwise compares bytes."""
    cur = ws
    for part in rel.split("/")[:-1]:
        cur = cur / part
        try:
            st = cur.lstat()
        except FileNotFoundError:
            return "missing", None
        except OSError:
            return "unsafe", None
        if _reparse_or_link(st) or not stat.S_ISDIR(st.st_mode):
            return "unsafe", None
    final = ws.joinpath(rel)
    try:
        st = final.lstat()
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unsafe", None
    if _reparse_or_link(st) or not stat.S_ISREG(st.st_mode):
        return "unsafe", None
    try:
        fh = open(final, "rb")
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unsafe", None
    with fh:
        fst = os.fstat(fh.fileno())
        if (_reparse_or_link(fst) or not stat.S_ISREG(fst.st_mode)
                or (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino)):
            return "unsafe", None
        digest = hashlib.sha256()
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    sha = digest.hexdigest()
    if expected is None:
        return "ok", sha
    return ("unchanged" if sha == expected else "modified"), sha


# --- capture --------------------------------------------------------------

def _write_manifest(output: Path, manifest: dict) -> None:
    """Atomic write that refuses to overwrite an existing output."""
    payload = (json.dumps(manifest, indent=2, sort_keys=True,
                          ensure_ascii=False) + "\n").encode("utf-8")
    if len(payload) > MAX_BYTES:
        _fail("generated handoff exceeds the 1 MiB limit")
    parent = output.parent
    if not parent.is_dir():
        _fail(f"output directory does not exist: {parent}")
    if os.path.lexists(output):
        raise FileExistsError(
            f"refusing to overwrite existing output: {output}")
    fd, tmp_name = tempfile.mkstemp(
        dir=str(parent), prefix=output.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.link(tmp, output)
        except FileExistsError:
            raise FileExistsError(
                f"refusing to overwrite existing output: {output}") from None
        except OSError as exc:
            # Refuse filesystems without atomic no-clobber publication rather
            # than race a check followed by replace over somebody else's file.
            raise OSError("atomic no-overwrite publication failed") from exc
        os.unlink(tmp)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def capture(workspace: Path, brief_path: Path, output: Path) -> dict:
    """Validate the brief, hash the union of observation paths, and write
    the manifest atomically. Returns the manifest dict."""
    ws = _canonical_workspace(workspace)
    brief = _validate_brief(_load_json(Path(brief_path), "brief"))
    files: dict[str, str] = {}
    for rel in _union_paths(brief):
        state, sha = _file_state(ws, rel, None)
        if state != "ok":
            _fail(f"observation path is not a readable regular file "
                  f"({state}): {rel}")
        files[rel] = sha
    manifest = {"version": VERSION, "workspace": str(ws),
                "brief": brief, "files": files}
    _write_manifest(Path(output), manifest)
    return manifest


# --- resume ---------------------------------------------------------------

def resume(workspace: Path, handoff_path: Path) -> dict:
    """Read-only drift report for a handoff under the same workspace."""
    ws = _canonical_workspace(workspace)
    manifest = _load_json(Path(handoff_path), "handoff")
    _validate_manifest(manifest, ws)
    brief = manifest["brief"]
    files_report = []
    for rel in sorted(manifest["files"]):
        state, _sha = _file_state(ws, rel, manifest["files"][rel])
        files_report.append({"path": rel, "status": state})
    status_by_path = {os.path.normcase(f["path"]): f["status"]
                      for f in files_report}
    observations = []
    for entry in brief["observations"]:
        changed = [p for p in entry["paths"]
                   if status_by_path.get(os.path.normcase(p)) != "unchanged"]
        observations.append({
            "claim": entry["claim"],
            "paths": list(entry["paths"]),
            "status": "stale" if changed else "unchanged",
            "changed_paths": changed,
        })
    return {
        "version": manifest["version"],
        "goal": brief["goal"],
        "acceptance": list(brief["acceptance"]),
        "constraints": list(brief["constraints"]),
        "pending": list(brief["pending"]),
        "observations": observations,
        "files": files_report,
    }


# --- rendering ------------------------------------------------------------

def render(report: dict) -> str:
    """Human-readable report: complete task context, stale evidence
    prominently marked."""
    required = {"version", "goal", "acceptance", "constraints", "pending",
                "observations", "files"}
    missing = required - set(report)
    if missing:
        _fail(f"report is missing keys: {sorted(missing)}")
    file_status = {f["path"]: f["status"] for f in report["files"]}
    lines: list[str] = []
    add = lines.append
    add(f"SESSION HANDOFF REPORT - version {report['version']}")
    add("")
    add("GOAL")
    add(f"  {report['goal']}")
    for title, items in (("ACCEPTANCE", report["acceptance"]),
                         ("CONSTRAINTS", report["constraints"]),
                         ("PENDING", report["pending"])):
        add("")
        add(title)
        if items:
            for item in items:
                add(f"  - {item}")
        else:
            add("  (none)")
    add("")
    add("OBSERVATIONS")
    if report["observations"]:
        for obs in report["observations"]:
            marker = ("[!! STALE]" if obs.get("status") == "stale"
                      else "[unchanged]")
            add(f"  {marker} {obs['claim']}")
            add(f"      evidence: {', '.join(obs['paths'])}")
            if obs.get("changed_paths"):
                details = ", ".join(
                    f"{p} ({file_status.get(p, 'modified')})"
                    for p in obs["changed_paths"])
                add(f"      CHANGED EVIDENCE: {details}")
    else:
        add("  (none)")
    add("")
    counts: dict[str, int] = {}
    for f in report["files"]:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    summary = ", ".join(f"{counts.get(s, 0)} {s}"
                        for s in ("unchanged", "modified", "missing",
                                  "unsafe") if counts.get(s))
    add(f"FILES ({len(report['files'])}"
        f"{': ' + summary if summary else ': none'})")
    for f in sorted(report["files"], key=lambda x: x["path"]):
        add(f"  {f['status']:<9} {f['path']}")
    add("")
    add("NOTE: 'unchanged' means byte-identical to capture time - it is not")
    add("truth, correctness, passing tests, or authorization. Nothing from")
    add("the handoff is ever executed; stale evidence must be re-inspected")
    add("before it is relied on.")
    rendered = "\n".join(lines) + "\n"
    return "".join(ch if ch in "\n\t" or ch.isprintable()
                   else f"\\u{ord(ch):04x}" for ch in rendered)


# --- CLI ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: S110 — optional
                pass
    ap = argparse.ArgumentParser(
        prog="handoff.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    cap = sub.add_parser(
        "capture", help="snapshot a validated brief into a handoff manifest")
    cap.add_argument("--workspace", required=True)
    cap.add_argument("--brief", required=True)
    cap.add_argument("--output", required=True)
    res = sub.add_parser(
        "resume", help="compare a handoff against the live workspace")
    res.add_argument("--workspace", required=True)
    res.add_argument("--handoff", required=True)
    res.add_argument("--json", action="store_true",
                     help="print the machine-readable drift report")
    args = ap.parse_args(argv)
    try:
        if args.command == "capture":
            manifest = capture(args.workspace, args.brief, args.output)
            print(json.dumps({"output": args.output,
                              "version": manifest["version"],
                              "workspace": manifest["workspace"],
                              "files": len(manifest["files"])}, indent=2))
            return 0
        report = resume(args.workspace, args.handoff)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render(report), end="")
        return 1 if any(f["status"] != "unchanged"
                        for f in report["files"]) else 0
    except (ValueError, OSError) as e:
        print(f"handoff: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
