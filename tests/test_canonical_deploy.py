""":mod:`tests.test_canonical_deploy` — v4.10.1 --canonical deploy tests,
split out of test_deploy_cli.py / test_deploy_ownership.py (file-size gate).

Covers: integrity-gate ordering, malformed-manifest fail-closed behavior,
ownership (valid adoption / manifest-claimed update / foreign collision
refusal with zero mutation), post-transaction verification and rollback."""
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

KIT = Path(__file__).resolve().parent.parent


def load_deploy():
    spec = importlib.util.spec_from_file_location(
        "deploy", KIT / "scripts" / "tools" / "deploy.py"
    )
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    return deploy


def _try_create_dir_link(target: Path, link: Path) -> bool:
    """Try creating junction on Windows or symlink on POSIX. Return True on success."""
    if sys.platform == "win32":
        try:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
            return True
        except Exception:
            pass
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except Exception:
        return False


def _make_kit(root: Path, skills: dict[str, str], version: str = "9.9.9-test") -> None:
    """Minimal kit fixture: VERSION + profile inventory + one SKILL.md
    per owned skill. When the fixture is baselined for the real (unmocked)
    integrity gate, copy integrity_manifest.py / kit_inventory.py in as
    well so the gate actually runs against this tree."""
    (root / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    entries = "\n".join(f"    - {s}" for s in sorted(skills))
    (root / "profile.yml").write_text(
        f'version: "{version}"\nskills:\n  always_on:\n'
        f"{entries}\n  domain: []\n",
        encoding="utf-8", newline="\n")
    for slug, body in skills.items():
        d = root / "skills" / slug
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")


def _make_gated_kit(root: Path, skills: dict[str, str],
                    version: str = "9.9.9-test") -> None:
    """_make_kit plus the modules the real integrity gate must import
    from the mocked KIT root (no bypass via stubbing the module)."""
    _make_kit(root, skills, version)
    tools = root / "scripts" / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    for name in ("integrity_manifest.py", "kit_inventory.py"):
        shutil.copy2(KIT / "scripts" / "tools" / name, tools / name)


def _load_integrity(root: Path):
    spec = importlib.util.spec_from_file_location(
        "integrity_manifest", KIT / "scripts" / "tools" / "integrity_manifest.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run_canonical(deploy, root: Path, argv: list,
                   patch_gate: bool = True) -> tuple:
    """Run deploy.main() in --canonical mode with the given mocked KIT
    root. patch_gate=False leaves the REAL integrity gate active (the
    fixture must then be baselined and carry the gate modules)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    patches = [
        mock.patch.object(deploy, "KIT", root),
        mock.patch.object(deploy, "SKILLS", root / "skills"),
        mock.patch.object(sys, "argv", ["deploy.py", *argv]),
        mock.patch.object(sys, "stdout", out_buf),
        mock.patch.object(sys, "stderr", err_buf),
    ]
    if patch_gate:
        patches.append(mock.patch.object(deploy, "integrity_gate"))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        try:
            rc = deploy.main()
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return rc, out_buf.getvalue(), err_buf.getvalue()


class CanonicalIntegrityOrderingTest(unittest.TestCase):
    """v4.10.1: --canonical runs the same integrity gate as a full deploy
    BEFORE any planning or write: a drifted control plane (or an unreadable
    baseline) makes both dry-run and apply exit 3, and nothing — not even
    the canonical destination — is touched. plan_canonical_sync must never
    run on a drifted tree (ordering), and the real (unmocked) gate must
    import the real integrity_manifest.py against the mocked KIT
    (coverage — no bypass via stubbing the module)."""

    def test_drifted_tree_fails_gate_before_planning_in_dry_run_and_apply(self):
        with tempfile.TemporaryDirectory(prefix="test-canonical-gate-") as td:
            root = Path(td)
            _make_gated_kit(root, {"alpha": "a"})
            # Baseline the fixture, then drift a control-plane file.
            _load_integrity(root).update_or_create(root, "9.9.9-test")
            (root / "OPS.md").write_text("# ops TAMPERED\n", encoding="utf-8",
                                          newline="\n")
            for argv in (["--canonical", "--dry-run"], ["--canonical"]):
                with self.subTest(argv=argv):
                    rc, out, err = _run_canonical(
                        load_deploy(), root, argv, patch_gate=False)
                    self.assertEqual(rc, 3, f"expected gate exit 3, got {rc}: {out}{err}")
                    self.assertIn("INTEGRITY FAIL", out)
                    # ordering: the planner never ran on the drifted tree
                    self.assertNotIn("DRY RUN", out)
                    self.assertNotIn("canonical:", out)
                    # coverage: the real gate (not a stub) flagged real drift
                    self.assertIn("OPS.md", out)
                    # fail closed: the canonical destination was never created
                    self.assertFalse((root / ".agents").exists(),
                                     "gate failure must not even create .agents")

    def test_missing_baseline_fails_gate_before_planning(self):
        with tempfile.TemporaryDirectory(prefix="test-canonical-nobase-") as td:
            root = Path(td)
            _make_gated_kit(root, {"alpha": "a"})
            # No integrity-manifest.json at all -> refuse to plan.
            for argv in (["--canonical", "--dry-run"], ["--canonical"]):
                with self.subTest(argv=argv):
                    rc, out, err = _run_canonical(
                        load_deploy(), root, argv, patch_gate=False)
                    self.assertEqual(rc, 3, f"expected gate exit 3, got {rc}: {out}{err}")
                    self.assertIn("INTEGRITY FAIL", out)
                    self.assertFalse((root / ".agents").exists())

    def test_clean_tree_passes_gate_and_completes_canonical_sync(self):
        with tempfile.TemporaryDirectory(prefix="test-canonical-clean-") as td:
            root = Path(td)
            _make_gated_kit(root, {"alpha": "a"})
            _load_integrity(root).update_or_create(root, "9.9.9-test")
            rc, out, err = _run_canonical(
                load_deploy(), root, ["--canonical"], patch_gate=False)
            self.assertEqual(rc, 0, f"clean tree must sync: {rc}: {out}{err}")
            self.assertIn("integrity OK", out)
            self.assertIn("canonical sync complete", out)
            canon = root / ".agents" / "skills" / "alpha" / "SKILL.md"
            self.assertEqual(canon.read_text(encoding="utf-8"), "a")
            mani = json.loads(
                (root / ".agents" / "skills" / ".kit-manifest.json")
                .read_text(encoding="utf-8"))
            self.assertEqual(mani["skills"], ["alpha"])


class CanonicalOwnershipTest(unittest.TestCase):
    """v4.10.1 canonical collision rule: a differing pre-existing same-name
    skill is overwritten only when the kit previously owned it (destination
    manifest claim) or it is byte-identical to master. A foreign differing
    collision is refused with ZERO mutation of the destination (dry-run
    and apply). Source skill trees are preflighted for links/escapes
    before any write is planned. A malformed destination manifest fails
    closed — never a silent empty ownership that would reclassify every
    previously-owned skill as a foreign collision target."""

    def test_valid_adoption_of_unclaimed_byte_identical_skill(self):
        """A byte-identical unclaimed skill is safely adopted: sync
        succeeds, the manifest claims it, and rc is 0."""
        with tempfile.TemporaryDirectory(prefix="test-canonical-adopt-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "same body"})
            canon = root / ".agents" / "skills"
            (canon / "alpha").mkdir(parents=True)
            (canon / "alpha" / "SKILL.md").write_text(
                "same body", encoding="utf-8", newline="\n")
            rc, out, err = _run_canonical(
                load_deploy(), root, ["--canonical"])
            self.assertEqual(rc, 0, out + err)
            mani = json.loads(
                (canon / ".kit-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(mani["skills"], ["alpha"])

    def test_manifest_claimed_drifted_skill_is_still_updated(self):
        """The collision rule must not block normal kit-owned drift repair:
        a skill claimed by the destination manifest is updated even when
        its content differs."""
        with tempfile.TemporaryDirectory(prefix="test-canonical-claim-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "new body"})
            canon = root / ".agents" / "skills"
            (canon / "alpha").mkdir(parents=True)
            (canon / "alpha" / "SKILL.md").write_text(
                "old body", encoding="utf-8", newline="\n")
            (canon / ".kit-manifest.json").write_text(
                '{"kit_version": "0.0.1", "skills": ["alpha"]}',
                encoding="utf-8", newline="\n")
            rc, out, err = _run_canonical(
                load_deploy(), root, ["--canonical"])
            self.assertEqual(rc, 0, out + err)
            self.assertEqual(
                (canon / "alpha" / "SKILL.md").read_text(encoding="utf-8"),
                "new body")

    def test_foreign_same_name_collision_refused_with_zero_mutation(self):
        with tempfile.TemporaryDirectory(prefix="test-canonical-collide-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "kit master body", "beta": "beta body"})
            canon = root / ".agents" / "skills"
            # A foreign pre-existing same-name skill: no manifest claim,
            # content differing from master.
            (canon / "alpha").mkdir(parents=True)
            (canon / "alpha" / "SKILL.md").write_text(
                "foreign user body", encoding="utf-8", newline="\n")
            (canon / "alpha" / "custom.txt").write_text(
                "foreign extra", encoding="utf-8", newline="\n")
            # foreign dir that must survive untouched
            (canon / "user-tool").mkdir()
            (canon / "user-tool" / "SKILL.md").write_text(
                "foreign skill", encoding="utf-8", newline="\n")

            for argv in (["--canonical", "--dry-run"], ["--canonical"]):
                with self.subTest(argv=argv):
                    rc, out, err = _run_canonical(load_deploy(), root, argv)
                    self.assertNotEqual(rc, 0,
                                        "foreign collision must fail the run")
                    self.assertIn("ERROR", out)
                    self.assertIn("alpha", out)
                    self.assertIn("refusing to overwrite", out)
                    # ZERO mutation: foreign skill byte-identical and no
                    # kit skill ever copied
                    self.assertEqual(
                        (canon / "alpha" / "SKILL.md").read_text(encoding="utf-8"),
                        "foreign user body")
                    self.assertEqual(
                        (canon / "alpha" / "custom.txt").read_text(encoding="utf-8"),
                        "foreign extra")
                    self.assertFalse((canon / "beta").exists(),
                                     "no kit skill may be written when a "
                                     "collision blocks the plan")
                    self.assertEqual(
                        (canon / "user-tool" / "SKILL.md").read_text(encoding="utf-8"),
                        "foreign skill")
                    self.assertFalse((canon / ".kit-manifest.json").exists(),
                                     "manifest must not be written on collision")

    def test_malformed_ownership_manifest_fails_closed_not_empty_ownership(self):
        """A destination manifest that exists but cannot be parsed as a
        valid ownership claim must FAIL the sync (both dry-run and apply)
        instead of silently degrading to empty ownership — which would
        reclassify every previously-owned skill as a foreign collision
        target."""
        with tempfile.TemporaryDirectory(prefix="test-canonical-badmani-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "kit body"})
            canon = root / ".agents" / "skills"
            (canon / "alpha").mkdir(parents=True)
            (canon / "alpha" / "SKILL.md").write_text(
                "kit body", encoding="utf-8", newline="\n")
            for payload in ("{ this is not json", "[]", "null", "42", '"text"',
                            '{"skills": 42}', '{"skills": [42]}'):
                manifest = canon / ".kit-manifest.json"
                manifest.write_text(payload, encoding="utf-8", newline="\n")
                for argv in (["--canonical", "--dry-run"], ["--canonical"]):
                    with self.subTest(payload=payload, argv=argv):
                        rc, out, err = _run_canonical(load_deploy(), root, argv)
                        self.assertNotEqual(rc, 0)
                        self.assertIn("ERROR", out)
                        self.assertIn("manifest", out)
                        self.assertEqual(manifest.read_text(encoding="utf-8"), payload)
                        self.assertEqual((canon / "alpha" / "SKILL.md").read_text(
                            encoding="utf-8"), "kit body")

    def test_source_link_escape_blocks_plan_before_any_destination_write(self):
        """A linked/escaping SOURCE skill must fail the plan (dry-run and
        apply) before a single byte is written to the destination."""
        with tempfile.TemporaryDirectory(prefix="test-canonical-srclink-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "a", "beta": "b"})
            external = root / "external"
            external.mkdir()
            sentinel = external / "SKILL.md"
            sentinel.write_text("SENTINEL", encoding="utf-8", newline="\n")
            # Replace the real source skill dir with a junction out.
            shutil.rmtree(root / "skills" / "alpha")
            if not _try_create_dir_link(external, root / "skills" / "alpha"):
                self.skipTest("Filesystem does not support junctions/links")

            for argv in (["--canonical", "--dry-run"], ["--canonical"]):
                with self.subTest(argv=argv):
                    rc, out, err = _run_canonical(load_deploy(), root, argv)
                    self.assertNotEqual(rc, 0,
                                        "source link must fail the run")
                    self.assertIn("ERROR", out)
                    self.assertIn("source skill alpha", out)
                    self.assertFalse((root / ".agents" / "skills" / "beta").exists(),
                                     "no destination write on source preflight failure")
                    self.assertFalse((root / ".agents" / "skills" / "alpha").exists(),
                                     "linked source must not be copied")
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "SENTINEL")

    def test_missing_source_skill_blocks_plan(self):
        with tempfile.TemporaryDirectory(prefix="test-canonical-nosrc-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "a", "beta": "b"})
            shutil.rmtree(root / "skills" / "beta")
            rc, out, err = _run_canonical(
                load_deploy(), root, ["--canonical", "--dry-run"])
            self.assertNotEqual(rc, 0, "missing source skill must fail the plan")
            self.assertIn("source skill missing", out)
            self.assertIn("beta", out)


class CanonicalVerificationTest(unittest.TestCase):
    """v4.10.1: the canonical result is re-verified after the transaction
    and a mismatch rolls back (semantics preserved) and fails the run."""

    def test_post_sync_drift_triggers_exact_rollback_and_failure(self):
        """Simulate content swapped between write and verification: the
        post-transaction check must detect the mismatch, restore the
        pre-sync state exactly, and exit non-zero."""
        with tempfile.TemporaryDirectory(prefix="test-canonical-verify-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "new body"})
            canon = root / ".agents" / "skills"
            canon.mkdir(parents=True)
            (canon / "alpha").mkdir()
            (canon / "alpha" / "SKILL.md").write_text(
                "old body", encoding="utf-8", newline="\n")
            (canon / ".kit-manifest.json").write_text(
                json.dumps({"kit_version": "9.9.9-test", "skills": ["alpha"]}),
                encoding="utf-8", newline="\n")

            deploy = load_deploy()
            original_verify = deploy.verify_canonical_result

            def tampering_verify(canon_path, plan):
                # Corrupt the just-written skill BEFORE the real check runs.
                (canon_path / "alpha" / "SKILL.md").write_text(
                    "tampered after sync", encoding="utf-8", newline="\n")
                return original_verify(canon_path, plan)

            with mock.patch.object(deploy, "verify_canonical_result",
                                   tampering_verify):
                rc, out, err = _run_canonical(deploy, root, ["--canonical"])
            self.assertNotEqual(rc, 0, "post-sync drift must fail the run")
            self.assertIn("VERIFY FAIL", out)
            # rollback semantics preserved: exact pre-sync state restored
            self.assertEqual(
                (canon / "alpha" / "SKILL.md").read_text(encoding="utf-8"),
                "old body")
            self.assertIn(
                '"9.9.9-test"',
                (canon / ".kit-manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("canonical sync complete", out)

    def test_successful_sync_passes_post_transaction_verification(self):
        """Happy path: the in-transaction verification inspects the real
        written state on every successful sync (observed via a spy) and a
        clean sync passes it end-to-end."""
        with tempfile.TemporaryDirectory(prefix="test-canonical-ok-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "final body"})
            deploy = load_deploy()
            seen = []

            def spy_verify(canon_path, plan):
                seen.append((canon_path, plan))
                # The destination now holds the freshly written copy:
                # assert the check observes the post-write state.
                self.assertTrue(
                    (canon_path / "alpha" / "SKILL.md").exists(),
                    "verification must run after the skill was written")
                self.assertEqual(
                    (canon_path / "alpha" / "SKILL.md").read_text(encoding="utf-8"),
                    "final body")
                return []

            with mock.patch.object(deploy, "verify_canonical_result",
                                   spy_verify):
                rc, out, err = _run_canonical(deploy, root, ["--canonical"])
            self.assertEqual(rc, 0, f"clean sync must succeed: {out}{err}")
            self.assertEqual(len(seen), 1,
                             "verification must run exactly once per sync")
            self.assertIn("canonical sync complete", out)
            self.assertEqual(
                (root / ".agents" / "skills" / "alpha" / "SKILL.md")
                .read_text(encoding="utf-8"),
                "final body")

    def test_verify_canonical_result_passes_on_exact_copy(self):
        with tempfile.TemporaryDirectory(prefix="test-canonical-vfy-") as td:
            root = Path(td)
            _make_kit(root, {"alpha": "x", "beta": "y"})
            deploy = load_deploy()
            canon = root / ".agents" / "skills"
            for slug, body in (("alpha", "x"), ("beta", "y")):
                (canon / slug).mkdir(parents=True)
                (canon / slug / "SKILL.md").write_text(
                    body, encoding="utf-8", newline="\n")
            (canon / ".kit-manifest.json").write_text(
                json.dumps({"kit_version": deploy.VERSION,
                            "skills": ["alpha", "beta"]}),
                encoding="utf-8", newline="\n")
            with mock.patch.object(deploy, "KIT", root), \
                    mock.patch.object(deploy, "SKILLS", root / "skills"):
                self.assertEqual(deploy.verify_canonical_result(canon, []), [])
            # and it catches each failure mode:
            (canon / "alpha" / "SKILL.md").write_text(
                "drifted", encoding="utf-8", newline="\n")
            with mock.patch.object(deploy, "KIT", root), \
                    mock.patch.object(deploy, "SKILLS", root / "skills"):
                errs = deploy.verify_canonical_result(canon, [])
            self.assertTrue(any("alpha" in e for e in errs), errs)

if __name__ == "__main__":
    unittest.main()
