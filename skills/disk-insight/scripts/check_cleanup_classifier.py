#!/usr/bin/env python3
"""Independent CLI checks for cleanup_classifier against synthetic scan reports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("cleanup_classifier.py")
GIB = 1024 ** 3


class CleanupClassifierChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="disk-insight-cleanup-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()

    def _snapshot(self, name, rows):
        path = self.base / f"{name}.json"
        path.write_text(json.dumps({
            "schema": "disk_probe/scan/1",
            "results": [{"root": rows[0]["path"], "status": "complete", "rows": rows,
                         "large_files": []}],
        }), encoding="utf-8")
        return path

    def _snapshot_multi(self, name, groups):
        """groups: [(root, status, rows)]"""
        path = self.base / f"{name}.json"
        path.write_text(json.dumps({
            "schema": "disk_probe/scan/1",
            "results": [{"root": root, "status": status, "rows": rows, "large_files": []}
                        for root, status, rows in groups],
        }), encoding="utf-8")
        return path

    def _report(self, snapshots, comparisons):
        return {
            "capacity_after": {"available_bytes": 15 * GIB},
            "capacity_delta_from_previous_bytes": -5 * GIB,
            "measurements": [{"id": name, "status": "complete", "snapshot": str(path)}
                             for name, path in snapshots.items()],
            "comparisons": comparisons,
        }

    def _run(self, report):
        report_path = self.base / "report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        out = self.base / "out.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--report", str(report_path), "--out", str(out)],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(out.read_text())

    def test_occupancy_and_growth_are_reported_separately(self):
        snapshots = {
            "app": self._snapshot_multi("app", [
                ("/sandbox/app/Library/Caches", "complete", [
                    {"path": "/sandbox/app/Library/Caches", "allocated_bytes": 3 * GIB},
                    {"path": "/sandbox/app/Library/Caches/sub", "allocated_bytes": 2 * GIB},
                ]),
                ("/sandbox/app/Library/Application Support/app", "complete", [
                    {"path": "/sandbox/app/Library/Application Support/app", "allocated_bytes": 5 * GIB},
                ]),
            ]),
        }
        comparisons = [{"id": "app", "status": "COMPARABLE", "top_growth": [
            {"path": "/sandbox/app/Library/Caches", "delta_bytes": 2 * GIB,
             "before_bytes": 1 * GIB, "after_bytes": 3 * GIB},
        ]}]
        result = self._run(self._report(snapshots, comparisons))
        classes = {b["class"]: b for b in result["occupancy_ranking"]}
        self.assertIn("cache-root", classes)
        self.assertIn("unclassified", classes)
        # 父子路径不叠加：缓存根 3GiB 与其子目录 2GiB 只计最深的一层 2GiB。
        self.assertEqual(classes["cache-root"]["total_bytes"], 2 * GIB)
        self.assertEqual(result["growth_ranking"][0]["delta_bytes"], 2 * GIB)
        self.assertEqual(result["reclaimable_occupancy_gib"], 2.0)

    def test_kept_categories_are_not_reclaimable(self):
        snapshots = {
            "chat": self._snapshot("chat", [
                {"path": "/sandbox/app/Library/Containers/com.tencent.xinWeChat",
                 "allocated_bytes": 200 * GIB},
            ]),
            "swap": self._snapshot("swap", [
                {"path": "/System/Volumes/VM", "allocated_bytes": 5 * GIB},
            ]),
        }
        result = self._run(self._report(snapshots, []))
        classes = {b["class"]: b for b in result["occupancy_ranking"]}
        self.assertFalse(classes["messaging-data"]["reclaimable"])
        self.assertFalse(classes["system-swap"]["reclaimable"])
        self.assertEqual(result["reclaimable_occupancy_gib"], 0.0)
        self.assertEqual(result["keep_occupancy_gib"], 205.0)

    def test_partial_targets_are_not_counted(self):
        snapshots = {
            "app": self._snapshot("app", [
                {"path": "/sandbox/app/Library/Caches", "allocated_bytes": 4 * GIB},
            ]),
        }
        report = self._report(snapshots, [])
        path = snapshots["app"]
        data = json.loads(path.read_text())
        data["results"][0]["status"] = "partial"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = self._run(report)
        self.assertEqual(result["reclaimable_occupancy_gib"], 0.0)


if __name__ == "__main__":
    unittest.main()
