import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Set up imports from coding-kit
import sys
KIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT_ROOT / "memory" / "db-tools"))
sys.path.insert(0, str(KIT_ROOT / "memory" / "scripts"))

import findings_db
import findings
import search_all

class MemoryOrganizationTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="test_mem_org_")
        self.db_path = os.path.join(self.tmpdir, "research.db")
        os.environ["MEMORY_ROOT_RESEARCH_DB"] = self.db_path
        findings_db.DB = self.db_path

    def tearDown(self):
        findings_db.DB = findings_db.research_db_path()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_schema_migration_adds_columns_and_indices(self):
        con = findings_db.connect()
        cols = {r[1]: r[2] for r in con.execute("PRAGMA table_info(findings)")}
        self.assertIn("project", cols)
        self.assertIn("importance", cols)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertIn("finding_classifications", tables)
        con.close()

    def test_add_finding_with_project_and_importance(self):
        con = findings_db.connect()
        con.close()

        args = findings.arg_parser().parse_args([
            "add", "test-topic", "--text", "sample finding text",
            "--project", "coding-kit", "--importance", "high"
        ])
        findings.cmd_add(args)

        con = findings_db.connect_read()
        row = con.execute("SELECT * FROM findings WHERE topic='test-topic'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["project"], "coding-kit")
        self.assertEqual(row["importance"], "high")

        # Verify audit trail
        audit = con.execute("SELECT * FROM finding_classifications WHERE finding_id=?", (row["id"],)).fetchone()
        self.assertIsNotNone(audit)
        self.assertEqual(audit["project"], "coding-kit")
        self.assertEqual(audit["importance"], "high")
        con.close()

    def test_edit_validates_importance_and_updates_audit(self):
        con = findings_db.connect()
        con.close()

        # Add initial
        args = findings.arg_parser().parse_args([
            "add", "edit-topic", "--text", "initial body",
            "--project", "portable", "--importance", "normal"
        ])
        findings.cmd_add(args)

        con = findings_db.connect_read()
        fid = con.execute("SELECT id FROM findings WHERE topic='edit-topic'").fetchone()["id"]
        con.close()

        # Invalid importance should be rejected (exit 2)
        args_invalid = findings.arg_parser().parse_args([
            "edit", str(fid), "--importance", "bogus-level"
        ])
        with self.assertRaises(SystemExit) as cm:
            findings.cmd_edit(args_invalid)
        self.assertEqual(cm.exception.code, 2)

        # Valid edit
        args_valid = findings.arg_parser().parse_args([
            "edit", str(fid), "--project", "coding-kit", "--importance", "high"
        ])
        findings.cmd_edit(args_valid)

        con = findings_db.connect_read()
        row = con.execute("SELECT * FROM findings WHERE id=?", (fid,)).fetchone()
        self.assertEqual(row["project"], "coding-kit")
        self.assertEqual(row["importance"], "high")

        # Verify updated audit trail
        audit = con.execute("SELECT * FROM finding_classifications WHERE finding_id=?", (fid,)).fetchone()
        self.assertEqual(audit["project"], "coding-kit")
        self.assertEqual(audit["importance"], "high")
        self.assertEqual(audit["project_provenance"], "cli_edit")
        con.close()

    def test_legacy_ro_projection_defaults(self):
        # Create a legacy DB without project or importance
        legacy_path = os.path.join(self.tmpdir, "legacy.db")
        con = sqlite3.connect(legacy_path)
        con.execute("""
            CREATE TABLE findings (
                id INTEGER PRIMARY KEY,
                created TEXT NOT NULL,
                topic TEXT NOT NULL,
                text TEXT NOT NULL,
                tags TEXT DEFAULT '',
                source TEXT DEFAULT '',
                file TEXT DEFAULT '',
                symbol TEXT DEFAULT '',
                verify_cmd TEXT DEFAULT '',
                verified_at TEXT DEFAULT ''
            );
        """)
        con.execute("CREATE VIRTUAL TABLE findings_fts USING fts5(topic, text, content='findings', content_rowid='id');")
        con.execute("INSERT INTO findings (id, created, topic, text) VALUES (1, '2026-09-01', 'legacy-t', 'legacy-body');")
        con.execute("INSERT INTO findings_fts(rowid, topic, text) VALUES (1, 'legacy-t', 'legacy-body');")
        con.commit()
        con.close()

        # search_findings in ro mode against legacy DB should return defaults without OperationalError
        hits = search_all.search_findings("legacy", limit=5, research_db=legacy_path)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].meta.get("project"), "unknown")
        self.assertEqual(hits[0].meta.get("importance"), "unreviewed")

    def test_batch_classify_atomic_rollback_on_error(self):
        con = findings_db.connect()
        con.close()

        args1 = findings.arg_parser().parse_args([
            "add", "item-1", "--text", "body 1", "--project", "unknown", "--importance", "unreviewed"
        ])
        findings.cmd_add(args1)

        # Batch with valid first row and invalid second row
        bad_batch = [
            {"id": 1, "project": "coding-kit", "importance": "high", "rationale": "first"},
            {"id": 999, "project": "invalid slug with spaces", "importance": "high", "rationale": "second"}
        ]
        batch_file = os.path.join(self.tmpdir, "bad_batch.json")
        with open(batch_file, "w", encoding="utf-8") as fp:
            json.dump(bad_batch, fp)

        args_classify = findings.arg_parser().parse_args([
            "classify", batch_file
        ])
        with self.assertRaises(SystemExit):
            findings.cmd_classify(args_classify)

        # Confirm atomicity: item 1 must NOT have been updated
        con = findings_db.connect_read()
        row = con.execute("SELECT project, importance FROM findings WHERE id=1").fetchone()
        self.assertEqual(row["project"], "unknown")
        self.assertEqual(row["importance"], "unreviewed")
        con.close()

    def test_batch_classify_idempotent_preserves_user_curated(self):
        con = findings_db.connect()
        con.close()

        # Add two findings
        args1 = findings.arg_parser().parse_args([
            "add", "item-1", "--text", "body 1", "--project", "user-proj", "--importance", "high"
        ])
        findings.cmd_add(args1)

        args2 = findings.arg_parser().parse_args([
            "add", "item-2", "--text", "body 2", "--project", "unknown", "--importance", "unreviewed"
        ])
        findings.cmd_add(args2)

        # Batch attempting to overwrite item 1 and item 2
        batch = [
            {"id": 1, "project": "overwritten-proj", "importance": "low", "rationale": "try overwrite"},
            {"id": 2, "project": "coding-kit", "importance": "normal", "rationale": "classify item 2"}
        ]
        batch_file = os.path.join(self.tmpdir, "batch.json")
        with open(batch_file, "w", encoding="utf-8") as fp:
            json.dump(batch, fp)

        args_classify = findings.arg_parser().parse_args([
            "classify", batch_file
        ])
        findings.cmd_classify(args_classify)

        con = findings_db.connect_read()
        r1 = con.execute("SELECT project, importance FROM findings WHERE id=1").fetchone()
        self.assertEqual(r1["project"], "user-proj")
        self.assertEqual(r1["importance"], "high")

        r2 = con.execute("SELECT project, importance FROM findings WHERE id=2").fetchone()
        self.assertEqual(r2["project"], "coding-kit")
        self.assertEqual(r2["importance"], "normal")
        con.close()

    def test_classify_preserves_project_when_importance_unreviewed(self):
        con = findings_db.connect()
        con.close()
        # Add finding with user-chosen project but unreviewed importance
        args = findings.arg_parser().parse_args([
            "add", "proj-only", "--text", "some text", "--project", "user-proj", "--importance", "unreviewed"
        ])
        findings.cmd_add(args)

        # Batch trying to classify without --force
        batch = [{"id": 1, "project": "overwritten", "importance": "high", "rationale": "try overwrite"}]
        batch_file = os.path.join(self.tmpdir, "batch_p.json")
        with open(batch_file, "w", encoding="utf-8") as fp:
            json.dump(batch, fp)

        findings.cmd_classify(findings.arg_parser().parse_args(["classify", batch_file]))
        con = findings_db.connect_read()
        r = con.execute("SELECT project, importance FROM findings WHERE id=1").fetchone()
        # User project must be preserved!
        self.assertEqual(r["project"], "user-proj")
        self.assertEqual(r["importance"], "unreviewed")
        con.close()

    def test_classify_rejects_missing_finding_id_without_mutation(self):
        con = findings_db.connect()
        con.close()
        args = findings.arg_parser().parse_args([
            "add", "exist-1", "--text", "body", "--project", "unknown", "--importance", "unreviewed"
        ])
        findings.cmd_add(args)

        # Batch with valid id=1 but nonexistent id=999
        batch = [
            {"id": 1, "project": "coding-kit", "importance": "high", "rationale": "valid"},
            {"id": 999, "project": "coding-kit", "importance": "high", "rationale": "nonexistent"}
        ]
        batch_file = os.path.join(self.tmpdir, "batch_missing.json")
        with open(batch_file, "w", encoding="utf-8") as fp:
            json.dump(batch, fp)

        with self.assertRaises(SystemExit):
            findings.cmd_classify(findings.arg_parser().parse_args(["classify", batch_file]))

        con = findings_db.connect_read()
        r = con.execute("SELECT project, importance FROM findings WHERE id=1").fetchone()
        # Atomic rollback / zero mutation: id=1 was not modified
        self.assertEqual(r["project"], "unknown")
        self.assertEqual(r["importance"], "unreviewed")
        con.close()

    def test_classify_rejects_duplicate_ids_in_batch(self):
        batch = [
            {"id": 1, "project": "coding-kit", "importance": "high", "rationale": "first"},
            {"id": 1, "project": "portable", "importance": "low", "rationale": "second"}
        ]
        batch_file = os.path.join(self.tmpdir, "batch_dup.json")
        with open(batch_file, "w", encoding="utf-8") as fp:
            json.dump(batch, fp)

        with self.assertRaises(SystemExit):
            findings.cmd_classify(findings.arg_parser().parse_args(["classify", batch_file]))

    def test_classify_rejects_boolean_or_malformed_ids(self):
        batch = [{"id": True, "project": "coding-kit", "importance": "high", "rationale": "bool id"}]
        batch_file = os.path.join(self.tmpdir, "batch_bool.json")
        with open(batch_file, "w", encoding="utf-8") as fp:
            json.dump(batch, fp)

        with self.assertRaises(SystemExit):
            findings.cmd_classify(findings.arg_parser().parse_args(["classify", batch_file]))

    def test_classify_dry_run_does_not_mutate_legacy_database_bytes(self):
        import hashlib
        legacy_path = os.path.join(self.tmpdir, "legacy_dry.db")
        con = sqlite3.connect(legacy_path)
        con.execute("CREATE TABLE findings (id INTEGER PRIMARY KEY, topic TEXT, text TEXT);")
        con.execute("INSERT INTO findings VALUES (1, 't', 'b');")
        con.commit()
        con.close()

        with open(legacy_path, "rb") as fp:
            orig_hash = hashlib.sha256(fp.read()).hexdigest()

        findings_db.DB = legacy_path
        batch = [{"id": 1, "project": "coding-kit", "importance": "high", "rationale": "dry"}]
        batch_file = os.path.join(self.tmpdir, "batch_dry.json")
        with open(batch_file, "w", encoding="utf-8") as fp:
            json.dump(batch, fp)

        findings.cmd_classify(findings.arg_parser().parse_args(["classify", batch_file, "--dry-run"]))

        with open(legacy_path, "rb") as fp:
            post_hash = hashlib.sha256(fp.read()).hexdigest()
        self.assertEqual(orig_hash, post_hash, "Dry-run must not mutate legacy DB bytes or schema")

    def test_classify_evidence_secrets_lint(self):
        con = findings_db.connect()
        con.close()
        args = findings.arg_parser().parse_args([
            "add", "item-sec", "--text", "normal text", "--project", "unknown", "--importance", "unreviewed"
        ])
        findings.cmd_add(args)

        # Rationale containing credential shape
        batch = [{"id": 1, "project": "coding-kit", "importance": "high", "rationale": "password=supersecret123"}]
        batch_file = os.path.join(self.tmpdir, "batch_sec.json")
        with open(batch_file, "w", encoding="utf-8") as fp:
            json.dump(batch, fp)

        with self.assertRaises(SystemExit) as cm:
            findings.cmd_classify(findings.arg_parser().parse_args(["classify", batch_file]))
        self.assertEqual(cm.exception.code, 2)

    def test_legacy_ro_findings_list_and_search_no_columns(self):
        legacy_path = os.path.join(self.tmpdir, "legacy_ro_findings.db")
        con = sqlite3.connect(legacy_path)
        con.execute("""
            CREATE TABLE findings (
                id INTEGER PRIMARY KEY,
                created TEXT NOT NULL,
                topic TEXT NOT NULL,
                text TEXT NOT NULL,
                tags TEXT DEFAULT '',
                source TEXT DEFAULT '',
                file TEXT DEFAULT '',
                symbol TEXT DEFAULT '',
                verify_cmd TEXT DEFAULT '',
                verified_at TEXT DEFAULT ''
            );
        """)
        con.execute("CREATE VIRTUAL TABLE findings_fts USING fts5(topic, text, content='findings', content_rowid='id');")
        con.execute("INSERT INTO findings VALUES (1, '2026-09-01', 'legacy-t', 'legacy-body', '', '', '', '', '', '');")
        con.execute("INSERT INTO findings_fts(rowid, topic, text) VALUES (1, 'legacy-t', 'legacy-body');")
        con.commit()
        con.close()

        findings_db.DB = legacy_path
        # cmd_list and cmd_search must succeed without crashing or mutating
        args_list = findings.arg_parser().parse_args(["list", "--limit", "10"])
        findings.cmd_list(args_list)

        args_search = findings.arg_parser().parse_args(["search", "legacy-body"])
        findings.cmd_search(args_search)

    def test_search_all_project_and_importance_filtering(self):
        con = findings_db.connect()
        con.close()

        args1 = findings.arg_parser().parse_args([
            "add", "high-perf", "--text", "important performance finding",
            "--project", "multiproxy", "--importance", "high"
        ])
        findings.cmd_add(args1)

        args2 = findings.arg_parser().parse_args([
            "add", "normal-perf", "--text", "standard performance note",
            "--project", "coding-kit", "--importance", "normal"
        ])
        findings.cmd_add(args2)

        # Filter by project multiproxy
        hits_mp = search_all.search_all("performance", research_db=self.db_path, project="multiproxy")
        self.assertEqual(len(hits_mp), 1)
        self.assertIn("finding#1", hits_mp[0][2])

        # Filter by importance high
        hits_high = search_all.search_all("performance", research_db=self.db_path, importance="high")
        self.assertEqual(len(hits_high), 1)
        self.assertEqual(hits_high[0].meta.get("importance"), "high")
if __name__ == "__main__":
    unittest.main()
