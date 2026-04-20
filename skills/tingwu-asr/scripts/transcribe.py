#!/usr/bin/env python3
"""tingwu-asr CLI 入口 — 上传音频/视频到通义听悟进行云端转录"""

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tingwu import TingwuClient, LANG_MAP
from format_output import result_to_markdown, lab_to_markdown, save_archive


def main():
    parser = argparse.ArgumentParser(description="通义听悟云端语音转写")
    parser.add_argument("path", nargs="?", help="音频/视频文件路径或目录（批量模式）")
    parser.add_argument("-o", "--output", help="输出 Markdown 文件路径")
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

    if not args.path:
        parser.print_help()
        sys.exit(1)

    lang = LANG_MAP.get(args.lang, args.lang)
    target = Path(args.path)

    if args.batch and target.is_dir():
        files = [f for f in sorted(target.iterdir())
                 if f.suffix.lower() in (AUDIO_EXTS := {".mp3", ".wav", ".m4a", ".wma", ".aac",
                                                         ".ogg", ".amr", ".flac", ".aiff",
                                                         ".mp4", ".wmv", ".m4v", ".flv", ".rmvb",
                                                         ".dat", ".mov", ".mkv", ".webm", ".avi",
                                                         ".mpeg", ".3gp"})]
        if not files:
            print(f"目录 {target} 中没有找到音视频文件")
            sys.exit(1)
        print(f"找到 {len(files)} 个文件，开始批量转录...")
        for f in files:
            print(f"\n{'='*50}")
            print(f"转录: {f.name}")
            try:
                _transcribe_one(client, f, args, lang)
            except Exception as e:
                print(f"失败: {e}")
    else:
        if not target.exists():
            print(f"文件不存在: {target}")
            sys.exit(1)
        if getattr(args, 'async'):
            _submit_async(client, target, args, lang)
        else:
            _transcribe_one(client, target, args, lang)


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


def _transcribe_one(client, file_path, args, lang):
    result = client.transcribe(
        file_path,
        lang=lang,
        role_split_num=args.speakers,
        poll_interval=args.poll_interval,
        poll_timeout=args.poll_timeout,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    trans_result = result["result"]

    # 获取 PPT 幻灯片（如果启用）
    ppt_slides = None
    if args.ppt:
        try:
            print("获取 PPT 幻灯片...")
            ppt_slides = client.get_ppt_info(result["trans_id"])
            if not ppt_slides:
                print("  未检测到 PPT 幻灯片")
                ppt_slides = None
            else:
                print(f"  找到 {len(ppt_slides)} 张幻灯片")
                if args.output:
                    out_dir = Path(args.output).parent
                else:
                    out_dir = file_path.parent
                downloaded = client.download_ppt_images(ppt_slides, out_dir)
                print(f"  已下载 {len(downloaded)} 张幻灯片图片到 {out_dir / 'slides'}")
        except Exception as e:
            print(f"获取 PPT 失败（不影响转录结果）: {e}")
            ppt_slides = None

    md = result_to_markdown(
        trans_result.get("result", "{}"),
        file_path.name,
        duration=trans_result.get("duration"),
        word_count=trans_result.get("wordCount"),
        max_speakers=args.speakers,
        ppt_slides=ppt_slides,
    )

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = file_path.with_suffix(".md")

    out_path.write_text(md, encoding="utf-8")
    print(f"转录完成: {out_path}")

    # 获取智能分析
    if not args.no_lab:
        try:
            print("获取智能分析...")
            lab_data = client.get_lab_info(result["trans_id"])
            lab_md = lab_to_markdown(lab_data)
            if lab_md:
                md += lab_md
                out_path.write_text(md, encoding="utf-8")
                print(f"智能分析已追加到: {out_path}")
        except Exception as e:
            print(f"获取智能分析失败（不影响转录结果）: {e}")

    if not args.no_archive:
        archive_root = SKILL_ROOT / "archive"
        md_path, archive_dir = save_archive(
            file_path, md, result["trans_id"], trans_result, archive_root
        )
        print(f"已归档: {archive_dir}")

    print(f"时长: {trans_result.get('duration', 'N/A')}秒 | 字数: {trans_result.get('wordCount', 'N/A')}")


if __name__ == "__main__":
    main()
