"""Tests for scripts/tools/deploy.py CLI contracts and the CK-01 full-deploy preview.

Ensures:
- `deploy.py --help` / `-h` prints help, exits 0, and causes ZERO mutations.
- Unknown arguments exit 2 (argparse standard), print error, and cause ZERO mutations.
- `deploy.py --dry-run` (full-deploy preview) opens no transaction, mutates
  nothing in the fake home, and its planned actions predict exactly the file
  set a real deploy creates/changes/deletes; unrelated home files stay untouched.
- The same zero-write invariants hold for a real subprocess with HOME,
  USERPROFILE, APPDATA, LOCALAPPDATA and MEMORY_ROOT redirected to a temp root.
- `deploy.py` (no args) still runs the full documented deploy sequence,
  including bump_claude_md (behavioral replacement for the deleted
  source-text pin in test_release_contract.py).
"""
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parent.parent
VERSION = (KIT / "VERSION").read_text(encoding="utf-8").strip()


def load_deploy():
    spec = importlib.util.spec_from_file_location(
        "deploy", KIT / "scripts" / "tools" / "deploy.py"
    )
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    return deploy


def snapshot(root: Path) -> dict:
    """relative-path -> sha256 for every file under root."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()
    }


def changed_paths(before: dict, after: dict) -> set:
    """Paths created, deleted, or byte-changed between two snapshots."""
    return {p for p in set(before) | set(after) if before.get(p) != after.get(p)}


def seed_home(deploy, home: Path) -> dict:
    """Deterministic preexisting state: a drifted owned skill, a stale manifest
    entry, an old CLAUDE.md, and an unrelated user file."""
    owned, stale = deploy.master_skill_names()[0], "ghost-skill"
    src = deploy.SKILLS / owned
    dest = home / ".claude" / "skills"
    shutil.copytree(src, dest / owned)
    rels = sorted(p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file())
    drifted = rels[0]
    (dest / owned / drifted).write_text("drifted content\n", encoding="utf-8")
    deleted = rels[-1] if len(rels) > 2 else None
    if deleted:
        (dest / owned / deleted).unlink()
    (dest / owned / "zzz_extra.md").write_text("local leftover\n", encoding="utf-8")
    (dest / stale).mkdir()
    (dest / stale / "SKILL.md").write_text("stale skill\n", encoding="utf-8")
    (dest / deploy.MANIFEST_NAME).write_text(
        '{"kit_version": "0.0.1", "skills": ["%s", "%s"]}' % (owned, stale),
        encoding="utf-8")
    (home / ".claude" / "CLAUDE.md").write_text(
        "coding-kit v0.0.1 (repo master; machine CLAUDE.md refreshed 2020-01-01) (12, English)\n"
        "# machine-local triggers stay below the version line\n",
        encoding="utf-8")
    unrelated = home / "Documents" / "keep.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("unrelated user file\n", encoding="utf-8")
    return {"owned": owned, "drifted": drifted, "deleted": deleted, "unrelated": unrelated}


def _expand_action(deploy, home: Path, target: Path, action: str, before: dict) -> set:
    verb, _, rest = action.partition(" ")
    if rest == deploy.MANIFEST_NAME:
        return {(target / rest).relative_to(home).as_posix()}
    if verb == "add":
        src = deploy.SKILLS / rest
        return {
            (target / rest / p.relative_to(src)).relative_to(home).as_posix()
            for p in src.rglob("*") if p.is_file()
        }
    if verb in ("upd", "del"):
        return {(target / rest).relative_to(home).as_posix()}
    if verb == "rm-dir":
        prefix = (target / rest).relative_to(home).as_posix() + "/"
        return {p for p in before if p.startswith(prefix)}
    raise AssertionError(f"unrecognized preview action: {action!r}")


def plan_paths(deploy, home: Path, claude_md: Path, out: str, before: dict) -> set:
    """Every file path the preview says a real deploy would create/change/delete."""
    planned = set()
    section = "skills"
    for line in out.splitlines():
        if line.startswith("=== ROUTERS ==="):
            section = "routers"
            continue
        if section == "skills":
            if ": " not in line or line.startswith("DRY RUN"):
                continue
            target_s, actions_s = line.split(": ", 1)
            target = Path(target_s)
            if not target.is_absolute() or actions_s == "no changes":
                continue
            for action in actions_s.split(", "):
                planned |= _expand_action(deploy, home, target, action, before)
        elif line.startswith("would regenerate: "):
            planned.add(Path(line.split(": ", 1)[1]).relative_to(home).as_posix())
        elif line.startswith("CLAUDE.md: would bump"):
            planned.add(claude_md.relative_to(home).as_posix())
    return planned


class DeployCliTest(unittest.TestCase):
    def _run_deploy_in_isolated_sandbox(self, argv: list):
        """Runs deploy.main() with completely isolated sandbox paths.

        Returns (returncode, stdout, stderr, created_files_in_fake_home).
        """
        spec = importlib.util.spec_from_file_location(
            "deploy", KIT / "scripts" / "tools" / "deploy.py"
        )
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)

        with tempfile.TemporaryDirectory(prefix="test-deploy-home-") as td:
            fake_home = Path(td)
            out_buf = io.StringIO()
            err_buf = io.StringIO()

            # Set up mock targets pointing into fake_home
            fake_claude_md = fake_home / ".claude" / "CLAUDE.md"
            fake_sync_targets = [
                str(fake_home / ".claude" / "skills"),
                str(fake_home / ".agents" / "skills"),
            ]
            fake_harnesses = [
                {
                    "id": "test_omp",
                    "router": str(fake_home / ".omp" / "agent" / "AGENTS.md"),
                    "name": "TestOMP",
                    "skills_line": None,
                    "skills_dir": None,
                }
            ]

            with mock.patch.object(sys, "argv", ["deploy.py", *argv]), \
                 mock.patch.object(sys, "stdout", out_buf), \
                 mock.patch.object(sys, "stderr", err_buf), \
                 mock.patch.object(deploy, "CLAUDE_MD", fake_claude_md), \
                 mock.patch.object(deploy, "SYNC_TARGETS", fake_sync_targets), \
                 mock.patch.object(deploy, "HARNESSES", fake_harnesses):

                rc = None
                try:
                    res = deploy.main()
                    rc = 0 if res is None else res
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)

            created_files = [
                str(p.relative_to(fake_home))
                for p in fake_home.rglob("*")
                if p.is_file()
            ]
            return rc, out_buf.getvalue(), err_buf.getvalue(), created_files

    def test_help_flag_exits_zero_and_causes_zero_mutations(self):
        for flag in ["--help", "-h"]:
            with self.subTest(flag=flag):
                rc, stdout, stderr, created = self._run_deploy_in_isolated_sandbox([flag])
                self.assertEqual(rc, 0, f"{flag} must exit 0, got {rc}")
                self.assertIn("usage:", stdout.lower() + stderr.lower())
                self.assertEqual(
                    created, [],
                    f"{flag} must not mutate or create files, found: {created}"
                )

    def test_unknown_argument_exits_2_and_causes_zero_mutations(self):
        rc, stdout, stderr, created = self._run_deploy_in_isolated_sandbox(["--bogus-flag"])
        self.assertEqual(rc, 2, f"Unknown arg must exit 2 (argparse), got {rc}")
        self.assertEqual(
            created, [],
            f"Unknown arg must not mutate or create files, found: {created}"
        )


class DeployDryRunBoundaryTest(unittest.TestCase):
    """The deploy steps are replaced with recorders, so a parser fall-through
    is observable (the recorded sequence) instead of being masked by the
    integrity gate's exit 3 or by mutating anything real."""

    def _main_with_recorders(self, argv: list, forbid_transaction: bool = False):
        spec = importlib.util.spec_from_file_location(
            "deploy", KIT / "scripts" / "tools" / "deploy.py"
        )
        deploy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(deploy)

        calls: list = []
        out_buf = io.StringIO()
        err_buf = io.StringIO()

        def rec(name, result=None):
            def _fn(*args, **kwargs):
                calls.append(name)
                return result
            return _fn

        def no_transaction(*args, **kwargs):
            raise AssertionError("preview must not open a deploy transaction")

        tx_patch = (
            mock.patch.object(deploy, "DeployTransaction", no_transaction)
            if forbid_transaction
            else mock.patch.object(deploy, "DeployTransaction")
        )

        with mock.patch.object(deploy, "integrity_gate", rec("integrity_gate")), \
             mock.patch.object(deploy, "preflight_routers_and_claude", rec("preflight_routers_and_claude", (True, []))), \
             mock.patch.object(deploy, "preflight_skills", rec("preflight_skills", (True, [], []))), \
             mock.patch.object(deploy, "execute_skills", rec("execute_skills", [])), \
             mock.patch.object(deploy, "regen_routers", rec("regen_routers", [])), \
             mock.patch.object(deploy, "bump_claude_md",
                               rec("bump_claude_md", "unchanged")), \
             mock.patch.object(deploy, "verify", rec("verify", True)), \
             tx_patch, \
             mock.patch.object(sys, "argv", ["deploy.py", *argv]), \
             mock.patch.object(sys, "stdout", out_buf), \
             mock.patch.object(sys, "stderr", err_buf):
            try:
                res = deploy.main()
                rc = 0 if res is None else res
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        return rc, calls, out_buf.getvalue(), err_buf.getvalue()

    def test_standalone_dry_run_previews_read_only_steps(self):
        rc, calls, out, err = self._main_with_recorders(["--dry-run"], forbid_transaction=True)
        self.assertEqual(rc, 0, f"preview must exit 0 on a clean plan, got {rc}: {out}{err}")
        self.assertIn("DRY RUN", out)
        self.assertEqual(
            calls,
            ["integrity_gate", "preflight_routers_and_claude", "preflight_skills",
             "execute_skills", "regen_routers", "bump_claude_md"],
            "preview must run the read-only plan steps and stop before any "
            "mutation step (no verify, no transaction)")

    def test_no_args_still_runs_full_deploy_sequence(self):
        rc, calls, _out, _err = self._main_with_recorders([])
        self.assertEqual(rc, 0)
        self.assertEqual(
            calls,
            ["integrity_gate", "preflight_routers_and_claude", "preflight_skills",
             "execute_skills", "regen_routers", "bump_claude_md", "verify"],
            "no-args deploy must run the documented sequence, including the "
            "CLAUDE.md bump (verify() fails on every VERSION bump without it)")


class DeployPreviewTest(unittest.TestCase):
    """CK-01 preview subset: the preview computes the same plan as a real deploy,
    mutates nothing, and predicts the exact set of touched files."""

    def _run(self, home: Path, argv: list):
        deploy = load_deploy()
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        claude_md = home / ".claude" / "CLAUDE.md"
        patchers = [
            mock.patch.object(sys, "argv", ["deploy.py", *argv]),
            mock.patch.object(sys, "stdout", out_buf),
            mock.patch.object(sys, "stderr", err_buf),
            mock.patch.object(deploy, "SYNC_TARGETS",
                              [str(home / ".claude" / "skills"), str(home / ".agents" / "skills")]),
            mock.patch.object(deploy, "HARNESSES", [
                {"id": "test_omp", "router": str(home / ".omp" / "agent" / "AGENTS.md"),
                 "name": "TestOMP", "skills_line": None, "skills_dir": None},
            ]),
            mock.patch.object(deploy, "CLAUDE_MD", claude_md),
            mock.patch.object(deploy, "integrity_gate"),
        ]
        for p in patchers:
            p.start()
        try:
            rc = deploy.main()
            rc = 0 if rc is None else rc
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        finally:
            for p in patchers:
                p.stop()
        return deploy, claude_md, rc, out_buf.getvalue(), err_buf.getvalue()

    def test_preview_mutates_nothing_and_predicts_real_deploy(self):
        with tempfile.TemporaryDirectory(prefix="test-preview-home-") as td:
            home = Path(td)
            fixture = seed_home(load_deploy(), home)
            before = snapshot(home)

            deploy, claude_md, rc, out, err = self._run(home, ["--dry-run"])
            self.assertEqual(rc, 0, f"preview must exit 0 on a clean fixture: {out}{err}")
            self.assertIn("DRY RUN", out)
            self.assertEqual(snapshot(home), before,
                             "preview must not create, change or delete any file")
            planned = plan_paths(deploy, home, claude_md, out, before)
            self.assertIn("Documents/keep.txt", snapshot(home),
                          "preview must leave unrelated home files in place")
            self.assertTrue(planned, "preview must plan real work for this fixture")

        with tempfile.TemporaryDirectory(prefix="test-preview-apply-") as td:
            home = Path(td)
            fixture = seed_home(load_deploy(), home)
            before = snapshot(home)

            _, _, rc, out, err = self._run(home, [])
            self.assertEqual(rc, 0, f"real deploy must succeed on the fixture: {out}{err}")
            actual = changed_paths(before, snapshot(home))
            unrelated_after = (home / "Documents" / "keep.txt").read_text(encoding="utf-8")

        self.assertEqual(
            planned, actual,
            "preview plan and actual deploy must touch exactly the same files")
        self.assertEqual(unrelated_after, "unrelated user file\n")

    def test_preview_aborts_on_conflict_without_writing(self):
        with tempfile.TemporaryDirectory(prefix="test-preview-conflict-") as td:
            home = Path(td)
            deploy = load_deploy()
            dest = home / ".claude" / "skills"
            dest.mkdir(parents=True)
            unowned = deploy.master_skill_names()[0]
            (dest / unowned).mkdir()
            (dest / unowned / "SKILL.md").write_text("foreign content\n", encoding="utf-8")
            before = snapshot(home)

            _, _, rc, out, _err = self._run(home, ["--dry-run"])
            self.assertEqual(rc, 1, f"preview must fail closed on a conflict: {out}")
            self.assertIn("PREVIEW ABORTED", out)
            self.assertEqual(snapshot(home), before,
                             "conflicting preview must not touch the fake home")


class DeployPreviewSubprocessTest(unittest.TestCase):
    """CK-01: a real subprocess with every home-derived env var redirected leaves
    the temporary home and the repository byte-identical."""

    def _repo_state(self):
        state = {}
        for root in (KIT / "skills", KIT / "scripts" / "tools", KIT / ".agents"):
            if not root.exists():
                continue
            for rel, digest in snapshot(root).items():
                if "__pycache__" in rel:
                    continue
                state[f"{root.relative_to(KIT).as_posix()}/{rel}"] = digest
        for f in (KIT / "integrity-manifest.json", KIT / "AGENTS.md",
                  KIT / "OPS.md", KIT / "profile.yml"):
            if f.exists():
                state[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
        return state

    def _run(self, argv: list, home: Path):
        env = dict(os.environ)
        env.update({
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "MEMORY_ROOT": str(home / ".memory"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return subprocess.run(
            [sys.executable, str(KIT / "scripts" / "tools" / "deploy.py"), *argv],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, cwd=str(home), timeout=300)

    def test_preview_help_and_invalid_args_never_write(self):
        repo_before = self._repo_state()
        with tempfile.TemporaryDirectory(prefix="test-preview-subprocess-") as td:
            home = Path(td)
            unrelated = home / "Documents" / "keep.txt"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("keep\n", encoding="utf-8")
            home_before = snapshot(home)

            for argv, expected_rc in ((["--dry-run"], 0), (["--help"], 0), (["--bogus-flag"], 2)):
                with self.subTest(argv=argv):
                    proc = self._run(argv, home)
                    self.assertEqual(
                        proc.returncode, expected_rc,
                        f"{argv} exited {proc.returncode}: {proc.stdout}{proc.stderr}")
                    self.assertEqual(
                        snapshot(home), home_before,
                        f"{argv} must not create or change any file in the redirected home")
                    self.assertEqual(
                        self._repo_state(), repo_before,
                        f"{argv} must leave the repository byte-identical")
            dry = self._run(["--dry-run"], home)
            self.assertIn("DRY RUN", dry.stdout)
            self.assertIn("add ", dry.stdout,
                          "redirected-home preview must plan the fresh skill copies")
            unrelated_after = unrelated.read_text(encoding="utf-8")

        self.assertEqual(unrelated_after, "keep\n")

    def test_full_deploy_subprocess_in_isolated_repo_copy(self):
        """Roadmap CK-01 proof: a real apply run against a disposable repository
        copy with every home-derived env var redirected. The original repository
        and any unrelated home file stay byte-identical."""
        repo_before = self._repo_state()
        with tempfile.TemporaryDirectory(prefix="test-deploy-drill-") as td:
            root = Path(td)
            kit_copy = root / "kit"
            shutil.copytree(
                KIT, kit_copy,
                ignore=shutil.ignore_patterns(
                    ".git", "dist", "__pycache__", ".pytest_cache", ".agents"))
            home = root / "home"
            (home / "Documents").mkdir(parents=True)
            unrelated = home / "Documents" / "keep.txt"
            unrelated.write_text("keep\n", encoding="utf-8")

            env = dict(os.environ)
            env.update({
                "HOME": str(home),
                "USERPROFILE": str(home),
                "APPDATA": str(home / "AppData" / "Roaming"),
                "LOCALAPPDATA": str(home / "AppData" / "Local"),
                "MEMORY_ROOT": str(home / ".memory"),
                "PYTHONDONTWRITEBYTECODE": "1",
            })
            proc = subprocess.run(
                [sys.executable, str(kit_copy / "scripts" / "tools" / "deploy.py")],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env=env, cwd=str(kit_copy), timeout=600)
            self.assertEqual(proc.returncode, 0,
                             f"isolated full deploy failed: {proc.stdout}{proc.stderr}")

            source_skills = sorted(p.name for p in (kit_copy / "skills").iterdir() if p.is_dir())
            deployed = home / ".claude" / "skills"
            deployed_skills = {k: v for k, v in snapshot(deployed).items()
                               if not k.startswith(".kit-manifest.json")}
            self.assertEqual(deployed_skills, snapshot(kit_copy / "skills"),
                             "deployed skills must be byte-identical to the master copy")
            manifest = json.loads((deployed / ".kit-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(manifest["skills"]), source_skills)
            for router in (home / "AGENTS.md", home / ".omp" / "agent" / "AGENTS.md"):
                text = router.read_text(encoding="utf-8")
                self.assertIn(f"v{VERSION}", text)
                self.assertIn(kit_copy.as_posix(), text)
            self.assertFalse((home / ".omp" / "agent" / "AGENTS.md.kit-bak").exists(),
                             "no backup is needed when the router did not exist before")
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep\n")
            self.assertEqual(self._repo_state(), repo_before,
                             "the deployed-from repository must stay byte-identical")
            self.assertEqual(snapshot(home / ".claude" / "skills"), snapshot(home / ".agents" / "skills"),
                             "every sync target must receive the same skill bytes")


if __name__ == "__main__":
    unittest.main()
