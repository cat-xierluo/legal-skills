#!/usr/bin/env python3
"""
从给定路径向上回溯，定位所属项目根并输出其信息文件内容。
用于报销清单自动填补事由/案号/日期/路线等"报销信息"字段。
纯标准库，无外部依赖。
"""
import argparse
import sys
from pathlib import Path

# 项目根标志文件（按优先级）
DEFAULT_MARKERS = ["项目信息.md", "待办事项.md", "README.md"]


def find_project_root(start: Path, markers, max_up=8):
    """从 start 向上回溯，返回 (项目根Path, 首个命中标志文件Path)。"""
    p = start.expanduser().resolve()
    if p.is_file():
        p = p.parent
    for _ in range(max_up):
        for m in markers:
            candidate = p / m
            if candidate.is_file():
                return p, candidate
        if p == p.parent:  # 已到文件系统根
            break
        p = p.parent
    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="向上回溯定位项目根，输出其信息文件内容（供报销清单填补事由）"
    )
    parser.add_argument("path", help="发票所在目录或文件路径")
    parser.add_argument(
        "--markers", nargs="*", default=DEFAULT_MARKERS,
        help=f"项目根标志文件名，默认: {DEFAULT_MARKERS}",
    )
    parser.add_argument("--max-up", type=int, default=8, help="最多向上回溯层级")
    parser.add_argument("--list-dir", action="store_true", help="额外列出项目根一层目录")
    args = parser.parse_args()

    start = Path(args.path)
    if not start.exists():
        print(f"❌ 路径不存在: {start}")
        raise SystemExit(1)

    root, marker = find_project_root(start, args.markers, args.max_up)
    if not root:
        print(f"未在 {start} 向上 {args.max_up} 层内识别到项目根（标志: {args.markers}）。")
        print("请用户确认发票所属项目或直接提供事由。")
        raise SystemExit(1)

    print(f"项目根: {root}")
    print(f"命中标志: {marker.name}")
    print()

    # 输出项目根下所有命中的标志文件内容
    found = [root / m for m in args.markers if (root / m).is_file()]
    for f in found:
        print(f"========== {f.name} ==========")
        try:
            print(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[读取失败: {e}]")
        print()

    if args.list_dir:
        print(f"========== {root.name}/ 目录 ==========")
        for child in sorted(root.iterdir()):
            tag = "/" if child.is_dir() else ""
            print(f"  {child.name}{tag}")


if __name__ == "__main__":
    main()
