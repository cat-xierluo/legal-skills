#!/usr/bin/env python3
"""
钉钉 AI 听记 —— 本地归档 + 增量同步

将 dws 中的 AI 听记同步到本技能 archive/ 目录，仅拉取新增内容（增量）。
每条听记存为:
    archive/<YYMMDD>_<标题>/meta.json     # 列表元数据 + 摘要/关键词/待办
    archive/<YYMMDD>_<标题>/transcript.md # 语音转写逐字稿（已翻页拉全）
目录名格式：日期(YYMMDD，如 260508) + 下划线 + 听记标题（文件系统安全化）。

同步状态记录在:
    archive/index.json              # last_sync(上次同步时间) + synced_uuids(已同步集合) + uuid_to_dir(uuid→目录名映射)

增量原理: 用 index.json 里的 last_sync 作为 dws `minutes list all --start` 的参数，
          服务端只返回该时间之后的听记；本地已存在的 uuid 跳过，避免重复拉取。
          目录名虽可读化，但去重与增量判定仍以 uuid 为准，通过 uuid_to_dir 回溯目录。

用法:
    python sync.py                  # 增量同步（默认 archive/ 相对 skill 根）
    python sync.py --archive-dir /path/to/archive
    python sync.py --full          # 忽略 last_sync，全量重扫（仍跳过已存在的 uuid）
    python sync.py --dry-run       # 预览将同步哪些，不写文件
    python sync.py --list-new      # 只输出本次新增的标题清单，不拉逐字稿

依赖: dws CLI (PATH 中可执行)，Python 标准库。
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Any, Optional, Dict

# 尝试复用同目录的列表解析辅助（若存在）
_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
try:
    from minutes_list_parse import parse_list_payload
except Exception:
    parse_list_payload = None


def run_dws(args: List[str], dry_run: bool = False) -> Optional[Any]:
    cmd = ["dws"] + args
    if dry_run:
        print(f"  [dry-run] {' '.join(cmd)}")
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print(f"  [timeout] {' '.join(cmd)}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(f"  [dws error] {proc.stderr.strip()}", file=sys.stderr)
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"  [json error] raw: {proc.stdout[:200]}", file=sys.stderr)
        return None


def load_index(archive_dir: Path) -> Dict[str, Any]:
    idx_path = archive_dir / "index.json"
    if idx_path.exists():
        try:
            return json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_sync": None, "synced_uuids": [], "uuid_to_dir": {}, "updated_at": None}


def safe_dirname(title: str, date_yymmdd: str, uuid: str, uuid_to_dir: Dict[str, str], archive_dir: Path) -> str:
    """生成可读目录名：YYMMDD_标题，冲突时追加短 uuid 后缀。"""
    # 文件名安全化：去斜杠、控制字符，压缩空白
    clean = "".join(c if c.isalnum() or c in " _-（）()．." else "_" for c in (title or "(无标题)"))
    clean = clean.strip().strip("_")
    if not clean:
        clean = "(无标题)"
    base = f"{date_yymmdd}_{clean}"
    # 若 uuid 已有映射目录且仍存在，直接复用（保证增量回溯稳定）
    if uuid in uuid_to_dir:
        old = uuid_to_dir[uuid]
        if (archive_dir / old).exists():
            return old
    # 冲突检测：同名不同 uuid 时加短后缀
    cand = base
    if (archive_dir / cand).exists():
        # 检查该目录是否是同一个 uuid（通过 meta.json）
        meta_path = archive_dir / cand / "meta.json"
        same = False
        if meta_path.exists():
            try:
                if json.loads(meta_path.read_text(encoding="utf-8")).get("uuid") == uuid:
                    same = True
            except Exception:
                pass
        if not same:
            cand = f"{base}_{uuid[:6]}"
    return cand


def save_index(archive_dir: Path, index: Dict[str, Any]) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def list_minutes_since(start_iso: Optional[str], dry_run: bool) -> List[Dict[str, Any]]:
    """翻页拉取 list all，按 --start 过滤。返回 itemList 扁平列表。"""
    items: List[Dict[str, Any]] = []
    next_token: Optional[str] = None
    while True:
        args = ["minutes", "list", "all", "--format", "json", "--max", "50"]
        if start_iso:
            args += ["--start", start_iso]
        if next_token:
            args += ["--next-token", next_token]
        data = run_dws(args, dry_run=dry_run)
        if not data:
            break
        res = data.get("result", {})
        page_items = res.get("itemList", [])
        items.extend(page_items)
        next_token = res.get("nextToken")
        if not next_token or not res.get("hasMore"):
            break
    return items


def get_transcription(uuid: str, dry_run: bool) -> List[str]:
    """翻页拉取完整逐字稿，返回段落文本列表（含发言人前缀）。"""
    paras: List[str] = []
    cursor: Optional[str] = None
    while True:
        args = ["minutes", "get", "transcription", "--id", uuid, "--format", "json"]
        if cursor:
            args += ["--next-token", cursor]
        data = run_dws(args, dry_run=dry_run)
        if not data:
            break
        res = data.get("result", {})
        for p in res.get("paragraphList", []):
            sp = p.get("nickName") or p.get("speakerDisplay", {}).get("nickName", "?")
            paras.append(f"【{sp}】{p.get('paragraph', '')}")
        cursor = res.get("nextToken")
        if not cursor or not res.get("hasNext"):
            break
    return paras


def get_extra(uuid: str, sub: str, dry_run: bool) -> Optional[Any]:
    data = run_dws(
        ["minutes", "get", sub, "--id", uuid, "--format", "json"], dry_run=dry_run
    )
    return data.get("result") if data else None


def parse_iso(s: str) -> datetime:
    # 处理 +08:00 这样的偏移
    return datetime.fromisoformat(s)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="钉钉 AI 听记 本地归档/增量同步")
    ap.add_argument("--archive-dir", default=None, help="存档目录（默认 <skill根>/archive）")
    ap.add_argument("--full", action="store_true", help="忽略 last_sync，全量重扫")
    ap.add_argument("--list-new", action="store_true", help="只列新增标题，不拉逐字稿")
    ap.add_argument("--dry-run", action="store_true", help="预览，不写文件")
    args = ap.parse_args()

    skill_root = _scripts_dir.parent
    archive_dir = Path(args.archive_dir) if args.archive_dir else (skill_root / "archive")

    index = load_index(archive_dir)
    synced: set = set(index.get("synced_uuids", []))
    uuid_to_dir: Dict[str, str] = index.get("uuid_to_dir", {})
    last_sync = None if args.full else index.get("last_sync")

    print(f"存档目录: {archive_dir}")
    if last_sync:
        print(f"上次同步时间(last_sync): {last_sync}  → 仅拉取此后的新增")
    else:
        print("无 last_sync  → 全量扫描（已存在 uuid 仍会跳过）")

    items = list_minutes_since(last_sync, dry_run=args.dry_run)
    print(f"dws 返回听记条数: {len(items)}")

    new_uuids: List[Dict[str, Any]] = []
    max_time = last_sync
    for it in items:
        uuid = it.get("uuid")
        title = it.get("title", "(无标题)")
        start_iso = it.get("startTimeISO")
        if not uuid:
            continue
        if uuid in synced:
            continue  # 已同步，跳过
        new_uuids.append(it)
        if start_iso:
            try:
                if max_time is None or parse_iso(start_iso) > parse_iso(max_time):
                    max_time = start_iso
            except Exception:
                pass

    if not new_uuids:
        print("✅ 没有新增听记，本地存档已是最新。")
        if not args.dry_run:
            index["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_index(archive_dir, index)
        return 0

    print(f"🔄 本次新增 {len(new_uuids)} 条:")
    for it in new_uuids:
        print(f"   - {it.get('title')}  ({it.get('startTimeISO')})  [{it.get('uuid')}]")

    if args.list_new:
        print("(--list-new: 仅列出，未拉取逐字稿)")
        return 0

    # 落盘
    if not args.dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)

    for it in new_uuids:
        uuid = it["uuid"]
        if args.dry_run:
            print(f"  [dry-run] 将写入 archive/{uuid}/")
            continue
        # 目录名：YYMMDD_标题（可读化）
        start_iso = it.get("startTimeISO") or ""
        try:
            dt = parse_iso(start_iso)
            date_yymmdd = dt.strftime("%y%m%d")
        except Exception:
            date_yymmdd = "000000"
        dir_name = safe_dirname(it.get("title", "(无标题)"), date_yymmdd, uuid, uuid_to_dir, archive_dir)
        rec_dir = archive_dir / dir_name
        rec_dir.mkdir(parents=True, exist_ok=True)
        uuid_to_dir[uuid] = dir_name

        # 1) 元数据
        meta = {
            "uuid": uuid,
            "title": it.get("title"),
            "startTimeISO": it.get("startTimeISO"),
            "endTimeISO": it.get("endTimeISO"),
            "durationMicros": it.get("durationMicros"),
            "shareUrl": it.get("shareUrl"),
            "creator": (it.get("flashUserInfo") or {}).get("name"),
            "keywords": (it.get("keywordsInfo") or {}).get("keywords"),
            "summary": get_extra(uuid, "summary", args.dry_run),
            "todos": get_extra(uuid, "todos", args.dry_run),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        (rec_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 2) 逐字稿
        paras = get_transcription(uuid, dry_run=args.dry_run)
        md = f"# {it.get('title', '')}\n\n"
        md += f"> 开始时间: {it.get('startTimeISO')}  \n"
        md += f"> 分享链接: {it.get('shareUrl')}  \n\n---\n\n"
        md += "\n\n".join(paras)
        (rec_dir / "transcript.md").write_text(md, encoding="utf-8")

        synced.add(uuid)
        print(f"   ✅ 已存档: {it.get('title')}  ({len(paras)} 段)")

    if not args.dry_run:
        index["last_sync"] = max_time or last_sync
        index["synced_uuids"] = sorted(synced)
        index["uuid_to_dir"] = uuid_to_dir
        index["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_index(archive_dir, index)
        print(f"\n📌 同步完成。last_sync 更新为: {index['last_sync']}")
        print(f"📁 已存档 {len(synced)} 条听记于: {archive_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
