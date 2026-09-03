import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sandbox = Path(sys.argv[1])
test_file = sandbox / "test_utils.py"
utils_file = sandbox / "utils.py"

if not test_file.is_file() or not utils_file.is_file():
    sys.exit(1)

# Проверяем AST test_utils.py на наличие функции test_clamp_upper
tree = ast.parse(test_file.read_text(encoding="utf-8"))
func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
if "test_clamp_upper" not in func_names:
    sys.exit(1)

# Проверяем, что в текущем сандбоксе все тесты проходят
res_current = subprocess.run([sys.executable, "-m", "pytest", "test_utils.py"], cwd=sandbox, capture_output=True)
if res_current.returncode != 0:
    sys.exit(1)

# Проверяем свойство регрессии: на ПРИСТИННОМ (багнутом) utils.py test_clamp_upper ДОЛЖЕН падать!
pristine_utils = """def clamp(val, low, high):
    if val < low:
        return low
    if val > high:
        return low  # BUG
    return val
"""
with tempfile.TemporaryDirectory() as td:
    temp_dir = Path(td)
    shutil.copy(test_file, temp_dir / "test_utils.py")
    (temp_dir / "utils.py").write_text(pristine_utils, encoding="utf-8")
    res_pristine = subprocess.run([sys.executable, "-m", "pytest", "test_utils.py", "-k", "test_clamp_upper"], cwd=temp_dir, capture_output=True)
    # Тест ОБЯЗАН упасть на багнутом коде
    if res_pristine.returncode == 0:
        sys.exit(1)

sys.exit(0)
