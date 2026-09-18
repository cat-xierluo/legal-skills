#!/usr/bin/env python3
"""OSS 上传代理隔离回归测试 — 2026-09-18 事故固化。

背景：shell 常驻 HTTP_PROXY/HTTPS_PROXY（Clash 系）时，oss2 上传走代理，
771MB 视频实测在 50% 处被掐断（ProxyError: Cannot connect to proxy）。
修复：OSS 上传 session 默认 trust_env=False（忽略环境代理直连），
TINGWU_OSS_USE_PROXY=1 可恢复走代理的旧行为。
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import tingwu  # noqa: E402

try:
    import oss2  # noqa: F401
    HAS_OSS2 = True
except ImportError:
    HAS_OSS2 = False

try:
    import requests  # noqa: F401
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = True  # tingwu.py 把 requests 当硬依赖，import 失败会 sys.exit


FAKE_STS = {
    "accessKeyId": "ak",
    "accessKeySecret": "sk",
    "securityToken": "token",
    "endpoint": "https://oss-cn-shanghai.aliyuncs.com",
    "bucket": "tingwu-test-bucket",
    "fileKey": "k.mp4",
}


def _clear_proxy_env():
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy", "TINGWU_OSS_USE_PROXY"):
        os.environ.pop(k, None)


class TestBuildOssBucketProxyIsolation(unittest.TestCase):
    """_build_oss_bucket：默认 trust_env=False，逃生阀恢复。"""

    def setUp(self):
        _clear_proxy_env()
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:1082"
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1082"

    def tearDown(self):
        _clear_proxy_env()

    @unittest.skipUnless(HAS_OSS2, "oss2 未安装")
    def test_default_ignores_env_proxy(self):
        """常驻代理下，bucket 的内层 requests session 必须 trust_env=False。"""
        bucket = tingwu._build_oss_bucket(FAKE_STS)
        self.assertIsNotNone(bucket)
        self.assertFalse(bucket.session.session.trust_env,
                         "OSS 上传 session 必须忽略环境代理（trust_env=False）")

    @unittest.skipUnless(HAS_OSS2, "oss2 未安装")
    def test_escape_hatch_restores_proxy(self):
        """TINGWU_OSS_USE_PROXY=1 时恢复旧行为（trust_env 默认 True）。"""
        os.environ["TINGWU_OSS_USE_PROXY"] = "1"
        bucket = tingwu._build_oss_bucket(FAKE_STS)
        self.assertTrue(bucket.session.session.trust_env,
                        "逃生阀未生效：应保持 requests 默认 trust_env=True")

    @unittest.skipUnless(HAS_OSS2, "oss2 未安装")
    def test_no_proxy_env_still_direct(self):
        """无代理变量时同样 trust_env=False：无条件直连，行为确定不随环境漂移。"""
        _clear_proxy_env()
        bucket = tingwu._build_oss_bucket(FAKE_STS)
        self.assertFalse(bucket.session.session.trust_env)


class TestUploadViaRequestsProxyIsolation(unittest.TestCase):
    """_upload_via_requests 兜底路径同样绕过环境代理。"""

    def setUp(self):
        _clear_proxy_env()
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:1082"
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1082"

    def tearDown(self):
        _clear_proxy_env()

    def test_put_uses_trust_env_false_session(self):
        """默认分支应使用 trust_env=False 的 Session 发 PUT。"""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"x" * 16)
            path = f.name
        try:
            captured = {}

            def fake_put(self_session, url, **kw):
                captured["trust_env"] = self_session.trust_env
                resp = MagicMock()
                resp.raise_for_status.return_value = None
                return resp

            with patch.object(tingwu.requests.Session, "put", fake_put):
                tingwu._upload_via_requests(
                    path, {"putLink": "https://oss.example/put", "sts": FAKE_STS})
            self.assertFalse(captured["trust_env"],
                             "兜底 PUT 必须走 trust_env=False 的 Session")
        finally:
            os.unlink(path)

    def test_put_escape_hatch_uses_module_level_request(self):
        """TINGWU_OSS_USE_PROXY=1 时走模块级 requests.put（旧行为）。"""
        os.environ["TINGWU_OSS_USE_PROXY"] = "1"
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"x" * 16)
            path = f.name
        try:
            captured = {}

            def fake_put(url, **kw):
                captured["called"] = True
                resp = MagicMock()
                resp.raise_for_status.return_value = None
                return resp

            with patch.object(tingwu.requests, "put", fake_put):
                tingwu._upload_via_requests(
                    path, {"putLink": "https://oss.example/put", "sts": FAKE_STS})
            self.assertTrue(captured.get("called"),
                            "逃生阀应恢复模块级 requests.put 旧行为")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
