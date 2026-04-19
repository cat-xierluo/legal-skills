#!/usr/bin/env python3
"""为 review-plan 自动补全策略字段。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .plan_loader import enrich_plan, load_plan
except ImportError:
    from plan_loader import enrich_plan, load_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="补全 review-plan 的策略字段")
    parser.add_argument("--input", required=True, help="输入 review-plan.json 路径")
    parser.add_argument("--output", help="输出路径；默认生成 *_enriched.json")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="就地覆盖输入文件（优先级高于 --output）",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"审查计划文件不存在: {input_path}")

    if args.in_place:
        output_path = input_path
    elif args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = input_path.with_name(f"{input_path.stem}_enriched.json")

    plan = load_plan(input_path)
    enriched = enrich_plan(plan)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"输出计划: {output_path}")


if __name__ == "__main__":
    main()
