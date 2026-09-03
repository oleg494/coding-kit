"""eval/rigor/runner.py — A/B benchmark runner for Adaptive Rigor v1."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TASKS_DIR = HERE / "tasks"
ROUTE_FILE = HERE / "route" / "cases.json"

sys.path.insert(0, str(ROOT / "eval"))
from results_io import save_result
from rigor.policy import compute_bundle_hash, extract_policy_bundle_from_git
from rigor.isolation import check_managed_settings_windows, get_claude_version, run_canary_isolation_probe
from task_runner import executor_env, shortcut_patterns

TIER_SCHEMA = {
    "type": "object",
    "properties": {
        "tier": {"type": "string", "enum": ["FAST", "STANDARD", "HIGH_ASSURANCE"]},
        "signals": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["tier"],
    "additionalProperties": False
}

TIER_RANKS = {
    "FAST": 1,
    "STANDARD": 2,
    "HIGH_ASSURANCE": 3
}

def _sandbox_diff(pristine_fixture: Path, sandbox: Path) -> str:
    import difflib
    before, after = {}, {}
    for p in pristine_fixture.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            before[p.relative_to(pristine_fixture).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
    for p in sandbox.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            after[p.relative_to(sandbox).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
    lines = []
    for k in sorted(set(before) | set(after)):
        if before.get(k) != after.get(k):
            lines.extend(difflib.unified_diff(
                before.get(k, "").splitlines(),
                after.get(k, "").splitlines(),
                fromfile=f"a/{k}", tofile=f"b/{k}", lineterm=""
            ))
    return "\n".join(lines)

def evaluate_route(bundle_root: Path, executor_cmd: str | None = None, model: str | None = None) -> list[dict]:
    cases = json.loads(ROUTE_FILE.read_text(encoding="utf-8"))
    results = []
    
    always_loaded = ""
    for fn in ["AGENTS.md", "OPS.md", "SKILL_RUNTIME.md"]:
        fpath = bundle_root / fn
        if fpath.is_file():
            always_loaded += f"=== {fn} ===\n" + fpath.read_text(encoding="utf-8") + "\n\n"
            
    superpowers_file = bundle_root / "skills" / "superpowers" / "SKILL.md"
    if superpowers_file.is_file():
        always_loaded += "=== skills/superpowers/SKILL.md ===\n" + superpowers_file.read_text(encoding="utf-8") + "\n\n"

    for case in cases:
        if not executor_cmd:
            results.append({
                "id": case["id"],
                "expected": case["expected_tier"],
                "minimum": case["minimum_tier"],
                "prompt": case["prompt"],
                "verdict": "DRY_RUN",
                "assigned_tier": None,
            })
            continue

        # Create system prompt file containing always-loaded policy
        with tempfile.TemporaryDirectory(prefix="rigor-route-") as rtd:
            sys_file = Path(rtd) / "system_prompt.txt"
            sys_prompt = (
                "You are an expert development router evaluating task requests according to the policy below.\n\n"
                f"{always_loaded}\n"
                "Classify the user's request into exactly one of: FAST, STANDARD, HIGH_ASSURANCE.\n"
                "Return valid JSON matching the schema."
            )
            sys_file.write_text(sys_prompt, encoding="utf-8")
            
            user_prompt = f"Classify this request according to the policy:\n{case['prompt']}"
            schema_str = json.dumps(TIER_SCHEMA)
            
            cmd_parts = shlex.split(executor_cmd, posix=(sys.platform != "win32"))
            if model:
                cmd_parts.extend(["--model", model])
            cmd_parts.extend([
                "-p", user_prompt,
                "--safe-mode",
                "--no-session-persistence",
                "--tools", "",
                "--system-prompt-file", str(sys_file),
                "--output-format", "json",
                "--json-schema", schema_str
            ])
            if sys.platform == "win32" and not cmd_parts[0].lower().endswith((".cmd", ".bat", ".exe")):
                cmd_parts = ["cmd", "/c", *cmd_parts]

            assigned_tier = None
            for _ in range(4):
                proc = subprocess.run(cmd_parts, capture_output=True, env=executor_env(), timeout=120)
                if proc.returncode != 0 and any(err in proc.stderr.decode("utf-8", "replace").lower() for err in ["500", "503", "rate limit", "timeout"]):
                    time.sleep(2)
                    continue
                try:
                    out_text = proc.stdout.decode("utf-8", "replace").strip()
                    out_data = json.loads(out_text)
                    if isinstance(out_data, dict) and "tier" in out_data:
                        assigned_tier = out_data["tier"]
                    elif isinstance(out_data, str):
                        inner = json.loads(out_data)
                        assigned_tier = inner.get("tier")
                except Exception:
                    pass
                break

            # Scoring: below minimum_tier is HARD FAIL.
            # exact match is required for accuracy / PASS.
            assigned_rank = TIER_RANKS.get(assigned_tier, 0)
            min_rank = TIER_RANKS.get(case["minimum_tier"], 0)
            
            if assigned_rank < min_rank:
                verdict = "FAIL"  # Under-classification
            elif assigned_tier == case["expected_tier"]:
                verdict = "PASS"  # Exact match
            else:
                verdict = "FAIL"

            results.append({
                "id": case["id"],
                "expected": case["expected_tier"],
                "minimum": case["minimum_tier"],
                "assigned_tier": assigned_tier,
                "verdict": verdict,
                "under_classified": (assigned_rank < min_rank),
            })
    return results

def run_microtask(task_name: str, bundle_root: Path, executor_cmd: str | None, model: str | None = None, timeout: int = 300) -> dict:
    tdir = TASKS_DIR / task_name
    fixture = tdir / "fixture"
    verify = tdir / "verify.py"
    brief = (tdir / "TASK.md").read_text(encoding="utf-8")
    
    if not executor_cmd:
        return {
            "name": task_name,
            "verdict": "DRY_RUN",
            "duration_s": 0.0,
            "agent_steps": 0,
            "tool_calls": 0,
            "shortcuts": [],
        }

    with tempfile.TemporaryDirectory(prefix=f"rigor-{task_name}-") as sandbox_tmp:
        sandbox = Path(sandbox_tmp) / "sandbox"
        shutil.copytree(fixture, sandbox)
        
        cmd_parts = shlex.split(executor_cmd, posix=(sys.platform != "win32"))
        if model:
            cmd_parts.extend(["--model", model])
        cmd_parts.extend([
            "-p", brief,
            "--safe-mode",
            "--no-session-persistence",
            "--add-dir", str(bundle_root),
            "--permission-mode", "dontAsk",
            "--tools", "Read,Edit,Bash",
            "--allowedTools", "Read,Edit,Bash",
            "--output-format", "stream-json",
            "--verbose",
        ])
        if sys.platform == "win32" and not cmd_parts[0].lower().endswith((".cmd", ".bat", ".exe")):
            cmd_parts = ["cmd", "/c", *cmd_parts]

        t0 = time.perf_counter()
        agent_steps = 0
        tool_calls = 0
        proc_out = ""
        proc_err = ""
        
        for launch_idx in range(4):
            proc = subprocess.run(
                cmd_parts,
                cwd=sandbox,
                capture_output=True,
                env=executor_env(),
                timeout=timeout
            )
            proc_out = proc.stdout.decode("utf-8", "replace")
            proc_err = proc.stderr.decode("utf-8", "replace")
            
            # Robust parsing of Claude stream-json lines
            steps_in_run, tools_in_run = 0, 0
            for line in proc_out.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    etype = event.get("type")
                    if etype in ("assistant", "message"):
                        msg = event.get("message")
                        content = msg.get("content") if isinstance(msg, dict) else event.get("content")
                        if content:
                            steps_in_run += 1
                    elif etype == "tool_use" or (etype == "tool" and event.get("tool_call_id")):
                        tools_in_run += 1
                except Exception:
                    pass
            
            if steps_in_run == 0 and proc.returncode != 0 and any(err in proc_err.lower() for err in ["rate limit", "500", "503", "network"]):
                time.sleep(3)
                continue
                
            agent_steps = steps_in_run
            tool_calls = tools_in_run
            break
            
        duration = round(time.perf_counter() - t0, 3)
        diff = _sandbox_diff(fixture, sandbox)
        shortcuts = shortcut_patterns(diff)
        
        # Run verifier
        v = subprocess.run([sys.executable, str(verify), str(sandbox)], capture_output=True, timeout=60, env=executor_env())
        verdict = "PASS" if v.returncode == 0 else "FAIL"
        
        return {
            "name": task_name,
            "verdict": verdict,
            "clean_pass": (verdict == "PASS" and not shortcuts),
            "duration_s": duration,
            "agent_steps": agent_steps,
            "tool_calls": tool_calls,
            "shortcuts": shortcuts,
            "verifier_stderr": v.stderr.decode("utf-8", "replace") if v.returncode != 0 else "",
        }

def run_rigor_suite(arm_name: str, ref: str, executor_cmd: str | None = None, model: str = "unspecified", json_out: str | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"rigor-bundle-{arm_name}-") as bundle_tmp:
        bundle_root = Path(bundle_tmp)
        if ref == "worktree":
            for fn in ["AGENTS.md", "OPS.md", "SKILL_RUNTIME.md"]:
                if (ROOT / fn).is_file():
                    shutil.copy(ROOT / fn, bundle_root / fn)
            if (ROOT / "skills").is_dir():
                shutil.copytree(ROOT / "skills", bundle_root / "skills")
            bundle_hash = compute_bundle_hash(bundle_root)
        else:
            bundle_hash = extract_policy_bundle_from_git(ROOT, ref, bundle_root)
            
        isolation_state = check_managed_settings_windows()
        claude_ver = get_claude_version()
        
        canary_res = {"canary_passed": True}
        if executor_cmd:
            canary_res = run_canary_isolation_probe(executor_cmd, model=model)
            
        controlled = isolation_state["controlled"] and canary_res.get("canary_passed", False)
        
        route_results = evaluate_route(bundle_root, executor_cmd, model=model)
        
        task_results = []
        for tpath in sorted(TASKS_DIR.iterdir()):
            if tpath.is_dir() and (tpath / "TASK.md").is_file() and (tpath / "verify.py").is_file():
                res = run_microtask(tpath.name, bundle_root, executor_cmd, model=model)
                task_results.append(res)
                
        hash_after = compute_bundle_hash(bundle_root)
        assert bundle_hash == hash_after, "Policy bundle modified during execution!"
        
        payload = {
            "mode": "live" if executor_cmd else "dry-run",
            "arm": arm_name,
            "policy_ref": ref,
            "policy_bundle_hash": bundle_hash,
            "executor_command": executor_cmd or "none",
            "claude_version": claude_ver,
            "controlled": controlled,
            "isolation_probe": {
                **isolation_state,
                "canary_probe": canary_res,
            },
            "route_results": route_results,
            "task_results": task_results,
        }
        
        if json_out:
            out_path = Path(json_out) if json_out != "auto" else None
            save_result("rigor", model, payload, path=out_path, executor_spec=executor_cmd)
            
        return payload

def main():
    parser = argparse.ArgumentParser(description="Adaptive Rigor v1 A/B Suite")
    parser.add_argument("--arm", required=True, choices=["baseline", "candidate"])
    parser.add_argument("--ref", required=True, help="git commit hash or 'worktree'")
    parser.add_argument("--executor", default=None, help="CLI executor command")
    parser.add_argument("--model", default="unspecified")
    parser.add_argument("--json", default=None, help="Path or 'auto' to save schema-v1 rigor result")
    args = parser.parse_args()
    
    res = run_rigor_suite(args.arm, args.ref, args.executor, args.model, args.json)
    print(f"Rigor suite [{args.arm}] completed successfully. Bundle SHA: {res['policy_bundle_hash']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
