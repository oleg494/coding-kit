import json
import sys
from pathlib import Path

sandbox = Path(sys.argv[1])
try:
    data = json.loads((sandbox / "metadata.json").read_text(encoding="utf-8"))
    if data.get("build_number") == 43 and data.get("project") == "core-lib" and data.get("status") == "release":
        files = [p.name for p in sandbox.rglob("*") if p.is_file() and not p.name.startswith(".")]
        if set(files) == {"metadata.json"}:
            sys.exit(0)
except Exception:
    pass
sys.exit(1)
