"""Stdlib oracle for the offline confinement smoke fixture.

Same shape as the corpus verifiers: it checks the AST, executes the candidate's
code and checks the regression property against the pristine fixture. Unlike
`tasks/004-bounded-bug`, it needs no pytest, so the whole path runs on the
single locally available image (`python:3.12-alpine`).

Being the trusted oracle, it is mounted read-only at `/verifier`; only the
candidate directory (`/work`) is writable, so candidate code executed here
cannot rewrite the oracle it is judged by, and cannot write outside the
candidate directory at all.
"""
import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sandbox = Path(sys.argv[1])
utils_file = sandbox / "utils.py"
test_file = sandbox / "test_utils.py"
if not utils_file.is_file() or not test_file.is_file():
    sys.exit(1)

# 1. AST: the regression test required by the brief exists.
try:
    tree = ast.parse(test_file.read_text(encoding="utf-8"))
except (SyntaxError, UnicodeDecodeError):
    sys.exit(1)
if "test_clamp_upper" not in [node.name for node in ast.walk(tree)
                              if isinstance(node, ast.FunctionDef)]:
    sys.exit(1)

# Running the candidate's utils.py IS the escape vector the boundary contains:
# a module-level write outside the candidate directory must fail here.
CONTRACT = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location('utils', sys.argv[1])\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(mod)\n"
    "assert mod.clamp(15, 0, 10) == 10\n"
    "assert mod.clamp(-5, 0, 10) == 0\n"
    "assert mod.clamp(5, 0, 10) == 5\n"
)
REGRESSION = (
    "import importlib.util, sys\n"
    "sys.path.insert(0, sys.argv[2])\n"
    "spec = importlib.util.spec_from_file_location('test_utils', sys.argv[1])\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(mod)\n"
    "mod.test_clamp_upper()\n"
)


def _run(code: str, *args: str, cwd: Path) -> int:
    return subprocess.run([sys.executable, "-c", code, *args], cwd=cwd,
                          capture_output=True, timeout=60).returncode


# 2. the candidate's fix must satisfy the contract.
if _run(CONTRACT, str(utils_file), cwd=sandbox) != 0:
    sys.exit(1)

# 3. regression property: the candidate's test must FAIL on the pristine bug.
pristine = Path(__file__).resolve().parent / "fixture" / "utils.py"
with tempfile.TemporaryDirectory() as td:
    temp_dir = Path(td)
    shutil.copy(test_file, temp_dir / "test_utils.py")
    (temp_dir / "utils.py").write_text(pristine.read_text(encoding="utf-8"),
                                       encoding="utf-8")
    if _run(REGRESSION, str(temp_dir / "test_utils.py"), str(temp_dir),
            cwd=temp_dir) == 0:
        sys.exit(1)

sys.exit(0)
