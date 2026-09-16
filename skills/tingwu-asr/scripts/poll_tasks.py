#!/usr/bin/env python3
"""tingwu-asr 异步任务轮询 — 检查 pending 任务状态，完成后自动生成 Markdown"""

import argparse
import contextlib
import fcntl
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tingwu import TingwuClient, VIDEO_EXTS
from format_output import result_to_markdown, lab_to_markdown, save_archive

PENDING_PATH = SKILL_ROOT / "config" / "pending_tasks.json"
COMPLETED_PATH = SKILL_ROOT / "config" / "completed_tasks.json"
LOCK_PATH = SKILL_ROOT / "config" / ".pending_tasks.lock"

STATUS_NAMES = {0: "已提交，待转录开始", 1: "排队中/转录中", 2: "转录中", 3: "已完成", 4: "失败", 11: "上传中"}

# 后端把拒绝类错误（如"仅支持16k及以上采样率文件"）也归到 status=2（名义上的
# "转录中"），若只看 status 会无限轮询。从 statusMsg 识别关键词，命中即判失败。
_BACKEND_REJECT_KEYWORDS = (
    "仅支持", "采样率", "不支持", "无法", "失败",
    "not supported", "error", "invalid", "failed",
)


def _is_backend_reject(status_msg):
    """status=2 时判断 statusMsg 是否为后端拒绝类软错误"""
    msg = (status_msg or "").strip()
    if not msg:
        return False
    lowered = msg.lower()
    return any(kw in msg or kw in lowered for kw in _BACKEND_REJECT_KEYWORDS)


@contextlib.contextmanager
def pending_lock(timeout=0):
    """对 pending_tasks 加排他文件锁。

    - timeout=0（默认）：非阻塞抢锁；抢不到立即退出，由 monitor 下一轮重试
    - timeout>0：阻塞抢锁，最多等 N 秒（适用于强制串行场景）

    锁文件 .pending_tasks.lock 紧邻 pending_tasks.json，
    利用 fcntl.flock(LOCK_EX | LOCK_NB) 实现跨进程互斥。
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = open(LOCK_PATH, "w")
    try:
        if timeout <= 0:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fd.close()
                yield False
                return
        else:
            deadline = time.time() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.time() >= deadline:
                        fd.close()
                        yield False
                        return
                    time.sleep(0.2)
        yield True
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception:
            pass
        fd.close()


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

    # PPT（视频自动启用）
    ppt_slides = None
    slides_ext = ".png"
    is_video = Path(task["file_path"]).suffix.lower() in VIDEO_EXTS
    if task.get("ppt") or is_video:
        try:
            print(f"  获取 PPT 幻灯片...")
            ppt_slides = client.get_ppt_info(trans_id)
            if ppt_slides:
                file_stem = Path(task["file_path"]).stem
                out_dir = Path(task["output_path"]).parent if task.get("output_path") else Path(task["file_path"]).parent
                client.download_ppt_images(ppt_slides, out_dir, file_stem=file_stem)
                slides_dir = out_dir / f"{file_stem}_slides"
                slides_ext = client.compress_slides(slides_dir)
                print(f"  已下载 {len(ppt_slides)} 张幻灯片到 {file_stem}_slides/")
        except Exception as e:
            print(f"  PPT 下载失败: {e}")

    file_stem = Path(task["file_path"]).stem
    md = result_to_markdown(
        trans_result.get("result", "{}"),
        file_name,
        duration=trans_result.get("duration"),
        word_count=trans_result.get("wordCount"),
        max_speakers=speakers,
        ppt_slides=ppt_slides,
        slides_dir_name=f"{file_stem}_slides" if ppt_slides else "slides",
        slides_ext=slides_ext,
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

    # 自动 AI 总结
    # summary.py inject 需要 Agent 预先生成 {out}.json（prompt → LLM → inject 流程），
    # 纯脚本 runtime 里 json 不存在属正常情况：打印延后提示而非报错。
    if not task.get("no_summary"):
        try:
            summary_py = SKILL_ROOT.parent / "funasr-transcribe" / "scripts" / "summary.py"
            summary_json = out_path.with_suffix(".json")
            if not summary_py.exists():
                print(f"  跳过 AI 总结: 未找到 funasr-transcribe/summary.py")
            elif summary_json.exists():
                print(f"  注入 AI 总结...")
                proc = subprocess.run(
                    [
                        sys.executable, str(summary_py), "inject",
                        str(out_path), str(summary_json),
                    ],
                    check=False, timeout=120,
                )
                if proc.returncode == 0:
                    print(f"  AI 总结已注入")
            else:
                print(f"  AI 总结待生成: 缺 {summary_json.name}（Agent 可用 summary.py prompt 生成后 inject）")
        except Exception as e:
            print(f"  AI 总结失败: {e}")

    return {
        "output_path": str(out_path),
        "duration": trans_result.get("duration"),
        "word_count": trans_result.get("wordCount"),
    }


def check_once(client, task_id_filter=None):
    """检查所有 pending 任务的状态，完成的自动处理。

    Args:
        client: TingwuClient 实例
        task_id_filter: 只处理指定 trans_id（watch_active.sh 单任务高频轮询用），None 处理全部

    加锁语义：抢不到锁直接返回 []，由 monitor_loop 下一轮重试。
    抢到锁后才读 pending_tasks.json，确保拿到最新列表，
    避免在 pending → completed 的写窗口里被另一个进程重复处理。
    """
    with pending_lock(timeout=0) as got:
        if not got:
            print("[锁定] 另一个 poll_tasks 正在处理，跳过本轮")
            return []

        # 锁内重新读取，避免读到过期快照
        tasks = load_tasks(PENDING_PATH)
        if task_id_filter is not None:
            tasks = [t for t in tasks if t.get("trans_id") == task_id_filter]
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

            # 实测 status=0 二义：刚提交（transStartTime 为空）与真正完成均为 0，
            # 仅凭 status 会把刚提交的任务误判完成并生成空 Markdown。
            # 仅当 transStartTime 已设置才视为完成。
            if status == 3 or (status == 0 and info.get("transStartTime")):
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
            elif status == 2 and _is_backend_reject(info.get("statusMsg")):
                # 后端拒绝类软错误（如采样率不支持）伪装成"转录中"，立即判失败，
                # 否则 watcher/monitor 会无限轮询（2026-06-22 真实案例）。
                status_msg = info.get("statusMsg", "")
                print(f"[{trans_id}] 失败（后端拒绝）: {status_msg}")
                task["status"] = "failed"
                task["error"] = f"后端拒绝(status=2): {status_msg}"
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

        # 锁内一次性写回，避免和另一个进程交叉写。
        # task_id_filter 模式下 remaining 只含被过滤任务，须按 trans_id 剔除
        # 已完成/失败的，保留其余 pending 任务，否则会把别的任务一并抹掉。
        done_ids = {t["trans_id"] for t in completed}
        if task_id_filter is not None:
            all_pending = load_tasks(PENDING_PATH)
            remaining = [t for t in all_pending if t.get("trans_id") not in done_ids]
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
    parser.add_argument("--once", action="store_true", help="单次检查（默认行为，供 watch_active.sh 显式调用）")
    parser.add_argument("--task-id", help="只轮询指定任务（watch_active.sh 单任务监控用）")
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
        # --once 与默认行为一致：单次检查（可配合 --task-id 过滤）
        check_once(client, task_id_filter=args.task_id)


if __name__ == "__main__":
    main()
