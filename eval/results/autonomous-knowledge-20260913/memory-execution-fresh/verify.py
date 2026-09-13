"""Verify the memory-routing execution scenario.

Usage: python verify.py <candidate-workspace>

Loads <candidate-workspace>/solution.py in a fresh namespace (no other files
are imported), runs its route() on concrete generated inputs for four cases
in three arms, judges the returned dicts against an independent oracle, and
checks determinism and non-mutation. The bundled reference implementation is
also executed and its agreement with the oracle is REPORTED SEPARATELY under
"reference_agreement"; it never contributes to "passed" or the exit code.

Prints one JSON object:
{"checks": [{"name", "ok", ...}...],          behavioral score (candidate)
 "reference_agreement": {...},                scenario self-check, unscored
 "passed": bool}                              all behavioral checks ok
Exit code 0 iff every behavioral check passes.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

VERIFIER_DIR = Path(__file__).resolve().parent


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Cases. Each case is a repository dict and a memory list. Arms vary only the
# memory argument. The expected outcomes below are the scenario oracle; they
# are derived from the spec in prompt.txt and held ONLY here and in notes.json
# (never in the candidate workspace).
# --------------------------------------------------------------------------

def _cedar():
    repository = {
        "id": "repo-incident-cedar",
        "topic": "uploads",
        "facts": {"project": "cedar", "west_available": False,
                  "east_available": True, "queuing_supported": True},
        "authorities": [{
            "id": "ops-general-playbook", "date": "2026-07-01",
            "approved": True, "supersedes": [],
            "rules": [
                {"topic": "uploads", "when": {"east_available": True},
                 "action": "reroute_east", "fallback": True},
                {"topic": "uploads", "when": {"queuing_supported": True},
                 "action": "request_policy", "fallback": True}]}],
        "default_action": "request_policy"}
    memory = [{
        "id": "decision-2026-08-20-cedar-region", "date": "2026-08-20",
        "approved": True, "supersedes": [],
        "rules": [
            {"topic": "uploads",
             "when": {"project": "cedar", "west_available": False,
                      "queuing_supported": True},
             "action": "queue_uploads"}]}]
    return repository, memory


def _birch():
    repository = {
        "id": "migration-2026-09-08-birch",
        "topic": "events_schema",
        "facts": {"project": "birch", "consumers_accept": "v2",
                  "producer_emitting": "v1"},
        "authorities": [{
            "id": "migration-2026-09-08-birch", "date": "2026-09-08",
            "approved": True, "supersedes": ["decision-2026-08-20-birch-schema"],
            "rules": [
                {"topic": "events_schema",
                 "when": {"consumers_accept": "v2",
                          "producer_emitting": "v1"},
                 "action": "emit_v2"}]}],
        "default_action": "request_policy"}
    memory = [{
        "id": "decision-2026-08-20-birch-schema", "date": "2026-08-20",
        "approved": True, "supersedes": [],
        "rules": [
            {"topic": "events_schema", "when": {"project": "birch"},
             "action": "emit_v1"}]}]
    return repository, memory


def _maple():
    repository = {
        "id": "api-contract-2026-09-01-maple",
        "topic": "http_error",
        "facts": {"project": "maple", "status": 400,
                  "payload": "missing_required_field"},
        "authorities": [{
            "id": "api-contract-2026-09-01-maple", "date": "2026-09-01",
            "approved": True, "supersedes": [],
            "rules": [
                {"topic": "http_error", "when": {"status": 400},
                 "action": "repair_payload"}]}],
        "default_action": "request_policy"}
    memory = [{
        "id": "ops-draft-2026-09-07-maple-retry", "date": "2026-09-07",
        "approved": False, "supersedes": [],
        "rules": [
            {"topic": "http_error", "when": {"status": 400,
                                             "project": "maple"},
             "action": "retry_three_times"}]}]
    return repository, memory


def _ash():
    repository = {
        "id": "import-contract-ash",
        "topic": "import_recovery",
        "facts": {"project": "ash", "restart_after_commit": 42,
                  "non_idempotent_effects_before_commit": True},
        "authorities": [{
            "id": "import-contract-ash", "date": "2026-08-15",
            "approved": True, "supersedes": [],
            "rules": [
                {"topic": "import_recovery",
                 "when": {"restart_after_commit": 42},
                 "action": "resume_cursor_42"}]}],
        "default_action": "request_policy"}
    memory = [{
        "id": "decision-2026-09-01-ash-resume", "date": "2026-09-01",
        "approved": True, "supersedes": [],
        "rules": [
            {"topic": "import_recovery",
             "when": {"project": "ash",
                      "non_idempotent_effects_before_commit": True},
             "action": "resume_cursor_42", "fallback": True}]}]
    return repository, memory


CASES = {
    "useful-hidden-decision": (_cedar, {
        "repository_only": {"action": "reroute_east",
                            "evidence": ["ops-general-playbook"],
                            "retrieved": []},
        "memory": {"action": "queue_uploads",
                   "evidence": ["decision-2026-08-20-cedar-region"],
                   "retrieved": ["decision-2026-08-20-cedar-region"]}}),
    "stale-decision": (_birch, {
        "repository_only": {"action": "emit_v2",
                            "evidence": ["migration-2026-09-08-birch"],
                            "retrieved": []},
        "memory": {"action": "emit_v2",
                   "evidence": ["migration-2026-09-08-birch"],
                   "retrieved": []}}),
    "conflicting-current-authority": (_maple, {
        "repository_only": {"action": "repair_payload",
                            "evidence": ["api-contract-2026-09-01-maple"],
                            "retrieved": []},
        "memory": {"action": "repair_payload",
                   "evidence": ["api-contract-2026-09-01-maple"],
                   "retrieved": ["ops-draft-2026-09-07-maple-retry"]}}),
    "repository-sufficient-control": (_ash, {
        "repository_only": {"action": "resume_cursor_42",
                            "evidence": ["import-contract-ash"],
                            "retrieved": []},
        "memory": {"action": "resume_cursor_42",
                   "evidence": ["import-contract-ash"],
                   "retrieved": ["decision-2026-09-01-ash-resume"]}}),
}


def _judged(route_fn, case_id, arm):
    """Run route on one case/arm; return (observed, ok, detail)."""
    repository, memory = CASES[case_id][0]()
    args = (copy.deepcopy(repository),
            [] if arm == "repository_only" else copy.deepcopy(memory))
    expected = CASES[case_id][1][arm]
    try:
        observed = route_fn(*args)
    except NotImplementedError:
        return None, False, "route raised NotImplementedError (stub)"
    except Exception as exc:  # candidate crash = failed check, not abort
        return None, False, "route raised %s: %s" % (type(exc).__name__, exc)
    if not isinstance(observed, dict):
        return observed, False, "route did not return a dict"
    ok = all(observed.get(key) == value
             for key, value in expected.items())
    detail = "expected %r, got %r" % (expected,
                                      {key: observed.get(key)
                                       for key in expected})
    return observed, ok, detail


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: python verify.py "
                                   "<candidate-workspace>"}))
        return 2
    workspace = Path(sys.argv[1])
    solution = workspace / "solution.py"
    if not solution.is_file():
        print(json.dumps({"error": "missing solution.py in %s" % workspace,
                          "passed": False}))
        return 1

    checks = []

    def record(name, ok, **extra):
        checks.append(dict(name=name, ok=bool(ok), **extra))

    candidate = _load_module(solution, "candidate_solution")
    # A missing or non-callable route fails every behavioral check through
    # the exception paths below; no API plumbing row is scored.
    route = getattr(candidate, "route", None)
    for case_id, (_, arms) in CASES.items():
        for arm in arms:
            observed, ok, detail = _judged(route, case_id, arm)
            record("case:%s/%s" % (case_id, arm), ok, detail=detail)

    def _safe(args):
        try:
            return "ok", route(*args)
        except Exception as exc:
            return "error", "%s: %s" % (type(exc).__name__, exc)

    # Non-mutation: route receives the ACTUAL argument objects (no copies);
    # a deep snapshot taken before the call is compared against them after.
    repo_a, mem_a = _maple()
    before = copy.deepcopy((repo_a, mem_a))
    status_a, first = _safe((repo_a, mem_a))
    if status_a == "ok":
        record("no_input_mutation", (repo_a, mem_a) == before,
               detail="route mutated its arguments")
    else:
        record("no_input_mutation", False,
               detail="route raised; mutation check not meaningful")

    # Determinism: fresh equal inputs must give identical results.
    repo_b, mem_b = _maple()
    status_b, second = _safe((repo_b, mem_b))
    if status_a == "ok" and status_b == "ok":
        record("determinism", first == second,
               detail="first %r second %r" % (first, second))
    else:
        record("determinism", False, detail="route raised: %r" % first)

    # Reference agreement: scenario self-check, reported but NEVER scored.
    reference = _load_module(VERIFIER_DIR / "reference.py",
                             "scenario_reference")
    reference_rows = []
    for case_id, (_, arms) in CASES.items():
        for arm in arms:
            _, ok, detail = _judged(reference.route, case_id, arm)
            reference_rows.append({"case": case_id, "arm": arm,
                                   "ok": bool(ok), "detail": detail})
    reference_agreement = {
        "all_ok": all(row["ok"] for row in reference_rows),
        "rows": reference_rows,
        "scored": False,
        "note": "scenario self-check only; excluded from passed/exit code"}

    passed = all(check["ok"] for check in checks)
    print(json.dumps({"checks": checks,
                      "reference_agreement": reference_agreement,
                      "passed": passed}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
