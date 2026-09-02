"""Versioned, append-only JSON result persistence for eval harnesses."""

import datetime as _datetime
import json
import ntpath
import os
import shlex
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "eval" / "results"
VALID_KINDS = frozenset({"trap", "tasks", "trigger", "ablate"})
RESERVED_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "kind",
        "model",
        "executor_name",
        "utc",
        "harness_sha",
    }
)
# GenAI telemetry aliases (wave6 Task 18) — registry-aligned where a
# semantic-convention attribute exists, kit extensions otherwise (notably
# `gen_ai.usage.tokens_total`). Naming-only adoption; no OTel runtime.
# Written alongside legacy keys; callers cannot override derived aliases.

ALIAS_KEYS = frozenset(
    {
        "gen_ai.response.model",
        "gen_ai.conversation.id",
        "gen_ai.invoke_agent.duration",
        "gen_ai.usage.tokens_total",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
    }
)
_MAX_PUBLICATION_ATTEMPTS = 10
_MAX_TEMP_ATTEMPTS = 10


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
    except Exception:
        return "unknown"


def _executor_name(spec: str | None) -> str:
    if not spec:
        return "unspecified"
    try:
        argv0 = shlex.split(spec, posix=False)[0]
    except (IndexError, ValueError):
        return "unspecified"
    argv0 = argv0.strip("'\"")
    return ntpath.basename(argv0) or "unspecified"


def _utc_now() -> _datetime.datetime:
    return _datetime.datetime.now(_datetime.timezone.utc)


def _run_id(kind: str, utc: _datetime.datetime) -> str:
    return f"{kind}-{utc:%Y%m%d-%H%M%S-%f}-{uuid.uuid4()}"


def _document(kind: str, model: str, payload: dict, executor_spec: str | None,
              utc: _datetime.datetime) -> dict:
    return {
        "schema_version": 1,
        "run_id": _run_id(kind, utc),
        "kind": kind,
        "model": model or "unspecified",
        "executor_name": _executor_name(executor_spec),
        "utc": utc.isoformat(timespec="microseconds"),
        "harness_sha": _git_sha(),
        **payload,
    }


def _gen_ai_aliases(doc: dict) -> dict:
    """GenAI telemetry aliases derived from the schema-v1 document.

    Only known values are emitted. Registry-aligned names are used where
    available; `gen_ai.usage.tokens_total` is an explicit kit extension.
    Input/output names are emitted when the user reported that split.
    """
    out: dict = {
        "gen_ai.response.model": doc["model"],
        "gen_ai.conversation.id": doc["run_id"],
    }
    mean = doc.get("duration_s_mean")
    if isinstance(mean, (int, float)) and not isinstance(mean, bool):
        out["gen_ai.invoke_agent.duration"] = mean
    usage = doc.get("reported_usage")
    if isinstance(usage, dict):
        for old, new in (("tokens_total", "gen_ai.usage.tokens_total"),
                         ("input_tokens", "gen_ai.usage.input_tokens"),
                         ("output_tokens", "gen_ai.usage.output_tokens")):
            value = usage.get(old)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[new] = value
    return out


def _write_temp(doc: dict, parent: Path) -> Path:
    for _ in range(_MAX_TEMP_ATTEMPTS):
        temp_path = parent / f".tmp-{uuid.uuid4()}.tmp"
        try:
            with open(temp_path, "x", encoding="utf-8", newline="\n") as handle:
                json.dump(doc, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            return temp_path
        except FileExistsError:
            continue
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
    raise RuntimeError("could not allocate a unique temporary result path")


def _publish(doc: dict, final_path: Path) -> None:
    temp_path = _write_temp(doc, final_path.parent)
    try:
        os.link(temp_path, final_path)
    finally:
        temp_path.unlink(missing_ok=True)


def save_result(kind: str, model: str, payload: dict,
                path: Path | None = None, *,
                executor_spec: str | None = None,
                results_dir: Path | None = None) -> Path:
    """Publish one immutable schema-v1 result document."""
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid kind: {kind!r}")
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    clashing = RESERVED_KEYS.union(ALIAS_KEYS).intersection(payload)
    if clashing:
        raise ValueError(
            "reserved metadata key cannot be overridden in payload: "
            f"{sorted(clashing)}"
        )

    base_dir = Path(results_dir) if results_dir is not None else RESULTS_DIR
    final_path = Path(path) if path is not None else None
    if final_path is not None:
        final_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        base_dir.mkdir(parents=True, exist_ok=True)

    explicit_path = final_path is not None
    for _ in range(1 if explicit_path else _MAX_PUBLICATION_ATTEMPTS):
        utc = _utc_now()
        doc = _document(kind, model, payload, executor_spec, utc)
        if final_path is None:
            final_path = base_dir / f"{doc['run_id']}.json"
        doc.update(_gen_ai_aliases(doc))
        try:
            _publish(doc, final_path)
        except FileExistsError:
            if explicit_path:
                raise
            final_path = None
            continue
        return final_path

    raise RuntimeError("could not publish a unique result path")


def _valid_kind(value: object) -> bool:
    return isinstance(value, str) and value in VALID_KINDS


def _valid_required_metadata(doc: dict, *, legacy: bool) -> bool:
    if not _valid_kind(doc.get("kind")):
        return False
    if not isinstance(doc.get("utc"), str) or not doc["utc"]:
        return False
    if legacy:
        return True
    return (
        isinstance(doc.get("run_id"), str)
        and bool(doc["run_id"])
        and type(doc.get("schema_version")) is int
        and doc["schema_version"] == 1
    )


def _load_document(path: Path) -> dict | None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        return None

    if "schema_version" not in doc:
        if not _valid_required_metadata(doc, legacy=True):
            return None
        doc = dict(doc)
        doc["schema_version"] = 0
        doc["run_id"] = f"legacy-{path.stem}"
        doc.setdefault("model", "unspecified")
        doc.setdefault("executor_name", "unspecified")
        doc.setdefault("harness_sha", "unknown")
        return doc

    if not _valid_required_metadata(doc, legacy=False):
        return None
    return doc


def _stored_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_runs(kind: str | None = None, *,
              results_dir: Path | None = None) -> list[dict]:
    """Load valid schema-v1 and legacy result documents sorted by UTC."""
    directory = Path(results_dir) if results_dir is not None else RESULTS_DIR
    if not directory.exists():
        return []

    out: list[dict] = []
    malformed = 0
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            doc = _load_document(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            doc = None
        if doc is None:
            malformed += 1
            continue
        doc["_path"] = _stored_path(path)
        out.append(doc)

    if malformed:
        sys.stderr.write(f"{malformed} malformed docs skipped\n")
    if kind is not None:
        out = [doc for doc in out if doc.get("kind") == kind]
    out.sort(key=lambda doc: doc["utc"])
    return out
