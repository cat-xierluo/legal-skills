#!/usr/bin/env python3
"""元典法条检索 API 命令行工具"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "http://aiapi.ailaw.cn:8319"
TIMEOUT = 30


def load_api_key():
    """从环境变量或 .env 文件加载 API Key"""
    key = os.environ.get("YD_API_KEY", "")
    if key:
        return key

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "YD_API_KEY":
                    return v.strip()

    print("错误：未找到 YD_API_KEY。请在 scripts/.env 文件中配置，或设置环境变量。", file=sys.stderr)
    sys.exit(1)


def api_post(endpoint, body):
    """发送 POST 请求到元典 API"""
    api_key = load_api_key()
    url = f"{BASE_URL}{endpoint}?api_key={api_key}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print(f"HTTP 错误 {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"网络错误: {e.reason}", file=sys.stderr)
        sys.exit(1)


def format_law_results(data):
    """格式化法条检索结果为 Markdown"""
    if not data:
        return "未找到相关法条。"

    lines = []
    for i, item in enumerate(data, 1):
        lines.append(f"### {i}. {item.get('法规名称', '')} — {item.get('法条序号', '')}")
        lines.append("")
        if item.get("法条全文"):
            lines.append(f"> {item['法条全文']}")
            lines.append("")
        meta = []
        if item.get("发布机关"):
            meta.append(f"发布机关: {item['发布机关']}")
        if item.get("发文字号"):
            meta.append(f"发文字号: {item['发文字号']}")
        if item.get("发布日期"):
            meta.append(f"发布日期: {item['发布日期']}")
        if item.get("实施日期"):
            meta.append(f"实施日期: {item['实施日期']}")
        if item.get("时效性"):
            meta.append(f"时效性: {item['时效性']}")
        if meta:
            lines.append(" | ".join(meta))
            lines.append("")
        if item.get("法规链接"):
            lines.append(f"[查看原文]({item['法规链接']})")
            lines.append("")
    return "\n".join(lines)


def format_case_results(data):
    """格式化案例检索结果为 Markdown"""
    if not data:
        return "未找到相关案例。"

    lines = []
    for i, item in enumerate(data, 1):
        lines.append(f"### {i}. {item.get('标题', item.get('案号', ''))}")
        lines.append("")
        meta = []
        if item.get("案号"):
            meta.append(f"案号: {item['案号']}")
        if item.get("类型"):
            meta.append(f"类型: {item['类型']}")
        if item.get("案件类别"):
            meta.append(f"类别: {item['案件类别']}")
        if item.get("案由"):
            meta.append(f"案由: {', '.join(item['案由']) if isinstance(item['案由'], list) else item['案由']}")
        if item.get("经办法院"):
            meta.append(f"法院: {item['经办法院']}")
        if item.get("裁判日期"):
            meta.append(f"日期: {item['裁判日期']}")
        if meta:
            lines.append(" | ".join(meta))
            lines.append("")
        if item.get("正文"):
            text = item["正文"]
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(text)
            lines.append("")
        if item.get("案例链接"):
            lines.append(f"[查看原文]({item['案例链接']})")
            lines.append("")
    return "\n".join(lines)


# ── 子命令处理 ──────────────────────────────────────────────

def cmd_search(args):
    """法条语义检索"""
    body = {"query": args.query}
    if args.effect1:
        body["effect1"] = args.effect1
    if args.sxx:
        body["sxx"] = args.sxx
    result = api_post("/search", body)
    print(format_law_results(result.get("data", [])))


def cmd_keyword(args):
    """法条关键词检索"""
    body = {"query": args.query}
    if args.effect1:
        body["effect1"] = args.effect1
    if args.sxx:
        body["sxx"] = args.sxx
    if args.search_mode:
        body["search_mode"] = args.search_mode
    for date_field in ("fbrq_start", "fbrq_end", "ssrq_start", "ssrq_end"):
        val = getattr(args, date_field, None)
        if val:
            body[date_field] = val
    result = api_post("/search_keyword", body)
    print(format_law_results(result.get("data", [])))


def cmd_detail(args):
    """法条详情检索"""
    body = {"query": args.query, "ft_name": args.ft_name}
    if args.reference_date:
        body["reference_date"] = args.reference_date
    result = api_post("/search_ft_info", body)
    print(format_law_results(result.get("data", [])))


def cmd_case(args):
    """案例关键词检索"""
    body = {}
    if args.query:
        body["query"] = args.query
    if args.search_mode:
        body["search_mode"] = args.search_mode
    if args.authority_only:
        body["authority_only"] = True
    for field in ("ah", "title"):
        val = getattr(args, field, None)
        if val:
            body[field] = val
    for field in ("ay", "jbdw", "xzqh_p", "wszl"):
        val = getattr(args, field, None)
        if val:
            body[field] = val
    if args.ajlb:
        body["ajlb"] = args.ajlb
    for date_field in ("jarq_start", "jarq_end"):
        val = getattr(args, date_field, None)
        if val:
            body[date_field] = val
    result = api_post("/search_al", body)
    print(format_case_results(result.get("data", [])))


def cmd_case_semantic(args):
    """案例语义检索"""
    body = {"query": args.query}
    if args.authority_only:
        body["authority_only"] = True
    for field in ("xzqh_p", "wenshu_type"):
        val = getattr(args, field, None)
        if val:
            body[field] = val
    for field in ("fayuan", "wszl"):
        val = getattr(args, field, None)
        if val:
            body[field] = val
    for date_field in ("jarq_start", "jarq_end"):
        val = getattr(args, date_field, None)
        if val:
            body[date_field] = val
    result = api_post("/search_al_vector", body)
    print(format_case_results(result.get("data", [])))


def cmd_raw(args):
    """原始 JSON 输出（用于调试）"""
    body = {"query": args.query}
    if args.extra:
        try:
            extra = json.loads(args.extra)
            body.update(extra)
        except json.JSONDecodeError:
            print("错误：--extra 参数不是有效的 JSON", file=sys.stderr)
            sys.exit(1)
    result = api_post(args.endpoint, body)
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ── 参数解析 ──────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="元典法条检索命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  %(prog)s search "正当防卫的限度" --sxx 现行有效
  %(prog)s keyword "人工智能 监管" --effect1 法律 --effect1 行政法规
  %(prog)s detail "民法典" --ft-name "第十五条"
  %(prog)s case "买卖合同纠纷" --province 广西 --authority-only
  %(prog)s case-semantic "正当防卫的限度" --jarq-start 2020-01-01
"""
    )
    sub = parser.add_subparsers(dest="command")

    # ── search ──
    p = sub.add_parser("search", help="法条语义检索")
    p.add_argument("query", help="自然语言问题")
    p.add_argument("--effect1", action="append", help="效力级别（可多次指定）")
    p.add_argument("--sxx", action="append", help="时效性（可多次指定）")
    p.set_defaults(func=cmd_search)

    # ── keyword ──
    p = sub.add_parser("keyword", help="法条关键词检索")
    p.add_argument("query", help="关键词，多个用空格分隔")
    p.add_argument("--effect1", action="append", help="效力级别")
    p.add_argument("--sxx", action="append", help="时效性")
    p.add_argument("--search-mode", choices=["and", "or"], default="and", help="多关键词逻辑")
    p.add_argument("--fbrq-start", help="发布日期起点 yyyy-MM-dd")
    p.add_argument("--fbrq-end", help="发布日期终点")
    p.add_argument("--ssrq-start", help="实施日期起点")
    p.add_argument("--ssrq-end", help="实施日期终点")
    p.set_defaults(func=cmd_keyword)

    # ── detail ──
    p = sub.add_parser("detail", help="法条详情检索")
    p.add_argument("query", help="法规名称")
    p.add_argument("--ft-name", required=True, help="法条编号，如 '第十五条'")
    p.add_argument("--reference-date", help="参考日期 yyyy-MM-dd")
    p.set_defaults(func=cmd_detail)

    # ── case ──
    p = sub.add_parser("case", help="案例关键词检索")
    p.add_argument("query", nargs="?", default="", help="全文关键词")
    p.add_argument("--search-mode", choices=["and", "or"], default="and")
    p.add_argument("--authority-only", action="store_true", help="仅检索权威案例")
    p.add_argument("--ah", help="案号")
    p.add_argument("--title", help="标题")
    p.add_argument("--ay", action="append", help="案由/罪名（可多次指定）")
    p.add_argument("--jbdw", action="append", help="经办法院（可多次指定）")
    p.add_argument("--ajlb", help="案件类别")
    p.add_argument("--xzqh-p", "--province", action="append", help="省份")
    p.add_argument("--wszl", action="append", help="文书种类")
    p.add_argument("--jarq-start", help="结案日期起点")
    p.add_argument("--jarq-end", help="结案日期终点")
    p.set_defaults(func=cmd_case)

    # ── case-semantic ──
    p = sub.add_parser("case-semantic", help="案例语义检索")
    p.add_argument("query", help="自然语言问题")
    p.add_argument("--authority-only", action="store_true")
    p.add_argument("--xzqh-p", "--province", help="省份")
    p.add_argument("--fayuan", action="append", help="法院名称")
    p.add_argument("--wenshu-type", help="案件类型，如 民事案件")
    p.add_argument("--wszl", action="append", help="文书种类")
    p.add_argument("--jarq-start", help="日期起点")
    p.add_argument("--jarq-end", help="日期终点")
    p.set_defaults(func=cmd_case_semantic)

    # ── raw ──
    p = sub.add_parser("raw", help="原始 JSON 输出（调试用）")
    p.add_argument("endpoint", help="API 路径，如 /search")
    p.add_argument("query", help="查询内容")
    p.add_argument("--extra", help="额外 JSON 参数")
    p.set_defaults(func=cmd_raw)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
