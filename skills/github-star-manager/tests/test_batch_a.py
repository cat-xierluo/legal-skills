#!/usr/bin/env python3
"""github-star-manager 批次 A 离线回归套件（2026-10-15 审计修复验证）

覆盖审计 F01（快照完整性守卫）、F03（三断点）、批量计数器、时区、
分类双格式加载、价值配置读取、version-diff 参数校验。
全部离线运行：不访问网络、不需要 Token、不依赖 openai。

运行：python3 tests/test_batch_a.py
"""

import io
import json
import sys
import tempfile
import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import star_tracker  # noqa: E402
from star_tracker import StarTracker  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def make_tracker(tmp: Path) -> StarTracker:
    """离线 tracker：缓存指向临时目录，不读真实 output/"""
    t = StarTracker.__new__(StarTracker)
    t.github_token = None
    t.user = None
    t._auth_username = None
    t.last_fetch_meta = None
    t._client = None
    t._use_ai = False
    t.headers = {"Accept": "application/vnd.github.v3+json"}
    t.CACHE_DIR = tmp
    t.CONFIG_DIR = tmp
    t.CATEGORIES_FILE = tmp / "categories.yaml"
    t.TAGS_FILE = tmp / "tags.json"
    t.SETTINGS_FILE = tmp / "user_settings.json"
    t.categories = StarTracker._get_default_categories(t)
    t.tags = {"version": "1.0", "tags": [], "tag_aliases": {}}
    t.settings = {}
    return t


@contextlib.contextmanager
def no_yaml():
    """模拟 pyyaml 缺失"""
    saved = star_tracker.yaml
    star_tracker.yaml = None
    try:
        yield
    finally:
        star_tracker.yaml = saved


# ============ F01：快照完整性守卫 ============
print("\n[F01] 快照完整性守卫")
with tempfile.TemporaryDirectory() as td:
    t = make_tracker(Path(td))

    # 1. 完整快照可提交
    t.save_latest([{"full_name": "a/b", "id": 4242}], fetch_meta={
        "complete": True, "failed_pages": [], "account_id": "u",
        "limit_truncated": False})
    snap = t.load_latest()
    ok, reason = StarTracker.is_snapshot_submittable(snap)
    check("完整快照 complete=True 可提交", ok)
    check("快照写入 snapshot_meta", snap.get("snapshot_meta", {}).get("complete") is True)
    check("schema_version=2", snap.get("schema_version") == 2)
    check("repo 数字主键 id 进快照（D-00 缺口闭合）", snap["repos"][0].get("id") == 4242)

    # 2. 部分快照不可提交（旧基线保留语义）
    t.save_latest([{"full_name": "a/c"}], fetch_meta={
        "complete": False, "failed_pages": [{"page": 3, "status": "503"}],
        "account_id": "u", "limit_truncated": False})
    snap2 = t.load_latest()
    ok2, reason2 = StarTracker.is_snapshot_submittable(snap2)
    check("部分快照 complete=False 拒绝提交", not ok2)
    check("拒绝原因含失败页信息", "partial" in reason2)
    # CLI 守卫语义：check/init 在 is_snapshot_submittable 为 False 时不调用 save_latest
    # （save_latest 本身允许覆盖——守卫在 main.py 的调用层，见 init_command/check_command）

    # 4. 无元数据保存 → 完整性未知
    t.save_latest([{"full_name": "a/d"}])
    snap3 = t.load_latest()
    ok3, reason3 = StarTracker.is_snapshot_submittable(snap3)
    check("无元数据保存标记 completeness=unknown", not ok3 and "unknown" in reason3)

    # 5. v1 旧快照（无 snapshot_meta）加载时标记未知
    v1 = {"timestamp": "2026-01-01T00:00:00", "total_count": 1,
          "repos": [{"full_name": "a/v1"}]}
    (Path(td) / "original_latest.json").write_text(json.dumps(v1))
    snap4 = t.load_latest()
    ok4, reason4 = StarTracker.is_snapshot_submittable(snap4)
    check("v1 快照加载后标记完整性未知", not ok4 and "unknown" in reason4)
    check("v1 快照数据本身未损坏", snap4["repos"][0]["full_name"] == "a/v1")

    # 6. 空快照拒绝
    ok5, _ = StarTracker.is_snapshot_submittable(None)
    check("空快照拒绝提交", not ok5)


# ============ F03：三断点 ============
print("\n[F03] 三个可复现断点")
import inspect

# 1. load_latest 不再接受多余参数（generate_report 调用已改）
check("load_latest 仅 self 无额外必填参数", len([
    p for p in inspect.signature(StarTracker.load_latest).parameters.values()
    if p.default is inspect.Parameter.empty and p.name != "self"]) == 0)

# 2. HAS_OPENAI 已定义（NameError 消除）
check("模块级 HAS_OPENAI 已定义", hasattr(star_tracker, "HAS_OPENAI"))

# 3. AI 摘要在 openai 不可用时降级而非 NameError
with tempfile.TemporaryDirectory() as td:
    t = make_tracker(Path(td))
    saved_flag = star_tracker.HAS_OPENAI
    star_tracker.HAS_OPENAI = False
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = t.summarize_with_ai({"name": "x", "full_name": "a/x",
                                          "description": "d"})
        check("AI 不可用时降级为基础摘要", "核心功能" in result)
    finally:
        star_tracker.HAS_OPENAI = saved_flag

# 4. 分类加载兼容 {categories: [...]}（generate_categories.py 写出的格式）
# 注：本机 pyyaml 4.2b4 与 Python 3.14 不兼容（safe_load 解析 mapping 即崩），
# 这里 monkeypatch 成 json loader 验证解包分支——JSON 是 YAML 子集，双格式分支逻辑相同。
import types as _types
_json_loader = _types.SimpleNamespace(safe_load=lambda f: json.load(f))
_saved_yaml = star_tracker.yaml
star_tracker.yaml = _json_loader
try:
    with tempfile.TemporaryDirectory() as td:
        t = make_tracker(Path(td))
        (Path(td) / "categories.yaml").write_text(json.dumps({
            "categories": [{"id": "gen1", "name": "G", "icon": "x", "color": "#fff",
                            "keywords": ["gen"]}],
            "_meta": {"generated_at": "now"}}))
        cats = t._load_categories()
        check("根对象格式分类正确解包", any(c["id"] == "gen1" for c in cats))

    # 5. 裸列表格式仍兼容
    with tempfile.TemporaryDirectory() as td:
        t = make_tracker(Path(td))
        (Path(td) / "categories.yaml").write_text(json.dumps(
            [{"id": "bare1", "name": "B", "icon": "x", "color": "#fff", "keywords": []}]))
        cats = t._load_categories()
        check("裸列表格式分类仍可加载", any(c["id"] == "bare1" for c in cats))
finally:
    star_tracker.yaml = _saved_yaml

# 6. yaml 解析崩溃不再静默（旧 pyyaml 环境必须可见）
class _CrashYaml:
    @staticmethod
    def safe_load(f):
        raise AttributeError("module 'collections' has no attribute 'Hashable'")

star_tracker.yaml = _CrashYaml
try:
    with tempfile.TemporaryDirectory() as td:
        t = make_tracker(Path(td))
        (Path(td) / "categories.yaml").write_text("categories: []")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cats = t._load_categories()
        check("yaml 崩溃时回落默认分类", any(c["id"] == "ai" for c in cats))
        check("yaml 崩溃时打印可见警告", "加载失败" in buf.getvalue() and "pyyaml" in buf.getvalue())
finally:
    star_tracker.yaml = _saved_yaml


# ============ 批量计数器 ============
print("\n[批量] batch_star/batch_unstar 计数器")
with tempfile.TemporaryDirectory() as td:
    t = make_tracker(Path(td))

    def fake_unstar(name):
        return False, "模拟失败"

    saved = t.unstar_repo
    t.unstar_repo = fake_unstar
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            success, failed, failed_repos = t.batch_unstar(["a/fail"], dry_run=False)
        check("失败路径不再 TypeError（failed 为整数）", isinstance(failed, int))
        check("失败计数正确", success == 0 and failed == 1 and failed_repos == ["a/fail"])
    finally:
        t.unstar_repo = saved


def fake_star(name):
    return False, "模拟失败"


with tempfile.TemporaryDirectory() as td:
    t = make_tracker(Path(td))
    saved = t.star_repo
    t.star_repo = fake_star
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            success, failed, _ = t.batch_star(["a/fail"], dry_run=False)
        check("batch_star 失败路径同样安全", failed == 1)
    finally:
        t.star_repo = saved


# ============ 时区 ============
print("\n[时区] cleanup_stale_repos aware/naive")
with tempfile.TemporaryDirectory() as td:
    t = make_tracker(Path(td))

    def fake_get_starred(username, limit=200, include_starred_at=True):
        recent = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        return [{"full_name": "a/new", "updated_at": recent,
                 "stargazers_count": 5}]

    saved = t.get_starred_repos
    t.get_starred_repos = fake_get_starred
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            count, repos = t.cleanup_stale_repos("u", days_threshold=90)
        check("aware 时间不再崩溃", count == 0 and repos == [])
    finally:
        t.get_starred_repos = saved


# ============ 配置持久化 ============
print("\n[配置] import/save_settings/get_value_config")
with tempfile.TemporaryDirectory() as td:
    t = make_tracker(Path(td))
    ok = t.import_config({"username": "u", "value_keywords": ["rust"], "min_stars": 50})
    check("import_config 持久化成功", ok and t.SETTINGS_FILE.exists())
    on_disk = json.loads(t.SETTINGS_FILE.read_text())
    check("设置真实落盘", on_disk.get("value_keywords") == ["rust"])
    vc = t.get_value_config()
    check("get_value_config 读回自定义关键词", vc["value_keywords"] == ["rust"])
    check("get_value_config 读回阈值", vc["min_stars"] == 50)

    check("缺 username 的配置拒绝", not t.import_config({"foo": 1}))


# ============ version-diff 参数校验 ============
print("\n[version-diff] CLI 参数校验（不发网络请求）")
import importlib.util
spec = importlib.util.spec_from_file_location("gsm_main", SCRIPTS / "main.py")
# main.py import 时会执行模块级代码（load_dotenv 等），安全；main() 不执行


def run_vd(repo=None, old=None, new=None):
    """直接调用 version_diff_command 的参数校验路径（缺参在发请求前返回 1）"""
    import main as main_mod

    class A:
        pass

    a = A()
    a.version_repo = repo
    a.old_version = old
    a.new_version = new
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main_mod.version_diff_command(None, a)
    return rc, buf.getvalue()


def load_main_module():
    import main as main_mod
    return main_mod


main_mod = load_main_module()
rc1, out1 = run_vd()
check("全缺参返回 1", rc1 == 1 and "--repo" in out1)
rc2, out2 = run_vd(repo="owner/repo", old="v1")
check("缺 new-version 返回 1", rc2 == 1 and "--new-version" in out2)

# get_version_diff 网络异常路径（tracker 无 token、_request_with_retry 返回 None）
with tempfile.TemporaryDirectory() as td:
    t = make_tracker(Path(td))
    t._request_with_retry = lambda *a, **k: None
    diff = t.get_version_diff("o/r", "v1", "v2")
    check("网络失败返回 error 字段而非崩溃", "error" in diff and "compare_url" in diff)


# ============ common.py 共享价值评估 ============
print("\n[common] 统一价值评估")
import common

cfg_default = common.load_value_config(Path("/nonexistent/settings.json"))
check("配置缺失回落默认关键词", cfg_default["value_keywords"] == common.DEFAULT_VALUE_KEYWORDS)
check("高星判定 high", common.assess_value(
    {"stargazers_count": 9000, "language": "Go", "description": "x"}, cfg_default) == "high")
check("普通判定 low", common.assess_value(
    {"stargazers_count": 10, "language": "Ruby", "description": "x"}, cfg_default) == "low")
cfg_kw = dict(cfg_default, value_keywords=["mykw"])
check("自定义关键词生效", common.assess_value(
    {"stargazers_count": 10, "language": "Ruby", "description": "mykw tool"}, cfg_kw) == "high")

# 两条导出路径使用同一实现
import quick_export
check("quick_export.assess_value 即 common 实现", quick_export.assess_value is common.assess_value)

# ============ 汇总 ============
print(f"\n{'=' * 50}")
print(f"结果: {PASS} 通过 / {FAIL} 失败")
sys.exit(1 if FAIL else 0)
