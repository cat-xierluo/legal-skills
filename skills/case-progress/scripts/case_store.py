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

    for name in ("show", "add-task", "set-status", "add-deadline", "set-stage", "validate"):
        sub.choices[name].add_argument("--actor", default="ai", choices=["user", "ai"],
                                       help="操作者（source=user 行与锁定阶段仅接受 user）")

    args = ap.parse_args()
    root = find_root(args.root)
    table = {"show": cmd_show, "list": cmd_list, "add-task": cmd_add_task,
             "set-status": cmd_set_status, "add-deadline": cmd_add_deadline,
             "set-stage": cmd_set_stage, "validate": cmd_validate}
    table[args.cmd](root, args.case_id, args) if args.cmd != "list" else table["list"](root)


if __name__ == "__main__":
    main()
