"""Backup/DR for the memory pillar (wave1 Task 4) — red-first tests.

Covers: SQLite online-backup API usage (never a raw copy of a live db),
corrupt-then-restore drill with a search probe, doctor WARN rows."""
import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tools"))
import backup_memory

KIT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "doctor", KIT / "scripts" / "doctor.py")
doctor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(doctor)


def _seed_memory_root(tmp: Path) -> Path:
    """Wiki tree + one research.db with a findable row + one junk file."""
    root = tmp / "memory"
    (root / "Wiki").mkdir(parents=True)
    (root / "Wiki" / "index.md").write_text("# index\ntest-entry\n",
                                             encoding="utf-8")
    (root / "db").mkdir()
    con = sqlite3.connect(root / "db" / "research.db")
    con.executescript(
        "CREATE TABLE findings (id INTEGER PRIMARY KEY, topic TEXT,"
        " text TEXT);"
        "INSERT INTO findings (topic, text) VALUES ('test-topic',"
        " 'test-conclusion-body');")
    con.commit()
    con.close()
    (root / "notes.txt").write_text("plain file", encoding="utf-8")
    return root


class BackupDrillTest(unittest.TestCase):
    def test_backup_then_corrupt_then_restore_drill(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                # Backup (SQLite online-backup API — never a raw copy)
                result = backup_memory.backup(dest=tmp / "dest", root=root)
                self.assertTrue((Path(result["path"]) / "notes.txt").is_file())
                self.assertGreaterEqual(result["dbs"], 1)
                # The BACKUP copy itself must already be readable + intact.
                con = sqlite3.connect(
                    str(Path(result["path"]) / "db" / "research.db"))
                rows = con.execute(
                    "SELECT topic, text FROM findings").fetchall()
                con.close()
                self.assertEqual(rows,
                                 [("test-topic", "test-conclusion-body")])

                # Corrupt the ORIGINAL db (the DR scenario), then drill:
                # restore into a temp root and verify integrity there.
                (root / "db" / "research.db").write_bytes(b"garbage")
                drill = backup_memory.restore_drill(
                    Path(result["path"]), root=root)
                self.assertTrue(drill["integrity_ok"],
                                "restored db must pass integrity_check")
                self.assertGreaterEqual(drill["dbs"], 1)
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_backup_skips_backups_dir_and_caches(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                first = backup_memory.backup(dest=tmp / "dest", root=root)
                # Second backup into the SAME dest must not recurse into
                # the first backup (no backups-in-backup).
                second = backup_memory.backup(dest=tmp / "dest", root=root)
                self.assertNotEqual(first["path"], second["path"])
                self.assertFalse(
                    Path(second["path"], "backups").exists(),
                    "nested backups dir leaked into the backup")
            finally:
                os.environ.pop("MEMORY_ROOT", None)


class DoctorBackupFreshnessTest(unittest.TestCase):
    def test_warns_when_no_backups(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            doctor.KIT = KIT  # keep real kit path for tool lookup
            import os
            old = os.environ.get("MEMORY_ROOT")
            os.environ["MEMORY_ROOT"] = str(Path(tmp) / "memory")
            try:
                ok, detail = doctor.check_backup_freshness()
                self.assertTrue(ok, "WARN-tier must keep doctor green")
                self.assertIn("WARN", detail)
            finally:
                if old is None:
                    os.environ.pop("MEMORY_ROOT", None)
                else:
                    os.environ["MEMORY_ROOT"] = old

    def test_green_when_backup_fresh(self):
        import tempfile
        import time as _time
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "memory"
            (root / "backups" / _time.strftime("%Y%m%dT%H%M%S")).mkdir(
                parents=True)
            import os
            old = os.environ.get("MEMORY_ROOT")
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                ok, detail = doctor.check_backup_freshness()
                self.assertTrue(ok)
                self.assertNotIn("WARN", detail)
            finally:
                if old is None:
                    os.environ.pop("MEMORY_ROOT", None)
                else:
                    os.environ["MEMORY_ROOT"] = old

    def test_warns_when_backup_stale(self):
        import datetime
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "memory"
            old_stamp = (datetime.datetime.now()  # noqa: DTZ005
                         - datetime.timedelta(days=30)).strftime(
                "%Y%m%dT%H%M%S")
            (root / "backups" / old_stamp).mkdir(parents=True)
            import os
            old = os.environ.get("MEMORY_ROOT")
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                ok, detail = doctor.check_backup_freshness()
                self.assertTrue(ok, "WARN-tier stays green")
                self.assertIn("WARN", detail)
            finally:
                if old is None:
                    os.environ.pop("MEMORY_ROOT", None)
                else:
                    os.environ["MEMORY_ROOT"] = old


if __name__ == "__main__":
    unittest.main()
