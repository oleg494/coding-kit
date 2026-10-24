"""Optional offline neural retrieval with an atomic, disposable SQLite index.

Source stores stay authoritative. Each query checks selected document hashes and
model identity; stale/missing entries fail explicitly instead of serving old facts.
"""
import argparse
import json
import math
import os
import sqlite3
import struct
import tempfile
from contextlib import closing
from pathlib import Path

from embedding_model import EmbeddingError, LocalEmbedding
from memory_corpus import connect_ro, content_digest, inventory


class VectorError(ValueError):
    pass


def index_location(db_dir, index_path=None):
    return Path(index_path) if index_path else Path(db_dir).parent / "indexes" / "semantic.sqlite"


def build_index(db_dir, research_db, model_dir=None, index_path=None):
    records, failures, attempted = inventory(db_dir, research_db)
    if failures or not attempted:
        raise VectorError("; ".join(failures) or "no searchable stores to index")
    target = index_location(db_dir, index_path).resolve()
    sources = [*Path(db_dir).glob("*.db"), Path(research_db)]
    if any(target == p.resolve() for p in sources):
        raise VectorError("semantic index must not overwrite a source database")
    model = LocalEmbedding(model_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with closing(connect_ro(target)) as con:
            try:
                version = con.execute("SELECT value FROM metadata WHERE name='format'").fetchone()
            except sqlite3.Error as exc:
                raise VectorError("destination is not a semantic index; refusing overwrite") from exc
            if version != ('1',):
                raise VectorError("unsupported semantic index format; refusing overwrite")
    fd, temporary = tempfile.mkstemp(prefix="semantic-", suffix=".sqlite", dir=target.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(temporary)) as con:
            con.executescript("CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT NOT NULL);"
                              "CREATE TABLE documents(key TEXT PRIMARY KEY, digest TEXT NOT NULL);"
                              "CREATE TABLE vectors(key TEXT NOT NULL, chunk INTEGER NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(key,chunk));")
            con.executemany("INSERT INTO metadata VALUES (?,?)", [
                ("format", "1"), ("model", model.identity),
                ("db_dir", str(Path(db_dir).resolve())),
                ("research_db", str(Path(research_db).resolve()))])
            chunks = 0
            for record in records:
                con.execute("INSERT INTO documents VALUES (?,?)", (record["key"], content_digest(record)))
                for chunk, vector in enumerate(model.encode_chunks(record["embedding_text"])):
                    con.execute("INSERT INTO vectors VALUES (?,?,?)", (record["key"], chunk, struct.pack('<384f', *vector)))
                    chunks += 1
            con.commit()
        # Do not publish a mixed snapshot if any source changed during inference.
        current, failures, _ = inventory(db_dir, research_db)
        if failures or {r['key']: content_digest(r) for r in current} != {r['key']: content_digest(r) for r in records}:
            raise VectorError("memory changed while indexing; rerun index build")
        os.replace(temporary, target)
        return {"documents": len(records), "chunks": chunks, "model": model.identity, "index": str(target)}
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


_MODELS = {}  # fingerprint -> loaded session; identity covers weights+tokenizer


def search(query, records, db_dir, research_db, limit=5, model_dir=None, index_path=None):
    path = index_location(db_dir, index_path)
    if not path.is_file():
        raise VectorError("semantic index missing; run vector_search.py build --model-dir PATH")
    try:
        with closing(connect_ro(path)) as con:
            metadata = dict(con.execute("SELECT name,value FROM metadata"))
            identity = LocalEmbedding.identity_for(model_dir)
            if metadata.get("model") != identity:
                raise VectorError("semantic index model/store mismatch; rebuild index")
            model = _MODELS.get(identity) or _MODELS.setdefault(identity, LocalEmbedding(model_dir))
            expected = {"format": "1", "model": model.identity,
                        "db_dir": str(Path(db_dir).resolve()), "research_db": str(Path(research_db).resolve())}
            if any(metadata.get(k) != v for k, v in expected.items()):
                raise VectorError("semantic index model/store mismatch; rebuild index")
            stored = dict(con.execute("SELECT key,digest FROM documents"))
            if any(stored.get(r["key"]) != content_digest(r) for r in records):
                raise VectorError("semantic index stale; rebuild index after memory changes")
            if not records:
                return []
            query_vector = model.encode_query(query)
            scores = []
            for record in records:
                vectors = con.execute("SELECT vector FROM vectors WHERE key=? ORDER BY chunk", (record["key"],)).fetchall()
                if not vectors:
                    raise VectorError("semantic index incomplete; rebuild index")
                best = -1.0
                for (blob,) in vectors:
                    if len(blob) != 384 * 4:
                        raise VectorError("invalid embedding dimensions in index")
                    vector = struct.unpack('<384f', blob)
                    norm = sum(v*v for v in vector)
                    if not all(math.isfinite(v) for v in vector) or abs(norm - 1) > 0.01:
                        raise VectorError("invalid embedding values in index")
                    best = max(best, sum(a*b for a,b in zip(query_vector, vector)))
                scores.append((best, record))
            scores.sort(key=lambda item: (-item[0], item[1]["key"]))
            return scores[:limit]
    except sqlite3.Error as exc:
        raise VectorError(f"cannot read semantic index: {exc}") from exc


def reciprocal_rank_fusion(*rankings, k=60):
    scores = {}
    for ranking in rankings:
        for position, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + position)
    return scores


def prepare_model(target):
    """Download only the pinned public model artifacts; never execute remote code."""
    from embedding_model import MODEL_FILES, MODEL_REPO, MODEL_REVISION
    target = Path(target).expanduser().resolve()
    if any((target / name).exists() for name in MODEL_FILES):
        raise VectorError("model directory already contains managed artifacts; choose another path")
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL_REPO, revision=MODEL_REVISION,
                      allow_patterns=list(MODEL_FILES), local_dir=str(target))
    # Constructor verifies the artifacts and loads them locally; no remote code.
    model = LocalEmbedding(target)
    return {"model_dir": str(target), "fingerprint": model.identity,
            "repo": MODEL_REPO, "revision": MODEL_REVISION}


def main():
    from _compat import chulan_root, fix_encoding
    from findings_db import research_db_path
    fix_encoding()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare-model", "build"])
    parser.add_argument("--model-dir")
    parser.add_argument("--index", dest="index_path")
    args = parser.parse_args()
    try:
        if args.command == "prepare-model":
            if not args.model_dir:
                raise VectorError("--model-dir is required for prepare-model")
            print(json.dumps(prepare_model(args.model_dir)))
        else:
            print(json.dumps(build_index(chulan_root() / 'db', research_db_path(), args.model_dir, args.index_path)))
        return 0
    except (EmbeddingError, VectorError, OSError, sqlite3.Error, ImportError) as exc:
        import sys
        print(f"semantic index error: {exc}", file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
