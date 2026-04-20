#!/usr/bin/env python3
"""tingwu-asr 异步任务轮询 — 检查 pending 任务状态，完成后自动生成 Markdown"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tingwu import TingwuClient
from format_output import result_to_markdown, lab_to_markdown, save_archive

PENDING_PATH = SKILL_ROOT / "config" / "pending_tasks.json"
COMPLETED_PATH = SKILL_ROOT / "config" / "completed_tasks.json"

STATUS_NAMES = {0: "已完成", 1: "排队中", 2: "转录中", 3: "已完成", 4: "失败", 11: "上传中"}


def load_tasks(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def save_tasks(path, tasks):
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def finish_task(client, task):
    """任务完成：获取结果 → 生成 Markdown → PPT → 智能分析 → 归档"""
    trans_id = task["trans_id"]
    file_name = task["file_name"]
    speakers = task.get("role_split_num", 4)

    print(f"  获取转录结果...")
    trans_result = client.get_trans_result(trans_id)

    # PPT
    ppt_slides = None
    if task.get("ppt"):
        try:
            print(f"  获取 PPT 幻灯片...")
            ppt_slides = client.get_ppt_info(trans_id)
            if ppt_slides:
                out_dir = Path(task["output_path"]).parent if task.get("output_path") else Path(task["file_path"]).parent
                client.download_ppt_images(ppt_slides, out_dir)
                print(f"  已下载 {len(ppt_slides)} 张幻灯片")
        except Exception as e:
            print(f"  PPT 下载失败: {e}")

    md = result_to_markdown(
        trans_result.get("result", "{}"),
        file_name,
        duration=trans_result.get("duration"),
        word_count=trans_result.get("wordCount"),
        max_speakers=speakers,
        ppt_slides=ppt_slides,
    )

    if task.get("output_path"):
        out_path = Path(task["output_path"])
    else:
        out_path = Path(task["file_path"]).with_suffix(".md")
    out_path.write_text(md, encoding="utf-8")
    print(f"  转录完成: {out_path}")

    # 智能分析
    if not task.get("no_lab"):
        try:
            lab_data = client.get_lab_info(trans_id)
            lab_md = lab_to_markdown(lab_data)
            if lab_md:
                md += lab_md
                out_path.write_text(md, encoding="utf-8")
        except Exception:
            pass

    # 归档
    if not task.get("no_archive"):
        archive_root = SKILL_ROOT / "archive"
        save_archive(Path(task["file_path"]), md, trans_id, trans_result, archive_root)

    return {
        "output_path": str(out_path),
        "duration": trans_result.get("duration"),
        "word_count": trans_result.get("wordCount"),
    }


def check_once(client):
    """检查所有 pending 任务的状态，完成的自动处理"""
    tasks = load_tasks(PENDING_PATH)
    if not tasks:
        print("无待处理任务")
        return []

    completed = []
    remaining = []

    for task in tasks:
        trans_id = task["trans_id"]
        try:
            info = client.get_trans_list(trans_id)
        except Exception as e:
            print(f"[{trans_id}] 查询失败: {e}")
            remaining.append(task)
            continue

        if info is None:
            print(f"[{trans_id}] 任务未出现在列表中")
            remaining.append(task)
            continue

        status = info.get("status", -1)
        name = STATUS_NAMES.get(status, f"未知({status})")

        if status in (0, 3):
            print(f"[{trans_id}] {name} — 正在生成输出...")
            try:
                result_info = finish_task(client, task)
                task["status"] = "completed"
                task["completed_at"] = datetime.now().isoformat()
                task["result"] = result_info
                completed.append(task)
            except Exception as e:
                print(f"[{trans_id}] 生成输出失败: {e}")
                task["status"] = "error"
                task["error"] = str(e)
                completed.append(task)
        elif status == 4:
            print(f"[{trans_id}] 失败: {info.get('statusMsg', '未知原因')}")
            task["status"] = "failed"
            task["error"] = info.get("statusMsg", "未知原因")
            completed.append(task)
        else:
            extra = ""
            forecast = info.get("forecastTransDoneTime")
            now = info.get("serverCurrentTime")
            if forecast and now and status in (1, 2):
                remain_s = max(0, (forecast - now) / 1000)
                extra = f" | 预计剩余: {remain_s / 60:.1f} 分钟"
            print(f"[{trans_id}] {name}{extra}")
            remaining.append(task)

    save_tasks(PENDING_PATH, remaining)

    if completed:
        existing = load_tasks(COMPLETED_PATH)
        existing.extend(completed)
        save_tasks(COMPLETED_PATH, existing)

    return completed


def monitor_loop(client, timeout=3600, interval=120):
    """阻塞式循环轮询，直到所有任务完成或超时"""
    start = time.time()
    while time.time() - start < timeout:
        tasks = load_tasks(PENDING_PATH)
        if not tasks:
            print("所有任务已完成")
            return True

        print(f"\n--- {datetime.now().strftime('%H:%M:%S')} 检查 {len(tasks)} 个待处理任务 ---")
        completed = check_once(client)

        tasks = load_tasks(PENDING_PATH)
        if not tasks:
            print("\n全部转录完成！")
            return True

        elapsed = int(time.time() - start)
        print(f"等待 {interval} 秒后重试（已耗时 {elapsed}s）...")
        time.sleep(interval)

    print(f"\n轮询超时 ({timeout}s)，仍有 {len(load_tasks(PENDING_PATH))} 个任务未完成")
    return False


def main():
    parser = argparse.ArgumentParser(description="tingwu-asr 异步任务轮询")
    parser.add_argument("--monitor", action="store_true", help="阻塞式循环轮询")
    parser.add_argument("--timeout", type=int, default=3600, help="监控超时秒数 (默认: 3600)")
    parser.add_argument("--interval", type=int, default=120, help="轮询间隔秒数 (默认: 120)")
    parser.add_argument("--cookie", help="Cookie 文件路径")
    args = parser.parse_args()

    try:
        client = TingwuClient(cookie_path=args.cookie)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)

    if args.monitor:
        ok = monitor_loop(client, timeout=args.timeout, interval=args.interval)
        sys.exit(0 if ok else 1)
    else:
        check_once(client)


if __name__ == "__main__":
    main()
