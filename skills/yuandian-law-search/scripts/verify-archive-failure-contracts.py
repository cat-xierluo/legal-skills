#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无网络故障注入回归：归档失败不得吞掉已取得的 API 响应（issue #158）。

覆盖：
1. GET / POST 响应已取得时，归档写入 PermissionError 只告警降级，不抛异常、不重试；
2. --no-archive：不写任何本地留存（目录不创建、返回 None），查重读取不受影响；
3. --archive-dir / YD_ARCHIVE_DIR 重设归档目录生效；
4. SKILL.md 不再宣称 --no-report 能"完全跳过"本地归档。
"""

import contextlib
import io
import os
import sys
import types
from pathlib import Path

import yd_search


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        import json
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_archive_failure_does_not_swallow_response():
    """api_post / api_get 响应已取得后，归档 PermissionError 只降级告警。"""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        return _FakeResponse({"code": 0, "data": {"ok": True}})

    def failing_save(endpoint, payload, response):
        raise PermissionError(13, "Permission denied", "/readonly/archive")

    original_urlopen = yd_search.urlopen
    original_save = yd_search._archive_save
    original_key = yd_search.load_api_key
    yd_search.urlopen = fake_urlopen
    yd_search._archive_save = failing_save
    yd_search.load_api_key = lambda: "test-key"
    try:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            post_result, post_cached, post_path = yd_search.api_post(
                "/open/law_vector_search", {"query": "测试"}, use_cache=True
            )
            get_result, get_cached, get_path = yd_search.api_get(
                "/open/rh_fg_search", params={"fgmc": "民法典"}, use_cache=True
            )
        _require(post_result == {"code": 0, "data": {"ok": True}}, "POST 响应被归档失败吞掉")
        _require(get_result == {"code": 0, "data": {"ok": True}}, "GET 响应被归档失败吞掉")
        _require(post_cached is False and get_cached is False, "应发起实际请求")
        _require(post_path is None and get_path is None, "归档失败时应返回 None 而非抛异常")
        _require(len(calls) == 2, "归档失败不得触发自动重试")
        warning = stderr.getvalue()
        _require("归档写入失败" in warning, "应有 stderr 告警")
        _require("--archive-dir" in warning, "告警应给出修复出口")
    finally:
        yd_search.urlopen = original_urlopen
        yd_search._archive_save = original_save
        yd_search.load_api_key = original_key
    print("PASS 归档失败不吞响应（POST/GET 均正常交付、零重试、stderr 告警）")


def test_no_archive_flag(tmp_root):
    """--no-archive：不创建目录、不写文件；查重仍读已有归档。"""
    original_dir = yd_search.ARCHIVE_DIR
    original_no = yd_search.NO_ARCHIVE
    archive_dir = tmp_root / "no_archive_case"
    try:
        yd_search.ARCHIVE_DIR = archive_dir
        yd_search.NO_ARCHIVE = True

        path = yd_search._archive_save("/open/law_vector_search", {"query": "测试"}, {"data": {}})
        _require(path is None, "NO_ARCHIVE 时 _archive_save 应返回 None")
        _require(not archive_dir.exists(), "NO_ARCHIVE 时不得创建归档目录")

        # 查重不受 --no-archive 影响：预置一份归档，_archive_lookup 应能命中
        yd_search.NO_ARCHIVE = False
        yd_search._archive_save("/open/law_vector_search", {"query": "查重命中测试"}, {"data": {"hit": True}})
        _require(archive_dir.exists(), "对照组应正常写入归档")
        cached, _ = yd_search._archive_lookup("/open/law_vector_search", {"query": "查重命中测试"})
        _require(cached is not None and cached.get("data", {}).get("hit") is True, "查重应命中已有归档")
    finally:
        yd_search.ARCHIVE_DIR = original_dir
        yd_search.NO_ARCHIVE = original_no
    print("PASS --no-archive 零写入；查重仍读已有归档")


def test_archive_dir_settings(tmp_root):
    """--archive-dir 优先于 YD_ARCHIVE_DIR，YD_ARCHIVE_DIR 优先于默认值。"""
    original_dir = yd_search.ARCHIVE_DIR
    original_no = yd_search.NO_ARCHIVE
    cli_dir = tmp_root / "from_cli"
    env_dir = tmp_root / "from_env"
    old_env = os.environ.get("YD_ARCHIVE_DIR")
    try:
        # CLI 优先
        os.environ["YD_ARCHIVE_DIR"] = str(env_dir)
        yd_search._apply_archive_settings(types.SimpleNamespace(archive_dir=str(cli_dir), no_archive=False))
        _require(yd_search.ARCHIVE_DIR == cli_dir.resolve(), "--archive-dir 应优先生效")
        # env 次之
        yd_search._apply_archive_settings(types.SimpleNamespace(archive_dir=None, no_archive=False))
        _require(yd_search.ARCHIVE_DIR == env_dir.resolve(), "YD_ARCHIVE_DIR 应生效")
        # no_archive 透传
        yd_search._apply_archive_settings(types.SimpleNamespace(archive_dir=None, no_archive=True))
        _require(yd_search.NO_ARCHIVE is True, "--no-archive 应置位")
    finally:
        yd_search.ARCHIVE_DIR = original_dir
        yd_search.NO_ARCHIVE = original_no
        if old_env is None:
            os.environ.pop("YD_ARCHIVE_DIR", None)
        else:
            os.environ["YD_ARCHIVE_DIR"] = old_env
    print("PASS 归档目录解析优先级：--archive-dir > YD_ARCHIVE_DIR > 默认")


def test_skill_doc_no_report_claim():
    """SKILL.md 不得再宣称 --no-report 可关闭 archive JSON 归档。"""
    doc = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text("utf-8")
    _require(
        "完全跳过本地报告" not in doc and "完全跳过归档" not in doc,
        "SKILL.md 仍有 --no-report 完全跳过的失实表述",
    )
    _require("--no-archive" in doc, "SKILL.md 应说明 --no-archive 语义")
    print("PASS SKILL.md --no-report/--no-archive 语义表述准确")


def main():
    import tempfile
    with tempfile.TemporaryDirectory(prefix="yd_archive_test_") as td:
        tmp_root = Path(td)
        test_archive_failure_does_not_swallow_response()
        test_no_archive_flag(tmp_root)
        test_archive_dir_settings(tmp_root)
    test_skill_doc_no_report_claim()
    print("\n全部通过：4 项归档故障注入契约")


if __name__ == "__main__":
    sys.exit(main())
