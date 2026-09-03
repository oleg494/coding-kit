import sys
from pathlib import Path

sandbox = Path(sys.argv[1])
readme = (sandbox / "README.md").read_text(encoding="utf-8")
if "## Installation Instructions" in readme and "## Instllation Instructions" not in readme:
    # check no other files changed
    files = [p.name for p in sandbox.rglob("*") if p.is_file() and not p.name.startswith(".")]
    if set(files) == {"README.md"}:
        sys.exit(0)
sys.exit(1)
