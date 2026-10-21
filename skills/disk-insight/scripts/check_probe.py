#!/usr/bin/env python3
"""Independent CLI checks against real synthetic files and SQLite inputs."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("disk_probe.py")


class ProbeChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="disk-insight-check-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "root"
        self.root.mkdir()
        self.seq = 0

    def run_cli(self, *args, code=0):
        self.seq += 1
        out = self.base / f"out-{self.seq}.json"
        command = [sys.executable, str(SCRIPT), *map(str, args), "--output", str(out)]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, code, proc.stderr)
        if code:
            self.assertFalse(out.exists(), proc.stderr)
            return None
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        return json.loads(out.read_text()), out

    def test_allocated_hardlinks_symlink_and_no_source_writes(self):
        file = self.root / "source.dat"
        file.write_bytes(b"a" * 20000)
        os.link(file, self.root / "hard.dat")
        external = self.base / "external"
        external.mkdir()
        (external / "private.dat").write_bytes(b"x" * 90000)
        (self.root / "escape").symlink_to(external, target_is_directory=True)
        before = hashlib.sha256(file.read_bytes()).hexdigest()
        data, _ = self.run_cli("scan", "--root", self.root)
        r = data["results"][0]
        self.assertEqual(r["status"], "complete")
        expected = sum(p.lstat().st_blocks * 512 for p in [self.root, file, self.root / "escape"])
        self.assertEqual(r["rows"][0]["allocated_bytes"], expected)
        self.assertEqual(r["rows"][0]["logical_bytes"], 20000)
        self.assertEqual(before, hashlib.sha256(file.read_bytes()).hexdigest())
        self.assertEqual(set(p.name for p in self.root.iterdir()), {"source.dat", "hard.dat", "escape"})

    def test_budget_and_reject_partial_comparison(self):
        for i in range(10):
            (self.root / str(i)).write_text("a")
        data, a = self.run_cli("scan", "--root", self.root, "--max-entries", 2)
        self.assertEqual(data["results"][0]["status"], "partial")
        _, b = self.run_cli("scan", "--root", self.root)
        self.run_cli("compare", "--before", a, "--after", b, code=2)

    def test_independent_growth_and_missing_not_zero(self):
        old = self.root / "old"
        old.mkdir()
        (old / "a").write_bytes(b"a" * 4096)
        _, a = self.run_cli("scan", "--root", self.root)
        initial = (old / "a").stat().st_blocks * 512
        (old / "a").write_bytes(b"a" * 24000)
        (self.root / "new").mkdir()
        _, b = self.run_cli("scan", "--root", self.root)
        diff, _ = self.run_cli("compare", "--before", a, "--after", b)
        rows = {r["path"]: r for r in diff["rows"]}
        self.assertEqual(rows[str(old)]["delta_bytes"], (old / "a").stat().st_blocks * 512 - initial)
        self.assertIsNone(rows[str(self.root / "new")]["delta_bytes"])
        self.assertEqual(rows[str(self.root / "new")]["status"], "not_recorded_before")
        self.run_cli("compare", "--before", b, "--after", a, code=2)

    def test_paths_outputs_and_parameter_failures(self):
        self.run_cli("scan", "--root", self.root, "--root", self.root / "nested", code=2)
        self.run_cli("scan", "--root", self.root, "--seconds", "nan", code=2)
        self.run_cli("scan", "--root", self.root, "--unknown", code=2)
        self.run_cli("scan", "--root", self.base / "missing")  # explicit unavailable, never zero
        out = self.base / "existing.json"
        out.write_text("keep")
        p = subprocess.run([sys.executable, str(SCRIPT), "scan", "--root", str(self.root),
                            "--output", str(out)], capture_output=True, timeout=10)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(out.read_text(), "keep")
        link = self.base / "link"
        link.symlink_to(self.root, target_is_directory=True)
        self.run_cli("scan", "--root", link, code=2)

    def make_db(self):
        db = self.base / "history #中文.db"
        conn = sqlite3.connect(db)
        conn.executescript("""
          PRAGMA user_version=9;
          CREATE TABLE snapshots(id INTEGER PRIMARY KEY, created_at TEXT, root TEXT,
            min_kb INTEGER, exclude_names TEXT, metric_version INTEGER, plan_id TEXT,
            collection_status TEXT, denied_count INTEGER, vanished_count INTEGER);
          CREATE TABLE entries(snapshot_id INTEGER, path TEXT, size_kb INTEGER);
        """)
        for i, root in ((1, "/sample"), (2, "/sample"), (3, "/other")):
            conn.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (i, f"2026-10-{i:02}T12:00:00", root, 10, "", 1, "plan", "partial", 1, 0))
        conn.executemany("INSERT INTO entries VALUES(?,?,?)", [
            (1, "/sample", 100), (2, "/sample", 150), (1, "/sample/a", 50),
            (2, "/sample/a", 80), (1, "/sample/gone", 20), (2, "/sample/new", 50),
            (2, "/sample/new/deep", 30), (2, "/sample-other", 999)])
        conn.commit()
        conn.close()
        return db

    def make_history_db(self, name):
        db = self.base / name
        conn = sqlite3.connect(db)
        conn.executescript("""
          PRAGMA user_version=9;
          CREATE TABLE snapshots(id INTEGER PRIMARY KEY, created_at TEXT, root TEXT,
            min_kb INTEGER, exclude_names TEXT, metric_version INTEGER, plan_id TEXT,
            collection_status TEXT, denied_count INTEGER, vanished_count INTEGER);
          CREATE TABLE entries(snapshot_id INTEGER, path TEXT, size_kb INTEGER);
          CREATE TABLE volume_stats(snapshot_id INTEGER PRIMARY KEY, total_bytes INTEGER,
            free_bytes INTEGER);
          CREATE TABLE container_capacity_samples(id INTEGER PRIMARY KEY, container_id TEXT,
            total_bytes INTEGER, free_bytes INTEGER, source TEXT, sampled_at TEXT);
        """)
        for i, day, root in ((1, "01", "/sample"), (2, "04", "/sample"), (3, "08", "/sample")):
            conn.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (i, f"2026-10-{day}T12:00:00", root, 10, "", 1, "plan", "partial", 1, 0))
            conn.execute("INSERT INTO volume_stats VALUES(?,?,?)", (i, 1000, 100 - i))
        conn.executemany("INSERT INTO entries VALUES(?,?,?)", [
            (1, "/sample", 100), (2, "/sample", 110), (3, "/sample", 150),
            (1, "/sample/agent", 40), (2, "/sample/agent", 45), (3, "/sample/agent", 80)])
        conn.executemany("INSERT INTO container_capacity_samples VALUES(?,?,?,?,?,?)", [
            (1, "container", 1000, 100, "test", "2026-10-01T12:00:00"),
            (2, "container", 1000, 90, "test", "2026-10-04T12:00:00"),
            (3, "container", 1000, 40, "test", "2026-10-08T12:00:00")])
        conn.commit()
        conn.close()
        return db

    def test_fathom_literal_scope_units_missing_and_readonly(self):
        db = self.make_db()
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        data, _ = self.run_cli("fathom-diff", "--db", db, "--before", 1, "--after", 2,
                               "--focus", "/sample")
        rows = {r["path"]: r for r in data["rows"]}
        self.assertEqual(rows["/sample/a"]["delta_bytes"], 30 * 1024)
        self.assertIsNone(rows["/sample/gone"]["delta_bytes"])
        self.assertIsNone(rows["/sample/new"]["delta_bytes"])
        self.assertNotIn("/sample-other", rows)
        self.assertNotIn("/sample/new/deep", rows)
        self.assertEqual(before, hashlib.sha256(db.read_bytes()).hexdigest())

    def test_fathom_reject_mismatch_unknown_schema_and_missing(self):
        db = self.make_db()
        common = ("fathom-diff", "--db", db, "--before", 1, "--focus", "/sample")
        self.run_cli(*common, "--after", 3, code=2)
        self.run_cli(*common, "--after", 99, code=2)
        self.run_cli(*common, "--after", 2, "--focus", "/sample-other", code=2)
        with sqlite3.connect(db) as c:
            c.execute("UPDATE snapshots SET metric_version=NULL WHERE id=1")
        self.run_cli(*common, "--after", 2, code=2)
        with sqlite3.connect(db) as c:
            c.execute("PRAGMA user_version=99")
        self.run_cli("fathom-list", "--db", db, code=2)
        self.run_cli("fathom-list", "--db", self.base / "missing.db", code=2)
        self.assertFalse((self.base / "missing.db").exists())

    def test_history_auto_prefers_matching_window_and_reports_capacity(self):
        db = self.make_history_db("primary-fathom.db")
        # A second DB without a comparable pair must remain visible but not become selected.
        empty = self.base / "empty-fathom.db"
        conn = sqlite3.connect(empty)
        conn.executescript("""
          PRAGMA user_version=9;
          CREATE TABLE snapshots(id INTEGER PRIMARY KEY, created_at TEXT, root TEXT,
            min_kb INTEGER, exclude_names TEXT, metric_version INTEGER, plan_id TEXT,
            collection_status TEXT, denied_count INTEGER, vanished_count INTEGER);
          CREATE TABLE entries(snapshot_id INTEGER, path TEXT, size_kb INTEGER);
        """)
        conn.commit()
        conn.close()
        data, _ = self.run_cli("history", "--db", db, "--db", empty,
                               "--focus", "/sample", "--days", 4)
        self.assertEqual(data["status"], "history_found")
        self.assertEqual((data["before"]["id"], data["after"]["id"]), (2, 3))
        self.assertAlmostEqual(data["actual_days"], 4.0)
        rows = {r["path"]: r for r in data["rows"]}
        self.assertEqual(rows["/sample/agent"]["delta_bytes"], 35 * 1024)
        self.assertEqual(data["volume_stats"]["before"]["free_bytes"], 98)
        capacity = {r["container_id"]: r for r in data["capacity_deltas"]}["container"]
        self.assertEqual(capacity["free_bytes_delta"], -50)
        self.assertEqual(capacity["before_distance_seconds"], 0.0)
        self.assertEqual(capacity["after_distance_seconds"], 0.0)
        reports = {r["path"]: r for r in data["discovered_dbs"]}
        self.assertEqual(reports[str(db)]["status"], "usable")
        self.assertEqual(reports[str(empty)]["status"], "no_comparable_focus_pair")

    def test_history_db_dir_no_history_and_id_override_validation(self):
        search = self.base / "search"
        search.mkdir()
        db = self.make_history_db("search/fathom.db")
        data, _ = self.run_cli("history", "--db-dir", search, "--focus", "/sample", "--days", 3)
        self.assertEqual((data["before"]["id"], data["after"]["id"]), (2, 3))
        data, _ = self.run_cli("history", "--db", db, "--before", 1, "--after", 3,
                               "--focus", "/sample")
        self.assertEqual(data["rows"][0]["delta_bytes"], 50 * 1024)
        self.run_cli("history", "--db", db, "--before", 3, "--after", 1,
                     "--focus", "/sample", code=2)
        no_history, _ = self.run_cli("history", "--db", self.base / "missing.db",
                                     "--focus", "/sample")
        self.assertEqual(no_history["status"], "no_history")
        self.assertEqual(no_history["discovered_dbs"][0]["status"], "unavailable")

    def test_default_discovery_is_bounded_and_uses_fathom_db_env(self):
        support = self.base / "Application Support"
        project_db = support / "vendor" / "fathom" / "data" / "fathom.db"
        project_db.parent.mkdir(parents=True)
        source = self.make_history_db("source.db")
        project_db.write_bytes(source.read_bytes())
        env = dict(os.environ, HOME=str(self.base),
                   FATHOM_DB=str(self.base / "missing-env-fathom.db"))
        out = self.base / "history-default.json"
        command = [sys.executable, str(SCRIPT), "history", "--focus", "/sample",
                   "--days", "4", "--output", str(out)]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=20, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(out.read_text())
        reports = data["discovered_dbs"]
        self.assertIn({"path": str(self.base / "missing-env-fathom.db"),
                       "status": "unavailable", "reason": "[Errno 2] No such file or directory: '" +
                       str(self.base / "missing-env-fathom.db") + "'"}, reports)
        self.assertEqual(data["status"], "history_found")
        self.assertEqual(data["db"], str(project_db))

    def test_default_discovery_reports_missing_standard_db(self):
        home = self.base / "empty-home"
        home.mkdir()
        out = self.base / "history-standard-missing.json"
        env = dict(os.environ, HOME=str(home))
        proc = subprocess.run([sys.executable, str(SCRIPT), "history", "--focus", "/sample",
                               "--days", "4", "--output", str(out)], capture_output=True,
                              text=True, timeout=20, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(out.read_text())
        self.assertEqual(data["status"], "no_history")
        self.assertEqual(data["discovered_dbs"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
