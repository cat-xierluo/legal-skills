#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SuitAgent Dashboard 本地服务（case-dashboard skill）

范式沿用 content-registry / idle-task-runner：Python 标准库 http.server 单文件 + 读本地文件，
零额外依赖（仅用已安装的 PyYAML 读 yaml）。API 版本化 /api/v1/*。

启动：
    python3 .claude/skills/case-dashboard/scripts/dashboard_server.py    # 在项目根运行
    python3 dashboard_server.py --root /path/to/project --port 7879
    环境变量：DASHBOARD_PORT / DASHBOARD_HOST / SUITAGENT_ROOT / CASE_STORE_PATH

然后浏览器打开 http://127.0.0.1:7879

设计要点：
- ThreadingHTTPServer（单线程并发会卡死，参考 content-registry 实测 15s→1s）
- 端口 7879（避开 content-registry 的 8765 和 idle-task-runner 的 7878）
- 项目根发现：--root > SUITAGENT_ROOT > cwd 向上发现（含 6 位数字开头案件目录的祖先）；
  禁用 __file__.resolve()——本 skill 以符号链接安装，resolve 会穿透回 legal-skills 源仓库
- 数据源：**V = case.yaml v4.0（canonical，case-progress 契约）**——M4 存量迁移（2026-08-15）
  已完成 8 案件全量迁移，A–D 遗留适配器已删除；原格式文件以 .legacy 归档于各案件目录
- 写回：全部经 subprocess 调 case-progress 的 case_store CLI（--actor user，行级 source 保护）
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time
import shutil
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import mimetypes

import yaml

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).parent.parent  # 字符串级路径（不 resolve），经符号链接仍指向本 skill
DASHBOARD_HTML = SKILL_DIR / "assets" / "dashboard.html"
DEFAULT_PORT = 7879
DEFAULT_HOST = "127.0.0.1"
CASE_DIR_RE = re.compile(r"^(\d{6})\s")  # 案件目录：以 6 位数字开头
ROOT = None        # 项目根：main() 经 find_root 解析（--root > SUITAGENT_ROOT > cwd 向上发现）
CASE_STORE = None  # case-progress 写入引擎：main() 经 find_case_store 解析


def find_root(explicit=None):
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("SUITAGENT_ROOT")
    if env:
        return Path(env).expanduser()
    d = Path.cwd()
    if CASE_DIR_RE.match(d.name):
        return d.parent
    for cand in [d, *d.parents]:
        try:
            if any(c.is_dir() and CASE_DIR_RE.match(c.name) for c in cand.iterdir()):
                return cand
        except PermissionError:
            continue
    return None


def find_case_store(root):
    """定位 case-progress 的 case_store.py：环境变量 > 项目内符号链接 > 本仓库兄弟 skill。"""
    cands = []
    env = os.environ.get("CASE_STORE_PATH")
    if env:
        cands.append(Path(env))
    if root:
        cands.append(root / ".claude" / "skills" / "case-progress" / "scripts" / "case_store.py")
    cands.append(SKILL_DIR.parent / "case-progress" / "scripts" / "case_store.py")
    for c in cands:
        if c.exists():
            return c
    return None

TODAY = datetime.date.today()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def safe_read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8"), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def parse_date(s):
    """宽松日期解析，返回 datetime.date 或 None。"""
    if not s or not isinstance(s, str):
        return None
    m = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", s)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def days_left(end_date_str):
    d = parse_date(end_date_str)
    if not d:
        return None
    return (d - TODAY).days


def deadline_level(days, status=None):
    """期限红黄绿分级。"""
    if days is None:
        return "none"
    if status and ("完成" in str(status) or str(status) in ("passed", "done")):
        return "none"
    if days < 0:
        return "red"  # 逾期
    if days <= 7:
        return "red"  # 紧急
    if days <= 30:
        return "yellow"
    return "green"


def norm_status(raw, default="todo"):
    """把各来源的原始状态文本归一成 todo/in_progress/done。"""
    if raw is None:
        return default
    s = str(raw).strip()
    done_marks = ("done", "已完成", "已结案", "passed", "[x]", "✅")
    todo_marks = ("pending", "待开始", "todo", "[ ]", "未开始", "待办", "待完成", "待处理")
    prog_marks = ("in_progress", "进行中", "正在")
    for m in done_marks:
        if m in s:
            return "done"
    for m in prog_marks:
        if m in s:
            return "in_progress"
    for m in todo_marks:
        if m in s:
            return "todo"
    return default


def short_name(display_name):
    """从 display_name 生成侧边栏用的短名。"""
    if not display_name:
        return ""
    return display_name.replace("诉", " 诉 ").split(" 诉 ")[0][:12]


# ---------------------------------------------------------------------------
# 归一化适配层：4 种来源 → canonical 案件模型
# ---------------------------------------------------------------------------
def base_case(case_id, case_dir, display_name=None):
    return {
        "id": case_id,
        "dir_name": Path(case_dir).name,
        "display_name": display_name or Path(case_dir).name,
        "case_number": "",
        "cause": "",
        "status": "",
        "stage": "",
        "source_type": "none",
        "data_quality": "minimal",
        "tasks": [],
        "deadlines": [],
        "hearings": [],
        "timeline": [],
        "parties": [],
        "instants": [],
        "evidence": [],
        "fees": {"支出": {}, "索赔与评估": []},
        "amount": None,
        "court": "",
        "lifecycle": "",
        "stale": False,
        "yaml_path": "",
        "md_path": "",
        "case_dir": str(case_dir),
    }


def adapt_yaml_v4(data, case):
    """来源 V：case.yaml v4.0（canonical，case-progress 契约）。写回经 case_store CLI。"""
    case["source_type"] = "V"
    meta = data.get("meta") or {}
    info = data.get("案件基本信息") or {}
    case["display_name"] = info.get("案件名称") or case["display_name"]
    case["case_number"] = meta.get("法院案号") or next(
        (r.get("法院案号") for r in (data.get("审级记录") or []) if r.get("法院案号")), "")
    case["cause"] = info.get("案由", "")
    case["status"] = info.get("生命周期状态", "")
    case["lifecycle"] = info.get("生命周期状态", "")
    case["stage"] = info.get("程序阶段", "")
    case["amount"] = info.get("标的额")
    case["court"] = info.get("管辖法院", "")
    case["stale"] = bool((data.get("同步") or {}).get("状态过期"))
    case["business"] = (meta.get("业务领域") or "诉讼")
    pa = data.get("当事人与代理") or {}
    for side, key in (("我方", "我方当事人"), ("对方", "对方当事人")):
        for p in pa.get(key) or []:
            case["parties"].append({"side": side, "name": p.get("姓名", ""), "role": p.get("角色", ""),
                                    "type": p.get("类型", ""), "note": (p.get("扩展信息") or {}).get("备注", "")})
    for p in pa.get("其他诉讼参与人") or []:
        case["parties"].append({"side": "其他", "name": p.get("姓名", ""), "role": p.get("角色", ""),
                                "type": "", "note": p.get("备注", "")})
    for r in data.get("审级记录") or []:
        case["instants"].append(r)
    for ev in data.get("证据索引") or []:
        case["evidence"].append(ev)
    for t in data.get("任务") or []:
        case["tasks"].append({
            "id": f"{case['id']}-{t.get('id', '')}",
            "title": t.get("名称", ""),
            "status": norm_status(t.get("状态")),
            "priority": t.get("优先级", ""),
            "deadline": t.get("截止日期") or "",
            "file": t.get("关联文件") or "",
            "source_type": "V",
            "source_ref": {"kind": "case_store", "task_id": t.get("id", "")},
            "writable": True,
        })
    for d in data.get("法定期限") or []:
        dl = days_left(d.get("截止日期"))
        lvl = "none" if d.get("抵消标记") else deadline_level(dl, d.get("状态"))
        case["deadlines"].append({
            "name": d.get("名称", ""),
            "end_date": d.get("截止日期", ""),
            "days_left": dl,
            "level": lvl,
            "status": d.get("状态", ""),
            "file": d.get("来源文件") or "",
        })
    fees = data.get("费用信息") or {}
    case["fees"] = {"支出": fees.get("支出") or {}, "索赔与评估": fees.get("索赔与评估") or []}
    case["worklog"] = (data.get("工时统计") or {}).get("工作记录") or []
    case["worklog_total"] = (data.get("工时统计") or {}).get("总工时") or 0
    for e in data.get("案件时间线") or []:
        case["timeline"].append({"date": e.get("日期", ""), "event": e.get("事项", ""),
                                 "type": e.get("事件类型", ""), "file": e.get("来源文件") or ""})
    for h in data.get("开庭与听证") or []:
        dl = days_left(h.get("日期"))
        case["hearings"].append({
            "date": h.get("日期", ""), "type": h.get("类型", ""), "subject": h.get("事项", ""),
            "place": " / ".join(str(x) for x in (h.get("地点"), h.get("法庭")) if x),
            "status": h.get("状态", ""), "days_left": dl,
            "file": h.get("来源文件") or "",
            "level": "none" if h.get("状态") == "done" else deadline_level(dl, h.get("状态")),
        })
    case["data_quality"] = "full"
    return case



def find_yaml(case_dir):
    """M4 后唯一档案：<案件目录>/00 - 📅 日程管理/case.yaml（.legacy.yaml 不再读取）。"""
    p = case_dir / "00 - 📅 日程管理" / "case.yaml"
    return p if p.exists() else None



def detect_yaml_schema(data):
    """M4 后仅支持 v4.0。"""
    if isinstance(data, dict) and (data.get("模板版本") == "4.0" or "meta" in data):
        return "V"
    return None



def load_case(case_dir):
    """加载案件：case.yaml v4.0 → canonical 模型；无档案 → 最小骨架（none）。"""
    case_dir = Path(case_dir)
    m = CASE_DIR_RE.match(case_dir.name)
    case_id = m.group(1) if m else case_dir.name[:6]
    case = base_case(case_id, case_dir)

    yaml_path = find_yaml(case_dir)
    if not yaml_path:
        return case
    text, err = safe_read_text(yaml_path)
    if not text:
        return case
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return case
    if detect_yaml_schema(data) == "V":
        adapt_yaml_v4(data, case)
        case["yaml_path"] = str(yaml_path)
    if case["display_name"] == case["dir_name"]:
        case["display_name"] = re.sub(r"^\d{6}\s*", "", case["dir_name"])
    case["display_short"] = short_name(case["display_name"])
    return case


# ---------------------------------------------------------------------------
# 案件索引（内存缓存，按需重建）
# ---------------------------------------------------------------------------
_CASE_CACHE = None
_CACHE_TS = 0
_CACHE_TTL = 5  # 秒，文件频繁变动，缓存很短


def get_all_cases(force=False):
    global _CASE_CACHE, _CACHE_TS
    now = datetime.datetime.now().timestamp()
    if force or _CASE_CACHE is None or (now - _CACHE_TS) > _CACHE_TTL:
        cases = []
        for entry in sorted(ROOT.iterdir()):
            if entry.is_dir() and CASE_DIR_RE.match(entry.name):
                try:
                    cases.append(load_case(entry))
                except Exception:  # noqa: BLE001
                    continue
        _CASE_CACHE = cases
        _CACHE_TS = now
    return _CASE_CACHE


def find_case_by_id(case_id):
    for c in get_all_cases():
        if c["id"] == case_id:
            return c
    return None


# ---------------------------------------------------------------------------
# 写回引擎（writable 来源）
# ---------------------------------------------------------------------------

def toggle_via_case_store(case, source_ref, target_status):
    """V 案件写回：subprocess 调 case-progress 的 case_store（--actor user，人工点击）。"""
    if not CASE_STORE:
        return False, "未找到 case_store.py（case-progress skill 未安装？）"
    target = "done" if target_status == "done" else "todo"
    cmd = [sys.executable, str(CASE_STORE), "--root", str(ROOT),
           "set-status", case["id"], str(source_ref.get("task_id", "")), target, "--actor", "user"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout.strip() or r.stderr.strip() or "ok")

def toggle_task(case_id, source_ref, target_status):
    """写回唯一路径：case_store CLI（--actor user）。path 由服务端权威推导，不信前端。"""
    case = find_case_by_id(case_id)
    if not case:
        return False, "案件不存在"
    if source_ref.get("kind") != "case_store":
        return False, "仅支持 v4.0 案件（case_store）写回"
    return toggle_via_case_store(case, source_ref, target_status)


# ---------------------------------------------------------------------------
# API 数据组装
# ---------------------------------------------------------------------------
def build_focus():
    """今日焦点：红期限 / 60 天内开庭 / 停滞案件（已结案不参与）。"""
    red, hearings, stale = [], [], []
    for c in get_all_cases():
        if c.get("lifecycle") == "已结案":
            continue
        for d in c["deadlines"]:
            if d.get("level") == "red":
                red.append({**d, "case_id": c["id"], "case_short": c["display_short"]})
        for h in c.get("hearings") or []:
            n = h.get("days_left")
            if h.get("status") != "done" and n is not None and 0 <= n <= 60:
                hearings.append({**h, "case_id": c["id"], "case_short": c["display_short"]})
        todo = sum(1 for t in c["tasks"] if t["status"] == "todo")
        inprog = sum(1 for t in c["tasks"] if t["status"] == "in_progress")
        if c.get("stale") or (todo > 0 and inprog == 0):
            stale.append({"case_id": c["id"], "case_short": c["display_short"], "stage": c["stage"],
                          "todo": todo, "data_stale": c.get("stale", False)})
    red.sort(key=lambda x: x.get("days_left") if x.get("days_left") is not None else 0)
    hearings.sort(key=lambda x: x.get("days_left") or 0)
    return {"today": TODAY.isoformat(), "red_deadlines": red, "hearings_upcoming": hearings, "stale_cases": stale}


# ---------------------------------------------------------------------------
# 苹果日历（Calendar.app）导入：osascript AppleScript 本地查询（JXA whose 在本机不稳，弃），
# 窗口 today-30d ~ today+150d，5 分钟缓存。注意 tell 块内 handler 必须以 my 调用。
# ---------------------------------------------------------------------------
_APPLE_AS = """
on twoDig(n)
  if n < 10 then return "0" & (n as text)
  return n as text
end twoDig

set out to ""
tell application "Calendar"
  set startD to (current date) - 30 * days
  set endD to (current date) + 150 * days
  repeat with c in calendars
    set calName to (name of c) as text
    if {"计划的提醒事项", "Siri建议"} contains calName then set calName to "§SKIP§"
    if calName is not "§SKIP§" then
    try
      set evs to (events of c whose (start date > startD) and (start date < endD))
      repeat with e in evs
        try
          set d to start date of e
          set de to end date of e
          set evDate to ((year of d) as text) & "-" & my twoDig(month of d as integer) & "-" & my twoDig(day of d)
          set evTime to my twoDig((time of d) div 3600) & ":" & my twoDig(((time of d) mod 3600) div 60) & "-" & my twoDig((time of de) div 3600) & ":" & my twoDig(((time of de) mod 3600) div 60)
          set adText to "false"
          if allday event of e is true then set adText to "true"
          set evLoc to ""
          try
            set evLoc to (location of e) as text
          end try
          if evLoc is "missing value" then set evLoc to ""
          set out to out & calName & tab & evDate & tab & evTime & tab & adText & tab & (summary of e) & tab & evLoc & linefeed
        end try
      end repeat
    end try
    end if
  end repeat
end tell
return out
"""
_APPLE_CACHE = {"ts": 0.0, "events": None, "error": None}
_APPLE_TTL = 900


_APPLE_LOCK = threading.Lock()


CAL_DB = Path.home() / "Library" / "Group Containers" / "group.com.apple.calendar" / "Calendar.sqlitedb"
_CD_EPOCH = 978307200  # Core Data 时间纪元（2001-01-01）


def _apple_sqlite_fetch(skip_names):
    """直读日历本地库（需"完全磁盘访问"）：约 50ms，返回事件列表；失败抛异常。"""
    import sqlite3
    if not CAL_DB.exists():
        raise RuntimeError("Calendar.sqlitedb 不存在")
    now_cd = time.time() - _CD_EPOCH
    lo, hi = now_cd - 30 * 86400, now_cd + 150 * 86400
    con = sqlite3.connect(f"file:{CAL_DB}?mode=ro", uri=True, timeout=5)
    try:
        rows = con.execute(
            """
            SELECT ci.summary, ci.start_date, ci.end_date, ci.all_day, c.title,
                   COALESCE(l.title, l.address, '')
            FROM CalendarItem ci
            JOIN Calendar c ON ci.calendar_id = c.ROWID
            LEFT JOIN Location l ON ci.location_id = l.ROWID
            WHERE ci.hidden = 0 AND ci.start_date BETWEEN ? AND ?
              AND c.title NOT IN (%s)
            ORDER BY ci.start_date
            """ % ",".join("?" * len(skip_names)),
            (lo, hi, *skip_names)).fetchall()
    finally:
        con.close()
    out = []
    for summary, sd, ed, all_day, cal, loc in rows:
        ds = datetime.datetime.fromtimestamp(sd + _CD_EPOCH)
        de = datetime.datetime.fromtimestamp(ed + _CD_EPOCH)
        out.append({
            "cal": cal, "title": summary or "（无标题）",
            "date": ds.strftime("%Y-%m-%d"),
            "time": ds.strftime("%H:%M") + "-" + de.strftime("%H:%M"),
            "allDay": bool(all_day), "loc": loc or ""})
    return out


def _apple_do_fetch():
    """双通道：sqlite 直读（快，需完全磁盘访问）→ 失败回退 osascript AppleScript。
    更新缓存含 source/needs_fda（调用方负责持锁/置 fetching）。"""
    skip_names = [x.strip() for x in os.environ.get(
        "DASHBOARD_APPLECAL_SKIP", "计划的提醒事项,Siri建议").split(",") if x.strip()]
    try:
        events = _apple_sqlite_fetch(skip_names)
        _APPLE_CACHE.update(ts=time.time(), events=events, error=None,
                            source="sqlite", needs_fda=False)
        return
    except Exception:  # noqa: BLE001 — 无完全磁盘访问或库不可读 → 回退慢通道
        pass
    try:
        r = subprocess.run(["osascript", "-e", _APPLE_AS], capture_output=True, text=True, timeout=150)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "osascript 失败").strip().splitlines()[0][:160])
        events = []
        for ln in (r.stdout or "").splitlines():
            parts = ln.split("\t")
            if len(parts) != 6:
                continue
            cal, date, tm, all_day, title, loc = parts
            events.append({"cal": cal, "date": date, "time": tm,
                           "allDay": all_day == "true", "title": title,
                           "loc": "" if loc in ("missing value", "missing value\n") else loc})
        _APPLE_CACHE.update(ts=time.time(), events=events, error=None,
                            source="applescript", needs_fda=True)
    except Exception as ex:  # noqa: BLE001
        _APPLE_CACHE.update(ts=time.time(), events=None, error=str(ex)[:160],
                            source="applescript", needs_fda=True)
        if _APPLE_CACHE["events"] is None:  # 尚无任何成功数据 → 90s 后自动重试一次
            def _retry():
                time.sleep(90)
                _spawn_bg_fetch()
            threading.Thread(target=_retry, daemon=True).start()


def _spawn_bg_fetch():
    if _APPLE_CACHE.get("fetching"):
        return
    _APPLE_CACHE["fetching"] = True

    def _bg():
        try:
            with _APPLE_LOCK:
                _apple_do_fetch()
        finally:
            _APPLE_CACHE["fetching"] = False
    threading.Thread(target=_bg, daemon=True).start()


def fetch_apple_events():
    """永不阻塞：新鲜/过期旧值直返（过期则后台刷新）；错误 60s 重试窗；
    冷启动无数据→触发后台拉取并返回 pending 标记（调用方先出案件数据）。"""
    now = time.time()
    c = _APPLE_CACHE
    if c["events"] is not None and now - c["ts"] < _APPLE_TTL:
        return c["events"], None, False
    if c["error"] and now - c["ts"] < 180 and c["events"] is None:
        return [], c["error"], False
    if c["events"] is not None:  # 过期但可用 → 旧值先回 + 后台刷新
        _spawn_bg_fetch()
        return c["events"], None, False
    # 冷启动：无任何数据 → 后台拉，先标记 pending
    _spawn_bg_fetch()
    return [], None, True


def build_calendar():
    """月历数据：期限（不含已抵消/已完成）+ 开庭，按日期分组。"""
    days = {}
    for c in get_all_cases():
        for d in c["deadlines"]:
            if not d.get("end_date") or d.get("level") in ("none", None):
                continue
            days.setdefault(d["end_date"], []).append({
                "kind": "deadline", "case_id": c["id"], "case_short": c["display_short"],
                "name": d.get("name"), "level": d["level"], "days_left": d.get("days_left"),
                "file": d.get("file", "")})
        for h in c.get("hearings") or []:
            if not h.get("date"):
                continue
            days.setdefault(h["date"], []).append({
                "kind": "hearing", "case_id": c["id"], "case_short": c["display_short"],
                "name": f"{h.get('type')}·{h.get('subject')}", "place": h.get("place"),
                "status": h.get("status"), "file": h.get("file", "")})
    apple, apple_err, apple_pending = fetch_apple_events()
    for a in apple:
        days.setdefault(a["date"], []).append({
            "kind": "apple", "case_id": None, "case_short": a["cal"],
            "name": a["title"], "place": a["loc"],
            "time": a["time"], "all_day": a["allDay"]})
    payload = {"today": TODAY.isoformat(), "days": days,
               "apple_ok": not apple_err and not apple_pending}
    if apple_err:
        payload["apple_error"] = apple_err
    if apple_pending:
        payload["apple_pending"] = True
    payload["apple_source"] = _APPLE_CACHE.get("source")
    payload["needs_fda"] = bool(_APPLE_CACHE.get("needs_fda"))
    return payload


def build_overview():
    cases = get_all_cases()
    all_tasks = []
    deadlines = []
    for c in cases:
        for t in c["tasks"]:
            all_tasks.append({**t, "case_id": c["id"], "case_short": c["display_short"]})
        for d in c["deadlines"]:
            if d["level"] != "none":
                deadlines.append({**d, "case_id": c["id"], "case_short": c["display_short"]})

    def bucket(status):
        return [t for t in all_tasks if t["status"] == status]

    deadlines.sort(key=lambda x: (x.get("days_left") is None, x.get("days_left") if x.get("days_left") is not None else 0))
    return {
        "today": TODAY.isoformat(),
        "totals": {
            "cases": len(cases),
            "todo": len(bucket("todo")),
            "in_progress": len(bucket("in_progress")),
            "done": len(bucket("done")),
        },
        "deadlines": deadlines[:20],
        "kanban": {
            "todo": bucket("todo"),
            "in_progress": bucket("in_progress"),
            "done": bucket("done"),
        },
    }


def build_cases():
    out = []
    for c in get_all_cases():
        counts = {"todo": 0, "in_progress": 0, "done": 0}
        for t in c["tasks"]:
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        nearest = None
        for d in c["deadlines"]:
            if d["days_left"] is not None and d["level"] != "none":
                if nearest is None or (d["days_left"] < (nearest["days_left"] or 0)):
                    nearest = d
        next_hearing = None
        for h in c.get("hearings") or []:
            n = h.get("days_left")
            if h.get("status") != "done" and n is not None and n >= 0:
                if next_hearing is None or n < (next_hearing["days_left"] or 0):
                    next_hearing = h
        out.append({
            "id": c["id"],
            "display_name": c["display_name"],
            "case_number": c["case_number"],
            "cause": c["cause"],
            "status": c["status"],
            "lifecycle": c.get("lifecycle") or c["status"],
            "stage": c["stage"],
            "source_type": c["source_type"],
            "data_quality": c["data_quality"],
            "task_counts": counts,
            "nearest_deadline": nearest,
            "next_hearing": next_hearing,
            "stale": c.get("stale", False),
            "business": c.get("business", "诉讼"),
        })
    return out


def build_case(case_id):
    c = find_case_by_id(case_id)
    if not c:
        return None
    return c


def _parse_journal_recent(text, n=3):
    """JOURNAL.md 最近 n 条（按 **日期 时间 分割）。"""
    blocks = re.split(r"(?=^\*\*\d{4}-\d{2}-\d{2})", text, flags=re.MULTILINE)
    out = []
    for b in blocks[:n + 1]:
        b = b.strip()
        if b and re.match(r"^\*\*\d{4}-\d{2}-\d{2}", b):
            head = b.splitlines()[0][:80]
            out.append({"head": head, "preview": b[:300]})
    return out


def _parse_changelog_latest(text):
    m = re.search(r"(## \[[^\]]+\][^\n]*\n(?:(?!## \[).)*)", text, flags=re.DOTALL)
    return m.group(1).strip()[:1500] if m else ""


def _parse_tasks_md(text):
    done = len(re.findall(r"^\s*- \[[xX]\]", text, flags=re.MULTILINE))
    todo = len(re.findall(r"^\s*- \[ \]", text, flags=re.MULTILINE))
    return {"done": done, "todo": todo}


def build_project():
    result = {"tasks_md": {}, "journal_recent": [], "changelog_latest": ""}
    tasks_text, _ = safe_read_text(ROOT / "status" / "TASKS.md")
    if tasks_text:
        result["tasks_md"] = _parse_tasks_md(tasks_text)
    journal_text, _ = safe_read_text(ROOT / "status" / "JOURNAL.md")
    if journal_text:
        result["journal_recent"] = _parse_journal_recent(journal_text)
    cl_text, _ = safe_read_text(ROOT / "CHANGELOG.md")
    if cl_text:
        result["changelog_latest"] = _parse_changelog_latest(cl_text)
    return result


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "SuitAgentDashboard/1.0"

    def log_message(self, fmt, *args):  # 静默，仅 404/5xx 打印
        if args and ("404" in str(args[0]) or "5" in str(args[0])[:1]):
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            text, err = safe_read_text(DASHBOARD_HTML)
            if text is None:
                self._send(404, {"error": f"dashboard.html 未找到: {err}"})
            else:
                self._send(200, text, "text/html; charset=utf-8")
            return
        if path == "/api/v1/overview":
            self._send(200, build_overview())
            return
        if path == "/api/v1/grant-fda":
            subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"],
                           check=False)
            self._send(200, {"ok": True, "message": "已打开 系统设置→隐私与安全性→完全磁盘访问，请添加 ZCode"})
            return
        if path == "/api/v1/calendar":
            self._send(200, build_calendar())
            return
        if path == "/api/v1/focus":
            self._send(200, build_focus())
            return
        if path == "/api/v1/cases":
            self._send(200, build_cases())
            return
        if path == "/api/v1/project":
            self._send(200, build_project())
            return
        m = re.match(r"^/api/v1/case/(\w+)$", path)
        if m:
            c = build_case(m.group(1))
            self._send(200 if c else 404, c or {"error": "案件不存在"})
            return
        if path == "/api/v1/preview":
            qs = parse_qs(urlparse(self.path).query)
            cid = (qs.get("case_id") or [None])[0]
            rel = (qs.get("file") or [None])[0]
            if not cid or not rel:
                self._send(400, {"ok": False, "message": "缺 case_id/file"})
                return
            c = find_case_by_id(cid)
            if not c:
                self._send(404, {"ok": False, "message": "案件不存在"})
                return
            base = Path(c["case_dir"]).resolve()
            p = (base / rel).resolve()
            if base not in p.parents or not p.exists() or not p.is_file():
                self._send(400, {"ok": False, "message": f"文件不存在或越界: {rel}"})
                return
            # 轻量速览（M7-4）：PDF→首页图（pdftoppm）、docx→文本摘录（textutil）、图片/文本直出；
            # 不内嵌 PDF 阅读器；转换失败回退原始字节由前端提示"打开原件"
            ext = p.suffix.lower()
            try:
                if ext == ".pdf" and shutil.which("pdftoppm"):
                    fd, tmp = tempfile.mkstemp(suffix=".jpg")
                    os.close(fd)
                    try:
                        subprocess.run(["pdftoppm", "-jpeg", "-l", "1", "-scale-to", "900",
                                        str(p), tmp[:-4]], check=True, timeout=15,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        out = Path(tmp[:-4] + "-1.jpg")
                        if not out.exists():
                            out = Path(tmp[:-4] + "-01.jpg")
                        if out.exists():
                            data = out.read_bytes()
                            out.unlink(missing_ok=True)
                            Path(tmp).unlink(missing_ok=True)
                            pages = ""
                            try:
                                pi = subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True, timeout=10)
                                m = re.search(r"Pages:\s+(\d+)", pi.stdout or "")
                                pages = m.group(1) if m else ""
                            except Exception:  # noqa: BLE001
                                pass
                            self.send_response(200)
                            self.send_header("Content-Type", "image/jpeg")
                            self.send_header("Content-Length", str(len(data)))
                            self.send_header("X-Preview", f"image;pages={pages}")
                            self.send_header("Cache-Control", "no-store")
                            self.end_headers()
                            self.wfile.write(data)
                            return
                    finally:
                        Path(tmp).unlink(missing_ok=True)
                if ext in (".docx", ".doc") and shutil.which("textutil"):
                    r = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(p)],
                                       capture_output=True, text=True, timeout=15)
                    if r.returncode == 0 and r.stdout.strip():
                        text = r.stdout.strip()
                        self._send(200, text[:4000], "text/plain; charset=utf-8")
                        return
                ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
                if ext == ".md":
                    ctype = "text/plain; charset=utf-8"
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:  # noqa: BLE001
                self._send(500, {"ok": False, "message": str(e)})
            return
        self._send(404, {"error": "not found", "path": path})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()
        if path == "/api/v1/task/toggle":
            case_id = body.get("case_id")
            source_ref = body.get("source_ref", {})
            target = body.get("target_status")
            # 只允许在 todo/done 间切换
            target = "done" if target == "done" else "todo"
            if not case_id or not source_ref.get("kind"):
                self._send(400, {"ok": False, "message": "参数缺失"})
                return
            ok, msg = toggle_task(case_id, source_ref, target)
            get_all_cases(force=True)  # 失效缓存
            self._send(200 if ok else 409, {"ok": ok, "message": msg})
            return
        if path == "/api/v1/open":
            case_id = body.get("case_id", "")
            c = find_case_by_id(case_id)
            if not c:
                self._send(404, {"ok": False, "message": "案件不存在，拒绝打开"})
                return
            target = Path(c["case_dir"])
            rel = body.get("file") or ""
            if rel:
                p = (target / str(rel)).resolve()
                if target.resolve() not in p.parents or not p.exists():
                    self._send(400, {"ok": False, "message": f"文件不存在或越界: {rel}"})
                    return
                target = p
            try:
                subprocess.run(["open", str(target)], check=False)
                self._send(200, {"ok": True})
            except Exception as e:  # noqa: BLE001
                self._send(500, {"ok": False, "message": str(e)})
            return
        self._send(404, {"error": "not found", "path": path})


def main():
    parser = argparse.ArgumentParser(description="SuitAgent Dashboard 本地服务（case-dashboard skill）")
    parser.add_argument("--root", default=None, help="项目根（默认 SUITAGENT_ROOT 或 cwd 向上发现）")
    parser.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", DEFAULT_PORT)))
    parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", DEFAULT_HOST))
    args = parser.parse_args()

    global ROOT, CASE_STORE
    ROOT = find_root(args.root)
    if not ROOT:
        print("❌ 未发现项目根：请 --root 指定（须为含 6 位数字开头案件目录的路径）", file=sys.stderr)
        sys.exit(1)
    CASE_STORE = find_case_store(ROOT)

    try:
        sys.stdout.reconfigure(line_buffering=True)  # 启动扫描结果立即显示
    except Exception:  # noqa: BLE001
        pass

    if not DASHBOARD_HTML.exists():
        print(f"⚠️  未找到 {DASHBOARD_HTML}", file=sys.stderr)

    # 启动自检
    cases = get_all_cases(force=True)
    print(f"✅ 项目根: {ROOT}")
    print(f"✅ 写入引擎: {CASE_STORE or '未找到（V 案件将无法写回）'}")
    print(f"✅ 扫描到 {len(cases)} 个案件:")
    for c in cases:
        flag = {"V": "v4.0", "none": "仅目录"}[c["source_type"]]
        w = "可写" if any(t["writable"] for t in c["tasks"]) else "只读"
        print(f"   · [{c['id']}] {c['display_short']:<14} {flag:<10} {w}")

    # 苹果日历：启动预热 + 定时刷新（默认 10 分钟，DASHBOARD_APPLECAL_INTERVAL 可调）
    # 抓取完全独立于页面访问——看板看到的永远是缓存里已就绪的数据
    def _prewarm():
        _APPLE_CACHE["fetching"] = True
        try:
            with _APPLE_LOCK:
                _apple_do_fetch()
        finally:
            _APPLE_CACHE["fetching"] = False

    def _scheduler():
        interval = max(120, int(os.environ.get("DASHBOARD_APPLECAL_INTERVAL", "180")))
        while True:
            time.sleep(interval)
            _spawn_bg_fetch()

    threading.Thread(target=_prewarm, daemon=True).start()
    threading.Thread(target=_scheduler, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"\n🌐 打开: {url}")
    print(f"   停止: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
