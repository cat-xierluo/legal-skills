#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""本地声纹库管理 CLI。

注册本身走"认领"路径：转录响应携带 speaker_embeddings，经用户确认身份后
由 Agent 调用服务的 POST /speaker/register 写入。本脚本提供本地管理与认领：

  list                列出声纹库（直接读库文件，无需服务运行）
  remove <name>       删除指定说话人（直接改库文件，无需服务运行）
  claim <name>        从转录结果 JSON 中取出指定标签的声纹向量并注册（需服务运行；
                      Task-020 认领入口，避免手工复制 192 个浮点数）
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

try:
    from . import speaker_store
except ImportError:
    import speaker_store


def load_profiles() -> list:
    """读取声纹库有效条目；坏条目隔离告警，损坏库直接报错退出（不静默当空库）。"""
    profiles, issues, corrupt = speaker_store.load_profiles(PROFILES_PATH)
    for issue in issues:
        print(f"⚠️  {issue}", file=sys.stderr)
    if corrupt:
        raise SystemExit(f"❌ 声纹库损坏，拒绝操作以保护原有记录: {issues[0] if issues else '无法解析'}")
    return profiles


def save_profiles(profiles: list) -> None:
    speaker_store.save_profiles(PROFILES_PATH, profiles)


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

    def _mutate(profiles: list, _issues: list[str]):
        remaining = [item for item in profiles
                     if not (isinstance(item, dict) and item.get("name") == name)]
        return remaining, len(remaining) != len(profiles)

    try:
        remaining, found, _issues = speaker_store.mutate_profiles(PROFILES_PATH, _mutate)
    except speaker_store.RegistryCorruptError as exc:
        print(f"❌ 声纹库损坏，拒绝操作以保护原有记录: {exc}")
        return 1
    if not found:
        print(f"❌ 声纹库中没有说话人: {name}")
        return 1
    print(f"✅ 已删除说话人: {name}（剩余 {len(remaining)} 人）")
    return 0


def cmd_claim(args) -> int:
    """从转录结果 JSON 取出指定标签的声纹向量并调用服务注册（Task-020）。

    注册是长期入库行为：仅当用户明确同意长期注册时调用；
    用户只是为当前稿件命名时，直接在 Markdown 中标注即可。
    """
    result_path = Path(args.result).expanduser()
    if not result_path.exists():
        print(f"❌ 结果文件不存在: {args.result}")
        return 1
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"❌ 结果文件解析失败: {exc}")
        return 1
    embeddings = result.get("speaker_embeddings") or {}
    label = args.label.strip()
    if label not in embeddings:
        available = "、".join(sorted(embeddings)) or "（无）"
        print(f"❌ 结果 JSON 中没有标签 {label} 的声纹向量。可用标签: {available}")
        return 1
    states = result.get("speaker_states") or {}
    state = states.get(label) or {}
    if state.get("status") in {"insufficient_audio", "extraction_failed", "disabled"}:
        print(f"❌ 标签 {label} 状态为 {state.get('status')}（{state.get('detail', '')}），"
              "没有可注册的合格声纹向量")
        return 1
    embedding = embeddings[label]

    source_file = args.source_file
    if not source_file:
        output_path = result.get("output_path") or ""
        source_file = Path(output_path).stem if output_path else None

    payload = json.dumps({
        "name": args.name.strip(),
        "embedding": embedding,
        "source_file": source_file,
        "source_label": label,
    }).encode()
    request = urllib.request.Request(
        args.server.rstrip("/") + "/speaker/register",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        print(f"❌ 服务返回 {exc.code}: {detail[:300]}")
        return 1
    except urllib.error.URLError as exc:
        print(f"❌ 无法连接服务（{exc.reason}）。请先启动: python3 scripts/server.py")
        return 1
    action = "更新" if data.get("replaced") else "注册"
    print(f"✅ 已{action}说话人: {data.get('name')}（库内共 {data.get('total')} 人，来源标签 {label}）")
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
    print(f"识别阈值: {data.get('threshold')}（score 为声纹相似度/余弦相似度，非身份正确概率）")
    for item in data.get("scores", []):
        score = item.get("score")
        score_text = f"{score:.4f}" if isinstance(score, float) else str(score)
        print(f"  {item.get('name')}: {score_text}")
    best = data.get("best")
    threshold = data.get("threshold")
    if best:
        if data.get("best_is_match"):
            print(f"✅ 识别为: {best.get('name')} ({best.get('score')})")
        else:
            print(f"❌ 未识别：最佳候选 {best.get('name')} 相似度 {best.get('score')} 低于阈值 {threshold}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="本地声纹库管理（list / remove / claim / test）")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出声纹库（无需服务运行）")
    remove_parser = sub.add_parser("remove", help="删除指定说话人（无需服务运行）")
    remove_parser.add_argument("name", help="说话人名称")
    claim_parser = sub.add_parser("claim", help="从转录结果 JSON 认领指定标签的声纹并注册（需服务运行）")
    claim_parser.add_argument("name", help="用户确认的说话人名称")
    claim_parser.add_argument("--result", required=True, help="转录结果 JSON 文件（auto_transcribe --save-result 或 transcribe --json 输出）")
    claim_parser.add_argument("--label", required=True, help="文件内说话人标签（如 S01）")
    claim_parser.add_argument("--source-file", help="认领来源录音名（默认取结果 output_path 的文件名）")
    claim_parser.add_argument("--server", default=DEFAULT_SERVER, help=f"服务地址（默认 {DEFAULT_SERVER}）")
    test_parser = sub.add_parser("test", help="提取音频声纹并与库比对（需服务运行）")
    test_parser.add_argument("file", help="音频/视频文件路径")
    test_parser.add_argument("--server", default=DEFAULT_SERVER, help=f"服务地址（默认 {DEFAULT_SERVER}）")
    test_parser.add_argument("--max-seconds", type=float, default=60.0, help="提取声纹使用的最长音频时长（默认 60 秒）")
    args = parser.parse_args()
    if args.command == "list":
        return cmd_list(args)
    if args.command == "remove":
        return cmd_remove(args)
    if args.command == "claim":
        return cmd_claim(args)
    return cmd_test(args)


if __name__ == "__main__":
    sys.exit(main())
