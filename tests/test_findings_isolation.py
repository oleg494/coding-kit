#!/usr/bin/env python3
"""tests/test_findings_isolation.py — the MEMORY_ROOT_RESEARCH_DB sandbox is
honored by EVERY module that resolves research.db.

Before this pin, only findings_db.py honored the hook; log.py, tasks.py,
githist.py and search.py::_did_you_mean hardcoded
ROOT/db/research.db — every "sandboxed" run silently wrote to the prod store
(demonstrated 2026-09-02: log_search with the hook set inserted a row into
the real search_log). research_db_path() in findings_db.py is now the single
resolver; this test fails loudly if any module re-hardcodes the path.
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

# Modules whose module-level DB constant must resolve through the hook.
MODULES = ("log", "tasks", "githist", "findings_db")

PROBE = """
import os, sys
sys.path.insert(0, r"{db_tools}")
sys.path.insert(0, str(__import__("pathlib").Path(r"{db_tools}").parent / "scripts"))
import findings_db
expected = os.environ["MEMORY_ROOT_RESEARCH_DB"]
def norm(p):
    return os.path.normcase(os.path.abspath(str(p)))
bad = []
if norm(findings_db.research_db_path()) != norm(expected):
    bad.append("findings_db.research_db_path()")
for name in {modules}:
    mod = __import__(name)
    if norm(mod.DB) != norm(expected):
        bad.append(name + ".DB")
print("BAD:" + ",".join(bad) if bad else "OK")
"""


class ResearchDbIsolationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kit-isolation-"))
        self.db_path = self.tmp / "sandbox.db"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_module_honors_memory_root_research_db(self):
        probe = PROBE.format(
            db_tools=DB_TOOLS,
            modules=repr(MODULES),
        )
        env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db_path),
            PYTHONIOENCODING="utf-8",
        )
        r = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=60,
        )
        self.assertEqual(
            r.returncode, 0,
            f"probe crashed:\n{r.stdout}\n{r.stderr}")
        self.assertEqual(
            r.stdout.strip(), "OK",
            f"modules ignoring MEMORY_ROOT_RESEARCH_DB: {r.stdout.strip()}")

    def test_default_path_is_root_db_research(self):
        """Without the hook the resolver points at ROOT/db/research.db."""
        probe = (
            "import os, sys\n"
            f"sys.path.insert(0, r'{DB_TOOLS}')\n"
            "sys.path.insert(0, os.path.join("
            f"    r'{DB_TOOLS}', os.pardir, 'scripts'))\n"
            "import findings_db\n"
            "expected = os.path.join(findings_db.ROOT, 'db', 'research.db')\n"
            "got = findings_db.research_db_path()\n"
            "print('OK' if os.path.normcase(os.path.abspath(got)) == "
            "os.path.normcase(os.path.abspath(expected)) else f'BAD:{got}')\n"
        )
        env = {k: v for k, v in os.environ.items()
               if k != "MEMORY_ROOT_RESEARCH_DB"}
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=60,
        )
        self.assertEqual(r.returncode, 0, f"probe crashed:\n{r.stderr}")
        self.assertEqual(r.stdout.strip(), "OK", r.stdout.strip())

    def test_function_level_sites_read_sandbox_not_prod(self):
        """repomap._findings_for and search._did_you_mean resolve the path
        INSIDE the function (no module-level DB constant to assert on). Pin
        them behaviorally: seed the sandbox with data prod does not have,
        call the functions, require the sandbox data back. If either site
        re-hardcodes the prod path, these return '' and the test fails."""
        import sqlite3
        con = sqlite3.connect(self.db_path)
        con.executescript(
            "CREATE TABLE findings (id INTEGER PRIMARY KEY, created TEXT, "
            " topic TEXT, text TEXT, tags TEXT DEFAULT '', source TEXT DEFAULT '',"
            " file TEXT DEFAULT '', symbol TEXT DEFAULT '',"
            " verify_cmd TEXT DEFAULT '', verified_at TEXT DEFAULT '');\n"
            "INSERT INTO findings (id, created, topic, text, file, symbol) "
            " VALUES (901, '2026-09-02 12:00', 'sandbox-only-topic-xyz', "
            " 't', 'sandbox_mod.py', 'fn');\n"
            "CREATE TABLE search_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            " ts TEXT, tool TEXT, db_name TEXT, query TEXT, hits INTEGER);\n"
            "INSERT INTO search_log (ts, tool, db_name, query, hits) VALUES "
            " ('2026-09-02 12:00', 't', 'd', 'sandboxdym token901', 5);\n")
        con.commit()
        con.close()
        # Subprocess, like the sibling probes in this file: repomap/search
        # bind ROOT/DEFAULT_DB at import time, so an in-process import would
        # cache them in sys.modules for every later test and leak sys.path.
        probe = (
            "import os, sys\n"
            f"sys.path.insert(0, r'{DB_TOOLS}')\n"
            "sys.path.insert(0, os.path.join("
            f"    r'{DB_TOOLS}', os.pardir, 'scripts'))\n"
            "import repomap, search\n"
            "out = repomap._findings_for('sandbox_mod.py')\n"
            "dym = search._did_you_mean('token901 please', 'somedb')\n"
            "ok1 = 'sandbox-only-topic-xyz' in out and '#research 901' in out\n"
            "ok2 = 'sandboxdym' in dym\n"
            "print(('OK' if ok1 and ok2 else f'BAD repomap={ok1} dym={ok2} ' "
            "f'out={out!r} dym={dym!r}'))\n"
        )
        env = dict(
            os.environ,
            MEMORY_ROOT_RESEARCH_DB=str(self.db_path),
            PYTHONIOENCODING="utf-8",
        )
        r = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=60,
        )
        self.assertEqual(r.returncode, 0, f"probe crashed:\n{r.stderr}")
        self.assertEqual(
            r.stdout.strip(), "OK",
            "function-level sites did not read the sandbox db: "
            + r.stdout.strip())


if __name__ == "__main__":
    unittest.main()
