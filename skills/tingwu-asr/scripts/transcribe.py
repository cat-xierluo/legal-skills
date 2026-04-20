#!/usr/bin/env python3
"""tingwu-asr CLI 入口 — 上传音频/视频到通义听悟进行云端转录"""

import argparse
import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

SKILL_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tingwu import TingwuClient, LANG_MAP
from format_output import result_to_markdown, lab_to_markdown, save_archive

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".wma", ".aac", ".ogg", ".amr", ".flac", ".aiff",
              ".mp4", ".wmv", ".m4v", ".flv", ".rmvb", ".dat", ".mov", ".mkv", ".webm", ".avi",
              ".mpeg", ".3gp"}


def main():
    parser = argparse.ArgumentParser(description="通义听悟云端语音转写")
    parser.add_argument("paths", nargs="*", help="音频/视频文件路径（支持多个文件并行转录）")
    parser.add_argument("-o", "--output", help="输出 Markdown 文件路径（单文件模式）")
    parser.add_argument("--lang", default="cn", help="语言: cn/en/ja/cant/cn_en (默认: cn)")
    parser.add_argument("--speakers", type=int, default=4,
                        help="说话人数: 0=不区分, 1=单人, 2=两人, 4=多人 (默认: 4)")
    parser.add_argument("--batch", action="store_true", help="批量转录目录下所有音视频文件")
    parser.add_argument("--check-auth", action="store_true", help="检查登录状态")
    parser.add_argument("--cookie", help="Cookie 文件路径 (默认: config/cookies.json)")
    parser.add_argument("--poll-interval", type=int, default=10, help="轮询间隔秒数 (默认: 10)")
    parser.add_argument("--poll-timeout", type=int, default=3600, help="轮询超时秒数 (默认: 3600)")
    parser.add_argument("--no-archive", action="store_true", help="不保存归档")
    parser.add_argument("--no-lab", action="store_true", help="不获取智能分析（关键词/议程/重点等）")
    parser.add_argument("--ppt", action="store_true", help="下载 PPT 幻灯片图片并嵌入 Markdown（仅视频有效）")
    parser.add_argument("--async", action="store_true", help="异步模式：上传后立即返回，用 poll_tasks.py 查询结果")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON 结果")
    parser.add_argument("--parallel", type=int, default=3, help="并行转录的最大文件数 (默认: 3)")

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
        "output_path": str(Path(args.output).resolve()) if args.output else None,
        "ppt": args.ppt,
        "no_lab": args.no_lab,
        "no_archive": args.no_archive,
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


def _transcribe_one(client, file_path, args, lang, verbose=True):
    """
    转录单个文件，结果同时保存到文件所在目录和 archive 目录

    Args:
        client: TingwuClient 实例
        file_path: 文件路径
        args: 命令行参数
        lang: 语言代码
        verbose: 是否打印详细信息

    Returns:
        包含所有输出路径的结果字典
    """
    result = client.transcribe(
        file_path,
        lang=lang,
        role_split_num=args.speakers,
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

    # 获取 PPT 幻灯片（如果启用）
    ppt_slides = None
    if args.ppt:
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
                downloaded = client.download_ppt_images(ppt_slides, out_dir)
                if verbose:
                    print(f"[{file_path.name}] 已下载 {len(downloaded)} 张幻灯片图片到 {out_dir / 'slides'}")
        except Exception as e:
            if verbose:
                print(f"[{file_path.name}] 获取 PPT 失败: {e}")
            ppt_slides = None

    md = result_to_markdown(
        trans_result.get("result", "{}"),
        file_path.name,
        duration=trans_result.get("duration"),
        word_count=trans_result.get("wordCount"),
        max_speakers=args.speakers,
        ppt_slides=ppt_slides,
    )

    # 1. 保存到文件所在目录
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

    if verbose:
        print(f"[{file_path.name}] 时长: {trans_result.get('duration', 'N/A')}秒 | 字数: {trans_result.get('wordCount', 'N/A')}")

    return {"result": result, "output_paths": output_paths}


if __name__ == "__main__":
    main()
