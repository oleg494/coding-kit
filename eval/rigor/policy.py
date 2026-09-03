"""Policy bundle generation and verification for Adaptive Rigor v1."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

ALWAYS_LOADED_FILES = ["AGENTS.md", "OPS.md", "SKILL_RUNTIME.md"]

def extract_policy_bundle_from_git(repo_root: Path, ref: str, dest_dir: Path) -> str:
    """Extracts AGENTS.md, OPS.md, SKILL_RUNTIME.md, and skills/ from a git ref into dest_dir.
    Returns SHA-256 digest of the bundle."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract always-loaded files
    for fname in ALWAYS_LOADED_FILES:
        res = subprocess.run(["git", "show", f"{ref}:{fname}"], cwd=repo_root, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            (dest_dir / fname).write_text(res.stdout, encoding="utf-8", newline="\n")
            
    # List skills from ref
    res = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "skills"], cwd=repo_root, capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 0:
        for file_path in res.stdout.splitlines():
            file_path = file_path.strip()
            if not file_path:
                continue
            show_res = subprocess.run(["git", "show", f"{ref}:{file_path}"], cwd=repo_root, capture_output=True)
            if show_res.returncode == 0:
                target_file = dest_dir / file_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_bytes(show_res.stdout)
                
    return compute_bundle_hash(dest_dir)

def compute_bundle_hash(bundle_root: Path) -> str:
    """Computes SHA-256 over sorted relative-path + NUL + file-bytes."""
    records = []
    for p in bundle_root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(bundle_root).as_posix()
            records.append((rel, p.read_bytes()))
    records.sort(key=lambda r: r[0])
    
    hasher = hashlib.sha256()
    for rel, data in records:
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(data)
    return hasher.hexdigest()
