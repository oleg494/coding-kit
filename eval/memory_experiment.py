"""Offline memory experiment preparation and outcome grading (no model execution).

prepare OUTPUT exports session A prompts. Supply A outputs as notes.json:
{case_id: {"note": "..."}}. Then: prepare OUTPUT --notes notes.json
exports B inputs for repository_only, memory, and inline arms.
Use separate clean sessions per input, with no shared history or host memory.
The memory arm receives an isolated native memory root and search command.
The inline arm controls for information availability versus memory retrieval.
Save B outputs in answers.json: {case_id: {arm: {action, evidence, retrieved}}}.
Optionally grade with --verify-retrieval PREPARED: re-run the isolated memory
search for every memory arm against the prepared store and cross-check each
retrieval claim against that real tool output. This is deterministic store
verification of retrieval plumbing (CLI, database, query); it does not call a
model, observe model behavior, or produce answers. Verification is null when
a prepared memory root is missing or its search fails.
Run: grade answers.json. Missing attempts remain missing, never counted as failure.
This package does not provide OS isolation or call models; use an independently
validated sandbox before a model trial. Never mount this evaluator or case oracle.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CASES = Path(__file__).with_name("memory_cases.json")
ARMS = ("repository_only", "memory", "inline")


def load_cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def memory_command(root, args, text=None):
    """Invoke the real memory CLI in a separate process with isolated storage."""
    root = root.resolve()
    env = {key: value for key, value in os.environ.items()
           if key in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update({key: str(root) for key in
                ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP",
                 "TMP", "MEMORY_ROOT")})
    env.update(MEMORY_ROOT_RESEARCH_DB=str(root / "research.db"),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, str(root / "db-tools/findings.py"), *args],
        input=text, text=True, encoding="utf-8", capture_output=True,
        env=env, cwd=root, timeout=30, check=True)
    return result.stdout


def prepare_memory(root, case, note):
    """Copy only the native memory engine; no host database or evaluator oracle."""
    source = Path(__file__).resolve().parents[1] / "memory"
    root.mkdir()
    for directory in ("db-tools", "scripts"):
        shutil.copytree(source / directory, root / directory,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "VERSION").write_text("offline-experiment\n", encoding="utf-8")
    memory_command(root, ["add", case["id"], "--stdin", "--source",
                          case["decision"]["id"], "--project", "portable"], note)


def prepare(output, notes):
    data = load_cases()
    # Refuse reuse: prevents residual notes/answers contaminating another run.
    output.mkdir(parents=True, exist_ok=False)
    for case in data["cases"]:
        root = output / case["id"]
        root.mkdir()
        a = {"prompt": data["session_a"], "decision": case["decision"]}
        (root / "session_a.json").write_text(json.dumps(a, indent=2), encoding="utf-8")
        if notes is None:
            continue
        note = notes[case["id"]]["note"]
        if not isinstance(note, str) or not note.strip():
            raise ValueError(f"Missing nonempty session A note: {case['id']}")
        for arm in ARMS:
            dest = root / arm
            dest.mkdir()
            b = {"prompt": data["session_b"], "repository": case["repository"],
                 "actions": case["actions"]}
            entry = {"id": case["decision"]["id"], "note": note}
            if arm == "memory":
                prepare_memory(dest / "memory-root", case, note)
                b["memory_path"] = "memory-root"
                b["memory_search"] = ["python", "memory-root/db-tools/findings.py",
                                      "search", "<query>", "--json"]
                b["memory_environment"] = {
                    "MEMORY_ROOT": str((dest / "memory-root").resolve()),
                    "MEMORY_ROOT_RESEARCH_DB": str((dest / "memory-root/research.db").resolve())}
            elif arm == "inline":
                b["inline_context"] = entry
            (dest / "input.json").write_text(json.dumps(b, indent=2), encoding="utf-8")
    return {"status": "prepared", "session": "A" if notes is None else "B",
            "path": str(output), "model_runs": 0}


def _store_sources(root, case):
    """Decision ids present in real search output from the prepared store.

    Searches the indexed topic (the case id); --source is a LIKE filter,
    not the indexed text, so it cannot serve as the query itself.
    """
    output = memory_command(root, ["search", "--json", case["id"]], "")
    sources = set()
    for finding in json.loads(output):
        source = finding.get("source")
        if isinstance(source, str):
            sources.add(source)
    return sources


def verify_retrieval(prepared):
    """Re-run each prepared memory arm's search in its own subprocess.

    Returns {case_id: set(decision ids present in real tool output)} and
    covers only the memory arm. Cases without a usable prepared store are
    simply absent (scored as null, never as a fabricated failure). This
    exercises the retrieval plumbing only — no model, no answers.
    """
    stores = {}
    for case in load_cases()["cases"]:
        root = prepared / case["id"] / "memory" / "memory-root"
        try:
            stores[case["id"]] = _store_sources(root, case)
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
    return stores


def grade(answers, stores=None):
    rows = []
    for case in load_cases()["cases"]:
        for arm in ARMS:
            answer = answers.get(case["id"], {}).get(arm)
            row = {"case": case["id"], "arm": arm}
            if answer is None:
                row["status"] = "missing"
            elif not isinstance(answer, dict) or not isinstance(answer.get("action"), str) or not isinstance(answer.get("evidence"), list) or not isinstance(answer.get("retrieved"), list):
                row["status"] = "invalid"
            else:
                row.update(status="observed", correct=answer["action"] == case["expected"],
                           provenance=case["required_source"] in answer["evidence"],
                           retrieval_claimed=case["decision"]["id"] in answer["retrieved"])
                if arm == "memory":
                    # Deterministic store verification, when a prepared
                    # memory root was supplied: null (absent) without one;
                    # true only when a retrieval claim is actually matched
                    # by that decision id in real search output from the
                    # case's store. Unclaimed answers never score true.
                    stored = stores.get(case["id"]) if stores is not None else None
                    in_store = (case["decision"]["id"] in stored
                                if isinstance(stored, (set, frozenset)) else None)
                    row["retrieval_verified"] = (
                        None if in_store is None
                        else bool(in_store and row["retrieval_claimed"]))
            rows.append(row)
    return {"rows": rows, "caution": "Retrieval claims are cross-checked only when store verification is enabled; without it they remain self-reported. Store verification checks retrieval plumbing, not model behavior: it re-runs the isolated search against the prepared store, calls no model, and grades no answers. Correctness is action-based, not a wording or citation match. No causal claim from an unreplicated pilot."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("prepare")
    p.add_argument("output", type=Path)
    p.add_argument("--notes", type=Path)
    g = subs.add_parser("grade")
    g.add_argument("answers", type=Path)
    g.add_argument("--verify-retrieval", dest="verify", type=Path, default=None,
                   help="re-run the isolated memory search per prepared memory "
                        "root and cross-check retrieval claims (deterministic "
                        "store verification; no model)")
    args = parser.parse_args()
    if args.command == "prepare":
        notes = json.loads(args.notes.read_text(encoding="utf-8")) if args.notes else None
        result = prepare(args.output, notes)
    else:
        answers = json.loads(args.answers.read_text(encoding="utf-8"))
        result = grade(answers, verify_retrieval(args.verify) if args.verify
                       else None)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
