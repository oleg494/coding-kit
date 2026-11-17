"""Canonical mirror sync (KIT/.agents/skills) extracted from deploy.py.

Reads dynamic attributes/mocks (KIT, SKILLS, VERSION, integrity_gate, etc.)
from `deploy_mod` so tests monkeypatching deploy module globals work seamlessly.
"""
import json
import shutil
import sys
from pathlib import Path


def _prune_empty_parents(file_path: Path, stop_at: Path) -> None:
    """Remove empty intermediate subdirectories up to (but excluding) stop_at."""
    parent = file_path.parent
    while parent != stop_at and parent.parent != parent:
        try:
            if any(parent.iterdir()):
                break
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def plan_canonical_sync(deploy_mod, canon: Path) -> list[dict]:
    """Compute ONE unified change plan for canonical sync (incl. manifest).
    Source skills are preflighted for links/escapes/presence; a differing
    pre-existing same-name skill is a collision error unless the kit
    previously owned it (manifest claim) or it is byte-identical (adoption)."""
    names = deploy_mod.master_skill_names()
    skills_dir = deploy_mod.SKILLS
    manifest_name = deploy_mod.MANIFEST_NAME
    plan = []
    if deploy_mod.is_link(canon) or deploy_mod.has_link_ancestor(canon, deploy_mod.KIT):
        return [{"op": "error", "target": canon,
                 "desc": f"ERROR: canonical target {canon} or ancestor is a link"}]

    previously_owned: set[str] = set()
    mani_file = canon / manifest_name
    if deploy_mod.is_link(mani_file):
        pass  # the manifest link check below adds the plan error
    elif mani_file.is_file():
        try:
            previous = json.loads(mani_file.read_text(encoding="utf-8"))
            skills_list = previous.get("skills") if isinstance(previous, dict) else None
            if (not isinstance(skills_list, list)
                    or not all(isinstance(name, str) for name in skills_list)):
                raise ValueError("invalid ownership manifest structure")
            previously_owned = set(skills_list)
        except (OSError, ValueError) as e:
            return [{"op": "error", "target": mani_file,
                     "desc": (f"ERROR: destination manifest {mani_file} is "
                              f"unreadable or malformed ({e}) — refusing to "
                              f"sync with unknown ownership; fix or remove it "
                              f"and re-run")}]

    for n in names:
        src = skills_dir / n
        if not src.exists():
            plan.append({"op": "error", "skill": n, "src": src,
                         "desc": f"ERROR: source skill missing: {src}"})
            continue
        bad_src = deploy_mod.scan_skill_links(skills_dir, src)
        if bad_src:
            plan.append({"op": "error", "skill": n, "src": src,
                         "desc": f"ERROR: source skill {n} contains link/escape: {', '.join(bad_src)}"})

    if not canon.exists():
        if any(item.get("op") == "error" for item in plan):
            return plan
        for n in names:
            plan.append({"op": "add-skill", "skill": n, "src": skills_dir / n,
                         "target": canon / n, "desc": f"add .agents/skills/{n}"})
        plan.append({"op": "upd-manifest", "target": canon / manifest_name,
                     "desc": f"add {manifest_name}"})
        return plan

    for n in names:
        src, target = skills_dir / n, canon / n
        if deploy_mod.is_link(target):
            try:
                if target.resolve() == src.resolve():
                    continue
            except Exception:
                pass
            plan.append({"op": "error", "skill": n, "target": target,
                         "desc": f"ERROR: skill {n} is a link: {target}"})
            continue
        if not target.exists():
            plan.append({"op": "add-skill", "skill": n, "src": src,
                         "target": target, "desc": f"add .agents/skills/{n}"})
            continue
        bad_links = deploy_mod.scan_skill_links(canon, target)
        if bad_links:
            plan.append({"op": "error", "skill": n, "target": target,
                         "desc": f"ERROR: skill {n} contains link/escape: {', '.join(bad_links)}"})
            continue
        if target.resolve() == src.resolve():
            continue
        if n not in previously_owned and not deploy_mod.dirs_byte_identical(src, target):
            plan.append({"op": "error", "skill": n, "target": target,
                         "desc": (f"ERROR: skill {n} already exists in {canon} with foreign content "
                                  f"(not claimed by {manifest_name}, not byte-identical to master) — refusing to overwrite")})
            continue
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                tf = target / rel
                if not tf.exists() or f.read_bytes() != tf.read_bytes():
                    plan.append({"op": "upd-file", "src": f, "target": tf,
                                 "desc": f"upd {n}/{rel}"})
        for f in target.rglob("*"):
            if f.is_file() and not (src / f.relative_to(target)).exists():
                plan.append({"op": "del-file", "skill": n, "target": f,
                             "desc": f"del {n}/{f.relative_to(target)}"})

    for entry in sorted(canon.iterdir()):
        if entry.is_dir() and entry.name in previously_owned and entry.name not in names:
            bad_links = deploy_mod.scan_skill_links(canon, entry)
            if bad_links:
                plan.append({"op": "error", "target": entry,
                             "desc": f"ERROR: stale dir {entry.name} contains link/escape: {', '.join(bad_links)}"})
            else:
                plan.append({"op": "rm-dir", "target": entry,
                             "desc": f"rm-dir {entry.name}"})

    if deploy_mod.is_link(mani_file):
        plan.append({"op": "error", "target": mani_file,
                     "desc": f"ERROR: manifest {mani_file} is a link"})
    elif not mani_file.exists():
        plan.append({"op": "upd-manifest", "target": mani_file,
                     "desc": f"add {manifest_name}"})
    else:
        try:
            curr_mani = json.loads(mani_file.read_text(encoding="utf-8"))
            if curr_mani.get("kit_version") != deploy_mod.VERSION or curr_mani.get("skills") != names:
                plan.append({"op": "upd-manifest", "target": mani_file,
                             "desc": f"upd {manifest_name}"})
        except Exception:
            plan.append({"op": "upd-manifest", "target": mani_file,
                         "desc": f"upd {manifest_name}"})

    return plan


def verify_canonical_result(deploy_mod, canon: Path, plan: list[dict]) -> list[str]:
    """Re-check the canonical destination after the transaction."""
    errs: list[str] = []
    names = deploy_mod.master_skill_names()
    for n in names:
        src, target = deploy_mod.SKILLS / n, canon / n
        if not target.exists():
            errs.append(f"skill {n} missing after sync: {target}")
            continue
        if deploy_mod.is_link(target):
            errs.append(f"skill {n} is a link after sync: {target}")
            continue
        bad = deploy_mod.scan_skill_links(canon, target)
        if bad:
            errs.append(f"skill {n} contains link/escape after sync: {', '.join(bad)}")
            continue
        if not deploy_mod.dirs_byte_identical(src, target):
            errs.append(f"skill {n} differs from master after sync")
    for item in plan:
        if item["op"] == "rm-dir" and item["target"].exists():
            errs.append(f"retired skill dir still present after sync: {item['target']}")
    mani = canon / deploy_mod.MANIFEST_NAME
    try:
        curr = json.loads(mani.read_text(encoding="utf-8"))
    except Exception as e:
        errs.append(f"manifest unreadable after sync: {mani} ({e})")
        return errs
    if curr.get("kit_version") != deploy_mod.VERSION or curr.get("skills") != names:
        errs.append(f"manifest mismatch after sync (want kit_version={deploy_mod.VERSION}, skills={names})")
    return errs


def canonical_mode(deploy_mod, argv=None) -> int:
    """--canonical: sync KIT/skills -> the repo's .agents/skills/ directory."""
    argv = list(sys.argv[1:]) if argv is None else argv
    dry = "--dry-run" in argv
    canon = deploy_mod.KIT / ".agents" / "skills"
    deploy_mod.integrity_gate()
    plan = deploy_mod.plan_canonical_sync(canon)
    has_errors = any(item.get("op") == "error" for item in plan)
    if dry:
        print("DRY RUN — no changes written")
        if not plan:
            print("no changes")
        else:
            for item in plan:
                print(item["desc"])
        return 1 if has_errors else 0

    if has_errors:
        for item in plan:
            if item.get("op") == "error":
                print(item["desc"])
        print("canonical sync aborted due to errors/links")
        return 1

    print(f"canonical: {canon}")
    actions: list[str] = []
    tx = deploy_mod.DeployTransaction()
    with tx:
        for item in plan:
            op = item["op"]
            if op in ("add-skill", "upd-file", "del-file", "rm-dir"):
                skill_name = item.get("skill")
                target_path = canon / skill_name if skill_name else item["target"]
                tx.record_absent_ancestors(target_path)
                tx.snapshot_target(target_path)
            elif op == "upd-manifest":
                tx.record_absent_ancestors(item["target"])
                tx.snapshot_target(item["target"])

        tx.mark_mutations_started()
        if not canon.exists():
            canon.mkdir(parents=True)

        try:
            for item in plan:
                op = item["op"]
                if op == "add-skill":
                    deploy_mod.safe_copytree(item["src"], item["target"], boundary=canon)
                    actions.append(item["desc"])
                elif op == "upd-file":
                    if not deploy_mod.is_safe_under_boundary(item["target"], canon):
                        print(f"ERROR: unsafe upd file target {item['target']}")
                        tx.rollback("unsafe upd file target")
                        return 1
                    item["target"].parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item["src"], item["target"])
                    actions.append(item["desc"])
                elif op == "del-file":
                    if not deploy_mod.is_safe_under_boundary(item["target"], canon):
                        print(f"ERROR: unsafe del file target {item['target']}")
                        tx.rollback("unsafe del file target")
                        return 1
                    item["target"].unlink()
                    skill_root = canon / item["skill"] if item.get("skill") else canon
                    _prune_empty_parents(item["target"], skill_root)
                    actions.append(item["desc"])
                elif op == "rm-dir":
                    deploy_mod.safe_rmtree(item["target"])
                    actions.append(item["desc"])
                elif op == "upd-manifest":
                    names = deploy_mod.master_skill_names()
                    deploy_mod.safe_write_text(
                        item["target"],
                        json.dumps({"kit_version": deploy_mod.VERSION, "skills": names}, indent=1),
                        boundary=canon,
                    )
                    actions.append(item["desc"])
                elif op == "error":
                    print(item["desc"])
                    tx.rollback(item["desc"])
                    return 1
        except Exception as e:
            tx.rollback(str(e))
            return 1

        verify_errs = deploy_mod.verify_canonical_result(canon, plan)
        if verify_errs:
            for e in verify_errs:
                print("VERIFY FAIL:", e)
            tx.rollback("canonical result verification failed")
            return 1
        tx.commit()

    for a in actions:
        print(a)
    if not actions:
        print("no changes")
    print("canonical sync complete")
    return 0
