import ast
import inspect
import subprocess
import sys
from pathlib import Path

sandbox = Path(sys.argv[1])
for f in ["transport.py", "client.py", "api.py", "test_client.py"]:
    if not (sandbox / f).is_file():
        sys.exit(1)

# 1. Проверяем AST test_client.py: должен быть тест, проверяющий timeout
test_code = (sandbox / "test_client.py").read_text(encoding="utf-8")
if "timeout" not in test_code:
    sys.exit(1)

# 2. Pytest в сандбоксе должен быть полностью зеленый
res = subprocess.run([sys.executable, "-m", "pytest", "test_client.py"], cwd=sandbox, capture_output=True)
if res.returncode != 0:
    sys.exit(1)

# 3. Инспекция сигнатур и проброса значений
sys.path.insert(0, str(sandbox))
try:
    import transport
    import client
    import api
    
    # Сигнатуры должны поддерживать timeout
    sig_trans = inspect.signature(transport.send)
    if "timeout" not in sig_trans.parameters:
        sys.exit(1)
        
    sig_client = inspect.signature(client.send_payload)
    if "timeout" not in sig_client.parameters:
        sys.exit(1)
        
    def test_forwarding():
        received_timeout = []
        orig_send = transport.send
        def spy_send(p, timeout=None):
            received_timeout.append(timeout)
            return orig_send(p, timeout=timeout)
        
        transport.send = spy_send
        client.send_payload("data2", timeout=42.5)
        return received_timeout == [42.5]
    
    if not test_forwarding():
        sys.exit(1)
        
    sys.exit(0)
except Exception:
    sys.exit(1)
