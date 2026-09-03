import sys
from pathlib import Path

sandbox = Path(sys.argv[1])
text = (sandbox / "banner.txt").read_text(encoding="utf-8")
if "Author: Bob Smith" in text and "Author: Alice Doe" not in text:
    files = [p.name for p in sandbox.rglob("*") if p.is_file() and not p.name.startswith(".")]
    if set(files) == {"banner.txt"}:
        sys.exit(0)
sys.exit(1)
