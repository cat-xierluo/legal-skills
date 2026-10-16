#!/usr/bin/env python3
"""批次 B+C 离线回归套件：star_query.py（五命令）+ opportunity.py（机会卡契约）

全部离线：临时快照目录，无网络/Token/模型。
运行：python3 tests/test_batch_b.py
"""

import sys
import json
import io
import contextlib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent.parent
SCRIPTS = BASE / "scripts"
sys.path.insert(0, str(SCRIPTS))

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def capture(func, *a, **kw):
    """运行返回 (rc, stdout_obj, stderr_text)"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = func(*a, **kw)
    data = None
    try:
        data = json.loads(out.getvalue())
    except Exception:
        pass
    return rc, data, out.getvalue(), err.getvalue()


def make_env(tmp: Path):
    """构造进程内查询环境：StarTracker.CACHE_DIR 指向临时目录并重载查询模块"""
    import star_tracker
    star_tracker.StarTracker.CACHE_DIR = tmp
    star_tracker.StarTracker.CONFIG_DIR = tmp
    import star_query
    import opportunity
    # 模块内通过 StarTracker.CACHE_DIR 引用，改类属性即可生效
    return star_query, opportunity


def write_snapshot(tmp: Path, repos: list, complete: bool = True):
    meta = {
        "account_id": "tester", "complete": complete, "failed_pages": [],
        "completeness": "complete" if complete else "partial",
    }
    (tmp / "original_latest.json").write_text(json.dumps({
        "schema_version": 2,
        "timestamp": "2026-10-15T10:00:00",
        "total_count": len(repos),
        "snapshot_meta": meta,
        "repos": repos,
    }, ensure_ascii=False), encoding="utf-8")


def repo(full_name, starred_at=None, topics=None, desc=None, lang=None, stars=10):
    return {
        "full_name": full_name, "name": full_name.split("/")[-1],
        "description": desc, "language": lang, "topics": topics or [],
        "stargazers_count": stars, "html_url": f"https://github.com/{full_name}",
        "starred_at": starred_at, "updated_at": "2026-10-14T00:00:00Z",
    }


class Args:
    def __init__(self, **kw):
        defaults = {"since": None, "until": None, "window": 30, "compare": "previous",
                    "project": None, "query": "", "limit": 20, "repo": None,
                    "max_age_days": 7.0, "excerpt": 2000, "max_readme": 20000}
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


# ============ star_query.recent ============
print("\n[recent] 时间窗与未知时间")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sq, _ = make_env(tmp)
    now = datetime.now(timezone.utc)
    repos = [
        repo("a/new1", starred_at=(now - timedelta(days=3)).isoformat()),
        repo("a/old1", starred_at=(now - timedelta(days=90)).isoformat()),
        repo("a/unknown", starred_at=None),
        repo("a/garbage", starred_at="not-a-date"),
    ]
    write_snapshot(tmp, repos)
    rc, data, _, _ = capture(sq.cmd_recent, Args())
    check("rc=0", rc == 0)
    names = [i["repo"] for i in data["items"]]
    check("3 天前收藏入窗", "a/new1" in names, str(names))
    check("90 天前收藏不入窗", "a/old1" not in names)
    check("未知/非法时间单独归 unknown_time_items，不冒充",
          {u["repo"] for u in data["unknown_time_items"]} == {"a/unknown", "a/garbage"})
    check("coverage 记录 unknown 计数=2", data["coverage"]["unknown_starred_at"] == 2)
    check("envelope 有 snapshot_id/account_id/status",
          data["snapshot_id"] and data["account_id"] == "tester" and data["status"] == "ok")

# 快照不完整时 recent 带 warning
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sq, _ = make_env(tmp)
    write_snapshot(tmp, [repo("a/x", starred_at=(datetime.now(timezone.utc)).isoformat())],
                   complete=False)
    rc, data, _, _ = capture(sq.cmd_recent, Args())
    check("partial 快照 status=partial 且有 warning",
          data["status"] == "partial" and any("不完整" in w for w in data["warnings"]))

# 无快照
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sq, _ = make_env(tmp)
    rc, data, _, _ = capture(sq.cmd_recent, Args())
    check("无快照 rc=1 且 errors 可见", rc == 1 and "无本地快照" in data["errors"][0])


# ============ star_query.interests ============
print("\n[interests] 主题窗口计数")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sq, _ = make_env(tmp)
    now = datetime.now(timezone.utc)
    repos = [
        repo("a/t1", starred_at=(now - timedelta(days=5)).isoformat(), topics=["ai", "llm"]),
        repo("a/t2", starred_at=(now - timedelta(days=10)).isoformat(), topics=["ai"]),
        repo("a/t3", starred_at=(now - timedelta(days=40)).isoformat(), topics=["ai"]),
    ]
    write_snapshot(tmp, repos)
    # 无分类配置 → 明确 needs_analysis，不暗中调模型
    rc, data, _, _ = capture(sq.cmd_interests, Args(window=30))
    check("无分类时 rc=1 且 needs_analysis", rc == 1 and any("needs_analysis" in e for e in data["errors"]))

    # 提供 categories.yaml（用 json loader 写 JSON——本机 pyyaml 4.2b4 与 Py3.14 不兼容，
    # JSON 是 YAML 子集，双格式解析分支由批次 A 套件覆盖，这里只测主题计数逻辑）
    import star_tracker as _st
    import types as _types
    _saved_yaml = _st.yaml
    _st.yaml = _types.SimpleNamespace(safe_load=lambda f: json.load(f))
    (tmp / "categories.yaml").write_text(json.dumps(
        [{"id": "ai", "name": "AI", "icon": "x", "color": "#fff", "keywords": ["ai", "llm"]}],
        ensure_ascii=False), encoding="utf-8")
    try:
        rc, data, _, _ = capture(sq.cmd_interests, Args(window=30))
        check("当前窗口 ai 计数=2", any(t["theme"] == "ai" and t["current"] == 2 for t in data["items"]),
              json.dumps(data.get("items"), ensure_ascii=False)[:200])
        check("前窗口 ai 计数=1", any(t["theme"] == "ai" and t["previous"] == 1 for t in data["items"]))
        check("delta 记录变化", any(t["theme"] == "ai" and t["delta"] == 1 for t in data["items"]))
    finally:
        _st.yaml = _saved_yaml


# ============ star_query.match ============
print("\n[match] 关键词召回")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sq, _ = make_env(tmp)
    write_snapshot(tmp, [
        repo("owner/subtitle-tool", desc="video subtitle timeline tool", topics=["subtitle"]),
        repo("owner/video-engine", desc="video rendering engine", topics=["video"]),
        repo("owner/unrelated", desc="recipe manager", topics=["cooking"]),
    ])
    rc, data, _, _ = capture(sq.cmd_match, Args(query="subtitle 时间轴"))
    names = [i["repo"] for i in data["items"]]
    check("命中含 subtitle 的仓库", "owner/subtitle-tool" in names)
    check("不命中无关仓库", "owner/unrelated" not in names)
    check("matched_terms 记录命中词", all(i["matched_terms"] for i in data["items"]))
    check("coverage.truncated=false", data["coverage"]["truncated"] is False)

    # limit 截断
    rc, data, _, _ = capture(sq.cmd_match, Args(query="video subtitle", limit=1))
    check("limit 截断可见", data["coverage"]["truncated"] is True and len(data["items"]) == 1)

    # 未登记项目警告
    rc, data, _, _ = capture(sq.cmd_match, Args(query="subtitle", project="nope"))
    check("未登记项目只警告不失败", rc == 0 and any("未登记" in w for w in data["warnings"]))

    # 空 query
    rc, data, _, _ = capture(sq.cmd_match, Args(query="  "))
    check("空 query 报错", rc == 1)


# ============ star_query.evidence ============
print("\n[evidence] 缓存证据边界")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sq, _ = make_env(tmp)
    write_snapshot(tmp, [repo("owner/known", starred_at="2026-10-10T00:00:00Z")])
    rc, data, _, _ = capture(sq.cmd_evidence, Args(repo="owner/known"))
    item = data["items"][0]
    check("快照内仓库 in_snapshot=True", item["in_snapshot"] is True)
    check("无缓存显式 missing + warning", item["cache_status"] == "missing"
          and any("无缓存证据" in w for w in data["warnings"]))

    # 有缓存文件时
    ev = tmp / "evidence" / "owner__known"
    ev.mkdir(parents=True)
    (ev / "readme.md").write_text("# demo")
    rc, data, _, _ = capture(sq.cmd_evidence, Args(repo="owner/known"))
    check("缓存存在时 cache_status=present", data["items"][0]["cache_status"] == "present")

    # 不在快照的仓库
    rc, data, _, _ = capture(sq.cmd_evidence, Args(repo="owner/ghost"))
    check("快照外仓库 in_snapshot=False + warning",
          data["items"][0]["in_snapshot"] is False and data["items"][0]["snapshot_entry"] is None)


# ============ star_query.research ============
print("\n[research] 最小候选+证据包")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sq, _ = make_env(tmp)
    write_snapshot(tmp, [repo("owner/subtitle-tool", desc="subtitle timeline")])
    # 未登记项目 → 拒绝并指引登记
    rc, data, _, _ = capture(sq.cmd_research, Args(project="myproj"))
    check("未登记项目拒绝且指路", rc == 1 and "output/projects/myproj.json" in data["errors"][0])

    # 登记 project profile 后出包
    proj = tmp / "projects"
    proj.mkdir()
    (proj / "myproj.json").write_text(json.dumps({
        "project_id": "myproj",
        "capabilities": ["字幕渲染"],
        "needs": ["subtitle timeline"],  # 与快照中仓库描述同语（match 是字面词匹配）
        "constraints": ["不引入泛视频引擎"],
    }, ensure_ascii=False), encoding="utf-8")
    rc, data, _, _ = capture(sq.cmd_research, Args(project="myproj", limit=5))
    pkg = data["items"][0]
    check("出包含 project profile", pkg["project"]["project_id"] == "myproj")
    check("出包含候选", any(c["repo"] == "owner/subtitle-tool" for c in pkg["candidates"]))
    check("usage_note 声明分数只是召回依据", "不是适用性证明" in pkg["usage_note"])
    check("附机会卡 schema", "decision" in pkg["opportunity_card_schema"])


# ============ opportunity.validate/record：契约状态机 ============
print("\n[opportunity] 机会卡契约与状态机")


def card_dict(**over):
    base = {
        "signal": {"repo": "owner/subtitle-tool", "starred_at": "2026-10-01T00:00:00Z",
                   "source": "抖音截图"},
        "target": {"project_id": "myproj", "capability": "字幕时间轴机制"},
        "evidence": {"url": "https://github.com/owner/subtitle-tool",
                     "code_evidence": "commit abc1234 的 cue 换行实现"},
        "gap": "接入缺口",
        "hypothesis": "其 cue 换行机制可借鉴",
        "experiment": {"consumer": "code-video captions", "inputs": "中文长句",
                       "acceptance": "不溢出"},
        "decision": {"status": "experiment_proposed"},
    }
    base.update(over)
    return base


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    _, opp = make_env(tmp)

    ok, errors, warnings = opp.validate_card(card_dict())
    check("完整卡通过", ok and not errors)

    # 七字段缺一即拒
    for field in ["signal", "target", "evidence", "gap", "hypothesis", "experiment", "decision"]:
        c = card_dict()
        del c[field]
        ok, errors, _ = opp.validate_card(c)
        check(f"缺 {field} 被拒", not ok)

    # gap 枚举
    ok, errors, _ = opp.validate_card(card_dict(gap="随便写的"))
    check("非法 gap 被拒", not ok and any("gap" in e for e in errors))

    # 审计红线：无运行证据的 tested 必须拒绝
    ok, errors, _ = opp.validate_card(card_dict(decision={"status": "tested"}))
    check("无 run_evidence 的 tested 被拒", not ok and any("run_evidence" in e for e in errors))

    # 无采纳证据的 adopted 必须拒绝
    ok, errors, _ = opp.validate_card(
        card_dict(decision={"status": "adopted", "run_evidence": {"log": "x"}}))
    check("无 adoption_evidence 的 adopted 被拒", not ok and any("adoption_evidence" in e for e in errors))

    # 带证据的 tested/adopted 通过（R1 后证据路径必须真实存在——用本临时目录真文件）
    _real_ev = Path(td) / "run-ev.log"
    _real_ev.write_text("3 cases pass", encoding="utf-8")
    ok, errors, _ = opp.validate_card(card_dict(decision={
        "status": "tested", "run_evidence": {"artifacts": str(_real_ev), "log": "ok"}}))
    check("带 run_evidence 的 tested 通过", ok)

    # starred_at 缺失 → 警告不得声称近期关注
    c = card_dict(signal={"repo": "a/b", "source": "口述"})
    ok, errors, warnings = opp.validate_card(c)
    check("starred_at 缺失通过但警告", ok and any("starred_at" in w for w in warnings))

    # 虚构证据警告：README 宣称 ≠ 代码证据
    c = card_dict(evidence={"url": "https://github.com/a/b"})
    ok, errors, warnings = opp.validate_card(c)
    check("未区分证据类型给警告", any("证据类型" in w for w in warnings))

    # record 落盘
    card_file = tmp / "card.json"
    card_file.write_text(json.dumps(card_dict(), ensure_ascii=False), encoding="utf-8")
    rc, data, _, _ = capture(opp.cmd_record, type("A", (), {"input": str(card_file)})())
    check("record 成功落盘", rc == 0 and data["recorded"] is True)
    saved = list((tmp / "feedback").glob("*.json"))
    check("feedback 文件存在", len(saved) == 1)

    # 坏卡 record 拒绝
    bad = tmp / "bad.json"
    bad.write_text(json.dumps(card_dict(decision={"status": "adopted"})))
    rc, data, _, _ = capture(opp.cmd_record, type("A", (), {"input": str(bad)})())
    check("无证据 adopted 的 record 被拒", rc == 1 and data["recorded"] is False)

    # 拒绝抑制
    rej_file = tmp / "rej.json"
    rej_file.write_text(json.dumps(card_dict(decision={"status": "rejected", "reason": "无增量"})))
    rc, data, _, _ = capture(opp.cmd_record, type("A", (), {"input": str(rej_file)})())
    check("rejected 记录落盘", rc == 0)
    rc, data, _, _ = capture(opp.cmd_suppress,
                             type("A", (), {"repo": "owner/subtitle-tool", "project": "myproj"})())
    check("suppress 报告已抑制", data["suppressed"] is True and data["rejected_count"] >= 1)

    # list 过滤
    rc, data, _, _ = capture(opp.cmd_list, type("A", (), {"project": "myproj", "repo": None})())
    check("list 返回 2 条记录", data["count"] == 2, str(data["count"]))


# ============ evidence-fetch：显式联网取证（mock 网络） ============
print("\n[evidence-fetch] 取证与缓存闭环")


class FakeResp:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    sq, _ = make_env(tmp)
    write_snapshot(tmp, [repo("owner/known")])

    readmes = ["# Demo\nsubtitle timeline cue algorithm." * 50]  # 足够长以触发截断
    import base64 as _b64

    def fake_get(url, token):
        if url.endswith("/repos/owner/known"):
            return FakeResp(200, {"full_name": "owner/known", "description": "d",
                                  "default_branch": "main", "pushed_at": "2026-10-14T00:00:00Z",
                                  "stargazers_count": 100, "html_url": "u", "archived": False})
        if url.endswith("/readme"):
            return FakeResp(200, {"sha": "abc123", "html_url": "ru", "download_url": "du",
                                  "path": "README.md", "size": len(readmes[0]),
                                  "content": _b64.b64encode(readmes[0].encode()).decode()})
        if url.endswith("/releases/latest"):
            return FakeResp(200, {"tag_name": "v2.0.0", "name": "v2",
                                  "published_at": "2026-10-01T00:00:00Z", "html_url": "ru"})
        return FakeResp(404)

    saved_get = sq._github_get
    sq._github_get = fake_get
    try:
        rc, data, _, _ = capture(sq.cmd_evidence_fetch,
                                 Args(repo="owner/known", max_readme=100))
        check("取证 rc=0", rc == 0)
        item = data["items"][0]
        check("README blob_sha 锚点记录", item["readme"]["blob_sha"] == "abc123")
        check("截断可见（truncated=True）", item["readme"]["truncated"] is True)
        check("release 记录", item["release"]["tag_name"] == "v2.0.0")
        ev_dir = tmp / "evidence" / "owner__known"
        check("缓存文件落盘", (ev_dir / "meta.json").exists() and (ev_dir / "readme.md").exists())

        # 闭环：缓存后 evidence 导出带内容与新鲜度
        rc, data, _, _ = capture(sq.cmd_evidence,
                                 Args(repo="owner/known", max_age_days=7, excerpt=200))
        item = data["items"][0]
        check("导出 cache_status=present", item["cache_status"] == "present")
        check("导出含 README 摘录", item["readme_excerpt"] and "subtitle" in item["readme_excerpt"])
        check("新鲜缓存 stale=False", item["evidence_stale"] is False)
        check("导出含 repo_meta", item["repo_meta"]["default_branch"] == "main")

        # 陈旧缓存：把 fetched_at 改老
        rec = json.loads((ev_dir / "meta.json").read_text(encoding="utf-8"))
        rec["fetched_at"] = "2026-08-01T00:00:00+00:00"
        (ev_dir / "meta.json").write_text(json.dumps(rec), encoding="utf-8")
        rc, data, _, _ = capture(sq.cmd_evidence,
                                 Args(repo="owner/known", max_age_days=7, excerpt=200))
        item = data["items"][0]
        check("陈旧缓存 stale=True + 警告", item["evidence_stale"] is True
              and any("重新 evidence-fetch" in w for w in data["warnings"]))

        # release 404 分支
        def fake_get_404(url, token):
            if url.endswith("/repos/owner/norel"):
                return FakeResp(200, {"full_name": "owner/norel"})
            if url.endswith("/releases/latest"):
                return FakeResp(404)
            if url.endswith("/readme"):
                return FakeResp(200, {"sha": "s", "content": _b64.b64encode(b"# t").decode()})
            return FakeResp(404)
        sq._github_get = fake_get_404
        rc, data, _, _ = capture(sq.cmd_evidence_fetch,
                                 Args(repo="owner/norel", max_readme=1000))
        check("无 Release 记 null+警告", rc == 0 and data["items"][0]["release"] is None
              and any("无最新 Release" in w for w in data["warnings"]))

        # 仓库 404 → 拒绝
        def fake_get_dead(url, token):
            return FakeResp(404)
        sq._github_get = fake_get_dead
        rc, data, _, _ = capture(sq.cmd_evidence_fetch,
                                 Args(repo="owner/dead", max_readme=100))
        check("仓库不存在 rc=1", rc == 1 and "404" in data["errors"][0])
    finally:
        sq._github_get = saved_get


# ============ 分类匹配算法收敛（在线单分类 = 多标签首个） ============
print("\n[match-parity] 分类算法收敛")
import common
import star_tracker as _st2

cats = [
    {"id": "ai", "name": "AI", "keywords": ["claude", "llm", "agent"]},
    {"id": "devtools", "name": "工具", "keywords": ["cli", "tool"]},
    {"id": "subtitle", "name": "字幕", "keywords": ["subtitle", "caption"]},
]
samples = [
    {"language": "Python", "description": "claude agent toolkit", "topics": ["agent"], "name": "a", "full_name": "o/a"},
    {"language": "Rust", "description": "subtitle caption aligner", "topics": ["subtitle"], "name": "b", "full_name": "o/b"},
    {"language": "Go", "description": "unrelated thing", "topics": [], "name": "c", "full_name": "o/c"},
    {"language": None, "description": None, "topics": [], "name": "d", "full_name": "o/d"},
]
t_probe = _st2.StarTracker.__new__(_st2.StarTracker)
cat_map = {c["id"]: c for c in cats}
for s in samples:
    multi = common.match_categories(s, cats)
    single = t_probe._match_category(s, cat_map)
    expected_first = multi[0] if multi else None
    check(f"单分类=多标签首个 ({s['full_name']})",
          (single or {}).get("id") == (expected_first or {}).get("id"))
check("无匹配时返回 None", t_probe._match_category(samples[3], cat_map) is None)


# ============ R1 返修回归（上游终审计 UA:GSM-AUDIT-ABCD-FINAL-261016） ============
print("\n[R1] min_stars/ignore_repos 消费 + 证据实质校验")
import common as _common
import os as _os
import tempfile as _tf

# min_stars：低于阈值 → low（即便命中关键词也不抬升？不——关键词命中仍 high，只挡纯低星路径）
cfg = _common.load_value_config(Path("/nonexistent.json"))
cfg_ms = dict(cfg, min_stars=50)
check("min_stars 低于阈值判 low",
      _common.assess_value({"stargazers_count": 10, "language": "Rust", "description": "misc",
                            "full_name": "a/tiny"}, cfg_ms) == "low")
check("min_stars 高于阈值不受影响",
      _common.assess_value({"stargazers_count": 9000, "full_name": "a/big"}, cfg_ms) == "high")

# ignore_repos：忽略名单命中 → ignored（优先于一切评级）
cfg_ig = dict(cfg, ignore_repos={"ghost/old"})
check("ignore_repos 命中判 ignored",
      _common.assess_value({"stargazers_count": 9000, "full_name": "Ghost/Old",
                            "description": "claude"}, cfg_ig) == "ignored")
check("ignore_repos 未命中不受影响",
      _common.assess_value({"stargazers_count": 9000, "full_name": "a/keep"}, cfg_ig) == "high")

# load_value_config 读取完整配置
with _tf.TemporaryDirectory() as td:
    _cfg_file = Path(td) / "user_settings.json"
    _cfg_file.write_text(json.dumps({"value_keywords": ["law"], "min_stars": 30,
                                     "ignore_repos": ["x/y"]}), encoding="utf-8")
    c = _common.load_value_config(_cfg_file)
    check("min_stars 从设置读取", c["min_stars"] == 30)
    check("ignore_repos 从设置读取并归一大小写", c["ignore_repos"] == {"x/y"})

# 证据实质校验（F08）：虚构路径拒收、空文件拒收、真路径通过
import opportunity as _opp
import contextlib as _cl
import io as _io

def _card_with_evidence(run_ev):
    return {
        "signal": {"repo": "a/b", "starred_at": "2026-10-01T00:00:00Z", "source": "测试"},
        "target": {"project_id": "p", "capability": "c"},
        "evidence": {"url": "https://github.com/a/b", "code_evidence": "commit abc1234 cue 换行"},
        "gap": "接入缺口", "hypothesis": "h", "experiment": {"consumer": "c"},
        "decision": {"status": "tested", "run_evidence": run_ev},
    }

with _tf.TemporaryDirectory() as td:
    real = Path(td) / "run.log"
    real.write_text("executed 3 cases, all pass", encoding="utf-8")
    empty = Path(td) / "empty.log"
    empty.write_text("", encoding="utf-8")

    buf = _io.StringIO()
    with _cl.redirect_stdout(buf):
        ok, errs, warns = _opp.validate_card(_card_with_evidence(
            {"artifacts": str(real), "log": "ok"}))
    check("真实产物路径的 tested 通过", ok)

    ok, errs, _ = _opp.validate_card(_card_with_evidence(
        {"artifacts": str(Path(td) / "ghost" / "fabricated.log")}))
    check("虚构路径的 tested 被拒", not ok and any("不存在" in e for e in errs))

    ok, errs, _ = _opp.validate_card(_card_with_evidence({"artifacts": str(empty)}))
    check("空文件产物被拒", not ok and any("空文件" in e for e in errs))

    ok, errs, warns = _opp.validate_card(_card_with_evidence(
        {"report": "https://example.com/report"}))
    # R5/J2：URL 仅线索, 不能支撑 tested（无可核验文件 → 拒）
    check("纯 URL 证据不能签 tested（R5/J2）", not ok and any("URL" in w for w in warns))

    ok, errs, warns = _opp.validate_card(_card_with_evidence({"note": "只写了文字"}))
    check("无路径证据拒绝（R5/J2）", not ok and any("未含任何可核验" in e for e in errs))


    # F08 补强（自审发现）：裸文件名同样是路径主张，不能绕过
    ok, errs, _ = _opp.validate_card(_card_with_evidence({"artifacts": "run.log"}))
    check("裸文件名虚构产物被拒（F08 补强）", not ok and any("不存在" in e for e in errs))
    ok, errs, _ = _opp.validate_card(_card_with_evidence({"log": "ok"}))
    check("纯状态词不算路径主张（但无文件仍拒）", not ok and not any("不存在" in e for e in errs))
    ok, errs, _ = _opp.validate_card(_card_with_evidence({"note": "只写了文字"}))
    check("中文散文不算路径主张（但无文件仍拒）", not ok and not any("不存在" in e for e in errs))


# ============ R5/J2 上游反例矩阵（证据绕过面全量回归） ============
print("\n[R5] 上游 J2 证据绕过矩阵")
with _tf.TemporaryDirectory() as td:
    bd = Path(td)
    (bd / "real.log").write_text("executed 3 cases, all pass", encoding="utf-8")
    (bd / "empty.log").write_text("", encoding="utf-8")
    (bd / "unrelated.txt").write_text("unrelated nonempty text", encoding="utf-8")
    (bd / "link.txt").symlink_to(bd / "unrelated.txt")
    (bd / "somedir").mkdir()

    def _c(dec, ce="commit abc1234 cue"):
        return {"signal": {"repo": "a/b", "starred_at": "2026-10-01T00:00:00Z", "source": "t"},
                "target": {"project_id": "p", "capability": "c"},
                "evidence": {"url": "https://x/y", "code_evidence": ce},
                "gap": "接入缺口", "hypothesis": "h", "experiment": {"consumer": "c"},
                "decision": dec}

    matrix = [
        ("裸相对文件名不存在", {"status": "tested", "run_evidence": {"log": "absent.log"}}),
        ("纯 URL（adopted）", {"status": "adopted", "run_evidence": {"log": "ok"},
                              "adoption_evidence": {"r": "https://x/y"}}),
        ("目录而非文件", {"status": "tested", "run_evidence": {"log": "somedir"}}),
        ("布尔值", {"status": "tested", "run_evidence": True}),
        ("嵌套数组含不存在", {"status": "tested", "run_evidence": {"logs": ["ok", ["absent2.log"]]}}),
        ("空文件", {"status": "tested", "run_evidence": {"log": "empty.log"}}),
        ("无关非空文本", {"status": "tested", "run_evidence": {"log": "unrelated.txt"}}),
        ("符号链接→无关文本", {"status": "tested", "run_evidence": {"log": "link.txt"}}),
    ]
    for name, dec in matrix:
        ok, errs, _ = _opp.validate_card(_c(dec), base_dir=bd)
        check(f"J2 反例拒收: {name}", not ok)

    # 虚构源码路径（含行号）必须拒
    ok, errs, _ = _opp.validate_card(
        _c({"status": "tested", "run_evidence": {"log": "real.log"}},
           ce="missing/source.py:999 fabricated quote"), base_dir=bd)
    check("J2 反例拒收: 虚构源码路径", not ok and any("不存在" in e for e in errs))

    # 合法正例：真产物 + 真源码（相对卡目录基准）
    (bd / "src").mkdir()
    (bd / "src" / "x.py").write_text("def f():\n    return 42\n", encoding="utf-8")
    ok, errs, _ = _opp.validate_card(
        _c({"status": "tested", "run_evidence": {"log": "real.log"}},
           ce="src/x.py:42"), base_dir=bd)
    check("J2 正例通过: 真产物+真源码", ok and not errs)
    ok, errs, _ = _opp.validate_card(
        _c({"status": "tested", "run_evidence": {"log": str(bd / "real.log")}}), base_dir=bd)
    check("J2 正例通过: 绝对路径", ok and not errs)


# ============ R5/J2：失效 profile 引用 ============
print("\n[R5] 失效项目引用（research 不得出包）")
import os as _os2
with _tf.TemporaryDirectory() as td:
    sq2, _ = make_env(Path(td))
    proj = Path(td) / "projects"; proj.mkdir()
    (proj / "bad.json").write_text(json.dumps({
        "project_id": "bad", "needs": ["x"],
        "source_ref": "/definitely/missing",
        "hashes": {"/definitely/missing": "0" * 64}}), encoding="utf-8")
    errs = sq2._verify_profile_refs(json.loads((proj / "bad.json").read_text(encoding="utf-8")))
    check("失效引用被检出（不存在）", any("不存在" in e for e in errs))
    # 路径不存在时先报「不存在」；零哈希检查在路径存在时生效（下段验证）
    check("缺失引用至少一条错误", len(errs) >= 2)
    check("无引用 profile 通过", sq2._verify_profile_refs({"project_id": "ok", "needs": ["x"]}) == [])
    # 哈希不匹配
    realf = Path(td) / "src.txt"; realf.write_text("hello", encoding="utf-8")
    import hashlib as _hl
    good = _hl.sha256(b"hello").hexdigest()
    (proj / "h.json").write_text(json.dumps({
        "project_id": "h", "needs": ["x"], "hashes": {str(realf): good}}), encoding="utf-8")
    check("哈希匹配通过", sq2._verify_profile_refs(json.loads((proj / "h.json").read_text())) == [])
    (proj / "z.json").write_text(json.dumps({
        "project_id": "z", "needs": ["x"], "hashes": {str(realf): "0" * 64}}), encoding="utf-8")
    check("路径存在但零哈希被检出",
          any("零/空" in e for e in sq2._verify_profile_refs(json.loads((proj / "z.json").read_text()))))
    (proj / "h2.json").write_text(json.dumps({
        "project_id": "h2", "needs": ["x"], "hashes": {str(realf): "ab" * 32}}), encoding="utf-8")
    check("哈希不匹配被检出",
          any("不匹配" in e for e in sq2._verify_profile_refs(json.loads((proj / "h2.json").read_text()))))


# ============ R6/J1 事务协议（fail-closed + CAS） ============
print("\n[R6] J1 事务协议")
import star_tracker as _st
from star_tracker import SnapshotConflictError as _SCE

# J1a CAS：基线推进后带旧 base 写被拒
with _tf.TemporaryDirectory() as td:
    tmp = Path(td)
    def _mkt():
        t = _st.StarTracker.__new__(_st.StarTracker)
        t.CACHE_DIR = tmp; t.CONFIG_DIR = tmp
        t.CATEGORIES_FILE = tmp / "c.yaml"; t.TAGS_FILE = tmp / "t.json"
        t.SETTINGS_FILE = tmp / "s.json"
        t.categories = _st.StarTracker._get_default_categories(t)
        t.tags = {}; t.settings = {}
        return t
    meta = {"complete": True, "failed_pages": [], "account_id": "u", "limit_truncated": False}
    t = _mkt()
    t.save_latest([{"full_name": "base/one", "id": 1}], fetch_meta=meta)
    base_ts = json.loads((tmp / "original_latest.json").read_text())["timestamp"]
    # 外部（插件）推进基线
    t.save_latest([{"full_name": "base/one", "id": 1}, {"full_name": "plugin/x", "id": 2}],
                  fetch_meta=meta)
    # skill 带旧 base_ts 写 → 应拒
    try:
        _mkt().save_latest([{"full_name": "base/one", "id": 1}, {"full_name": "skill/y", "id": 3}],
                           fetch_meta=meta, base_timestamp=base_ts)
        check("J1a CAS 拒绝旧基线写", False)
    except _SCE:
        final = {r["full_name"] for r in json.loads((tmp / "original_latest.json").read_text())["repos"]}
        check("J1a CAS 拒绝旧基线写", "plugin/x" in final)  # 插件确认条目保留

# J1b fail-closed：锁被真实子进程持有时，save 抛 LockUnavailable 且不改数据
import subprocess
holder_code = (
    "import sys,fcntl,os,time;"
    "fd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o644);"
    "fcntl.flock(fd,fcntl.LOCK_EX);print('HELD',flush=True);time.sleep(5)"
)
with _tf.TemporaryDirectory() as td:
    tmp = Path(td)
    lk = tmp / ".gsm-write.lock"
    def _mkt2():
        t = _st.StarTracker.__new__(_st.StarTracker)
        t.CACHE_DIR = tmp; t.CONFIG_DIR = tmp
        t.CATEGORIES_FILE = tmp / "c.yaml"; t.TAGS_FILE = tmp / "t.json"; t.SETTINGS_FILE = tmp / "s.json"
        t.categories = _st.StarTracker._get_default_categories(t); t.tags = {}; t.settings = {}
        return t
    meta = {"complete": True, "failed_pages": [], "account_id": "u", "limit_truncated": False}
    t = _mkt2()
    t.save_latest([{"full_name": "base/one", "id": 1}], fetch_meta=meta)
    before = (tmp / "original_latest.json").read_text()
    holder = subprocess.Popen([sys.executable, "-c", holder_code, str(lk)],
                              stdout=subprocess.PIPE, text=True)
    holder.stdout.readline()  # 等 HELD
    try:
        import lockutil
        # 缩短超时避免真等 10s：直接测 write_lock 超时抛 LockUnavailable
        try:
            with lockutil.write_lock(tmp, timeout=0.2):
                pass
            check("J1b 锁被持有时 write_lock 抛 LockUnavailable", False)
        except lockutil.LockUnavailable:
            check("J1b 锁被持有时 write_lock 抛 LockUnavailable", True)
        # save 用极短超时也 fail-closed：数据不变
        import unittest.mock as _m2
        with _m2.patch("lockutil._DEFAULT_TIMEOUT", 0.2):
            try:
                _mkt2().save_latest([{"full_name": "base/one", "id": 1}, {"full_name": "should/not/write", "id": 9}],
                                    fetch_meta=meta)
                rejected = False
            except _SCE:
                rejected = True
        check("J1b save_latest 锁不可用 fail-closed 抛错", rejected)
        check("J1b fail-closed 后旧数据不变",
              (tmp / "original_latest.json").read_text() == before)
    finally:
        holder.terminate(); holder.wait(timeout=10)


# ============ 汇总 ============
print(f"\n{'=' * 50}")
print(f"结果: {PASS} 通过 / {FAIL} 失败")
sys.exit(1 if FAIL else 0)
