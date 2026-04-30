#!/usr/bin/env python3
"""tingwu-asr CLI 入口 — 上传音频/视频到通义听悟进行云端转录"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

SKILL_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tingwu import TingwuClient, LANG_MAP, VIDEO_EXTS
from format_output import result_to_markdown, lab_to_markdown, save_archive

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".wma", ".aac", ".ogg", ".amr", ".flac", ".aiff",
              ".mp4", ".wmv", ".m4v", ".flv", ".rmvb", ".dat", ".mov", ".mkv", ".webm", ".avi",
              ".mpeg", ".3gp"}


def _load_task_history():
    """加载 completed_tasks.json + pending_tasks.json，用于去重检查"""
    history = []
    for fname in ("completed_tasks.json", "pending_tasks.json"):
        fpath = SKILL_ROOT / "config" / fname
        if fpath.exists():
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    history.extend(data)
            except (json.JSONDecodeError, OSError):
                pass
    return history


def _find_duplicate(file_path, history):
    """检查文件是否已有转录记录（已完成或进行中）。
    返回最近一条匹配记录，不检查本地输出文件是否存在。
    """
    resolved = str(file_path.resolve())
    for task in reversed(history):
        if task.get("file_path") != resolved:
            continue
        status = task.get("status")
        if status in ("completed", "pending", "transcribing"):
            return task
    return None


def main():
    parser = argparse.ArgumentParser(description="通义听悟云端语音转写")
    parser.add_argument("paths", nargs="*", help="音频/视频文件路径（支持多个文件并行转录）")
    parser.add_argument("-o", "--output", help="输出 Markdown 文件路径（单文件模式）")
    parser.add_argument("--lang", default="cn", help="语言: cn/en/ja/cant/cn_en (默认: cn)")
    parser.add_argument("--speakers", type=int, default=2,
                        help="说话人数: 0=不区分, 1=单人, 2=两人(默认), 4=多人")
    parser.add_argument("--batch", action="store_true", help="批量转录目录下所有音视频文件")
    parser.add_argument("--check-auth", action="store_true", help="检查登录状态")
    parser.add_argument("--cookie", help="Cookie 文件路径 (默认: config/cookies.json)")
    parser.add_argument("--poll-interval", type=int, default=10, help="轮询间隔秒数 (默认: 10)")
    parser.add_argument("--poll-timeout", type=int, default=3600, help="轮询超时秒数 (默认: 3600)")
    parser.add_argument("--no-archive", action="store_true", help="不保存归档")
    parser.add_argument("--no-lab", action="store_true", help="不获取智能分析（关键词/议程/重点等）")
    parser.add_argument("--no-summary", action="store_true", help="不自动生成 AI 总结")
    parser.add_argument("--ppt", action="store_true", help="下载 PPT 幻灯片图片并嵌入 Markdown（仅视频有效）")
    parser.add_argument("--async", action="store_true", help="异步模式：上传后立即返回，用 poll_tasks.py 查询结果")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON 结果")
    parser.add_argument("--parallel", type=int, default=3, help="并行转录的最大文件数 (默认: 3)")
    parser.add_argument("--force", action="store_true", help="强制重新上传，即使已有转录结果")

    args = parser.parse_args()

    try:
        client = TingwuClient(cookie_path=args.cookie)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)

    if args.check_auth:
        auth = client.check_auth()
        if auth["valid"]:
            print("登录状态: 有效")
            print(json.dumps(auth["user"], ensure_ascii=False, indent=2))
        else:
            print(f"登录状态: 无效 — {auth['error']}")
            print("请运行: python3 scripts/login.py")
            sys.exit(1)
        return

    if not args.paths:
        parser.print_help()
        sys.exit(1)

    lang = LANG_MAP.get(args.lang, args.lang)

    # 收集所有文件
    all_files = []
    for path_str in args.paths:
        target = Path(path_str)
        if args.batch and target.is_dir():
            files = [f for f in sorted(target.iterdir())
                     if f.suffix.lower() in AUDIO_EXTS]
            all_files.extend(files)
        else:
            if not target.exists():
                print(f"文件不存在: {target}")
                continue
            all_files.append(target)

    if not all_files:
        print("没有找到音视频文件")
        sys.exit(1)

    # 去重检查：跳过已转录或正在转录的文件；本地输出缺失时从云端重新下载
    if not args.force:
        history = _load_task_history()
        deduped = []
        redownload = []
        for f in all_files:
            dup = _find_duplicate(f, history)
            if not dup:
                deduped.append(f)
                continue
            dup_status = dup.get("status")
            if dup_status in ("pending", "transcribing"):
                tid = dup.get("trans_id", "?")
                print(f"  跳过 {f.name} — 正在转录中 (任务 {tid})")
            elif dup_status == "completed":
                local_output = dup.get("result", {}).get("output_path")
                if local_output and Path(local_output).exists():
                    prev_spk = dup.get("role_split_num", "?")
                    print(f"  跳过 {f.name} — 已有转录结果")
                    if prev_spk != args.speakers:
                        print(f"    (上次说话人={prev_spk}, 本次={args.speakers} — 如需重转请加 --force)")
                    else:
                        print(f"    输出: {local_output}")
                else:
                    redownload.append((f, dup))
        # 从云端重新下载（不重新上传）
        for f, task in redownload:
            prev_spk = task.get("role_split_num", "?")
            print(f"  {f.name} — 云端已有结果，直接下载...")
            if prev_spk != args.speakers:
                print(f"    (云端说话人={prev_spk}, 本次={args.speakers}，如需新参数请加 --force)")
            try:
                _transcribe_one(client, f, args, lang, existing_task=task)
            except Exception as e:
                print(f"  云端下载失败 ({e})，将重新上传")
                deduped.append(f)
        skipped = len(all_files) - len(deduped) - len(redownload)
        if skipped > 0 or redownload:
            print(f"\n去重: 跳过 {skipped} 个，云端下载 {len(redownload)} 个，剩余 {len(deduped)} 个待上传")
        if not deduped and not redownload:
            print("所有文件均已处理完成，无需重复操作。")
            return
        all_files = deduped
        if not all_files:
            return

    # 异步模式不支持并行
    if getattr(args, 'async'):
        for file_path in all_files:
            _submit_async(client, file_path, args, lang)
        return

    # 并行转录
    if len(all_files) > 1:
        print(f"找到 {len(all_files)} 个文件，开始并行转录（最大并发数: {args.parallel}）...")
        _transcribe_parallel(client, all_files, args, lang)
    else:
        _transcribe_one(client, all_files[0], args, lang)


def _submit_async(client, file_path, args, lang):
    """异步模式：上传并提交转录，保存任务到 pending_tasks.json"""
    from datetime import datetime

    task = client.submit_transcribe(file_path, lang=lang, role_split_num=args.speakers)

    pending_path = SKILL_ROOT / "config" / "pending_tasks.json"
    if pending_path.exists():
        tasks = json.loads(pending_path.read_text(encoding="utf-8"))
    else:
        tasks = []

    entry = {
        "trans_id": task["trans_id"],
        "file_path": str(file_path.resolve()),
        "file_name": task["file_name"],
        "lang": task["lang"],
        "role_split_num": task["role_split_num"],
        "output_path": str(file_path.with_suffix(".md").resolve()),
        "ppt": args.ppt or file_path.suffix.lower() in VIDEO_EXTS,
        "no_lab": args.no_lab,
        "no_archive": args.no_archive,
        "no_summary": args.no_summary,
        "submitted_at": datetime.now().isoformat(),
        "status": "pending",
    }
    tasks.append(entry)
    pending_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n异步任务已提交: {task['trans_id']}")
    print(f"任务已保存到: {pending_path}")
    print(f"查询状态: python3 scripts/poll_tasks.py")
    print(f"后台监控: python3 scripts/poll_tasks.py --monitor")


def _transcribe_parallel(client, files, args, lang):
    """并行转录多个文件"""
    results = []

    def transcribe_single(file_path):
        try:
            result = _transcribe_one(client, file_path, args, lang, verbose=False)
            return {"success": True, "file": file_path, "result": result}
        except Exception as e:
            return {"success": False, "file": file_path, "error": str(e)}

    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {executor.submit(transcribe_single, f): f for f in files}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            file_path = result["file"]
            if result["success"]:
                print(f"\n完成: {file_path.name}")
                for out_path in result["result"].get("output_paths", []):
                    print(f"  → {out_path}")
            else:
                print(f"\n失败: {file_path.name} - {result['error']}")

    # 汇总
    success_count = sum(1 for r in results if r["success"])
    print(f"\n{'='*50}")
    print(f"并行转录完成: {success_count}/{len(results)} 成功")

    return results


def _transcribe_one(client, file_path, args, lang, verbose=True, existing_task=None):
    """
    转录单个文件，结果同时保存到文件所在目录和 archive 目录

    Args:
        client: TingwuClient 实例
        file_path: 文件路径
        args: 命令行参数
        lang: 语言代码
        verbose: 是否打印详细信息
        existing_task: 已有的任务记录（从云端重新下载时传入，跳过上传）

    Returns:
        包含所有输出路径的结果字典
    """
    if existing_task:
        # 从云端重新下载已有结果，不重新上传
        trans_id = existing_task["trans_id"]
        speakers = existing_task.get("role_split_num", args.speakers)
        if verbose:
            print(f"[{file_path.name}] 从云端获取已有转录结果 (任务 {trans_id})...")
        trans_result = client.get_trans_result(trans_id)
        result = {
            "trans_id": trans_id,
            "task_info": None,
            "result": trans_result,
            "duration": trans_result.get("duration"),
            "word_count": trans_result.get("wordCount"),
        }
    else:
        speakers = args.speakers
        result = client.transcribe(
            file_path,
            lang=lang,
            role_split_num=speakers,
            poll_interval=args.poll_interval,
            poll_timeout=args.poll_timeout,
        )

    # JSON 模式下直接输出并返回
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return {"result": result, "output_paths": []}

    trans_result = result["result"]

    if verbose:
        print(f"[{file_path.name}] 获取 PPT 幻灯片...")

    # 获取 PPT 幻灯片（视频自动启用，音频需手动 --ppt）
    ppt_slides = None
    slides_ext = ".png"
    is_video = file_path.suffix.lower() in VIDEO_EXTS
    if is_video or args.ppt:
        try:
            ppt_slides = client.get_ppt_info(result["trans_id"])
            if not ppt_slides:
                if verbose:
                    print(f"[{file_path.name}] 未检测到 PPT 幻灯片")
                ppt_slides = None
            else:
                if verbose:
                    print(f"[{file_path.name}] 找到 {len(ppt_slides)} 张幻灯片")
                out_dir = file_path.parent
                downloaded = client.download_ppt_images(ppt_slides, out_dir, file_stem=file_path.stem)
                slides_subdir = f"{file_path.stem}_slides"
                slides_ext = client.compress_slides(out_dir / slides_subdir)
                if verbose:
                    print(f"[{file_path.name}] 已下载 {len(downloaded)} 张幻灯片图片到 {out_dir / slides_subdir}")
        except Exception as e:
            if verbose:
                print(f"[{file_path.name}] 获取 PPT 失败: {e}")
            ppt_slides = None

    md = result_to_markdown(
        trans_result.get("result", "{}"),
        file_path.name,
        duration=trans_result.get("duration"),
        word_count=trans_result.get("wordCount"),
        max_speakers=speakers,
        ppt_slides=ppt_slides,
        slides_dir_name=f"{file_path.stem}_slides" if ppt_slides else "slides",
        slides_ext=slides_ext,
    )

    # 1. 保存到文件所在目录（支持 --output 参数）
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = file_path.with_suffix(".md")
    out_path.write_text(md, encoding="utf-8")
    if verbose:
        print(f"[{file_path.name}] 转录完成: {out_path}")

    # 2. 获取智能分析并追加
    if not args.no_lab:
        try:
            if verbose:
                print(f"[{file_path.name}] 获取智能分析...")
            lab_data = client.get_lab_info(result["trans_id"])
            lab_md = lab_to_markdown(lab_data)
            if lab_md:
                md += lab_md
                out_path.write_text(md, encoding="utf-8")
                if verbose:
                    print(f"[{file_path.name}] 智能分析已追加到: {out_path}")
        except Exception as e:
            if verbose:
                print(f"[{file_path.name}] 获取智能分析失败: {e}")

    # 3. 保存到 archive 目录
    output_paths = [str(out_path)]
    if not args.no_archive:
        archive_root = SKILL_ROOT / "archive"
        md_path, archive_dir = save_archive(
            file_path, md, result["trans_id"], trans_result, archive_root
        )
        if verbose:
            print(f"[{file_path.name}] 已归档: {archive_dir}")
        output_paths.append(str(md_path))

    # 4. 自动 AI 总结（除非指定 --no-summary）
    if not getattr(args, "no_summary", False):
        try:
            summary_py = SKILL_ROOT.parent / "funasr-transcribe" / "scripts" / "summary.py"
            if summary_py.exists():
                if verbose:
                    print(f"[{file_path.name}] 生成 AI 总结...")
                subprocess.run(
                    [
                        "python3", str(summary_py), "inject",
                        str(out_path), str(out_path.with_suffix(".json")),
                    ],
                    check=False, timeout=120,
                )
                if verbose:
                    print(f"[{file_path.name}] AI 总结已生成")
        except Exception as e:
            if verbose:
                print(f"[{file_path.name}] AI 总结失败: {e}")

    if verbose:
        print(f"[{file_path.name}] 时长: {trans_result.get('duration', 'N/A')}秒 | 字数: {trans_result.get('wordCount', 'N/A')}")

    return {"result": result, "output_paths": output_paths}


if __name__ == "__main__":
    main()
