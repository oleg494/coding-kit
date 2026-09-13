"""Exact owned-path preimages for Hermes adapter recovery (handled failures only)."""
import base64
from pathlib import Path


def capture(path):
    if not path.exists():
        return None
    if path.is_file():
        return {"bytes": base64.b64encode(path.read_bytes()).decode("ascii")}
    return {"tree": {p.relative_to(path).as_posix():
                     base64.b64encode(p.read_bytes()).decode("ascii") if p.is_file() else None
                     for p in sorted(path.rglob("*"))}}


def restore_path(path, image, safe_rmtree):
    if path.is_dir():
        safe_rmtree(path)
    elif path.exists():
        path.unlink()
    if image is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if "bytes" in image:
        path.write_bytes(base64.b64decode(image["bytes"], validate=True))
    else:
        path.mkdir()
        for rel, content in image["tree"].items():
            target = path / rel
            if content is None:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base64.b64decode(content, validate=True))


def validate_image(image):
    if image is None:
        return
    if not isinstance(image, dict) or set(image) not in ({"bytes"}, {"tree"}):
        raise ValueError("invalid recovery image")
    if "bytes" in image:
        base64.b64decode(image["bytes"], validate=True)
        return
    for rel, content in image["tree"].items():
        p = Path(rel)
        if not rel or p.is_absolute() or p.drive or ".." in p.parts or ":" in rel:
            raise ValueError("unsafe recovery image path")
        if content is not None:
            base64.b64decode(content, validate=True)
