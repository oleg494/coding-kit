#!/usr/bin/env python3
"""Static contract tests for CI workflows (.github/workflows/test.yml and .github/workflows/evals.yml).

Ensures:
- Read-only contents permission (no repository modification rights).
- Both Ubuntu and Windows matrix OSes.
- Dry-only validation boundary (live executors and shared-store writes forbidden).
- Pytest installation precedes the test job.
- Uploads eval artifacts (trap/tasks/trigger dry JSON) via actions/upload-artifact@v4
  from the CI-only eval/ci-results dir, failing if missing (evals.yml).
- Absolute absence of live executor inputs, secret-bearing env, live runs,
  git commit/push steps, --json auto (shared-store pollution), and OS-specific branch skips.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALS_WORKFLOW = ROOT / ".github" / "workflows" / "evals.yml"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
ALL_WORKFLOWS = [TEST_WORKFLOW, EVALS_WORKFLOW]


class TestCIWorkflow(unittest.TestCase):
    """Static security and contract tests for CI workflows."""

    @classmethod
    def setUpClass(cls):
        cls.workflows = {}
        for path in ALL_WORKFLOWS:
            if not path.exists():
                raise FileNotFoundError(f"Workflow file missing: {path}")
            cls.workflows[path.name] = path.read_text(encoding="utf-8")
        cls.evals_content = cls.workflows["evals.yml"]
        cls.test_content = cls.workflows["test.yml"]

    def test_workflow_files_exist(self):
        """Workflow files exist at .github/workflows/test.yml and evals.yml."""
        for path in ALL_WORKFLOWS:
            with self.subTest(workflow=path.name):
                self.assertTrue(path.is_file(), f"{path.name} must exist")

    def test_top_level_read_only_permissions(self):
        """Workflows must explicitly enforce top-level read-only permissions."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertRegex(
                    content,
                    r"permissions:\s*\n\s*contents:\s*read",
                    f"Top-level permissions in {name} must be 'contents: read'",
                )

    def test_matrix_includes_both_oses(self):
        """Matrix must include both ubuntu-latest and windows-latest."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertIn("ubuntu-latest", content, f"Matrix in {name} must include ubuntu-latest")
                self.assertIn("windows-latest", content, f"Matrix in {name} must include windows-latest")
                self.assertRegex(
                    content,
                    r"os:\s*\[\s*(ubuntu-latest,\s*windows-latest|windows-latest,\s*ubuntu-latest)\s*\]|"
                    r"os:\s*\n\s*-\s*ubuntu-latest\s*\n\s*-\s*windows-latest|"
                    r"os:\s*\n\s*-\s*windows-latest\s*\n\s*-\s*ubuntu-latest",
                    f"Matrix in {name} must define both OS legs",
                )



    def test_installs_pytest_before_running_tests(self):
        """Clean GitHub runners must install the declared test dependency."""
        install = "python -m pip install pytest"
        tests = "python -m pytest tests -q"
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertIn(install, content, f"{name} must install pytest")
                self.assertLess(
                    content.index(install),
                    content.index(tests),
                    f"{name} must install pytest before running tests",
                )
    def test_uses_pytest_not_unittest(self):
        """Workflows must use pytest rather than unittest."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertIn(
                    "python -m pytest tests -q",
                    content,
                    f"{name} must use 'python -m pytest tests -q'",
                )
                self.assertNotIn(
                    "unittest",
                    content,
                    f"{name} must not use unittest in test step",
                )

    def test_artifact_upload_v4_configuration(self):
        """Artifact upload in evals.yml must use upload-artifact@v4 against the CI-only dir and fail if missing."""
        self.assertIn(
            "uses: actions/upload-artifact@v4",
            self.evals_content,
            "evals.yml must use actions/upload-artifact@v4",
        )
        self.assertRegex(
            self.evals_content,
            r"if-no-files-found:\s*error",
            "evals.yml artifact upload must fail when eval/ci-results is missing",
        )
        self.assertNotRegex(
            self.evals_content,
            r"if-no-files-found:\s*ignore",
            "evals.yml artifact upload must reject 'if-no-files-found: ignore'",
        )
        self.assertIn(
            "eval/ci-results",
            self.evals_content,
            "evals.yml artifact upload path must target the CI-only 'eval/ci-results' dir",
        )

    def test_absence_of_live_executor_inputs(self):
        """Workflows must not declare workflow_dispatch executor inputs."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertNotIn(
                    "executor:",
                    content,
                    f"{name} must not have executor input in workflow_dispatch",
                )
                self.assertNotIn(
                    "live_windows",
                    content,
                    f"{name} must not have live_windows input",
                )
                self.assertNotRegex(
                    content,
                    r"workflow_dispatch:\s*\n\s*inputs:",
                    f"{name} workflow_dispatch must not have inputs for arbitrary executor execution",
                )

    def test_absence_of_live_execution_flags(self):
        """Dry workflow steps must not invoke live execution flags."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertNotIn(
                    "--executor",
                    content,
                    f"{name} must not pass --executor in CI",
                )
                self.assertNotIn(
                    "EXECUTOR:",
                    content,
                    f"{name} must not expose EXECUTOR env var",
                )

    def test_absence_of_git_writes_and_push(self):
        """Workflows must not commit, configure git, or push to repository."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertNotIn("git push", content, f"{name} must not git push")
                self.assertNotIn("git commit", content, f"{name} must not git commit")
                self.assertNotIn("git config", content, f"{name} must not configure git bot")
                self.assertNotIn("git add", content, f"{name} must not git add")

    def test_no_json_auto_or_test_gate_json(self):
        """Dry CI must never use '--json auto'; the push/PR gate (test.yml) emits no JSON and never touches the shared store."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertNotIn(
                    "--json auto",
                    content,
                    f"{name} must not request '--json auto' (shared-store pollution)",
                )
                self.assertNotIn(
                    "eval/results",
                    content,
                    f"{name} must not write the shared 'eval/results' store",
                )
        self.assertNotIn(
            "--json",
            self.test_content,
            "test.yml (push/PR gate) must run producers dry with no JSON persistence",
        )

    def test_absence_of_mixed_os_shell_logic(self):
        """No shell-specific branching or OS skips in workflow steps."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertNotIn(
                    "live_windows",
                    content,
                    f"{name} must not have OS-specific live skipping logic",
                )
                self.assertNotIn(
                    "eval/trend.py",
                    content,
                    f"{name} must not generate trend reports",
                )

    def test_absence_of_secrets_and_api_keys(self):
        """Workflows must not reference secrets or API key environment variables."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertNotIn("secrets.", content.lower(), f"{name} must not reference GitHub secrets")
                self.assertNotIn("api_key", content.lower(), f"{name} must not reference API keys")

    def test_absence_of_write_permissions(self):
        """Workflows must not grant write permissions anywhere."""
        for name, content in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertNotIn("write", content, f"{name} must not grant write permissions")


if __name__ == "__main__":
    unittest.main()
