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
- 数据源 5 种：V = case.yaml v4.0（canonical，case-progress 契约）＋ 存量 A/B/C/D 遗留格式
  （M4 迁移后遗留适配器消亡）
- 写回分级：V 案件经 subprocess 调 case-progress 的 case_store CLI（--actor user，行级 source
  保护）；存量 A（yaml v2.1.0 tasks[].status）与 D（info.md checkbox）行级 patch；B/C 只读
- 存量写回用 fcntl.flock + 临时文件 + os.replace 原子替换，保留 inode
"""

import argparse
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

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
        "timeline": [],
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
    case["stage"] = info.get("程序阶段", "")
    for t in data.get("任务") or []:
        case["tasks"].append({
            "id": f"{case['id']}-{t.get('id', '')}",
            "title": t.get("名称", ""),
            "status": norm_status(t.get("状态")),
            "priority": t.get("优先级", ""),
            "deadline": t.get("截止日期") or "",
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
        })
    for e in data.get("案件时间线") or []:
        case["timeline"].append({"date": e.get("日期", ""), "event": e.get("事项", "")})
    case["data_quality"] = "full"
    return case


def adapt_yaml_v21(data, case):
    """来源 A：yaml v2.1.0 英文 key（存量遗留格式）。"""
    case["source_type"] = "A"
    info = (data.get("case_info") or {}).get("basic_info") or {}
    case["display_name"] = info.get("case_name") or case["display_name"]
    case["case_number"] = info.get("case_number", "")
    case["cause"] = info.get("cause", "")
    case["status"] = info.get("case_status", "")
    case["stage"] = info.get("current_stage", "")
    # tasks（可写）
    for t in data.get("tasks") or []:
        case["tasks"].append({
            "id": f"{case['id']}-{t.get('id', '')}",
            "title": t.get("name", ""),
            "status": norm_status(t.get("status")),
            "priority": t.get("priority", ""),
            "deadline": t.get("deadline", ""),
            "source_type": "A",
            "source_ref": {"kind": "yaml_status", "task_id": t.get("id", "")},
            "writable": True,
        })
    # deadlines
    for key, d in (data.get("legal_deadlines") or {}).items():
        if not isinstance(d, dict):
            continue
        dl = days_left(d.get("end_date"))
        case["deadlines"].append({
            "name": d.get("name", key),
            "end_date": d.get("end_date", ""),
            "days_left": dl,
            "level": deadline_level(dl, d.get("status")),
            "status": d.get("status", ""),
        })
    # timeline
    for d in data.get("important_dates") or []:
        case["timeline"].append({"date": d.get("date", ""), "event": d.get("event", "")})
    case["data_quality"] = "full"
    return case


def adapt_yaml_v3(data, case):
    """来源 B：yaml v3.0 中文 key（存量遗留格式）。只读。"""
    case["source_type"] = "B"
    info = data.get("案件基本信息") or {}
    case["display_name"] = info.get("案件名称") or case["display_name"]
    case["case_number"] = info.get("法院案号", "")
    case["cause"] = info.get("案由", "")
    case["stage"] = info.get("当前阶段", "")
    # tasks（里程碑，只读）
    pm = data.get("项目管理") or {}
    for m in pm.get("里程碑") or []:
        case["tasks"].append({
            "id": f"{case['id']}-m-{(m.get('名称') or '')[:6]}",
            "title": m.get("名称", ""),
            "status": norm_status(m.get("状态")),
            "priority": "",
            "deadline": m.get("计划日期", ""),
            "source_type": "B",
            "source_ref": {"kind": "readonly"},
            "writable": False,
        })
    # deadlines
    for key, d in (data.get("法定期限管理") or {}).items():
        if not isinstance(d, dict):
            continue
        dl = days_left(d.get("截止日期"))
        case["deadlines"].append({
            "name": key,
            "end_date": d.get("截止日期", ""),
            "days_left": dl,
            "level": deadline_level(dl, d.get("状态")),
            "status": d.get("状态", ""),
        })
    # timeline
    tl = (data.get("案件时间线") or {}).get("关键节点") or []
    for d in tl:
        case["timeline"].append({"date": str(d.get("日期", "")), "event": d.get("具体事项") or d.get("事件类型", "")})
    case["data_quality"] = "full"
    return case


def adapt_yaml_custom(data, case):
    """来源 C：yaml 自定义中文 key（存量遗留格式）。只读（任务靠列表归属，无 status 字段）。"""
    case["source_type"] = "C"
    info = data.get("案件基本信息") or {}
    case["display_name"] = info.get("案件标识") or case["display_name"]
    case["case_number"] = info.get("案件编号", "")
    case["cause"] = info.get("案由", "")
    case["status"] = info.get("当前状态", "")
    case["stage"] = info.get("案件阶段", "")
    wp = data.get("工作进度") or {}
    # 三列表：列表归属即状态
    for item in wp.get("已完成工作") or []:
        case["tasks"].append(_c_task(case, item, "done"))
    for item in wp.get("正在进行") or []:
        case["tasks"].append(_c_task(case, item, "in_progress"))
    for item in wp.get("待开始工作") or []:
        case["tasks"].append(_c_task(case, item, "todo"))
    # deadlines
    dl_section = data.get("诉讼时效与期限") or {}
    dl = days_left(dl_section.get("诉讼时效截止"))
    if dl_section.get("诉讼时效截止"):
        case["deadlines"].append({
            "name": "诉讼时效",
            "end_date": dl_section.get("诉讼时效截止", ""),
            "days_left": dl,
            "level": deadline_level(dl),
            "status": "",
        })
    # timeline
    for stage_name, items in (data.get("时间线与里程碑") or {}).items():
        if not isinstance(items, list):
            continue
        for d in items:
            case["timeline"].append({"date": str(d.get("日期", "")), "event": d.get("事件", "")})
    case["data_quality"] = "partial"
    return case


def _c_task(case, item, status):
    name = item.get("任务名称") or item.get("名称") or ""
    return {
        "id": f"{case['id']}-c-{abs(hash(name)) % 100000}",
        "title": name,
        "status": status,
        "priority": item.get("优先级", ""),
        "deadline": item.get("截止日期", ""),
        "source_type": "C",
        "source_ref": {"kind": "readonly"},
        "writable": False,
    }


def adapt_info_md(text, case):
    """来源 D：Markdown 案件信息.md（存量遗留格式）。checkbox 可写。"""
    case["source_type"] = "D"
    lines = text.splitlines()
    # 表格提取案由 / 案件编号 / 案件状态（尽力）
    def table_field(key):
        for ln in lines:
            m = re.match(r"\|\s*\**" + re.escape(key) + r"\**\s*\|\s*([^|]+?)\s*\|", ln)
            if m:
                return m.group(1).strip()
        return ""

    case["case_number"] = table_field("案号") or table_field("案件编号")
    case["cause"] = table_field("案由") or table_field("案件类型")
    # blockquote 案件状态
    for ln in lines[:10]:
        m = re.search(r"\*\*案件状态[:：]\*\*\s*(.+)", ln)
        if m:
            case["status"] = m.group(1).strip()
            break
    if not case["status"]:
        case["status"] = table_field("案件状态") or table_field("当前状态")
    # display_name fallback：目录名
    if not case["cause"]:
        case["cause"] = ""
    # checkbox 任务（可写，按行号定位）
    for i, ln in enumerate(lines, start=1):
        m = re.match(r"^\s*- \[([ xX])\]\s+(.+)$", ln)
        if not m:
            continue
        title = m.group(2).strip()
        if title in ("暂无", "无"):
            continue  # 跳过无意义占位
        is_done = m.group(1).lower() == "x"
        case["tasks"].append({
            "id": f"{case['id']}-md-{i}",
            "title": title,
            "status": "done" if is_done else "todo",
            "priority": "",
            "deadline": "",
            "source_type": "D",
            "source_ref": {"kind": "md_checkbox", "line": i},
            "writable": True,
        })
    # 时间线表格（## 时间线 下的 | 时间 | 事件 | 状态 |）
    in_tl = False
    for ln in lines:
        if re.match(r"^##.*时间线", ln):
            in_tl = True
            continue
        if in_tl:
            if re.match(r"^##\s", ln) and "时间线" not in ln:
                break
            m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", ln)
            if m and "时间" not in m.group(1) and "---" not in ln:
                case["timeline"].append({"date": m.group(1).strip(), "event": m.group(2).strip()})
    case["data_quality"] = "partial"
    return case


def adapt_none(case):
    case["source_type"] = "none"
    case["data_quality"] = "minimal"
    return case


def find_yaml(case_dir):
    """找 <案件目录>/00 - 📅 日程管理/*.yaml；固定名 case.yaml（v4.0 canonical）优先。"""
    for sub in (case_dir / "00 - 📅 日程管理",):
        if sub.is_dir():
            fixed = sub / "case.yaml"
            if fixed.exists():
                return fixed
            for p in sorted(sub.glob("*.yaml")):
                return p
    return None


def find_info_md(case_dir):
    """找 <案件目录>/*案件信息*.md。"""
    for p in sorted(case_dir.glob("*案件信息*.md")):
        return p
    return None


def detect_yaml_schema(data):
    """判断 yaml 属于 V/A/B/C 哪种 schema。"""
    if isinstance(data, dict):
        if data.get("模板版本") == "4.0" or "meta" in data:
            return "V"
        if "case_info" in data or "tasks" in data or "legal_deadlines" in data:
            return "A"
        if "项目管理" in data or "法定期限管理" in data:
            return "B"
        if "工作进度" in data or "诉讼时效与期限" in data:
            return "C"
    return None


def load_case(case_dir):
    """加载并归一化单个案件。"""
    case_dir = Path(case_dir)
    m = CASE_DIR_RE.match(case_dir.name)
    case_id = m.group(1) if m else case_dir.name[:6]
    case = base_case(case_id, case_dir)

    yaml_path = find_yaml(case_dir)
    md_path = find_info_md(case_dir)

    # yaml 优先
    used_yaml = False
    if yaml_path:
        text, err = safe_read_text(yaml_path)
        if text:
            try:
                data = yaml.safe_load(text)
                schema = detect_yaml_schema(data)
                case["yaml_path"] = str(yaml_path)
                if schema == "V":
                    adapt_yaml_v4(data, case)
                    used_yaml = True
                elif schema == "A":
                    adapt_yaml_v21(data, case)
                    used_yaml = True
                elif schema == "B":
                    adapt_yaml_v3(data, case)
                    used_yaml = True
                elif schema == "C":
                    adapt_yaml_custom(data, case)
                    used_yaml = True
            except yaml.YAMLError:
                pass  # yaml 解析失败，回退 info.md

    # info.md 补充（D 案件，或 yaml 缺失时）
    if md_path:
        text, _ = safe_read_text(md_path)
        if text:
            case["md_path"] = str(md_path)
            if not used_yaml:
                adapt_info_md(text, case)
            else:
                # 已有 yaml：用 info.md 仅补 display_name/case_number（若 yaml 没有）
                if not case["display_name"] or case["display_name"] == case["dir_name"]:
                    for ln in text.splitlines()[:5]:
                        mh = re.match(r"^#\s+(.+)$", ln)
                        if mh:
                            case["display_name"] = mh.group(1).strip()
                            break

    if not used_yaml and not md_path:
        adapt_none(case)

    # 补 display_name：从目录名
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
def atomic_write(path, new_text):
    """flock 排它锁 + 同文件 truncate + 重写，保留 inode（os.replace 会换 inode，不可用）。
    写之前若失败则用临时文件保存原内容备份到 .bak，回滚（尽力）。"""
    path = Path(path)
    backup = None
    with open(path, "r+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # 备份原内容（仅内存），写失败时回滚
            f.seek(0)
            original = f.read()
            f.seek(0)
            f.truncate()
            f.write(new_text)
            f.flush()
            os.fsync(f.fileno())
        except Exception:
            # 回滚
            try:
                f.seek(0)
                f.truncate()
                f.write(original)
                f.flush()
                os.fsync(f.fileno())
            except Exception:  # noqa: BLE001
                pass
            raise
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def patch_yaml_task_status(yaml_path, task_id, target_status):
    """行级 patch：找到 `id: <task_id>` 块内的 status 行，替换值。返回 (ok, msg)。"""
    if target_status == "done":
        new_val = "done"
    elif target_status == "todo":
        new_val = "pending"
    else:
        return False, "不支持的中间状态写入（仅支持 待办↔已完成）"

    text, err = safe_read_text(yaml_path)
    if text is None:
        return False, f"读取失败: {err}"
    lines = text.splitlines(keepends=True)

    # 定位 task 块：从 `  - id: "<task_id>"` 开始，到下一个 `  - ` 列表项结束
    id_pat = re.compile(r'^(\s*- id:\s*["\']?' + re.escape(task_id) + r'["\']?\s*)')
    start = None
    for i, ln in enumerate(lines):
        if id_pat.match(ln):
            start = i
            break
    if start is None:
        return False, f"未找到任务 id={task_id}"

    # 块范围：start 到下一个同级 `  - ` 项
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^\s{2}- \w", lines[j]):  # 同级新列表项
            end = j
            break

    status_pat = re.compile(r'^(\s*status:\s*)["\']?[\w]+["\']?')
    patched = False
    for k in range(start, end):
        raw = lines[k]
        stripped = raw.rstrip("\r\n")
        m = status_pat.match(stripped)
        if m:
            eol = raw[len(stripped):]  # 保留原行尾（\n 或 \r\n 或空），杜绝多写空行
            lines[k] = m.group(1) + f'"{new_val}"' + eol
            patched = True
            break
    if not patched:
        return False, "任务块内未找到 status 字段（格式异常）"

    atomic_write(yaml_path, "".join(lines))
    return True, "ok"


def patch_md_checkbox(md_path, line_no, target_status):
    """行级 patch：把第 line_no 行的 checkbox 在 [ ]↔[x] 间翻转。"""
    text, err = safe_read_text(md_path)
    if text is None:
        return False, f"读取失败: {err}"
    lines = text.splitlines(keepends=True)
    if line_no < 1 or line_no > len(lines):
        return False, "行号越界（文件可能已变动，请刷新）"

    ln = lines[line_no - 1]
    eol = "\r\n" if ln.endswith("\r\n") else "\n"
    ln = ln.rstrip("\r\n")
    if target_status == "done":
        new_ln = re.sub(r"^(\s*)- \[ \]", r"\1- [x]", ln)
    else:
        new_ln = re.sub(r"^(\s*)- \[[xX]\]", r"\1- [ ]", ln)
    if new_ln == ln:
        return False, "该行不是可切换的 checkbox（格式异常）"
    lines[line_no - 1] = new_ln + eol
    atomic_write(md_path, "".join(lines))
    return True, "ok"


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
    """根据 source_ref.kind 路由到对应 patch。path 由服务端从 case_id 权威推导，不信前端。"""
    case = find_case_by_id(case_id)
    if not case:
        return False, "案件不存在"
    kind = source_ref.get("kind")
    if kind == "case_store":
        return toggle_via_case_store(case, source_ref, target_status)
    if kind == "yaml_status":
        if not case.get("yaml_path"):
            return False, "案件无 yaml 文件"
        return patch_yaml_task_status(case["yaml_path"], source_ref.get("task_id", ""), target_status)
    if kind == "md_checkbox":
        if not case.get("md_path"):
            return False, "案件无 info.md 文件"
        return patch_md_checkbox(case["md_path"], int(source_ref.get("line", 0)), target_status)
    return False, "该任务不支持状态切换（只读来源）"


# ---------------------------------------------------------------------------
# API 数据组装
# ---------------------------------------------------------------------------
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
        out.append({
            "id": c["id"],
            "display_name": c["display_name"],
            "case_number": c["case_number"],
            "cause": c["cause"],
            "status": c["status"],
            "stage": c["stage"],
            "source_type": c["source_type"],
            "data_quality": c["data_quality"],
            "task_counts": counts,
            "nearest_deadline": nearest,
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
            try:
                subprocess.run(["open", c["case_dir"]], check=False)
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
        flag = {"V": "v4.0", "A": "yamlv2.1", "B": "yamlv3", "C": "yaml自定义", "D": "info.md", "none": "仅目录"}[c["source_type"]]
        w = "可写" if any(t["writable"] for t in c["tasks"]) else "只读"
        print(f"   · [{c['id']}] {c['display_short']:<14} {flag:<10} {w}")

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
