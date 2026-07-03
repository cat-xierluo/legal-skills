"""poll_tasks.py 状态机回归测试 — 验证 statusMsg 软错误识别。

背景：Tingwu 后端把"采样率不支持"等错误也归到 status=2（文档里的"转录中"），
本地必须从 statusMsg 字段识别并立即判失败，否则会无限轮询。
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

# 让 tests/ 作为 scripts/ 的子包时，能直接 import poll_tasks
TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import poll_tasks  # noqa: E402


class _FakeTingwuClient:
    """最小化的 TingwuClient 替代品，只暴露 check_once 用到的接口。"""

    def __init__(self, trans_responses):
        # trans_id → 返回的 status info dict
        self._responses = trans_responses

    def get_trans_list(self, trans_id=None):
        if trans_id is None:
            return list(self._responses.values())
        return self._responses.get(trans_id)


def _make_task(trans_id="test_task_001"):
    return {
        "trans_id": trans_id,
        "file_path": f"/tmp/{trans_id}.mp4",
        "file_name": f"{trans_id}.mp4",
        "lang": "cn",
        "role_split_num": 4,
        "status": "pending",
    }


class CheckOnceErrorRecognitionTest(unittest.TestCase):
    """check_once 的状态机行为：statusMsg 软错误 → 立即判失败。"""

    def setUp(self):
        """每个 case 用独立临时目录，避免污染真实 config/。"""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.pending_path = Path(self.tmpdir.name) / "pending_tasks.json"
        self.completed_path = Path(self.tmpdir.name) / "completed_tasks.json"

    def _run_check_once(self, trans_responses, task_id_filter=None):
        """跑一次 check_once，捕获 stdout，返回 (output, pending, completed) 三元组。"""
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch.object(poll_tasks, "PENDING_PATH", self.pending_path), \
                 patch.object(poll_tasks, "COMPLETED_PATH", self.completed_path):
                client = _FakeTingwuClient(trans_responses)
                poll_tasks.check_once(client, task_id_filter=task_id_filter)

        pending = json.loads(self.pending_path.read_text()) if self.pending_path.exists() else []
        completed = json.loads(self.completed_path.read_text()) if self.completed_path.exists() else []
        return buf.getvalue(), pending, completed

    # --- Case 1: 核心修复点 — status=2 + statusMsg 含错误关键词 → 判失败 ---

    def test_status_2_with_sample_rate_msg_marks_failed(self):
        """复现 2026-06-22 真实 bug：抖音无声视频被 Tingwu 拒绝，watcher 不该傻等。"""
        self.pending_path.write_text(json.dumps([_make_task("silent_video_test")], ensure_ascii=False))

        output, pending, completed = self._run_check_once({
            "silent_video_test": {
                "transId": "silent_video_test",
                "status": 2,
                "statusMsg": "仅支持16k及以上采样率文件",
            },
        })

        # 1. 输出包含 watcher 能 grep 的"失败:"信号
        self.assertIn("失败（后端拒绝）", output)
        self.assertIn("仅支持16k及以上采样率文件", output)

        # 2. 任务从 pending 移除
        self.assertEqual(pending, [], "失败的软错误任务必须从 pending 移除")

        # 3. 任务写入 completed 并标 failed + 完整 statusMsg 记录
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["trans_id"], "silent_video_test")
        self.assertEqual(completed[0]["status"], "failed")
        self.assertIn("后端拒绝(status=2)", completed[0]["error"])
        self.assertIn("仅支持16k及以上采样率文件", completed[0]["error"])

    # --- Case 2: 反向断言 — status=2 但 statusMsg 为空时**不**误判 ---

    def test_status_2_with_empty_msg_stays_in_progress(self):
        """statusMsg 为空不应触发关键词匹配，任务保留在 pending。"""
        self.pending_path.write_text(json.dumps([_make_task("normal_long_video")], ensure_ascii=False))

        output, pending, completed = self._run_check_once({
            "normal_long_video": {
                "transId": "normal_long_video",
                "status": 2,
                "statusMsg": "",
                "forecastTransDoneTime": 1782200000000,
                "serverCurrentTime": 1782116000000,
            },
        })

        # 1. 任务仍在 pending
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["trans_id"], "normal_long_video")

        # 2. completed 应该是空的
        self.assertEqual(completed, [])

        # 3. 输出走的是"转录中"分支，不是失败
        self.assertIn("转录中", output)
        self.assertNotIn("失败", output)
        # 4. 应该带预计剩余时间提示
        self.assertIn("预计剩余", output)

    # --- Case 3: 兼容回归 — status=4 仍走老路径，输出格式不变 ---

    def test_status_4_still_uses_legacy_failure_path(self):
        """已有 status=4 失败路径不能被新逻辑误改。"""
        self.pending_path.write_text(json.dumps([_make_task("api_reported_fail")], ensure_ascii=False))

        output, pending, completed = self._run_check_once({
            "api_reported_fail": {
                "transId": "api_reported_fail",
                "status": 4,
                "statusMsg": "音频解码失败",
            },
        })

        # 1. 输出沿用老格式 "失败: ..."（不带"后端拒绝"前缀），watcher 现有 grep 兼容
        self.assertIn("失败: 音频解码失败", output)
        self.assertNotIn("后端拒绝", output)

        # 2. 任务状态和 error 字段格式不变
        self.assertEqual(pending, [])
        self.assertEqual(completed[0]["status"], "failed")
        self.assertEqual(completed[0]["error"], "音频解码失败")

    # --- Case 4 (额外覆盖): 英文 statusMsg 也能识别 ---

    def test_english_error_keyword_recognized(self):
        """关键词列表里包含英文 error/invalid 等，必须大小写不敏感命中。"""
        self.pending_path.write_text(json.dumps([_make_task("english_err")], ensure_ascii=False))

        output, pending, completed = self._run_check_once({
            "english_err": {
                "transId": "english_err",
                "status": 2,
                "statusMsg": "INVALID audio format: AAC not supported",
            },
        })

        self.assertIn("失败（后端拒绝）", output)
        self.assertEqual(pending, [])
        self.assertEqual(completed[0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
