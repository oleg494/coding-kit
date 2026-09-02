#!/usr/bin/env python3
"""tests/test_findings_secrets.py — P4: secret/PII lint at the write choke point.

Contract (plan docs/research/2026-09-02-memory-findings-remediation-plan.md):
- add/edit REFUSE credential-shaped text (rc=2), --force overrides;
- prose containing secret KEYWORDS without credential-shaped values passes;
- email/IPv4 warn on stderr but insert (server inventory is legitimate);
- search telemetry scrubs credential-shaped queries before search_log INSERT.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
DB_TOOLS = KIT / "memory" / "db-tools"
FINDINGS = DB_TOOLS / "findings.py"

if str(DB_TOOLS) not in sys.path:
    sys.path.insert(0, str(DB_TOOLS))


class SecretLintPureTest(unittest.TestCase):
    """find_secrets/scrub_text without any DB."""

    def setUp(self):
        import findings
        self.f = findings

    def test_token_shapes_block(self):
        # FIXTURES MUST NEVER CARRY A REAL CREDENTIAL — this repo has a public
        # origin; a real password in a test leaks on the next push (this exact
        # mistake was caught in review 2026-09-02). Synthetic value only,
        # shaped to satisfy _looks_secret (mixed case + digit, >=6 chars).
        for text in [
            "key AKIAIOSFODNN7EXAMPLE here",
            "ghp_0123456789abcdefghijABCDEFGHIJ",
            "-----BEGIN RSA PRIVATE KEY-----",
            "пароль Zq8XwVrTnLm -> свой hbbs",
            "password=hunter2x",
            "api_key: sk1234567890abcdef",
            "TOKEN=AbCdEfGh12",
            'password="hunter2x"',      # quoted value — the common capture shape
            "token='AbCdEfGh12'",
            # AWS secret access key: keyword carries underscores so \b
            # never fired (measured 2026-09-02); the value is base64-ish
            # (slash-heavy, digit-poor) and must NOT be pathish
            "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_secret_access_key wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            # multi-segment path WITHOUT extension in last segment is
            # credential-shaped, not a doc ref (the new _pathish rule)
            "password abc/def123",
        ]:
            secrets, _ = self.f.find_secrets(text)
            self.assertTrue(secrets, f"must block: {text!r}")

    def test_prose_passes(self):
        for text in [
            "token budget matters for LLM context",
            "the secret to good ranking is bm25",
            "Bearer tokens are stateless",
            "password managers store secrets",
            "пароль должен быть длинным",  # keyword, no value
            "reset the api key rotation policy",  # 'api key' + word 'rotation'
            # verified FP repros (review 2026-09-02): keyword at end +
            # dated/path value is a doc reference, not a credential
            "see the api token docs/v2.9-2026",
            "conclusion mentions the rotated api token "
            "docs/research/2026-09-02-memory-findings-remediation-plan.md",
            # port/URL shapes must not trip the credential-URL patterns
            "server at https://host:8080/path",
            "postgresql://localhost:5432/db without userinfo",
            # Windows path value: backslash separator + extension in the
            # last segment is pathish (the kit lives on Windows paths)
            "token C:\\Users\\oleg2\\Desktop\\docs\\notes.md",
        ]:
            secrets, _ = self.f.find_secrets(text)
            self.assertFalse(secrets, f"must NOT block prose: {text!r}")

    def test_credential_url_shapes_block(self):
        # canonical curl/DSN credential shapes (P15 makes verify_cmd shell=True)
        for text in [
            "curl -u user:Zq8XwVrTnLm host",
            "postgresql://user:Zq8XwVrTnLm@db.host/prod",
            "curl -H \"Authorization: token Zq8XwVrTnLm\" host",
            "PASSWORD=Zq8XwVrTnLm python probe.py",
        ]:
            secrets, _ = self.f.find_secrets(text)
            self.assertTrue(secrets, f"must block: {text!r}")

    def test_pii_warns_only(self):
        secrets, pii = self.f.find_secrets("mail oleg2200000@gmail.com ip 87.242.85.247")
        self.assertFalse(secrets)
        self.assertEqual(len(pii), 2)

    def test_scrub_text_redacts(self):
        self.assertEqual(self.f.scrub_text("normal query"), "normal query")
        self.assertEqual(self.f.scrub_text("password=hunter2x"), "***redacted***")

    def test_quoted_value_strips_before_shape_check(self):
        """The regex captures the wrapping quotes: val='"hunter2x"'. The
        alnum-start gate must see the STRIPPED value or the most common
        credential format slips through (verified bypass, review 2026-09-02)."""
        self.assertTrue(self.f._looks_secret('"hunter2x"'))
        self.assertTrue(self.f._looks_secret("'AbCdEfGh12'"))
        self.assertFalse(self.f._looks_secret('"-m 1983 (9)"'))


class SecretLintCLITest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-secrets-"))
        self.db_path = self.tmp / "research.db"
        self.env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db_path),
            PYTHONIOENCODING="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args, stdin=None):
        return subprocess.run(
            [sys.executable, str(FINDINGS)] + list(args),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=120, input=stdin,
        )

    def test_add_refuses_credential(self):
        # synthetic credential (see test_token_shapes_block comment)
        r = self._run("add", "rustdesk notes",
                      "--text", "пароль Zq8XwVrTnLm -> hbbs 1.2.3.4")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("possible secret", r.stderr)

    def test_add_force_overrides(self):
        r = self._run("add", "forced", "--text", "password=hunter2x", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("id=1", r.stdout)

    def test_add_pii_warns_but_inserts(self):
        r = self._run("add", "server inventory", "--text", "host 10.99.99.2 mail a@b.com")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PII note", r.stderr)
        self.assertIn("id=1", r.stdout)

    def test_edit_refuses_credential(self):
        self._run("add", "clean", "--text", "clean text")
        r = self._run("edit", "1", "--text", "api_key: sk1234567890abcdef")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        r2 = self._run("edit", "1", "--text", "still clean")
        self.assertEqual(r2.returncode, 0, r2.stderr)

    def test_search_telemetry_scrubs_query(self):
        self._run("add", "row", "--text", "text")
        # A credential-shaped query must still run, but search_log stores the
        # scrubbed form, not the raw secret. Space-separated because '=' is
        # FTS5 column-filter syntax (crashes MATCH before logging — D-B class).
        self._run("search", "password hunter2x")
        import sqlite3
        con = sqlite3.connect(self.db_path)
        logged = [q for (q,) in con.execute(
            "SELECT query FROM search_log ORDER BY id")]
        con.close()
        self.assertIn("***redacted***", logged)
        self.assertNotIn("password hunter2x", logged)

    def test_add_refuses_credential_in_verify_cmd(self):
        """cmd_verify prints verify_cmd verbatim to stdout on every re-verify,
        so it is a worse leak channel than text — must be scanned (verified
        bypass: add with clean --text but secret in --verify-cmd, review).
        Keyword+value shape: a bare high-entropy word without a keyword is
        NOT blocked by design (entropy-only would refuse legitimate prose)."""
        r = self._run("add", "deploy notes", "--text", "clean conclusion",
                      "--verify-cmd", "curl -u user:пароль Zq8XwVrTnLm host")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("possible secret", r.stderr)

    def test_edit_refuses_credential_in_topic_and_source(self):
        """edit scanned only --text; --topic/--source were a bypass. Now all
        whitelisted columns are scanned (add/edit choke-point symmetry)."""
        self._run("add", "clean", "--text", "clean text")
        r_topic = self._run("edit", "1", "--topic", "password=hunter2x")
        self.assertEqual(r_topic.returncode, 2, r_topic.stdout + r_topic.stderr)
        r_src = self._run("edit", "1", "--source", "api_key: sk1234567890abcdef")
        self.assertEqual(r_src.returncode, 2, r_src.stdout + r_src.stderr)
        r_ok = self._run("edit", "1", "--topic", "still clean")
        self.assertEqual(r_ok.returncode, 0, r_ok.stderr)

    def test_add_reflex_with_dated_source_passes(self):
        """The documented AGENTS.md reflex: --text ending in a keyword +
        --source dated path must NOT be refused (verified cross-field FP:
        joined scan let the regex bridge the boundary)."""
        r = self._run(
            "add", "lint lesson",
            "--text", "conclusion mentions the rotated api token",
            "--source", "docs/research/2026-09-02-memory-findings-remediation-plan.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("id=1", r.stdout)

    def test_add_refuses_credential_url_in_verify_cmd(self):
        """curl -u user:pass is the canonical verify_cmd shape and P15 will
        execute it with shell=True — must be caught by the credential-URL
        pattern, not just keyword+value."""
        r = self._run("add", "deploy notes", "--text", "clean conclusion",
                      "--verify-cmd", "curl -u user:Zq8XwVrTnLm host")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("possible secret", r.stderr)

if __name__ == "__main__":
    unittest.main()
