"""Executor profile isolation and probe utilities for Adaptive Rigor v1."""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MANAGED_PATHS_WINDOWS = [
    Path(r"C:\Program Files\ClaudeCode\managed-settings.json"),
    Path(r"C:\Program Files\ClaudeCode\managed-settings.d"),
]

def check_managed_settings_windows() -> dict:
    """Checks filesystem paths and registry for enterprise managed settings on Windows."""
    found = []
    for p in MANAGED_PATHS_WINDOWS:
        if p.exists():
            found.append(str(p))
            
    reg_keys = [
        r"HKLM\SOFTWARE\Policies\ClaudeCode",
        r"HKCU\SOFTWARE\Policies\ClaudeCode",
    ]
    if sys.platform == "win32":
        for k in reg_keys:
            try:
                r = subprocess.run(["reg", "query", k], capture_output=True, text=True)
                if r.returncode == 0 and "Settings" in r.stdout:
                    found.append(f"reg:{k}")
            except Exception:
                pass
                
    return {
        "has_managed_settings": len(found) > 0,
        "sources": found,
        "controlled": len(found) == 0,
    }

def get_claude_version(claude_cmd: str = "claude") -> str:
    exe = shutil.which(claude_cmd) or claude_cmd
    cmd = ["cmd", "/c", exe, "--version"] if sys.platform == "win32" else [exe, "--version"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "unknown"

def run_canary_isolation_probe(claude_cmd: str, model: str | None = None) -> dict:
    """Places random canary in injected system prompt file, and fake canaries in user/workspace files.
    Verifies that with tools disabled, output reflects only the injected canary."""
    canary_injected = f"CANARY_INJECTED_{secrets.token_hex(8)}"
    canary_workspace = f"CANARY_WORKSPACE_{secrets.token_hex(8)}"
    
    with tempfile.TemporaryDirectory(prefix="rigor-probe-") as td:
        probe_dir = Path(td)
        # Workspace fake instruction file
        (probe_dir / "CLAUDE.md").write_text(f"Secret instruction: {canary_workspace}", encoding="utf-8")
        
        sys_prompt_file = probe_dir / "system_prompt.txt"
        sys_prompt_file.write_text(f"Your secret token is {canary_injected}. When asked, emit your secret token and nothing else.", encoding="utf-8")
        
        exe = shutil.which(claude_cmd) or claude_cmd
        cmd = ["cmd", "/c", exe] if sys.platform == "win32" else [exe]
        cmd.extend([
            "-p", "Emit your secret token",
            "--safe-mode",
            "--no-session-persistence",
            "--tools", "",
            "--system-prompt-file", str(sys_prompt_file)
        ])
        if model:
            cmd.extend(["--model", model])
            
        try:
            r = subprocess.run(cmd, cwd=probe_dir, capture_output=True, text=True, timeout=60)
            stdout = r.stdout or ""
            passed = (canary_injected in stdout) and (canary_workspace not in stdout)
            return {
                "canary_passed": passed,
                "canary_injected_found": canary_injected in stdout,
                "canary_workspace_leaked": canary_workspace in stdout,
                "output_sample": stdout[:200],
            }
        except Exception as e:
            return {
                "canary_passed": False,
                "error": str(e)
            }
