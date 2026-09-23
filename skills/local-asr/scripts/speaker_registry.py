#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""本地声纹库管理 CLI。

注册本身走"认领"路径：转录响应携带 speaker_embeddings，经用户确认身份后
由 Agent 调用服务的 POST /speaker/register 写入。本脚本只提供本地管理：

  list                列出声纹库（直接读库文件，无需服务运行）
  remove <name>       删除指定说话人（直接改库文件，无需服务运行）
  test <audio>        提取音频声纹与库比对（需服务已启动）

声纹库文件 assets/speaker-profiles.json 属本地个人数据，被 .gitignore 排除。
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
PROFILES_PATH = SCRIPT_DIR.parent / "assets" / "speaker-profiles.json"
DEFAULT_SERVER = "http://127.0.0.1:8765"


def load_profiles() -> list:
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"❌ 声纹库读取失败: {exc}")
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, list):
        return []
    return [item for item in profiles if isinstance(item, dict) and item.get("name")]


def save_profiles(profiles: list) -> None:
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "profiles": profiles}
    with open(PROFILES_PATH, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def cmd_list(_args) -> int:
    profiles = load_profiles()
    if not profiles:
        print("声纹库为空。注册方式：转录后在响应的 speaker_embeddings 中认领说话人，")
        print("再调用服务 POST /speaker/register。")
        return 0
    print(f"声纹库共 {len(profiles)} 人（{PROFILES_PATH}）：")
    for item in profiles:
        created = item.get("created_at") or "未知时间"
        source = item.get("source_file") or "未知来源"
        label = item.get("source_label") or "-"
        dim = item.get("dim") or "?"
        print(f"  - {item['name']}  维度={dim}  注册于={created}  来源={source} ({label})")
    return 0


def cmd_remove(args) -> int:
    name = args.name.strip()
    profiles = load_profiles()
    remaining = [item for item in profiles if item.get("name") != name]
    if len(remaining) == len(profiles):
        print(f"❌ 声纹库中没有说话人: {name}")
        return 1
    save_profiles(remaining)
    print(f"✅ 已删除说话人: {name}（剩余 {len(remaining)} 人）")
    return 0


def cmd_test(args) -> int:
    if not Path(args.file).exists():
        print(f"❌ 文件不存在: {args.file}")
        return 1
    url = args.server.rstrip("/") + "/speaker/test"
    payload = json.dumps({"file_path": str(Path(args.file).resolve()), "max_seconds": args.max_seconds}).encode()
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        print(f"❌ 服务返回 {exc.code}: {detail[:300]}")
        return 1
    except urllib.error.URLError as exc:
        print(f"❌ 无法连接服务（{exc.reason}）。请先启动: python3 scripts/server.py")
        return 1
    print(f"识别阈值: {data.get('threshold')}")
    for item in data.get("scores", []):
        score = item.get("score")
        score_text = f"{score:.4f}" if isinstance(score, float) else str(score)
        print(f"  {item.get('name')}: {score_text}")
    best = data.get("best")
    if best:
        print(f"最佳匹配: {best.get('name')} ({best.get('score')})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="本地声纹库管理（list / remove / test）")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出声纹库（无需服务运行）")
    remove_parser = sub.add_parser("remove", help="删除指定说话人（无需服务运行）")
    remove_parser.add_argument("name", help="说话人名称")
    test_parser = sub.add_parser("test", help="提取音频声纹并与库比对（需服务运行）")
    test_parser.add_argument("file", help="音频/视频文件路径")
    test_parser.add_argument("--server", default=DEFAULT_SERVER, help=f"服务地址（默认 {DEFAULT_SERVER}）")
    test_parser.add_argument("--max-seconds", type=float, default=60.0, help="提取声纹使用的最长音频时长（默认 60 秒）")
    args = parser.parse_args()
    if args.command == "list":
        return cmd_list(args)
    if args.command == "remove":
        return cmd_remove(args)
    return cmd_test(args)


if __name__ == "__main__":
    sys.exit(main())
