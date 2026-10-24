"""Offline multilingual MiniLM inference; optional dependencies load on demand.

Model: Xenova/paraphrase-multilingual-MiniLM-L12-v2 ONNX conversion of
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (mean pooling).
No downloads, remote code, or inference services are invoked by this module.
"""
import hashlib
import os
from pathlib import Path

MODEL_REPO = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "2c4055b12046f11709e9df2c122e59ffbdc2f900"
MODEL_FILES = ("onnx/model_quantized.onnx", "tokenizer.json")


class EmbeddingError(ValueError):
    """Model or optional runtime unavailable; never substitute lexical hashes."""


def model_path(value=None):
    value = value or os.environ.get("MEMORY_EMBEDDING_MODEL_DIR")
    if not value:
        raise EmbeddingError("set MEMORY_EMBEDDING_MODEL_DIR or --model-dir to the local MiniLM model directory")
    path = Path(value).expanduser().resolve()
    for name in MODEL_FILES:
        if not (path / name).is_file():
            raise EmbeddingError(f"missing local model artifact: {path / name}")
    return path


_FINGERPRINTS = {}


def fingerprint(path):
    """SHA-256 of the pinned artifacts; re-hashed whenever any file's
    size/mtime changes, so replaced weights never reuse an old identity."""
    files = [Path(path) / name for name in MODEL_FILES]
    key = tuple((str(f), f.stat().st_size, f.stat().st_mtime_ns) for f in files)
    if key not in _FINGERPRINTS:
        digest = hashlib.sha256(b"multilingual-minilm-mean-normalized-128-v1")
        for file in files:
            with file.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        _FINGERPRINTS[key] = digest.hexdigest()
    return _FINGERPRINTS[key]


class LocalEmbedding:
    @staticmethod
    def identity_for(directory=None):
        return fingerprint(model_path(directory))

    def __init__(self, directory=None):
        self.directory = model_path(directory)
        self.identity = self.identity_for(self.directory)
        try:
            import numpy as np
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise EmbeddingError("semantic search requires optional numpy, onnxruntime and tokenizers; lexical search does not") from exc
        self.np = np
        try:
            self.tokenizer = Tokenizer.from_file(str(self.directory / "tokenizer.json"))
            # Overflow windows are retained, never silently discard a long note.
            self.tokenizer.enable_truncation(max_length=128, stride=32)
            self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            self.session = ort.InferenceSession(
                str(self.directory / MODEL_FILES[0]), sess_options=options,
                providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise EmbeddingError(f"cannot load local MiniLM model: {exc}") from exc
        self.inputs = {item.name for item in self.session.get_inputs()}

    def encode_chunks(self, text):
        """Normalized vectors for every overlapping token window of a document."""
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError("cannot embed empty text")
        np = self.np
        encoded = self.tokenizer.encode(text)
        windows = [encoded, *encoded.overflowing]
        vectors = []
        for window in windows:
            mask = np.asarray([window.attention_mask], dtype=np.int64)
            inputs = {"input_ids": np.asarray([window.ids], dtype=np.int64),
                      "attention_mask": mask,
                      "token_type_ids": np.asarray([window.type_ids], dtype=np.int64)}
            try:
                output = self.session.run(None, {k: v for k, v in inputs.items() if k in self.inputs})[0]
            except Exception as exc:
                raise EmbeddingError(f"local embedding inference failed: {exc}") from exc
            if output.ndim != 3 or output.shape[-1] != 384:
                raise EmbeddingError("expected MiniLM token embeddings with 384 dimensions")
            vector = (output * mask[..., None]).sum(axis=1)[0] / max(int(mask.sum()), 1)
            norm = float(np.linalg.norm(vector))
            if not np.isfinite(vector).all() or not norm:
                raise EmbeddingError("model returned a non-finite or zero embedding")
            vectors.append((vector / norm).astype(np.float32).tolist())
        return vectors

    def encode_query(self, text):
        vectors = self.encode_chunks(text)
        np = self.np
        vector = np.mean(vectors, axis=0)
        norm = float(np.linalg.norm(vector))
        if not norm or not np.isfinite(vector).all():
            raise EmbeddingError("invalid query embedding")
        return (vector / norm).tolist()
