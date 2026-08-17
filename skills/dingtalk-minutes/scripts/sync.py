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
    python sync.py --no-mirror     # 本次只存档，不自动镜像到外部文件夹

自动镜像: 本次有新增存档且 config/mirror-target.local.json 存在时，
同步完成后自动调用同目录 mirror_output.py（增量 sha256，顺带补齐之前
未镜像成功的文件）；未配置镜像目标时跳过并提示，不影响存档结果。

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
        # NDJSON（如 keywords 接口逐行返回）→ 透传原始文本，由调用方逐行解析
        return {"_raw": proc.stdout}


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


def auto_mirror(archive_dir: Path) -> None:
    """同步后自动镜像到外部文件夹（调用同目录 mirror_output.py，增量 sha256）。

    - 镜像是副本操作，失败/未配置只提示，不影响已完成的存档（archive 是权威源）。
    - mirror_output.py 退出码 2 = 未配置镜像目标 → 静默降级为提示跳过。
    """
    mirror_script = _scripts_dir / "mirror_output.py"
    if not mirror_script.exists():
        print("⚠️ 未找到 mirror_output.py，跳过自动镜像。", file=sys.stderr)
        return
    print("\n🪞 自动镜像到外部文件夹 …", flush=True)
    proc = subprocess.run(
        [sys.executable, str(mirror_script), "--archive-dir", str(archive_dir)]
    )
    if proc.returncode == 2:
        print("ℹ️ 未配置镜像目标（config/mirror-target.local.json 缺失），跳过自动镜像；存档不受影响。")
    elif proc.returncode != 0:
        print(f"⚠️ 自动镜像失败（退出码 {proc.returncode}），存档已完成；可稍后单独运行 mirror_output.py 重试。", file=sys.stderr)


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
    """拉取单条听记的附属内容。keywords 接口返回 NDJSON（多行 JSON），需逐行解析。"""
    if sub == "keywords":
        # keywords 是 NDJSON：每行一个 {"keywords":[...]}
        out = run_dws(
            ["minutes", "get", sub, "--id", uuid, "--format", "json"], dry_run=dry_run
        )
        if out is None:
            return None
        text = out.get("_raw") if isinstance(out, dict) and out.get("_raw") else ""
        if text:
            kws: List[str] = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    kws.extend(obj.get("keywords", []))
                except Exception:
                    pass
            return {"keywords": kws}
        # 兜底：尝试标准 JSON
        return out.get("result") if isinstance(out, dict) else None
    data = run_dws(
        ["minutes", "get", sub, "--id", uuid, "--format", "json"], dry_run=dry_run
    )
    return data.get("result") if data else None


def _todos_to_lines(todos: Any) -> List[str]:
    """把 get todos 的 result 转成可读待办行。"""
    if isinstance(todos, dict):
        lines: List[str] = []
        actions = todos.get("actions") or []
        for a in actions:
            if isinstance(a, str):
                try:
                    a = json.loads(a)
                except Exception:
                    lines.append(f"- {a}")
                    continue
            if isinstance(a, dict) and a.get("value"):
                lines.append(f"- {a['value']}")
        if not lines and todos.get("dingtalkTodoList"):
            for t in todos["dingtalkTodoList"]:
                if isinstance(t, dict):
                    lines.append(f"- {t.get('title', '')}")
        return lines
    if isinstance(todos, list):
        return [f"- {t}" for t in todos]
    return [str(todos)]


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
    ap.add_argument("--with-audio", action="store_true", help="同时下载原始音频 mp3 到 archive（默认不下载，单条约 150MB）")
    ap.add_argument("--no-mirror", action="store_true", help="本次只存档，不自动镜像到外部文件夹（默认有新增时自动镜像）")
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

        # 1) 元数据（结构化，不含大段文本）
        summary = get_extra(uuid, "summary", args.dry_run)
        todos = get_extra(uuid, "todos", args.dry_run)
        keywords = get_extra(uuid, "keywords", args.dry_run)
        audio = get_extra(uuid, "audio", args.dry_run)
        meta = {
            "uuid": uuid,
            "title": it.get("title"),
            "startTimeISO": it.get("startTimeISO"),
            "endTimeISO": it.get("endTimeISO"),
            "durationMicros": it.get("durationMicros"),
            "shareUrl": it.get("shareUrl"),
            "creator": (it.get("flashUserInfo") or {}).get("name"),
            "keywords": (keywords or {}).get("keywords") if isinstance(keywords, dict) else keywords,
            "audio": {
                "videoUrl": (audio or {}).get("videoUrl"),
                "audioUrl": (audio or {}).get("audioUrl"),
                "size": (audio or {}).get("size"),
                "duration": (audio or {}).get("duration"),
                "filtered": (audio or {}).get("filtered"),
                "note": "URL 带过期鉴权，需重新执行 `dws minutes get audio` 获取有效地址；如需本地留底音频请加 --with-audio 下载",
            },
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        (rec_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 2) 逐字稿（含概览头）
        paras = get_transcription(uuid, dry_run=args.dry_run)
        md = f"# {it.get('title', '')}\n\n"
        md += f"> 开始时间: {it.get('startTimeISO')}  \n"
        md += f"> 分享链接: {it.get('shareUrl')}  \n"
        if meta.get("creator"):
            md += f"> 创建人: {meta['creator']}  \n"
        md += "\n---\n\n"

        # 概览：关键词 / AI 摘要 / 待办（来自 get 详细接口，比列表版完整）
        kw_list = meta.get("keywords") or []
        if kw_list:
            md += f"## 关键词\n\n{', '.join(kw_list)}\n\n"
        if isinstance(summary, dict) and summary.get("fullSummary"):
            md += f"## AI 摘要\n\n{summary['fullSummary']}\n\n"
        if todos:
            md += "## 待办事项\n\n"
            md += "\n".join(_todos_to_lines(todos)) + "\n\n"

        md += "---\n\n## 逐字稿\n\n"
        md += "\n\n".join(paras)
        (rec_dir / "transcript.md").write_text(md, encoding="utf-8")

        # 3) 拆分独立文件（信息越全越好，便于单独检索）
        if isinstance(summary, dict) and summary.get("fullSummary"):
            (rec_dir / "summary.md").write_text(
                f"# {it.get('title', '')} — AI 摘要\n\n{summary['fullSummary']}", encoding="utf-8"
            )
        if keywords:
            kw = meta.get("keywords") or []
            (rec_dir / "keywords.md").write_text(
                f"# {it.get('title', '')} — 关键词\n\n"
                + ("\n".join(f"- {k}" for k in kw) if kw else str(keywords)),
                encoding="utf-8",
            )
        if todos:
            tlines = "\n".join(_todos_to_lines(todos))
            (rec_dir / "todos.md").write_text(
                f"# {it.get('title', '')} — 待办事项\n\n{tlines}", encoding="utf-8"
            )

        # 4) 可选：下载原始音频（URL 带过期鉴权，下载后才真正留底）
        if args.with_audio:
            url = (audio or {}).get("videoUrl") or (audio or {}).get("audioUrl")
            if url:
                import urllib.request

                aud_path = rec_dir / "audio.mp3"
                try:
                    urllib.request.urlretrieve(url, aud_path)
                    print(f"   🎵 已下载音频: {aud_path.name}")
                except Exception as e:
                    print(f"   [audio error] {e}", file=sys.stderr)

        synced.add(uuid)
        extra = " + summary/keywords/todos/audio元数据" if not args.dry_run else ""
        print(f"   ✅ 已存档: {it.get('title')}  ({len(paras)} 段{extra})")

    if not args.dry_run:
        index["last_sync"] = max_time or last_sync
        index["synced_uuids"] = sorted(synced)
        index["uuid_to_dir"] = uuid_to_dir
        index["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_index(archive_dir, index)
        print(f"\n📌 同步完成。last_sync 更新为: {index['last_sync']}")
        print(f"📁 已存档 {len(synced)} 条听记于: {archive_dir}")
        if not args.no_mirror:
            auto_mirror(archive_dir)
        else:
            print("ℹ️ --no-mirror：本次跳过自动镜像。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
