"""Backup/DR for the memory pillar (wave1 Task 4) — red-first tests.

Covers: SQLite online-backup API usage (never a raw copy of a live db),
corrupt-then-restore drill with a search probe, doctor WARN rows."""
import importlib.util
import shutil
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
    """Wiki tree + one research.db with a findable row + one junk file.
    The findings table comes from the PROD schema (findings_db.SCHEMA):
    the drill's findings probe runs the real search CLI, whose SQL needs
    created/tags/source — a bare (id, topic, text) seed searches as
    'no such column: f.created'."""
    root = tmp / "memory"
    (root / "Wiki").mkdir(parents=True)
    (root / "Wiki" / "index.md").write_text("# index\ntest-entry\n",
                                             encoding="utf-8")
    (root / "db").mkdir()
    db_tools = KIT / "memory" / "db-tools"
    if str(db_tools) not in sys.path:
        sys.path.insert(0, str(db_tools))
    import findings_db
    con = sqlite3.connect(root / "db" / "research.db")
    con.executescript(findings_db.SCHEMA)
    con.execute(
        "INSERT INTO findings (created, topic, text) VALUES "
        "('2026-09-01', 'test-topic', 'test-conclusion-body');")
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
                # core scope: research.db + Wiki only — notes.txt is NOT
                # memory data; --full restores the old whole-root walk
                self.assertEqual(result["scope"], "core")
                self.assertFalse(
                    (Path(result["path"]) / "notes.txt").exists())
                self.assertTrue((Path(result["path"]) / "Wiki"
                                 / "index.md").is_file())
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

    def test_backup_skips_sqlite_sidecars_and_writes_completion_marker(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            (root / "db" / "research.db-wal").write_bytes(b"live wal")
            (root / "db" / "research.db-shm").write_bytes(b"live shm")
            result = backup_memory.backup(dest=tmp / "dest", root=root)
            saved = Path(result["path"])
            self.assertTrue((saved / ".complete").is_file())
            self.assertFalse((saved / "db" / "research.db-wal").exists())
            self.assertFalse((saved / "db" / "research.db-shm").exists())

    def test_corrupt_restored_db_reports_failed_integrity(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            result = backup_memory.backup(dest=tmp / "dest", root=root)
            (Path(result["path"]) / "db" / "research.db").write_bytes(
                b"not sqlite")
            drill = backup_memory.restore_drill(
                Path(result["path"]), root=root)
        self.assertFalse(drill["integrity_ok"])

    def test_drill_findings_probe_sees_restored_rows(self):
        """search_all is blind to research.db (no files_fts): the drill's
        findings probe must certify the restored store end-to-end — raw
        rank=1 content check, doctor rc, and a MATCH hit on a token
        DERIVED from the restored rows (real backups carry real findings,
        never test literals)."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest", root=root)
                drill = backup_memory.restore_drill(
                    Path(result["path"]), root=root)
                f = drill["findings"]
                self.assertTrue(f["present"], f)
                self.assertTrue(f["ok"], f)
                self.assertEqual(f["raw_rank1"], "passed")
                self.assertEqual(f["doctor_rc"], 0)
                self.assertEqual(f["search_token"], "test")
                self.assertGreaterEqual(f["search_hits"], 1)
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_drill_findings_probe_flags_empty_index(self):
        """D-C on arrival: a backup whose FTS index is empty over non-empty
        content must FAIL the drill, not certify it — the exact scenario
        search_all + PRAGMA integrity_check both miss."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            con = sqlite3.connect(root / "db" / "research.db")
            con.execute("DELETE FROM findings_fts WHERE rowid = 1")
            con.commit()
            con.close()
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest", root=root)
                drill = backup_memory.restore_drill(
                    Path(result["path"]), root=root)
                f = drill["findings"]
                self.assertFalse(f["ok"], f)
                self.assertIn("failed", f["raw_rank1"])
                self.assertEqual(
                    backup_memory.main(
                        ["--restore-drill", str(Path(result["path"]))]), 1)
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_core_vs_full_scope(self):
        """Core backup = research.db + Wiki (the only non-rebuildable
        state); --full must still carry everything else."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                core = backup_memory.backup(dest=tmp / "c", root=root)
                full = backup_memory.backup(dest=tmp / "f", root=root,
                                            full=True)
                self.assertEqual(core["scope"], "core")
                self.assertEqual(full["scope"], "full")
                self.assertFalse((Path(core["path"]) / "notes.txt").exists())
                self.assertTrue((Path(full["path"]) / "notes.txt").is_file())
                self.assertTrue(
                    (Path(core["path"]) / "db" / "research.db").is_file())
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_offsite_second_copy(self):
        """MEMORY_ROOT_BACKUP_DEST puts a second copy OUTSIDE the backups
        folder (plan P6, no cloud by constraint); absent env -> None."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            off = tmp / "offsite"
            os.environ["MEMORY_ROOT"] = str(root)
            os.environ["MEMORY_ROOT_BACKUP_DEST"] = str(off)
            try:
                result = backup_memory.backup(dest=tmp / "dest", root=root)
                self.assertIsNotNone(result["offsite"])
                self.assertTrue(
                    (Path(result["offsite"]) / "db"
                     / "research.db").is_file())
                self.assertTrue(
                    str(Path(result["offsite"])).startswith(str(off)))
            finally:
                os.environ.pop("MEMORY_ROOT", None)
                os.environ.pop("MEMORY_ROOT_BACKUP_DEST", None)

    def test_restore_live_with_pre_snapshot_and_verify(self):
        """Live restore: pre-restore snapshot FIRST, then replace, then
        the findings probe certifies the live store (P5 heals pre-FTS
        indexes on first connect)."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest", root=root)
                # mutate the live store so restore has something to undo
                con = sqlite3.connect(root / "db" / "research.db")
                con.execute("DELETE FROM findings WHERE id = 1")
                con.commit()
                con.close()
                out = backup_memory.restore(Path(result["path"]),
                                            root=root)
                self.assertTrue(out["verify"]["ok"], out)
                self.assertTrue(any("pre-restore" in n for n in
                                    [p.name for p in
                                     (root / "backups").iterdir()]),
                                "pre-restore snapshot must exist")
                con = sqlite3.connect(root / "db" / "research.db")
                rows = con.execute(
                    "SELECT topic FROM findings").fetchall()
                con.close()
                self.assertEqual([r[0] for r in rows], ["test-topic"])
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_restore_heals_corrupt_live_db(self):
        """The DR case: live research.db is garbage. Restore must replace
        it (unlink + sidecars, not crash on the copy) and verify green."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest", root=root)
                (root / "db" / "research.db").write_bytes(b"garbage")
                (root / "db" / "research.db-wal").write_bytes(b"wal")
                out = backup_memory.restore(Path(result["path"]),
                                            root=root)
                self.assertTrue(out["verify"]["ok"], out)
                self.assertIn("db/research.db", out["restored"])
                self.assertFalse(
                    (root / "db" / "research.db-wal").exists())
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_drill_on_core_backup_without_markers(self):
        """Core backups carry no root markers (VERSION/db-tools/
        scripts/_compat.py); search_all.py validates MEMORY_ROOT at
        import, so the search probe must SKIP, not traceback — a healthy
        core restore must drill rc 0 (advisory 2026-09-03)."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest", root=root)
                # put the REAL tool in the seed so probe["exists"] is
                # True: without db-tools/ the subprocess never launches
                # and the skip semantics stay unpinned (advisory
                # 2026-09-03)
                (root / "db-tools").mkdir()
                shutil.copy2(KIT / "memory" / "db-tools" / "search_all.py",
                             root / "db-tools" / "search_all.py")
                rc = backup_memory.main(
                    ["--restore-drill", str(Path(result["path"]))])
                self.assertEqual(rc, 0, "healthy core restore must drill 0")
                drill = backup_memory.restore_drill(
                    Path(result["path"]), root=root)
                self.assertTrue(drill["probe"]["exists"])
                self.assertTrue(drill["probe"]["skipped"])
                self.assertNotIn("returncode", drill["probe"],
                                 "marker-less restore must skip, not run")
                self.assertTrue(drill["findings"]["ok"])
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_restore_refuses_when_live_db_locked(self):
        """A BUSY live db must abort the restore: backup() tags the
        skip 'LOCKED', and a safety snapshot without the store is no
        safety copy (advisory 2026-09-03). Live bytes must survive."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest",
                                              root=root)
                live = root / "db" / "research.db"
                before = live.read_bytes()
                lock = sqlite3.connect(str(live), timeout=0.2)
                lock.execute("BEGIN EXCLUSIVE")
                try:
                    with self.assertRaises(RuntimeError):
                        backup_memory.restore(Path(result["path"]),
                                              root=root)
                finally:
                    lock.close()
                self.assertEqual(live.read_bytes(), before)
                hollow = [p for p in (root / "backups").iterdir()
                          if "-pre-restore" in p.name
                          and not (p / "db" / "research.db").is_file()]
                self.assertEqual(hollow, [],
                                 "hollow snapshot must be dropped")
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_restore_refuses_when_snapshot_reports_locked(self):
        """Deterministic pin of the refuse logic (advisory 2026-09-03):
        a snapshot whose db leg is tagged LOCKED must abort the restore,
        drop the hollow snapshot and leave the live bytes untouched —
        no real lock timing involved."""
        import os
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest",
                                              root=root)
                live = root / "db" / "research.db"
                before = live.read_bytes()
                with mock.patch.object(
                        backup_memory, "_backup_db",
                        side_effect=sqlite3.OperationalError(
                            "database is locked")):
                    with self.assertRaises(RuntimeError):
                        backup_memory.restore(Path(result["path"]),
                                              root=root)
                self.assertEqual(live.read_bytes(), before)
                hollow = [p for p in (root / "backups").iterdir()
                          if "-pre-restore" in p.name
                          and not (p / "db" / "research.db").is_file()]
                self.assertEqual(hollow, [])
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_restore_corrupt_live_degrades_snapshot_record(self):
        """The DR case: damaged live db -> snapshot degrades to a
        pre_restore_skipped record (not an abort), restore proceeds."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest",
                                              root=root)
                (root / "db" / "research.db").write_bytes(b"garbage")
                out = backup_memory.restore(Path(result["path"]),
                                            root=root)
                # the snapshot EXISTS (Wiki etc.) but carries no store:
                # the CORRUPT record is the signal, not a missing name
                self.assertIn("CORRUPT", out["pre_restore_skipped"])
                pre_dir = root / "backups" / out["pre_restore"]
                self.assertTrue(pre_dir.is_dir())
                self.assertFalse((pre_dir / "db" / "research.db").exists(),
                                 "hollow snapshot must carry no store")
                self.assertTrue((pre_dir / ".degraded").is_file(),
                                "hollow snapshot must not graduate")
                self.assertTrue(out["verify"]["ok"], out)
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_restore_non_tty_refuses_without_yes(self):
        """Non-interactive --restore gets rc 2 'refused', not EOFError
        (advisory 2026-09-03); the live root stays untouched."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                result = backup_memory.backup(dest=tmp / "dest",
                                              root=root)
                live = root / "db" / "research.db"
                before = live.read_bytes()
                rc = backup_memory.main(["--restore",
                                         str(Path(result["path"]))])
                self.assertEqual(rc, 2)
                self.assertEqual(live.read_bytes(), before)
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_degraded_backup_is_not_a_restore_point(self):
        """A snapshot that skipped a db must never graduate: no
        .complete (absent from --list-as-restore-point semantics and
        offsite), a .degraded marker instead, restore refuses (rc 3),
        drill fails, and the explicit override says loudly that the
        store is not restored (advisory 2026-09-03)."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                live = root / "db" / "research.db"
                lock = sqlite3.connect(str(live), timeout=0.2)
                lock.execute("BEGIN EXCLUSIVE")
                try:
                    res = backup_memory.backup(dest=tmp / "dest",
                                               root=root)
                finally:
                    lock.close()
                bad = Path(res["path"])
                self.assertFalse((bad / ".complete").is_file())
                self.assertTrue((bad / ".degraded").is_file())
                self.assertIn("LOCKED", res["skipped"][0])
                self.assertIsNone(res["offsite"])
                with self.assertRaises(RuntimeError):
                    backup_memory.restore(bad, root=root)
                rc = backup_memory.main(
                    ["--restore", str(bad), "--yes"])
                self.assertEqual(rc, 3)
                drill = backup_memory.restore_drill(bad, root=root)
                self.assertFalse(drill["integrity_ok"])
                self.assertIn("LOCKED", drill["degraded"])
                out = backup_memory.restore(bad, root=root,
                                            include_degraded=True)
                self.assertNotIn("db/research.db", out["restored"])
                self.assertTrue(out["verify"]["ok"], out)
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_degraded_retention_has_own_small_cap(self):
        """Degraded snapshots prune on their OWN cap (3), never on the
        good-backup budget: a lock event must not evict a valid restore
        point (advisory 2026-09-03)."""
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            os.environ["MEMORY_ROOT"] = str(root)
            try:
                dest = tmp / "dest"
                for i in range(4):
                    d = dest / f"2026010{i}T000000-deg"
                    d.mkdir(parents=True)
                    (d / ".degraded").write_text("x\n", encoding="utf-8")
                good = dest / "20260201T000000"
                good.mkdir()
                (good / ".complete").write_text("ok\n", encoding="utf-8")
                live = root / "db" / "research.db"
                lock = sqlite3.connect(str(live), timeout=0.2)
                lock.execute("BEGIN EXCLUSIVE")
                try:
                    backup_memory.backup(dest=dest, root=root)
                finally:
                    lock.close()
                degraded = sorted(p.name for p in dest.iterdir()
                                  if (p / ".degraded").is_file())
                self.assertEqual(len(degraded), 3, degraded)
                self.assertTrue((good / ".complete").is_file(),
                                "good backup must survive the lock event")
            finally:
                os.environ.pop("MEMORY_ROOT", None)

    def test_cli_fails_when_integrity_check_fails(self):
        from unittest import mock
        with mock.patch.object(
            backup_memory, "restore_drill",
            return_value={
                "integrity_ok": False,
                "probe": {"exists": False},
                "files": 1,
                "dbs": 1,
            },
        ):
            self.assertEqual(
                backup_memory.main(["--restore-drill", "unused"]), 1)

    def test_retention_keeps_latest_completed_backups(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = _seed_memory_root(tmp)
            dest = tmp / "dest"
            for day in range(1, 6):
                old = dest / f"2026010{day}T000000"
                old.mkdir(parents=True)
                (old / ".complete").write_text("ok", encoding="utf-8")
            backup_memory.backup(dest=dest, root=root, keep=3)
            completed = sorted(
                p for p in dest.iterdir()
                if p.is_dir() and (p / ".complete").is_file())
            self.assertEqual(len(completed), 3)


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
            fresh = root / "backups" / _time.strftime("%Y%m%dT%H%M%S")
            fresh.mkdir(parents=True)
            (fresh / ".complete").write_text("ok", encoding="utf-8")

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
            old = root / "backups" / old_stamp
            old.mkdir(parents=True)
            (old / ".complete").write_text("ok", encoding="utf-8")

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

    def test_warns_when_timestamp_dir_is_incomplete(self):
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
                self.assertIn("WARN", detail)
            finally:
                if old is None:
                    os.environ.pop("MEMORY_ROOT", None)
                else:
                    os.environ["MEMORY_ROOT"] = old


if __name__ == "__main__":
    unittest.main()
