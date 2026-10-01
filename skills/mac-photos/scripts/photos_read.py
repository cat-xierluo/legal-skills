#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mac-photos — 读取 Mac 照片图库（含 iCloud 同步的 iPhone 照片/截图）。

核心能力:
  scan    按条件（默认: 截图）从图库导出到本地工作区, 并对每张图 OCR 建全文索引
  search  按 OCR 出的文字内容搜索照片, 输出日期/文件/关键词上下文
  export  把搜索命中（或指定 uuid）的照片复制到任意目录保存
  list    浏览索引内容;  stats 查看索引统计;  doctor 环境自检

工作区默认 ~/Pictures/PhotosReader/（exports/ 存原片, index.jsonl 存索引）。
只使用 Python 标准库; 外部依赖 osxphotos（Python venv）与 ocr-vision（本技能编译）。
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent
DEFAULT_WS = Path.home() / "Pictures" / "PhotosReader"
DEFAULT_LIB = Path.home() / "Pictures" / "Photos Library.photoslibrary"
OSXPHOTOS = os.environ.get("OSXPHOTOS_BIN", str(Path.home() / "venvs" / "osxphotos" / "bin" / "osxphotos"))
OCR_BIN = SKILL_SCRIPTS / "bin" / "ocr-vision"
MKTEXT_BIN = SKILL_SCRIPTS / "bin" / "mktext"
SETUP_HINT = "请先在技能目录运行: bash scripts/setup.sh"
SMOKE_TEXT = "合同编号XS-2026-0918违约金50000元"
FDA_HINT = (
    "请到 系统设置 → 隐私与安全性 → 完全磁盘访问权限,\n"
    "为运行本脚本的终端应用（Terminal / iTerm / ZCode 等）打开开关, 然后重新运行。"
)


def eprint(*args):
    print(*args, file=sys.stderr)


def die(msg, hint=""):
    eprint(f"❌ {msg}")
    if hint:
        eprint(hint)
    sys.exit(1)


# ---------------------------------------------------------------- 工具函数

def ensure_bin(path, name):
    if not Path(path).exists():
        die(f"未找到 {name}: {path}", SETUP_HINT)


def run_osxphotos(args, check=True):
    ensure_bin(OSXPHOTOS, "osxphotos")
    cmd = [OSXPHOTOS] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        err = (proc.stderr or "")[-800:]
        if any(k in err for k in ("authorization denied", "Operation not permitted", "unable to open database")):
            die("无权读取照片图库（完全磁盘访问未授权）", FDA_HINT)
        die(f"osxphotos 执行失败 (exit {proc.returncode}):\n{err}")
    return proc


def ws_path(arg_ws):
    return Path(arg_ws).expanduser() if arg_ws else DEFAULT_WS


def ensure_ws(ws):
    (ws / "exports").mkdir(parents=True, exist_ok=True)
    return ws


def index_file(ws):
    return ws / "index.jsonl"


def load_index(ws):
    idx = {}
    f = index_file(ws)
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                idx[rec["uuid"]] = rec
            except (json.JSONDecodeError, KeyError):
                continue
    return idx


def write_index(ws, records):
    f = index_file(ws)
    tmp = f.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in sorted(records, key=lambda r: r.get("date") or ""):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(f)


def ocr_one(pair):
    uuid, path, date = pair
    proc = subprocess.run([str(OCR_BIN), str(path)], capture_output=True, text=True)
    text, err = "", ""
    out = proc.stdout.strip()
    if out:
        try:
            obj = json.loads(out.splitlines()[0])
            text, err = obj.get("text", ""), obj.get("error", "")
        except json.JSONDecodeError:
            err = "ocr-vision 输出无法解析"
    else:
        err = proc.stderr.strip()[:200] or f"ocr-vision exit {proc.returncode}"
    return {
        "uuid": uuid, "file": Path(path).name, "date": date,
        "size": Path(path).stat().st_size, "text": text or "",
    }, err


def context_of(text, term, width=44):
    pos = text.lower().find(term.lower())
    if pos < 0:
        return text.replace("\n", " ")[: width * 2]
    start, end = max(0, pos - width), min(len(text), pos + len(term) + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].replace("\n", " ⏎ ") + suffix


def build_filters(a):
    """把 argparse 参数翻译成 osxphotos 的过滤参数（query/export 通用）。"""
    filt = []
    if not a.all_types:
        filt.append("--screenshot")
    if a.from_date:
        filt += ["--from-date", a.from_date]
    if a.to_date:
        filt += ["--to-date", a.to_date]
    if a.album:
        filt += ["--album", a.album]
    if a.keyword:
        filt += ["--keyword", a.keyword]
    if a.favorite:
        filt.append("--favorite")
    if a.limit:
        filt += ["--limit", str(a.limit)]
    return filt


def global_lib_args(a):
    return ["--library", str(Path(a.library).expanduser())] if a.library else []


# ---------------------------------------------------------------- 子命令: doctor

def cmd_doctor(a):
    print("== mac-photos 环境自检 ==\n")
    ok = True

    print("[1/5] osxphotos")
    if Path(OSXPHOTOS).exists():
        ver = subprocess.run([OSXPHOTOS, "--version"], capture_output=True, text=True).stdout.splitlines()[0]
        print(f"  ✅ {ver.strip()}")
    else:
        ok = False
        print(f"  ❌ 未找到: {OSXPHOTOS}\n     {SETUP_HINT}")

    print("[2/5] 照片图库读取权限（完全磁盘访问）")
    lib = Path(a.library).expanduser() if a.library else DEFAULT_LIB
    if not lib.exists():
        ok = False
        print(f"  ❌ 照片库不存在: {lib}（用 --library 指定实际路径）")
    else:
        try:
            db = f"file:{lib}/database/photos.db?mode=ro&immutable=1"
            n = sqlite3.connect(db, uri=True).execute("SELECT COUNT(*) FROM ZASSET").fetchone()[0]
            print(f"  ✅ 可读, 图库共 {n} 条资产记录")
        except sqlite3.Error as e:
            ok = False
            print(f"  ❌ 无法读取照片库: {e}\n     {FDA_HINT}")

    print("[3/5] ocr-vision（Vision OCR 工具）")
    if OCR_BIN.exists():
        print(f"  ✅ {OCR_BIN}")
    else:
        ok = False
        print(f"  ❌ 未找到, {SETUP_HINT}")

    print("[4/5] OCR 识别冒烟测试")
    if OCR_BIN.exists() and MKTEXT_BIN.exists():
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "smoke.png"
            r = subprocess.run([str(MKTEXT_BIN), str(img), SMOKE_TEXT], capture_output=True, text=True)
            if r.returncode == 0:
                out = subprocess.run([str(OCR_BIN), str(img)], capture_output=True, text=True)
                text = ""
                if out.stdout.strip():
                    try:
                        text = json.loads(out.stdout.splitlines()[0]).get("text", "")
                    except json.JSONDecodeError:
                        pass
                normalized = text.replace(" ", "")
                if "违约金" in normalized and "50000" in normalized:
                    print("  ✅ 中文识别正常")
                else:
                    ok = False
                    print(f"  ❌ 识别结果异常: {text[:80]!r}")
            else:
                ok = False
                print(f"  ❌ 测试图生成失败: {r.stderr[:120]}")
    else:
        ok = False
        print("  ⏭️  跳过（依赖 [3/5]）")

    print("[5/5] 本地索引")
    ws = ws_path(a.workspace)
    n = len(load_index(ws))
    print(f"  {'✅' if n else 'ℹ️ '} 工作区 {ws}, 已索引 {n} 张（无索引时先运行 scan）")

    print()
    print("结论: " + ("✅ 全部就绪" if ok else "❌ 有未通过项, 按上面提示处理后重试"))
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------- 子命令: scan

def cmd_scan(a):
    ws = ensure_ws(ws_path(a.workspace))
    filt = build_filters(a)

    print(f"① 查询图库元数据（{'全部类型' if a.all_types else '仅截图'}"
          + (f", {a.from_date} 起" if a.from_date else "")
          + (f", 至 {a.to_date}" if a.to_date else "") + "）…")
    proc = run_osxphotos(global_lib_args(a) + ["query", "--json"] + filt)
    try:
        photos = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        die("osxphotos query --json 输出无法解析", (proc.stderr or "")[-400:])
    if not photos:
        print("  ⚠️  条件下没有匹配照片; 可尝试加 --all-types 或放宽日期范围")
        return
    meta = {p.get("uuid"): p for p in photos}
    print(f"  匹配 {len(meta)} 张")

    print("② 导出到工作区（增量, 含 iCloud 补下载）…")
    run_osxphotos(
        global_lib_args(a)
        + ["export", str(ws / "exports"), "--download-missing", "--update",
           "--filename", "{uuid}_{original_filename}"]
        + filt,
        check=False,
    )

    print("③ OCR 识别新导出的图片…")
    existing = load_index(ws)
    exported = sorted(p for p in (ws / "exports").iterdir() if p.is_file())
    keep, pending = [], []
    for f in exported:
        uuid = f.name.split("_", 1)[0]
        rec = existing.get(uuid)
        if rec and rec.get("file") == f.name and rec.get("size") == f.stat().st_size:
            keep.append(rec)  # 已索引且未变化, 跳过 OCR
            continue
        pending.append((uuid, str(f), (meta.get(uuid) or {}).get("date", "")))
    if not pending:
        print(f"  无新增（{len(keep)} 张均已在索引中）")
    else:
        errors = 0
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for rec, err in ex.map(ocr_one, pending):
                keep.append(rec)
                if err:
                    errors += 1
                    eprint(f"  ⚠️  {rec['file']}: {err}")
        print(f"  新识别 {len(pending) - errors} 张, 失败 {errors} 张")

    write_index(ws, keep)
    total = len(keep)
    print(f"✅ 完成: 索引共 {total} 张 → {index_file(ws)}")
    print(f"   搜索示例: python3 {Path(__file__).name} search 违约金")


# ---------------------------------------------------------------- 子命令: search / list / export / stats

def match_records(records, terms, or_mode):
    terms = [t.lower() for t in terms]
    hits = []
    for r in records:
        t = r.get("text", "").lower()
        ok = any(x in t for x in terms) if or_mode else all(x in t for x in terms)
        if ok:
            hits.append(r)
    return hits


def cmd_search(a):
    ws = ws_path(a.workspace)
    records = list(load_index(ws).values())
    if not records:
        die("索引为空, 请先运行 scan", f"示例: python3 {Path(__file__).name} scan")
    hits = sorted(match_records(records, a.terms, a.or_), key=lambda r: r.get("date") or "", reverse=True)
    if not hits:
        print(f"未命中（{len(records)} 张已索引）")
        return
    shown = hits[: a.limit]
    print(f"命中 {len(hits)} 张, 显示 {len(shown)} 张:\n")
    for r in shown:
        print(f"  📅 {r.get('date', '?')[:19]}  {r.get('file', '?')}")
        print(f"     {context_of(r.get('text', ''), a.terms[0])}")
        print(f"     {ws / 'exports' / r.get('file', '')}\n")
    if a.json:
        print(json.dumps(shown, ensure_ascii=False, indent=2))
    if a.reveal:
        for r in shown[: a.limit]:
            subprocess.run(["open", "-R", str(ws / "exports" / r.get("file", ""))])
    if a.open:
        for r in shown:
            subprocess.Popen(["qlmanage", "-p", str(ws / "exports" / r.get("file", ""))],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_list(a):
    records = sorted(load_index(ws_path(a.workspace)).values(), key=lambda r: r.get("date") or "", reverse=True)
    for r in records[: a.limit]:
        first_line = (r.get("text", "").splitlines() or [""])[0][:60]
        print(f"  {r.get('date', '?')[:19]}  {r.get('file', '?'):40s}  {first_line}")
    print(f"共 {len(records)} 张")


def cmd_export(a):
    ws = ws_path(a.workspace)
    records = load_index(ws)
    if a.uuid:
        hits = [records[u] for u in a.uuid if u in records]
        missing = [u for u in a.uuid if u not in records]
        if missing:
            eprint(f"⚠️  索引中无这些 uuid: {missing}")
    else:
        if not a.terms:
            die("请提供搜索词或 --uuid")
        hits = match_records(list(records.values()), a.terms, a.or_)
    if not hits:
        die("没有命中的照片")
    dest = Path(a.dest).expanduser() if a.dest else Path.cwd() / "photos-export"
    dest.mkdir(parents=True, exist_ok=True)
    for r in hits:
        src = ws / "exports" / r.get("file", "")
        if src.exists():
            shutil.copy2(src, dest / src.name)
        else:
            eprint(f"⚠️  文件缺失: {src}")
    print(f"✅ 已复制 {len(hits)} 张 → {dest}")


def cmd_stats(a):
    records = list(load_index(ws_path(a.workspace)).values())
    if not records:
        print("索引为空, 请先运行 scan")
        return
    dates = [r.get("date", "")[:10] for r in records if r.get("date")]
    print(f"已索引: {len(records)} 张")
    print(f"日期范围: {min(dates)} ~ {max(dates)}")
    with_text = sum(1 for r in records if r.get("text", "").strip())
    print(f"含文字: {with_text} 张（其余为无文字截图/照片）")


# ---------------------------------------------------------------- 入口

def main():
    ap = argparse.ArgumentParser(
        prog="photos_read.py",
        description="读取 Mac 照片图库: 筛选截图 → OCR 索引 → 内容搜索 → 导出",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--workspace", help=f"工作区目录（默认 {DEFAULT_WS}）")
        p.add_argument("--library", help="照片库路径（默认系统照片库）")

    p = sub.add_parser("doctor", help="环境自检: 依赖/权限/OCR 链路")
    common(p)
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("scan", help="从图库导出并 OCR 建索引（默认仅截图）")
    common(p)
    p.add_argument("--all-types", action="store_true", help="扫描全部类型（默认仅截图）")
    p.add_argument("--from-date", help="起始日期 YYYY-MM-DD")
    p.add_argument("--to-date", help="截止日期 YYYY-MM-DD")
    p.add_argument("--album", help="按相簿名筛选")
    p.add_argument("--keyword", help="按关键词筛选")
    p.add_argument("--favorite", action="store_true", help="仅收藏")
    p.add_argument("--limit", type=int, help="最多处理 N 张（配合增量, 可分批扫）")
    p.add_argument("--workers", type=int, default=4, help="OCR 并发数（默认 4）")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("search", help="按 OCR 内容搜索（多个词默认同时出现）")
    common(p)
    p.add_argument("terms", nargs="+", help="搜索词")
    p.add_argument("--or", dest="or_", action="store_true", help="任一词命中即可")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true", help="附 JSON 输出")
    p.add_argument("--reveal", action="store_true", help="在 Finder 中显示命中文件")
    p.add_argument("--open", action="store_true", help="QuickLook 预览命中文件")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("list", help="浏览索引")
    common(p)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("export", help="把命中照片复制到指定目录保存")
    common(p)
    p.add_argument("terms", nargs="*", help="搜索词（或用 --uuid）")
    p.add_argument("--or", dest="or_", action="store_true")
    p.add_argument("--uuid", nargs="+", help="按 uuid 导出")
    p.add_argument("--dest", help="目标目录（默认 ./photos-export）")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("stats", help="索引统计")
    common(p)
    p.set_defaults(fn=cmd_stats)

    a = ap.parse_args()
    if hasattr(a, "fn"):
        a.fn(a)


if __name__ == "__main__":
    main()
