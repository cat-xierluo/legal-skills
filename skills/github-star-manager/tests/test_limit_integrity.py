"""离线限额完整性回归：执行原函数 AST，隔离导入和网络依赖。"""
import ast
import contextlib
import io
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

def functions(filename, names, ns):
    tree = ast.parse((SCRIPTS / filename).read_text())
    nodes = []
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in names:
            n.decorator_list = []
            nodes.append(n)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), ns)
    return ns

NS = functions("star_tracker.py", {"get_starred_repos", "is_snapshot_submittable"},
               dict(datetime=datetime, timezone=timezone, Dict=Dict, List=List, Optional=Optional))
CLI = functions("main.py", {"init_command", "check_command"}, dict(StarTracker=object))

class LimitIntegrityTests(unittest.TestCase):
    def tracker(self, count=100):
        rows = [dict(id=i, full_name=f"test/repo-{i}", description="synthetic") for i in range(count)]
        pages = iter([rows, []])
        t = SimpleNamespace(github_token=None, headers={}, API_BASE="https://invalid.test",
            get_categories_map=lambda: {}, get_authenticated_user=lambda: None,
            _match_category=lambda *a: None,
            _request_with_retry=lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: next(pages)))
        t.get_starred_repos = lambda user, limit: NS["get_starred_repos"](t, user, limit)
        t.load_latest = lambda: dict(timestamp="2026-10-16", repos=rows)
        t.retry_null_descriptions = lambda r: r
        t.log_null_descriptions = lambda *a, **kw: None
        t.saved = []
        t.save_latest = lambda r, **kw: t.saved.append(r)
        return t

    def test_truncated_page_is_partial(self):
        t = self.tracker()
        self.assertEqual(len(t.get_starred_repos("synthetic", 50)), 50)
        self.assertFalse(t.last_fetch_meta["complete"])
        self.assertTrue(t.last_fetch_meta["limit_truncated"])

    def test_exact_full_page_is_not_proven_complete(self):
        t = self.tracker()
        t.get_starred_repos("synthetic", 100)
        self.assertFalse(t.last_fetch_meta["complete"])

    def test_short_page_at_limit_is_complete(self):
        t = self.tracker(50)
        t.get_starred_repos("synthetic", 50)
        self.assertTrue(t.last_fetch_meta["complete"])
        self.assertFalse(t.last_fetch_meta["limit_truncated"])

    def test_exhaustion_without_limit_is_complete(self):
        t = self.tracker()
        t.get_starred_repos("synthetic", 9999)
        self.assertTrue(t.last_fetch_meta["complete"])

    def test_legacy_contradictory_metadata_rejected(self):
        self.assertFalse(NS["is_snapshot_submittable"]({"snapshot_meta": {
            "complete": True, "limit_truncated": True}})[0])

    def test_real_cli_guards_preserve_existing_baseline(self):
        for name in ("init_command", "check_command"):
            with self.subTest(command=name), contextlib.redirect_stdout(io.StringIO()) as output:
                t = self.tracker()
                result = CLI[name](t, SimpleNamespace(user="synthetic", limit=50, summarize=False))
                self.assertEqual(result, 1)
                self.assertEqual(t.saved, [])
                self.assertNotIn("已记录 50 个取消 Star", output.getvalue())

if __name__ == "__main__":
    unittest.main()
