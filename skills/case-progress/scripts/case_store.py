#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""case_store.py — case.yaml v4.0 唯一写入引擎（case-progress skill）

字段契约：../references/schema.md（v4.0 唯一权威）
会话契约：../references/contract.md

用法：
    python3 case_store.py <子命令> [参数] [--root <项目根>]

子命令（M2 范围；audit/report 留 M6，migrate 留 M4）：
    show <案件短码>                          输出 canonical JSON（阶段按 锁定>手填>推断 解析）
    list                                     全部案件摘要（无 case.yaml 的存量案件标 unmigrated）
    add-task <短码> <标题> [--priority p] [--deadline D] [--owner X] [--desc S]
    set-status <短码> <task_id> <todo|in_progress|done>
    add-deadline <短码> <名称> --end <日期> [--type T] [--days N] [--start D] [--basis S]
    set-stage <短码> <阶段> [--lock] [--unlock]
    validate <短码>                          schema 校验

通用参数：
    --root <路径>     项目根（默认：SUITAGENT_ROOT 环境变量，或从 cwd 向上发现
                      含 6 位数字开头案件目录的祖先；禁止依赖本文件位置）
    --actor user|ai   操作者（默认 ai）。source=user 的行与已锁定的程序阶段
                      仅接受 --actor user；看板点击类操作由 server 以 --actor user 转发

写入路径（所有子命令一致）：
    schema 校验 → 行级 source 检查 → flock → 临时文件 + os.replace 原子替换
    每次成功写入追加 更新历史 并刷新 同步.最后同步时间
    注意：写入采用整文件 dump，yaml 注释不保留——填写指引以模板与 schema.md 为准（DEC-007）
"""

import argparse
import contextlib
import datetime
import fcntl
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# 常量与契约枚举（与 schema.md v4.0 对齐）
# ---------------------------------------------------------------------------
CASE_DIR_RE = re.compile(r"^(\d{6})\s")
CASE_YAML_GLOB = "0* - 📅 日程管理/case.yaml"

TRI_STATE = ("todo", "in_progress", "done")
PRIORITY = ("high", "medium", "low")
BUSINESS = ("诉讼", "商标", "专利", "咨询", "其他非诉")
CASE_TYPE = ("民事", "刑事", "行政", "执行", "仲裁")
LIFECYCLE = ("委托洽谈", "进行中", "已结案")
STAGE = ("诉前准备", "侦查", "审查起诉", "一审", "二审", "再审", "执行", "仲裁")
DL_TYPE = ("应诉", "举证", "上诉", "执行", "诉讼时效", "其他")
DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
CLOSED = "已结案"

REQUIRED_SECTIONS = ("meta", "案件基本信息", "当事人与代理", "任务", "案件时间线",
                     "费用信息", "上下文", "同步", "更新历史")
LIST_SECTIONS_WITH_SOURCE = ("任务", "法定期限", "案件时间线", "证据索引",
                             "开庭与听证", "审级记录")

TODAY = datetime.date.today()


def die(msg, code=1):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# 项目根发现（红线：禁 __file__.resolve()，符号链接安装会穿透回源仓库）
# ---------------------------------------------------------------------------
def find_root(explicit=None):
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_dir():
            die(f"--root 不是目录: {p}")
        return p
    env = os.environ.get("SUITAGENT_ROOT")
    if env:
        return Path(env).expanduser()
    d = Path.cwd().resolve()
    if CASE_DIR_RE.match(d.name):  # cwd 即案件目录 → 根为其父
        return d.parent
    for cand in [d, *d.parents]:
        try:
            if any(c.is_dir() and CASE_DIR_RE.match(c.name) for c in cand.iterdir()):
                return cand
        except PermissionError:
            continue
    die("未发现项目根：请用 --root 或设置 SUITAGENT_ROOT（须为含 6 位数字开头案件目录的路径）")


# ---------------------------------------------------------------------------
# 案件定位与读写
# ---------------------------------------------------------------------------
def case_dirs(root):
    return {CASE_DIR_RE.match(d.name).group(1): d
            for d in sorted(root.iterdir()) if d.is_dir() and CASE_DIR_RE.match(d.name)}


def case_yaml_path(root, case_id):
    dirs = case_dirs(root)
    if case_id not in dirs:
        die(f"案件不存在: {case_id}（可用: {', '.join(dirs) or '无'}）")
    matches = sorted(dirs[case_id].glob(CASE_YAML_GLOB))
    if not matches:
        die(f"案件 {case_id} 无 case.yaml（存量格式未迁移，M4 处理；新案件由 new-case v4.0 生成）")
    return matches[0]


def load_case(path):
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        die(f"YAML 解析失败 {path}: {e}")
    if not isinstance(data, dict):
        die(f"{path} 内容不是映射，请检查")
    return data


def atomic_write(path, data):
    """临时文件 + os.replace 原子替换（单写者语义由 case_lock 保证）。"""
    text = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextlib.contextmanager
def case_lock(yaml_path):
    """旁车锁：锁定 读-改-写 全周期，防并发丢失更新。

    锁文件为 <case.yaml>.lock（inode 稳定，不受 os.replace 影响；
    flock 由内核在进程退出时自动释放，无死锁残留）。运行时文件，不入库。
    """
    lock_path = yaml_path.parent / (yaml_path.name + ".lock")
    with open(lock_path, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# 校验（schema.md §5 六条规则的实现）
# ---------------------------------------------------------------------------
def _walk_strings(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_strings(item)
    elif isinstance(node, str):
        yield node


def validate_data(data, case_id):
    errs, warns = [], []
    for sec in REQUIRED_SECTIONS:
        if sec not in data:
            errs.append(f"缺少必填节: {sec}")
    meta = data.get("meta") or {}
    if meta.get("模板版本") != "4.0":
        errs.append(f"meta.模板版本 应为 \"4.0\"，当前: {meta.get('模板版本')}")
    if meta.get("业务领域") not in BUSINESS:
        errs.append(f"meta.业务领域 枚举非法: {meta.get('业务领域')}（{BUSINESS}）")
    if not (meta.get("案件短码") or "").strip() or meta.get("案件短码") != case_id:
        errs.append(f"meta.案件短码 应等于目录短码 {case_id}")

    info = data.get("案件基本信息") or {}
    for field, allowed in (("案件类型", CASE_TYPE), ("生命周期状态", LIFECYCLE)):
        if info.get(field) not in allowed:
            errs.append(f"案件基本信息.{field} 枚举非法: {info.get(field)}")
    if info.get("程序阶段") not in STAGE:
        errs.append(f"案件基本信息.程序阶段 枚举非法: {info.get('程序阶段')}")
    if info.get("生命周期状态") == CLOSED:
        warns.append(f"生命周期状态=已结案（只应经律师手工标记产生，请确认）")

    ids = set()
    for t in data.get("任务") or []:
        tid = t.get("id")
        if not tid:
            errs.append("任务行缺 id")
        elif tid in ids:
            errs.append(f"任务 id 重复: {tid}")
        else:
            ids.add(tid)

    for sec in LIST_SECTIONS_WITH_SOURCE:
        for row in data.get(sec) or []:
            src = row.get("source")
            if src not in ("user", "ai"):
                errs.append(f"{sec} 行缺/非法 source: {src}（{row.get('id') or row.get('名称') or row.get('日期') or '?'}）")

    for field in ("创建日期", "律所立案日期", "法院立案日期", "预计结案"):
        v = info.get(field)
        if v and not DATE_RE.match(str(v)):
            errs.append(f"日期格式非法 {field}: {v}（须 YYYY-MM-DD 或 YYYY-MM）")
    for t in data.get("任务") or []:
        if t.get("截止日期") and not DATE_RE.match(str(t["截止日期"])):
            errs.append(f"任务 {t.get('id')} 截止日期格式非法: {t['截止日期']}")
    for d in data.get("法定期限") or []:
        if not d.get("截止日期") or not DATE_RE.match(str(d["截止日期"])):
            errs.append(f"法定期限 [{d.get('名称')}] 截止日期缺失或格式非法")
    for row in data.get("案件时间线") or []:
        if not DATE_RE.match(str(row.get("日期") or "")):
            errs.append(f"时间线行日期非法: {row.get('日期')}")
    for d in data.get("开庭与听证") or []:
        if not DATE_RE.match(str(d.get("日期") or "")):
            errs.append(f"开庭与听证行日期非法: {d.get('日期')}")

    for s in _walk_strings(data.get("上下文")):
        if s.startswith("/") or re.match(r"^[A-Za-z]:\\\\", s):
            errs.append(f"上下文指针含绝对路径: {s}（契约要求相对路径）")
    return errs, warns


# ---------------------------------------------------------------------------
# 写入公共路径：校验 → source 检查（由各命令先行完成）→ 落盘 + 更新历史/同步
# ---------------------------------------------------------------------------
def commit_write(path, data, actor, action, detail):
    errs, warns = validate_data(data, (data.get("meta") or {}).get("案件短码") or "?")
    if errs:
        die("写入被 schema 校验拦截：\n  - " + "\n  - ".join(errs))
    data.setdefault("同步", {})["最后同步时间"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    data.setdefault("更新历史", []).append({
        "日期": TODAY.isoformat(),
        "操作者": "case_store" if actor == "ai" else "case_store(user)",
        "动作": action,
        "细节": detail,
    })
    atomic_write(path, data)
    for w in warns:
        print(f"⚠️ {w}")


# ---------------------------------------------------------------------------
# 派生逻辑
# ---------------------------------------------------------------------------
def days_left(end):
    if not end:
        return None
    m = DATE_RE.match(str(end))
    if not m or not m.group(1):
        return None
    try:
        return (datetime.date.fromisoformat(str(end)) - TODAY).days
    except ValueError:
        return None


STAGE_INFER_EVENTS = {"法院立案": "一审", "执行": "执行", "侦查": "侦查", "审查起诉": "审查起诉"}


def resolve_stage(data):
    """锁定 > 手填 > 规则推断（返回 (阶段, 来源)）。"""
    info = data.get("案件基本信息") or {}
    manual = info.get("程序阶段")
    if info.get("程序阶段锁定"):
        return manual, "locked"
    events = data.get("案件时间线") or []
    for ev in reversed(events):  # 最新的事件优先
        mapped = STAGE_INFER_EVENTS.get(ev.get("事件类型"))
        if mapped:
            return (manual if manual and manual != "诉前准备" else mapped), \
                   ("manual" if manual and manual != "诉前准备" else "inferred")
    return manual, "manual"


def deadline_display(d):
    dl = days_left(d.get("截止日期"))
    cancelled = bool(d.get("抵消标记"))
    return {"类型": d.get("类型"), "名称": d.get("名称"), "截止日期": d.get("截止日期"),
            "状态": d.get("状态"), "法律依据": d.get("法律依据"),
            "抵消": cancelled, "剩余天数": dl,
            "告警": None if cancelled or d.get("状态") == "done" else
                    ("red" if dl is not None and dl <= 7 else
                     "orange" if dl is not None and dl <= 30 else "normal")}


def build_show(data):
    stage, stage_src = resolve_stage(data)
    tasks = data.get("任务") or []
    counts = {s: sum(1 for t in tasks if t.get("状态") == s) for s in TRI_STATE}
    return {
        "meta": data.get("meta"),
        "案件基本信息": {**(data.get("案件基本信息") or {}),
                        "程序阶段": stage, "程序阶段来源": stage_src},
        "任务": tasks,
        "任务统计": counts,
        "法定期限": [deadline_display(d) for d in data.get("法定期限") or []],
        "开庭与听证": data.get("开庭与听证") or [],
        "审级记录": data.get("审级记录") or [],
        "上下文": data.get("上下文"),
        "同步": data.get("同步"),
    }


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def cmd_show(root, case_id, *_a, **_k):
    data = load_case(case_yaml_path(root, case_id))
    print(json.dumps(build_show(data), ensure_ascii=False, indent=2))


def cmd_list(root, *_a, **_k):
    out = []
    for cid, d in case_dirs(root).items():
        matches = sorted(d.glob(CASE_YAML_GLOB))
        if not matches:
            out.append({"案件": cid, "目录": d.name, "unmigrated": True})
            continue
        data = load_case(matches[0])
        stage, _ = resolve_stage(data)
        dl = [x for x in (deadline_display(d2) for d2 in data.get("法定期限") or [])
              if x["告警"] not in (None, "normal")]
        out.append({
            "案件": cid, "名称": (data.get("案件基本信息") or {}).get("案件名称"),
            "生命周期": (data.get("案件基本信息") or {}).get("生命周期状态"),
            "阶段": stage,
            "任务": {s: sum(1 for t in data.get("任务") or [] if t.get("状态") == s) for s in TRI_STATE},
            "临期期限": len(dl),
        })
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_add_task(root, case_id, args):
    path = case_yaml_path(root, case_id)
    with case_lock(path):
        data = load_case(path)
        tasks = data.setdefault("任务", [])
        existing = {int(m.group(1)) for t in tasks if (m := re.match(r"^task_(\d+)$", str(t.get("id") or "")))}
        new_id = f"task_{max(existing, default=0) + 1:03d}"
        if args.priority not in PRIORITY:
            die(f"--priority 枚举非法（{PRIORITY}）")
        if args.deadline and not DATE_RE.match(args.deadline):
            die("--deadline 须 YYYY-MM-DD")
        tasks.append({"id": new_id, "名称": args.title, "状态": "todo", "优先级": args.priority,
                      "截止日期": args.deadline, "负责人": args.owner, "描述": args.desc or "",
                      "source": args.actor})
        commit_write(path, data, args.actor, "新增任务", f"{new_id} {args.title}")
    print(f"✅ 已新增任务 {new_id}（source={args.actor}）")


def cmd_set_status(root, case_id, args):
    path = case_yaml_path(root, case_id)
    with case_lock(path):
        data = load_case(path)
        if args.status not in TRI_STATE:
            die(f"状态枚举非法（{TRI_STATE}）")
        task = next((t for t in data.get("任务") or [] if t.get("id") == args.task_id), None)
        if not task:
            die(f"未找到任务 {args.task_id}（show 可查全部 id）")
        if task.get("source") == "user" and args.actor != "user":
            die(f"任务 {args.task_id} 由律师手工创建（source=user），AI 不得改写；"
                f"请律师经看板操作，或 --actor user 显式代行")
        old = task.get("状态")
        task["状态"] = args.status
        commit_write(path, data, args.actor, "推进任务", f"{args.task_id} {task.get('名称')}: {old} → {args.status}")
    print(f"✅ {args.task_id}: {old} → {args.status}")


def cmd_add_deadline(root, case_id, args):
    path = case_yaml_path(root, case_id)
    with case_lock(path):
        data = load_case(path)
        if not args.end or not DATE_RE.match(args.end):
            die("--end 必填且须 YYYY-MM-DD")
        dtype = args.type
        if not dtype:
            dtype = next((t for t in DL_TYPE if t in args.name), "其他")
        if dtype not in DL_TYPE:
            die(f"--type 枚举非法（{DL_TYPE}）")
        if args.start and not DATE_RE.match(args.start):
            die("--start 须 YYYY-MM-DD")
        row = {"类型": dtype, "名称": args.name, "天数": args.days, "起算日期": args.start,
               "截止日期": args.end, "状态": "todo", "法律依据": args.basis,
               "抵消标记": None, "source": args.actor}
        data.setdefault("法定期限", []).append(row)
        commit_write(path, data, args.actor, "登记期限", f"{dtype}|{args.name} 截止 {args.end}")
    print(f"✅ 已登记期限 {args.name}（截止 {args.end}，剩余 {days_left(args.end)} 天）")


def cmd_set_stage(root, case_id, args):
    path = case_yaml_path(root, case_id)
    with case_lock(path):
        data = load_case(path)
        info = data.setdefault("案件基本信息", {})
        if args.stage not in STAGE:
            die(f"程序阶段枚举非法（{STAGE}）")
        if args.unlock:
            if args.actor != "user":
                die("解锁程序阶段属律师操作（--actor user）")
            info["程序阶段锁定"] = False
            commit_write(path, data, args.actor, "解锁程序阶段", f"原阶段 {info.get('程序阶段')}")
            print("✅ 已解锁程序阶段")
            return
        if info.get("程序阶段锁定") and args.actor != "user":
            die("程序阶段已锁定，AI 不得改写（律师可用 --actor user --unlock 解锁）")
        old = info.get("程序阶段")
        info["程序阶段"] = args.stage
        if args.lock:
            if args.actor != "user":
                die("加锁属律师操作（--actor user --lock）")
            info["程序阶段锁定"] = True
        commit_write(path, data, args.actor, "更新程序阶段" + ("（锁定）" if args.lock else ""),
                     f"{old} → {args.stage}")
    print(f"✅ 程序阶段: {old} → {args.stage}" + ("（已锁定）" if args.lock else ""))


def cmd_validate(root, case_id, *_a, **_k):
    path = case_yaml_path(root, case_id)
    data = load_case(path)
    errs, warns = validate_data(data, case_id)
    for e in errs:
        print(f"❌ {e}")
    for w in warns:
        print(f"⚠️ {w}")
    if errs:
        sys.exit(1)
    print(f"✅ 案件 {case_id} 校验通过（{'有' if warns else '无'}警告）")


# ---------------------------------------------------------------------------
# M4 存量迁移：5 种遗留来源 → case.yaml v4.0
# 安全设计：默认 dry-run；--apply 才写盘；原文件改名 .legacy.yaml/.legacy.md 永不删除；
# 生成的 v4.0 档案先过 validate_data，有 error 的案件跳过不写。
# ---------------------------------------------------------------------------
LEGACY_NOTE = "> ⚠️ **任务/期限/进度唯一真源为 `00 - 📅 日程管理/case.yaml`**（本节为迁移前存档，不再更新）"


def _norm3(raw):
    s = str(raw or "").strip()
    if any(k in s for k in ("已完成", "done", "passed", "已结案", "已收集", "结案")):
        return "done"
    if any(k in s for k in ("进行中", "in_progress", "正在")):
        return "in_progress"
    return "todo"


def _num(raw):
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.search(r"[\d,]+(?:\.\d+)?", str(raw or ""))
    return float(m.group().replace(",", "")) if m else None


def _date(raw):
    s = str(raw or "").strip()
    if DATE_RE.match(s):
        return s
    m = re.search(r"(\d{4})[年/-](\d{1,2})(?:[月/-](\d{1,2}))?", s)
    if m:
        y, mo, d = m.group(1), int(m.group(2)), m.group(3)
        return f"{y}-{mo:02d}" + (f"-{int(d):02d}" if d else "")
    m = re.search(r"^(\d{4})年?$", s)
    if m:
        return m.group(1) + "-01"  # 年份精度不足，记 YYYY-01 并出警告
    return None


def _stars(raw):
    return str(raw or "").count("⭐") or 2


def _party_v4(name, role, ptype="自然人", detail=None, warn=None):
    d = detail or {}
    return {"姓名": name, "角色": role, "类型": ptype if ptype in ("自然人", "法人", "非法人组织") else "自然人",
            "证件号码": d.get("证件号码") or d.get("id_number"), "联系方式": d.get("联系方式") or d.get("contact"),
            "住址": d.get("住址") or d.get("address"), "法定代表人": d.get("法定代表人") or d.get("representative"),
            "扩展信息": d.get("扩展信息", {}), "source": "user"}


def _base_v4(case_id, dir_name, warn):
    return {
        "meta": {"模板版本": "4.0", "业务领域": "诉讼", "案件短码": case_id, "目录标识": dir_name,
                 "律所案号": None, "法院案号": None, "创建日期": None},
        "案件基本信息": {"案件名称": None, "案由": None, "案件类型": "民事", "管辖法院": None,
                       "生命周期状态": "进行中", "程序阶段": "诉前准备", "程序阶段锁定": False,
                       "律所立案日期": None, "法院立案日期": None, "预计结案": None,
                       "标的额": None, "标的额备注": None, "关联案件": []},
        "当事人与代理": {"我方当事人": [], "对方当事人": [], "律师": [], "其他诉讼参与人": []},
        "法定期限": [], "任务": [], "案件时间线": [], "开庭与听证": [], "证据索引": [],
        "费用信息": {"支出": {k: {"金额": None, "状态": "待确定"} for k in ("律师费", "诉讼费", "鉴定费", "其他费用")},
                    "索赔与评估": []},
        "争议焦点与法律研究": {"争议焦点": [], "法律研究": []},
        "审级记录": [], "工时统计": {"总工时": 0},
        "上下文": {"叙事文档": "../案件信息.md", "工时记录": None, "关键报告": []},
        "扩展信息": {}, "同步": {"最后同步时间": None, "材料指纹": None, "状态过期": False},
        "更新历史": [],
    }


def build_v4_A(y00, y0653, case_id, dir_name, warn):
    """来源 A：v2.1.0 英文 key（00 目录期限 yaml + 根目录基础信息表 yaml 双文件合并）。"""
    v = _base_v4(case_id, dir_name, warn)
    rich = (y0653 or {}).get("case_info", {}).get("basic_info", {}) or {}
    base = y00.get("case_info", {}).get("basic_info", {}) or {}
    m = v["meta"]
    m["律所案号"] = rich.get("law_firm_case_number") or None
    m["法院案号"] = base.get("case_number") or rich.get("case_number") or None
    m["创建日期"] = _date(rich.get("law_firm_filing_date") or base.get("filing_date"))
    info = v["案件基本信息"]
    info.update({"案件名称": base.get("case_name") or rich.get("case_name"), "案由": base.get("cause"),
                 "案件类型": base.get("case_type") or "民事", "管辖法院": rich.get("jurisdiction_court"),
                 "生命周期状态": "已结案" if "结案" in str(base.get("case_status", "")) else "进行中",
                 "程序阶段": base.get("current_stage") or "诉前准备",
                 "律所立案日期": _date(rich.get("law_firm_filing_date") or base.get("filing_date"))})
    parties = {}
    for p in (y0653 or {}).get("case_info", {}).get("parties", {}).get("plaintiffs", []) or []:
        parties[p.get("name")] = {"证件号码": p.get("id_number"), "联系方式": p.get("contact"),
                                  "住址": p.get("address"), "法定代表人": p.get("representative")}
    rep = y00.get("case_info", {}).get("representation", {}) or {}
    for p in rep.get("represented_parties", []) or []:
        v["当事人与代理"]["我方当事人"].append(_party_v4(p.get("name"), p.get("role") or "原告",
                                                        detail=parties.get(p.get("name"), {})))
    for p in rep.get("opposing_parties", []) or []:
        v["当事人与代理"]["对方当事人"].append(_party_v4(p.get("name"), p.get("role") or "被告"))
    for l in (y00.get("case_info", {}).get("lawyers", []) or []):
        v["当事人与代理"]["律师"].append({"姓名": l.get("lawyer_name"), "角色": l.get("role") or "协办律师",
                                              "执业证号": None, "所属律所": None})
    cat_map = {"court": "开庭", "settlement": "调解", "file": "其他", "internal": "其他"}
    for k, d in (y00.get("legal_deadlines") or {}).items():
        tmap = {"appeal": "上诉", "execution": "执行"}.get(k, "其他")
        v["法定期限"].append({"类型": tmap, "名称": d.get("name") or k, "天数": d.get("days"),
                                "起算日期": _date(d.get("start_date")), "截止日期": _date(d.get("end_date")),
                                "状态": _norm3(d.get("status")), "法律依据": d.get("description"),
                                "抵消标记": None, "source": "user"})
    for t in y00.get("tasks", []) or []:
        v["任务"].append({"id": t.get("id") or f"task_{len(v['任务']) + 1:03d}", "名称": t.get("name"),
                          "状态": _norm3(t.get("status")), "优先级": t.get("priority") or "medium",
                          "截止日期": _date(t.get("deadline")), "负责人": None,
                          "描述": t.get("description") or "", "source": "user"})
    for e in y00.get("important_dates", []) or []:
        v["案件时间线"].append({"日期": _date(e.get("date")),
                                "事件类型": cat_map.get(e.get("category"), "其他"),
                                "事项": e.get("event"), "重要程度": 2, "来源文件": None,
                                "状态": "done", "source": "user"})
    fees = y00.get("fees", {}) or {}
    for src, dst in (("attorney_fee", "律师费"), ("court_fee", "诉讼费"), ("appraisal_fee", "鉴定费")):
        f = fees.get(src)
        if isinstance(f, dict) and f.get("amount") is not None:
            v["费用信息"]["支出"][dst] = {"金额": _num(f.get("amount")), "状态": "已确定"}
    v["上下文"]["工时记录"] = "工时记录.md"
    for h in (y00.get("update_history", []) or []):
        v["更新历史"].append({"日期": _date(h.get("date")), "操作者": h.get("operator") or "legacy",
                              "动作": h.get("action") or "更新", "细节": h.get("description") or ""})
    return v


def _stage_norm(raw):
    s = str(raw or "")
    for st in ("审查起诉", "诉前准备", "一审", "二审", "再审", "执行", "仲裁", "侦查"):
        if st in s:
            return st
    return "诉前准备"


def build_v4_B(y, case_id, dir_name, warn):
    """来源 B：v3.0 中文 key（现行旧模板，章节处置见 schema §3）。"""
    v = _base_v4(case_id, dir_name, warn)
    b = y.get("案件基本信息", {}) or {}
    v["meta"].update({"律所案号": b.get("律所案号") or None, "法院案号": b.get("法院案号") or None,
                      "创建日期": _date(b.get("律所立案日期"))})
    v["案件基本信息"].update({
        "案件名称": b.get("案件名称"), "案由": b.get("案由"), "案件类型": b.get("案件类型") or "民事",
        "管辖法院": b.get("管辖法院"), "程序阶段": _stage_norm(b.get("当前阶段")),
        "律所立案日期": _date(b.get("律所立案日期")), "法院立案日期": _date(b.get("法院立案日期")),
        "预计结案": _date(b.get("预计结案"))})
    pa = b.get("当事人信息", {}) or {}
    for p in pa.get("我方代理当事人", []) or []:
        v["当事人与代理"]["我方当事人"].append(_party_v4(
            p.get("姓名"), p.get("角色") or "原告", p.get("类型") or "自然人",
            {"证件号码": p.get("证件号码"), "联系方式": p.get("联系电话"), "住址": p.get("地址"),
             "法定代表人": p.get("法定代表人")}))
    for p in pa.get("对方当事人", []) or []:
        v["当事人与代理"]["对方当事人"].append(_party_v4(
            p.get("姓名"), p.get("角色") or "被告", p.get("类型") or "法人",
            {"证件号码": p.get("证件号码"), "联系方式": p.get("联系电话"), "住址": p.get("地址"),
             "法定代表人": p.get("法定代表人")}))
    if b.get("承办律师"):
        v["当事人与代理"]["律师"].append({"姓名": b.get("承办律师"), "角色": "主办律师", "执业证号": None, "所属律所": None})
    if b.get("协办律师"):
        v["当事人与代理"]["律师"].append({"姓名": b.get("协办律师"), "角色": "协办律师", "执业证号": None, "所属律所": None})
    fe = b.get("费用信息", {}) or {}
    ok = "已确定" if "已确定" in str(fe.get("费用状态", "")) else "待确定"
    for src, dst in (("律师费", "律师费"), ("诉讼费", "诉讼费"), ("鉴定费", "鉴定费"), ("其他费用", "其他费用")):
        if fe.get(src) is not None:
            v["费用信息"]["支出"][dst] = {"金额": _num(fe.get(src)), "状态": ok}
    for n in (y.get("案件时间线", {}) or {}).get("关键节点", []) or []:
        nd = _date(n.get("日期"))
        if not nd:
            warn.append(f"时间线行日期不可解析，留叙事文档：{n.get('日期')} {n.get('具体事项')}")
            continue
        v["案件时间线"].append({"日期": nd, "事件类型": n.get("事件类型") or "其他",
                                "事项": n.get("具体事项"), "重要程度": _stars(n.get("重要程度")),
                                "来源文件": n.get("来源文件"), "状态": _norm3(n.get("执行状态")),
                                "source": "user"})
    for i, ml in enumerate((y.get("项目管理", {}) or {}).get("里程碑", []) or [], start=1):
        v["任务"].append({"id": f"task_{i:03d}", "名称": ml.get("名称"), "状态": _norm3(ml.get("状态")),
                          "优先级": "medium", "截止日期": _date(ml.get("计划日期")), "负责人": None,
                          "描述": f"里程碑（实际 {ml.get('实际日期') or '—'}）", "source": "user"})
    tmap = {"应诉期限": "应诉", "举证期限": "举证", "上诉期限": "上诉", "执行申请期限": "执行", "诉讼时效": "诉讼时效"}
    for k, d in (y.get("法定期限管理", {}) or {}).items():
        if not isinstance(d, dict):
            continue
        end = _date(d.get("截止日期"))
        if not end:
            warn.append(f"期限[{k}] 截止日期缺失或不可解析（{d.get('截止日期')}），未入库")
            continue
        v["法定期限"].append({"类型": tmap.get(k, "其他"), "名称": k, "天数": d.get("期限天数"),
                                "起算日期": _date(d.get("开始日期")), "截止日期": end,
                                "状态": _norm3(d.get("状态")), "法律依据": None, "抵消标记": None,
                                "source": "user"})
    rs = y.get("争议焦点与法律研究", {}) or {}
    for f in rs.get("争议焦点列表", []) or []:
        v["争议焦点与法律研究"]["争议焦点"].append(
            {"名称": f.get("争议焦点名称"), "状态": _norm3({"已分析": "done", "待深入": "in_progress", "待识别": "todo"}.get(f.get("当前状态"), ""))})
    for r in rs.get("法律研究摘要", []) or []:
        v["争议焦点与法律研究"]["法律研究"].append(
            {"主题": r.get("研究主题"), "状态": _norm3({"已完成": "done", "进行中": "in_progress", "待开始": "todo"}.get(r.get("状态"), ""))})
    total = ((y.get("工时统计", {}) or {}).get("总计", {}) or {}).get("已记录工时")
    v["工时统计"]["总工时"] = _num(total) or 0
    v["上下文"]["工时记录"] = "工时记录.md"
    for h in y.get("更新历史", []) or []:
        v["更新历史"].append({"日期": _date(h.get("日期")), "操作者": h.get("更新人") or "legacy",
                              "动作": h.get("更新内容") or "更新", "细节": h.get("更新原因") or ""})
    warn.append("法条检索/判例研究明细未入库（留 .legacy 与叙事文档）")
    return v


def build_v4_C(y, case_id, dir_name, warn):
    """来源 C：自创中文 key（字段最富：证据/索赔/策略）。"""
    v = _base_v4(case_id, dir_name, warn)
    b = y.get("案件基本信息", {}) or {}
    court_no = (y.get("当事人信息", {}) or {}).get("法院信息", {}) or {}
    m = v["meta"]
    raw_no = b.get("案件编号") or court_no.get("案号")
    m["法院案号"] = raw_no if raw_no and "[" not in str(raw_no) else None
    m["创建日期"] = _date(b.get("创建日期"))
    info = v["案件基本信息"]
    info.update({"案件名称": b.get("案件标识") or dir_name, "案由": b.get("案由"),
                 "案件类型": b.get("案件性质") or "民事", "管辖法院": court_no.get("法院名称"),
                 "生命周期状态": "进行中", "程序阶段": b.get("案件阶段") or "诉前准备",
                 "法院立案日期": _date(b.get("立案日期")) if b.get("立案日期") and "[" not in str(b.get("立案日期")) else None})
    pa = y.get("当事人信息", {}) or {}
    wt = pa.get("委托人", {}) or {}
    v["当事人与代理"]["我方当事人"].append(_party_v4(
        wt.get("姓名"), "委托人", "自然人",
        {"证件号码": wt.get("身份证号"), "联系方式": wt.get("联系电话"), "住址": wt.get("地址"),
         "扩展信息": {k: wt[k] for k in ("与患者关系",) if wt.get(k)}}))
    pt = pa.get("患者信息", {}) or {}
    if pt.get("姓名"):
        v["当事人与代理"]["我方当事人"].append(_party_v4(
            pt.get("姓名"), "原告（患者）", "自然人",
            {"证件号码": pt.get("身份证号"), "住址": pt.get("住址"),
             "扩展信息": {k: pt[k] for k in ("当前状态", "与委托人关系") if pt.get(k)}}))
    op = pa.get("对方当事人", {}) or {}
    if op.get("名称"):
        v["当事人与代理"]["对方当事人"].append(_party_v4(
            op.get("名称"), "被告", op.get("类型") or "法人",
            {"联系方式": op.get("联系方式"), "住址": op.get("地址"), "法定代表人": op.get("法定代表人")}))
    lw = pa.get("律师信息", {}) or {}
    if lw.get("律师姓名") and "[" not in str(lw.get("律师姓名")):
        v["当事人与代理"]["律师"].append({"姓名": lw.get("律师姓名"), "角色": "主办律师",
                                              "执业证号": lw.get("执业证号") if "[" not in str(lw.get("执业证号")) else None,
                                              "所属律所": lw.get("所属律所") if "[" not in str(lw.get("所属律所")) else None})
    for fam in pa.get("家属信息", []) or []:
        v["当事人与代理"]["其他诉讼参与人"].append({"姓名": fam.get("姓名"), "角色": "家属",
                                                        "备注": fam.get("关系"), "source": "user"})
    wp = y.get("工作进度", {}) or {}
    seq = [("已完成工作", "done"), ("正在进行", "in_progress"), ("待开始工作", "todo")]
    for key, st in seq:
        for it in wp.get(key, []) or []:
            v["任务"].append({"id": f"task_{len(v['任务']) + 1:03d}", "名称": it.get("任务名称") or it.get("名称"),
                              "状态": st, "优先级": {"高": "high", "中": "medium", "低": "low"}.get(it.get("优先级"), "medium"),
                              "截止日期": _date(it.get("截止日期")),
                              "负责人": it.get("负责人"), "描述": it.get("产出") or it.get("预计时间") or "",
                              "source": "user"})
    dl = y.get("诉讼时效与期限", {}) or {}
    end = _date(dl.get("诉讼时效截止"))
    if end:
        v["法定期限"].append({"类型": "诉讼时效", "名称": "诉讼时效", "天数": None,
                                "起算日期": _date(dl.get("诉讼时效起算")), "截止日期": end, "状态": "todo",
                                "法律依据": None, "抵消标记": None, "source": "user"})
    for st_name, items in (y.get("时间线与里程碑", {}) or {}).items():
        for e in items or []:
            if isinstance(e, dict) and e.get("日期"):
                v["案件时间线"].append({"日期": _date(e.get("日期")), "事件类型": "其他", "事项": e.get("事件"),
                                        "重要程度": 2, "来源文件": None, "状态": _norm3(e.get("状态")),
                                        "source": "user"})
    ev = y.get("证据清单", {}) or {}
    for key, st in (("已收集证据", "done"), ("待收集证据", "todo")):
        for e in ev.get(key, []) or []:
            v["证据索引"].append({"名称": e.get("证据名称"), "类型": e.get("证据类型") or "书证",
                                  "来源": e.get("来源"), "证明目的": e.get("证明目的"), "状态": st,
                                  "目录位置": "05 - 📎 证据材料/", "取证方式": None, "source": "user"})
    fo = y.get("争议焦点", {}) or {}
    for key, st in (("已识别争议", "in_progress"), ("待分析争议", "todo")):
        for f in fo.get(key, []) or []:
            v["争议焦点与法律研究"]["争议焦点"].append({"名称": f.get("争议点"), "状态": st})
    for q in (y.get("法律研究", {}) or {}).get("待研究问题", []) or []:
        v["争议焦点与法律研究"]["法律研究"].append({"主题": q.get("问题"), "状态": _norm3(q.get("状态")) or "todo"})
    fe = y.get("费用评估", {}) or {}
    for it in fe.get("医疗费用", []) or []:
        v["费用信息"]["索赔与评估"].append({"项目": f"医疗费用-{it.get('项目', '')}", "金额": _num(it.get("金额")),
                                              "计算方式": None, "备注": it.get("状态")})
    for it in fe.get("预计赔偿", []) or []:
        v["费用信息"]["索赔与评估"].append({"项目": it.get("项目"), "金额": _num(it.get("金额")),
                                              "计算方式": it.get("计算方式"), "备注": it.get("包括") or it.get("备注")})
    for it in fe.get("律师费方案", []) or []:
        v["费用信息"]["支出"]["律师费"] = {"金额": _num(next(iter(it.values()))), "状态": "待确定",
                                              "计费方式": "风险" if "风险" in str(it) else None}
    v["工时统计"]["总工时"] = _num(y.get("工时统计", {}).get("总工时")) or 0
    warn.append("案件关键事实/策略方案/风险评估未入库（保留在叙事文档与 .legacy）")
    return v


def build_v4_D(md_text, case_id, dir_name, warn):
    """来源 D：Markdown 案件信息.md（表格字段 + checkbox 任务 + 时间线表）。"""
    v = _base_v4(case_id, dir_name, warn)
    lines = md_text.splitlines()

    def field(*keys):
        for ln in lines:
            for k in keys:
                m = re.match(r"\|\s*\**" + re.escape(k) + r"\**\s*\|\s*([^|]+?)\s*\|", ln)
                if m:
                    return m.group(1).strip()
        return None

    v["meta"]["法院案号"] = (lambda s: s if s and "____" not in s and "待" not in s else None)(field("案号", "案件编号"))
    info = v["案件基本信息"]
    info["案件名称"] = (lines[0].lstrip("# ").strip() if lines else dir_name) or dir_name
    info["案由"] = field("案由", "案件类型")
    info["管辖法院"] = field("管辖法院")
    amt = field("标的额")
    if amt:
        info["标的额"] = _num(amt)
        info["标的额备注"] = amt
    for ln in lines[:10]:
        m = re.search(r"\*\*案件状态[:：]\*\*\s*(.+)", ln)
        if m:
            s = m.group(1).strip()
            info["生命周期状态"] = "已结案" if "结案" in s else "进行中"
            break
    for i, ln in enumerate(lines, start=1):
        m = re.match(r"^\s*- \[([ xX])\]\s+(.+)$", ln)
        if not m or m.group(2).strip() in ("暂无", "无"):
            continue
        v["任务"].append({"id": f"task_{len(v['任务']) + 1:03d}", "名称": m.group(2).strip(),
                          "状态": "done" if m.group(1).lower() == "x" else "todo", "优先级": "medium",
                          "截止日期": None, "负责人": None, "描述": "", "source": "user"})
    if not v["任务"]:
        warn.append("未识别到 checkbox 任务（任务清单可能为表格格式），任务需人工核对补充")
    in_tl = False
    for ln in lines:
        if re.match(r"^##.*时间线", ln):
            in_tl = True
            continue
        if in_tl:
            if re.match(r"^##\s", ln) and "时间线" not in ln:
                break
            m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|", ln)
            if m and "时间" not in m.group(1) and "日期" not in m.group(1) and "---" not in ln:
                d = _date(m.group(1))
                if not d:
                    warn.append(f"时间线行日期不可解析，留叙事文档：{m.group(1)} {m.group(2)}")
                    continue
                if re.match(r"^\d{4}$", m.group(1).strip()) or "年" in m.group(1) and "-" not in m.group(1):
                    warn.append(f"时间线精度不足已记 {d}：{m.group(1)} {m.group(2)}")
                v["案件时间线"].append({"日期": d, "事件类型": "其他", "事项": m.group(2),
                                        "重要程度": 2, "来源文件": None, "状态": _norm3(m.group(3)),
                                        "source": "user"})
    return v


def build_v4_none(case_id, dir_name, warn):
    """来源 none：仅目录——最小骨架，basic_info 标待补充（enrich 可补）。"""
    v = _base_v4(case_id, dir_name, warn)
    warn.append("无任何结构化来源：仅生成骨架，basic_info 待律师/AI 补充（--enrich）")
    return v


def _deep_merge(dst, src):
    for k, val in src.items():
        if isinstance(val, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], val)
        else:
            dst[k] = val


def _legacy_kind(case_dir):
    """探测遗留来源与文件。返回 (kind, files{})。"""
    d00 = case_dir / "00 - 📅 日程管理"
    files = {"yaml00": None, "yaml_root": None, "md": None}
    if d00.is_dir():
        fixed = d00 / "case.yaml"
        if fixed.exists():
            return "V4", files
        for p in sorted(d00.glob("*.yaml")):
            files["yaml00"] = p
            break
    for p in sorted(case_dir.glob("*.yaml")):
        files["yaml_root"] = p
        break
    for p in sorted(case_dir.glob("*案件信息*.md")):
        files["md"] = p
        break
    if files["yaml00"]:
        try:
            data = yaml.safe_load(files["yaml00"].read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        if "case_info" in data or "tasks" in data or "legal_deadlines" in data:
            return "A", files
        if "项目管理" in data or "法定期限管理" in data:
            return "B", files
        if "工作进度" in data or "诉讼时效与期限" in data:
            return "C", files
    if files["md"]:
        return "D", files
    return "none", files


def cmd_set_fields(root, case_id, args):
    """通用字段补充：深合并 JSON 进 case.yaml（列表字段整体替换，任务增改请用 add-task/set-status）。"""
    path = case_yaml_path(root, case_id)
    payload = getattr(args, "json_").lstrip("@")
    raw = getattr(args, "json_")
    src = Path(payload).read_text(encoding="utf-8") if payload != raw else raw
    patch = json.loads(src)
    with case_lock(path):
        data = load_case(path)
        if data.get("案件基本信息", {}).get("生命周期状态") == CLOSED and args.actor != "user":
            if "生命周期状态" in json.dumps(patch, ensure_ascii=False):
                die("生命周期状态=已结案 的变更属律师操作（--actor user）")
        if data.get("案件基本信息", {}).get("程序阶段锁定") and args.actor != "user":
            if "程序阶段锁定" in json.dumps(patch, ensure_ascii=False):
                die("程序阶段已锁定，其变更属律师操作（--actor user）")
        _deep_merge(data, patch)
        commit_write(path, data, args.actor, "字段补充", f"set-fields 合并 {len(patch)} 个顶层键")
    print(f"✅ 已合并 {len(patch)} 个顶层键（source 保护与校验已过）")


def cmd_migrate(root, case_id, args):
    targets = [(case_id, case_dirs(root)[case_id])] if case_id else sorted(case_dirs(root).items())
    applied, skipped = [], []
    for cid, cdir in targets:
        kind, files = _legacy_kind(cdir)
        if kind == "V4":
            print(f"· [{cid}] 已是 v4.0，跳过")
            continue
        warn = []
        try:
            if kind == "A":
                y00 = yaml.safe_load(files["yaml00"].read_text(encoding="utf-8"))
                y0653 = yaml.safe_load(files["yaml_root"].read_text(encoding="utf-8")) if files["yaml_root"] else None
                v = build_v4_A(y00, y0653, cid, cdir.name, warn)
            elif kind == "B":
                v = build_v4_B(yaml.safe_load(files["yaml00"].read_text(encoding="utf-8")), cid, cdir.name, warn)
            elif kind == "C":
                v = build_v4_C(yaml.safe_load(files["yaml00"].read_text(encoding="utf-8")), cid, cdir.name, warn)
            elif kind == "D":
                v = build_v4_D(files["md"].read_text(encoding="utf-8"), cid, cdir.name, warn)
            else:
                v = build_v4_none(cid, cdir.name, warn)
        except Exception as e:  # noqa: BLE001
            print(f"❌ [{cid}] {kind} 解析失败：{e}")
            skipped.append(cid)
            continue
        if args.enrich:
            payload = args.enrich.lstrip("@")
            src = Path(payload).read_text(encoding="utf-8") if payload != args.enrich else args.enrich
            _deep_merge(v, json.loads(src))
        errs, vwarns = validate_data(v, cid)
        t, dl, tl = len(v["任务"]), len(v["法定期限"]), len(v["案件时间线"])
        mine = v["当事人与代理"]
        print(f"· [{cid}] 来源 {kind} → 任务 {t} / 期限 {dl} / 时间线 {tl} / "
              f"当事人 {len(mine['我方当事人'])}+{len(mine['对方当事人'])} / "
              f"阶段 {v['案件基本信息']['程序阶段']} / 生命周期 {v['案件基本信息']['生命周期状态']}")
        for w in warn + vwarns:
            print(f"    ⚠️ {w}")
        if errs:
            for e in errs:
                print(f"    ❌ {e}")
            print(f"    ↳ 校验未过，--apply 时将跳过该案件")
            skipped.append(cid)
            continue
        if not args.apply:
            continue
        # 落盘：写 case.yaml → 原 yaml 归档 .legacy → 叙事/工时固定名化
        d00 = cdir / "00 - 📅 日程管理"
        d00.mkdir(exist_ok=True)
        v["同步"]["最后同步时间"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        v["更新历史"].append({"日期": TODAY.isoformat(), "操作者": "case_store",
                                 "动作": "存量迁移", "细节": f"来源 {kind} → v4.0（M4）"})
        atomic_write(d00 / "case.yaml", v)
        for key in ("yaml00", "yaml_root"):
            if files[key]:
                files[key].rename(files[key].with_name(files[key].name + ".legacy.yaml"))
        if files["md"]:
            target = cdir / "案件信息.md"
            if files["md"].name != "案件信息.md":
                files["md"].rename(target)
            text = target.read_text(encoding="utf-8")
            if LEGACY_NOTE not in text:
                text = re.sub(r"(^##\s*.*任务清单\s*$)", r"\1\n\n" + LEGACY_NOTE.replace("\\", "\\\\"), text, count=1, flags=re.MULTILINE)
                target.write_text(text, encoding="utf-8")
        else:
            (cdir / "案件信息.md").write_text(
                f"# {v['案件基本信息'].get('案件名称') or cdir.name}\n\n> 本档案由 M4 迁移生成（来源 {kind}），"
                f"案情叙事待补充。状态唯一真源：`00 - 📅 日程管理/case.yaml`。\n", encoding="utf-8")
        ts = sorted(d00.glob("*工时记录.md"))
        if ts and ts[0].name != "工时记录.md":
            v["上下文"]["工时记录"] = "工时记录.md"
            ts[0].rename(d00 / "工时记录.md")
        print(f"    ✅ 已落盘 case.yaml（原文件归档 .legacy）")
        applied.append(cid)
    tail = "已迁移: " + ", ".join(applied) if applied else "（dry-run 未写盘）"
    if skipped:
        tail += " | 跳过: " + ", ".join(skipped)
    print(tail)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="case.yaml v4.0 唯一写入引擎（case-progress skill）")
    ap.add_argument("--root", default=None, help="项目根（默认 SUITAGENT_ROOT 或 cwd 向上发现）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("case_id", metavar="案件短码")

    sp = sub.add_parser("show", help="输出 canonical JSON"); common(sp)
    sub.add_parser("list", help="全部案件摘要")
    sp = sub.add_parser("add-task", help="新增任务"); common(sp)
    sp.add_argument("title", metavar="标题")
    sp.add_argument("--priority", default="medium")
    sp.add_argument("--deadline", default=None)
    sp.add_argument("--owner", default=None)
    sp.add_argument("--desc", default=None)
    sp = sub.add_parser("set-status", help="推进任务"); common(sp)
    sp.add_argument("task_id"); sp.add_argument("status")
    sp = sub.add_parser("add-deadline", help="登记期限"); common(sp)
    sp.add_argument("name", metavar="名称")
    sp.add_argument("--end", required=True)
    sp.add_argument("--type", default=None)
    sp.add_argument("--days", type=int, default=None)
    sp.add_argument("--start", default=None)
    sp.add_argument("--basis", default=None)
    sp = sub.add_parser("set-stage", help="更新程序阶段"); common(sp)
    sp.add_argument("stage", metavar="阶段")
    sp.add_argument("--lock", action="store_true")
    sp.add_argument("--unlock", action="store_true")
    sp = sub.add_parser("validate", help="schema 校验"); common(sp)
    sp = sub.add_parser("set-fields", help="通用字段补充（深合并 JSON；列表整体替换，任务增改用专用命令）")
    common(sp)
    sp.add_argument("json_", metavar="JSON", help="补充 JSON（@文件路径 或内联）")
    sp = sub.add_parser("migrate", help="存量迁移（默认 dry-run，--apply 落盘；原文件归档 .legacy）")
    sp.add_argument("case_id", nargs="?", default=None, metavar="案件短码（缺省=全部）")
    sp.add_argument("--apply", action="store_true", help="真正写盘（默认只演练）")
    sp.add_argument("--enrich", default=None, help="补充字段 JSON（@文件路径 或内联），深合并进生成结果")

    for name in ("show", "add-task", "set-status", "add-deadline", "set-stage", "validate", "set-fields"):
        sub.choices[name].add_argument("--actor", default="ai", choices=["user", "ai"],
                                       help="操作者（source=user 行与锁定阶段仅接受 user）")

    args = ap.parse_args()
    root = find_root(args.root)
    table = {"show": cmd_show, "list": cmd_list, "add-task": cmd_add_task,
             "set-status": cmd_set_status, "add-deadline": cmd_add_deadline,
             "set-stage": cmd_set_stage, "validate": cmd_validate, "migrate": cmd_migrate,
             "set-fields": cmd_set_fields}
    if args.cmd == "set-fields":
        cmd_set_fields(root, args.case_id, args)
    else:
        table[args.cmd](root, args.case_id, args) if args.cmd != "list" else table["list"](root)


if __name__ == "__main__":
    main()
