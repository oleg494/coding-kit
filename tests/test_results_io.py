import concurrent.futures
import json
import threading
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))

import results_io
from results_io import load_runs, save_result


VALID_KINDS = {"trap", "tasks", "trigger", "ablate", "rigor"}


def test_ablate_is_valid_kind(tmp_path):
    assert "ablate" in results_io.VALID_KINDS
    saved = save_result("ablate", "m1", {"experimental": True},
                        results_dir=tmp_path / "r")
    doc = json.loads(saved.read_text(encoding="utf-8"))
    assert doc["kind"] == "ablate"

def test_rigor_is_valid_kind(tmp_path):
    assert "rigor" in results_io.VALID_KINDS
    saved = save_result("rigor", "m1", {"experimental": True},
                        results_dir=tmp_path / "r")
    doc = json.loads(saved.read_text(encoding="utf-8"))
    assert doc["kind"] == "rigor"
RESERVED = {
    "schema_version",
    "run_id",
    "kind",
    "model",
    "executor_name",
    "utc",
    "harness_sha",
}


def _json_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.json")) if directory.exists() else []


def _temp_files(directory: Path) -> list[Path]:
    return sorted(directory.glob(".tmp-*.tmp")) if directory.exists() else []


def test_schema_v1_metadata_model_verbatim_filename_and_compatibility(tmp_path):
    results_dir = tmp_path / "results"
    model = "Provider / model: Δ release"

    generated = save_result(
        "trap", model, {"passed": 18, "total": 18}, results_dir=results_dir
    )
    document = json.loads(generated.read_text(encoding="utf-8"))

    assert generated.name == f"{document['run_id']}.json"
    assert model not in generated.name
    assert document["schema_version"] == 1
    assert document["kind"] == "trap"
    assert document["model"] == model
    assert document["run_id"].startswith("trap-")
    assert document["passed"] == 18

    positional_path = tmp_path / "positional.json"
    assert save_result("tasks", "m2", {"score": 1}, positional_path) == positional_path
    keyword_path = tmp_path / "keyword.json"
    assert (
        save_result("trigger", model="m3", payload={"fired": 2}, path=keyword_path)
        == keyword_path
    )
    assert json.loads(positional_path.read_text(encoding="utf-8"))["score"] == 1
    assert json.loads(keyword_path.read_text(encoding="utf-8"))["model"] == "m3"


def test_reserved_keys_and_invalid_kinds_rejected_before_store_mutation(tmp_path):
    results_dir = tmp_path / "results"

    for key in RESERVED:
        with pytest.raises(ValueError, match="reserved metadata key"):
            save_result("trap", "m1", {key: "override"}, results_dir=results_dir)
    assert not results_dir.exists()

    for kind in ("", "trap/other", r"tasks\other", "trigger:other", ".", ".."):
        with pytest.raises(ValueError, match="invalid kind"):
            save_result(kind, "m1", {}, results_dir=results_dir)
    assert not results_dir.exists()


def test_executor_spec_stores_only_cross_platform_basename_and_no_secret(tmp_path):
    results_dir = tmp_path / "results"
    secret = "distinctive-secret-7f1c"
    executor_spec = rf'"C:\Program Files\Acme\agent.exe" --token {secret}'

    path = save_result(
        "trigger",
        "m1",
        {"fired": 1},
        executor_spec=executor_spec,
        results_dir=results_dir,
    )
    raw = path.read_text(encoding="utf-8")
    document = json.loads(raw)

    assert document["executor_name"] == "agent.exe"
    assert secret not in raw
    assert secret not in str(path)


def test_concurrent_writes_publish_sixteen_complete_unique_documents(tmp_path):
    results_dir = tmp_path / "results"
    barrier = threading.Barrier(16)

    def write_one(index: int) -> Path:
        barrier.wait()
        return save_result(
            "tasks",
            "model-a",
            {"idx": index, "passed": 1, "total": 1},
            results_dir=results_dir,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        paths = list(executor.map(write_one, range(16)))

    assert len(paths) == 16
    assert len(set(paths)) == 16
    assert len(_json_files(results_dir)) == 16
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert len({document["run_id"] for document in documents}) == 16
    assert {document["idx"] for document in documents} == set(range(16))
    assert all(document["kind"] == "tasks" for document in documents)
    assert _temp_files(results_dir) == []


def test_default_link_collision_mints_new_document_without_overwriting_decoy(
    tmp_path, monkeypatch
):
    results_dir = tmp_path / "results"
    real_link = results_io.os.link
    calls: list[tuple[Path, Path]] = []
    decoy = b'{"decoy": true}\n'

    def collide_once(source, destination, *args, **kwargs):
        calls.append((Path(source), Path(destination)))
        if len(calls) == 1:
            Path(destination).write_bytes(decoy)
            raise FileExistsError(destination)
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(results_io.os, "link", collide_once)
    published = save_result(
        "trap", "m1", {"passed": 18}, results_dir=results_dir
    )

    assert len(calls) == 2
    assert calls[0][1] != calls[1][1]
    assert calls[0][1].read_bytes() == decoy
    assert published == calls[1][1]
    document = json.loads(published.read_text(encoding="utf-8"))
    assert published.name == f"{document['run_id']}.json"
    assert document["passed"] == 18
    assert _temp_files(results_dir) == []


def test_explicit_existing_path_raises_without_overwrite_or_shared_store_mutation(
    tmp_path,
):
    results_dir = tmp_path / "shared"
    target = tmp_path / "explicit" / "fixed.json"
    target.parent.mkdir(parents=True)
    original = b'{"original": true}\n'
    target.write_bytes(original)

    with pytest.raises(FileExistsError):
        save_result(
            "trap", "m1", {"passed": 2}, path=target, results_dir=results_dir
        )

    assert target.read_bytes() == original
    assert not results_dir.exists()
    assert _temp_files(target.parent) == []


def test_publication_and_sync_errors_propagate_without_fallback_files(tmp_path, monkeypatch):
    link_dir = tmp_path / "link-error"

    def fail_link(*args, **kwargs):
        raise PermissionError("publication denied")

    monkeypatch.setattr(results_io.os, "link", fail_link)
    with pytest.raises(PermissionError, match="publication denied"):
        save_result("trap", "m1", {}, results_dir=link_dir)
    assert _json_files(link_dir) == []
    assert _temp_files(link_dir) == []

    sync_dir = tmp_path / "sync-error"

    def fail_fsync(*args, **kwargs):
        raise OSError("sync denied")

    monkeypatch.setattr(results_io.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="sync denied"):
        save_result("tasks", "m1", {}, results_dir=sync_dir)
    assert _json_files(sync_dir) == []
    assert _temp_files(sync_dir) == []


def test_loader_skips_malformed_documents_validates_before_filter_and_sorts(
    tmp_path, capsys
):
    results_dir = tmp_path / "runs"
    results_dir.mkdir()
    (results_dir / "bad-encoding.json").write_bytes(b"\xff\xfe")
    (results_dir / "bad-json.json").write_text("{not json", encoding="utf-8")
    (results_dir / "non-dict.json").write_text("[]", encoding="utf-8")
    (results_dir / "v1-missing-run-id.json").write_text(
        json.dumps({"schema_version": 1, "kind": "trap", "utc": "2020"}),
        encoding="utf-8",
    )
    (results_dir / "unsupported-schema.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "future-1",
                "kind": "trap",
                "utc": "2021",
            }
        ),
        encoding="utf-8",
    )
    (results_dir / "legacy-missing-utc.json").write_text(
        json.dumps({"kind": "tasks", "model": "old"}), encoding="utf-8"
    )
    (results_dir / "legacy-valid.json").write_text(
        json.dumps({"kind": "trigger", "utc": "2000-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    (results_dir / ".orphan.json").write_text("{bad", encoding="utf-8")
    (results_dir / ".tmp-orphan.tmp").write_text("orphan", encoding="utf-8")
    generated = save_result("trap", "m1", {"passed": 1}, results_dir=results_dir)

    runs = load_runs(results_dir=results_dir)
    stderr = capsys.readouterr().err

    assert stderr == "6 malformed docs skipped\n"
    assert len(runs) == 2
    assert [run["utc"] for run in runs] == sorted(run["utc"] for run in runs)
    legacy = next(run for run in runs if run["run_id"] == "legacy-legacy-valid")
    assert legacy["schema_version"] == 0
    assert legacy["model"] == "unspecified"
    assert legacy["executor_name"] == "unspecified"
    assert legacy["harness_sha"] == "unknown"
    assert legacy["_path"] == str(results_dir / "legacy-valid.json")
    assert any(run["_path"] == str(generated) for run in runs)

    trigger_runs = load_runs("trigger", results_dir=results_dir)
    assert isinstance(trigger_runs, list)
    assert len(trigger_runs) == 1
    assert trigger_runs[0]["run_id"] == "legacy-legacy-valid"
    assert capsys.readouterr().err == "6 malformed docs skipped\n"


def test_no_arg_load_runs_uses_legacy_results_dir_global(tmp_path, monkeypatch):
    results_dir = tmp_path / "global"
    monkeypatch.setattr(results_io, "RESULTS_DIR", results_dir)

    path = save_result("trap", "m1", {"passed": 1})
    runs = load_runs()

    assert path.parent == results_dir
    assert len(runs) == 1
    assert runs[0]["_path"] == str(path)
