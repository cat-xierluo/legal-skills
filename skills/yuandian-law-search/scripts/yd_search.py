#!/usr/bin/env python3
"""元典法条检索 API 命令行工具（v1.0.0 - 开放平台版）"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from updater import SkillUpdater

BASE_URL = "https://open.chineselaw.com"
TIMEOUT = 60
COST_PER_CALL = "本次调用消耗 10 积分"
SKILL_ROOT = Path(__file__).parent.parent
ARCHIVE_DIR = SKILL_ROOT / "archive"

# 版本信息
CURRENT_VERSION = "1.1.1"

# 通用更新模块实例
_updater = SkillUpdater(
    skill_root=SKILL_ROOT,
    repo_raw_base="https://raw.githubusercontent.com/cat-xierluo/legal-skills/main/skills/yuandian-law-search",
    commits_feed="https://github.com/cat-xierluo/legal-skills/commits/main/skills/yuandian-law-search.atom",
    current_version=CURRENT_VERSION,
)


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


def _common_headers():
    """返回公共请求头"""
    return {
        "X-API-Key": load_api_key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _query_fingerprint(endpoint, payload):
    """根据端点和请求参数生成指纹，用于归档查重"""
    raw = json.dumps({"endpoint": endpoint, "payload": payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _make_archive_name(endpoint, payload):
    """生成归档文件名：YYYYMMDD_HHMMSS_{查询摘要}.json"""
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")

    # 从 payload 中提取查询摘要
    summary = ""
    for key in ("query", "keyword", "qw", "fgmc", "name", "ah"):
        val = payload.get(key, "")
        if val:
            summary = str(val)
            break
    if not summary:
        summary = endpoint.split("/")[-1]

    # 清理文件名：移除特殊字符，截断
    summary = re.sub(r'[/\\:*?"<>|？\s]', '_', summary)
    summary = summary.strip('_')[:40]

    return f"{ts}_{summary}.json"


def _archive_lookup(endpoint, payload):
    """在归档中查找相同查询，命中返回 (response, archive_path)，未命中返回 (None, None)"""
    if not ARCHIVE_DIR.exists():
        return None, None

    fingerprint = _query_fingerprint(endpoint, payload)
    # 按时间倒序遍历，优先命中最新归档
    for path in sorted(ARCHIVE_DIR.glob("*.json"), reverse=True):
        try:
            record = json.loads(path.read_text("utf-8"))
            if record.get("fingerprint") == fingerprint:
                return record.get("response"), str(path)
        except (json.JSONDecodeError, KeyError):
            continue
    return None, None


def _archive_save(endpoint, payload, response):
    """将查询和响应归档"""
    ARCHIVE_DIR.mkdir(exist_ok=True)
    fingerprint = _query_fingerprint(endpoint, payload)
    filename = _make_archive_name(endpoint, payload)
    path = ARCHIVE_DIR / filename

    record = {
        "id": filename.replace(".json", ""),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "endpoint": endpoint,
        "query": payload,
        "fingerprint": fingerprint,
        "response": response,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
    return str(path)


def api_post(endpoint, body, use_cache=True):
    """发送 POST 请求到元典开放平台 API（支持归档查重）"""
    if use_cache:
        cached, archive_path = _archive_lookup(endpoint, body)
        if cached is not None:
            return cached, True

    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers=_common_headers())
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print(f"HTTP 错误 {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"网络错误: {e.reason}", file=sys.stderr)
        sys.exit(1)

    if use_cache:
        _archive_save(endpoint, body, result)
    return result, False


def api_get(endpoint, params=None, use_cache=True):
    """发送 GET 请求到元典开放平台 API（支持归档查重）"""
    if use_cache:
        cached, archive_path = _archive_lookup(endpoint, params or {})
        if cached is not None:
            return cached, True

    url = f"{BASE_URL}{endpoint}"
    if params:
        qs = urlencode({k: v for k, v in params.items() if v})
        if qs:
            url = f"{url}?{qs}"
    headers = {
        "X-API-Key": load_api_key(),
        "Accept": "application/json",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        print(f"HTTP 错误 {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"网络错误: {e.reason}", file=sys.stderr)
        sys.exit(1)

    if use_cache:
        _archive_save(endpoint, params or {}, result)
    return result, False


# ── 格式化输出 ──────────────────────────────────────────────


def format_law_results(data):
    """格式化法条检索结果为 Markdown"""
    if not data:
        return "未找到相关法条。"

    lines = []
    for i, item in enumerate(data, 1):
        title = item.get("fgtitle", item.get("ftmc", ""))
        if isinstance(title, list):
            title = title[0] if title else ""
        num = item.get("num", item.get("ft_num", item.get("tid", "")))
        lines.append(f"### {i}. {title or item.get('fgmc', '')} — {num}")
        lines.append("")

        content = item.get("content", "")
        if content:
            lines.append(f"> {content}")
            lines.append("")

        meta = []
        if item.get("effect1") or item.get("xljb_1"):
            meta.append(f"效力级别: {item.get('effect1', '') or item.get('xljb_1', '')}")
        if item.get("effect2") or item.get("xljb_2"):
            meta.append(f"二级效力: {item.get('effect2', '') or item.get('xljb_2', '')}")
        if item.get("sxx"):
            meta.append(f"时效性: {item['sxx']}")
        if item.get("start"):
            meta.append(f"实施日期: {item['start']}")
        if item.get("fbrq"):
            meta.append(f"发布日期: {item['fbrq']}")
        if item.get("fbbm"):
            meta.append(f"发布部门: {item['fbbm']}")
        if item.get("fwzh"):
            meta.append(f"发文字号: {item['fwzh']}")
        if meta:
            lines.append(" | ".join(meta))
            lines.append("")

    return "\n".join(lines)


def format_case_results(data):
    """格式化案例检索结果为 Markdown"""
    if not data:
        return "未找到相关案例。"

    lines = []
    for i, item in enumerate(data, 1):
        title = item.get("title", item.get("ah", ""))
        lines.append(f"### {i}. {title}")
        lines.append("")

        meta = []
        if item.get("ah"):
            meta.append(f"案号: {item['ah']}")
        if item.get("ajlb"):
            meta.append(f"类别: {item['ajlb']}")
        if item.get("anyou"):
            ay = item["anyou"]
            if isinstance(ay, list):
                ay = ", ".join(str(a) for a in ay)
            meta.append(f"案由: {ay}")
        if item.get("jbdw"):
            meta.append(f"法院: {item['jbdw']}")
        if item.get("cj"):
            meta.append(f"法院层级: {item['cj']}")
        if item.get("wszl"):
            meta.append(f"文书: {item['wszl']}")
        if item.get("jaDate") or item.get("cprq"):
            meta.append(f"日期: {item.get('jaDate') or item.get('cprq')}")
        if item.get("xzqh_p"):
            meta.append(f"省份: {item['xzqh_p']}")
        if meta:
            lines.append(" | ".join(meta))
            lines.append("")

        content = item.get("content", "")
        if content:
            text = str(content)
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(text)
            lines.append("")

    return "\n".join(lines)


def format_regulation_results(data):
    """格式化法规检索结果为 Markdown"""
    if not data:
        return "未找到相关法规。"

    lines = []
    for i, item in enumerate(data, 1):
        name = item.get("fgtitle", item.get("fgmc", ""))
        if isinstance(name, list):
            name = name[0] if name else ""
        lines.append(f"### {i}. {name}")
        lines.append("")

        meta = []
        if item.get("effect1") or item.get("xljb_1"):
            meta.append(f"效力级别: {item.get('effect1', '') or item.get('xljb_1', '')}")
        if item.get("sxx"):
            meta.append(f"时效性: {item['sxx']}")
        if item.get("fbrq"):
            meta.append(f"发布日期: {item['fbrq']}")
        if item.get("ssrq"):
            meta.append(f"实施日期: {item['ssrq']}")
        if item.get("fbbm"):
            meta.append(f"发布部门: {item['fbbm']}")
        if item.get("fgid"):
            meta.append(f"ID: {item['fgid']}")
        if meta:
            lines.append(" | ".join(meta))
            lines.append("")

        content = item.get("content", "")
        if content:
            text = str(content)
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(text)
            lines.append("")

    return "\n".join(lines)


def format_enterprise_results(data):
    """格式化企业检索结果为 Markdown"""
    if not data:
        return "未找到相关企业。"
    if isinstance(data, dict):
        data = [data]

    lines = []
    for i, item in enumerate(data, 1):
        name = item.get("name", item.get("企业名称", ""))
        lines.append(f"### {i}. {name}")
        lines.append("")

        meta = []
        credit_code = item.get("tyshxydm", item.get("统一社会信用代码", ""))
        if credit_code:
            meta.append(f"信用代码: {credit_code}")
        ent_type = item.get("企业类型", "")
        if ent_type:
            meta.append(f"类型: {ent_type}")
        status = item.get("经营状态", item.get("status", ""))
        if status:
            meta.append(f"状态: {status}")
        legal_person = item.get("法定代表人", item.get("legal_person", ""))
        if legal_person:
            meta.append(f"法定代表人: {legal_person}")
        if meta:
            lines.append(" | ".join(meta))
            lines.append("")

    return "\n".join(lines)


# ── 子命令处理 ──────────────────────────────────────────────


def _print_footer(cached):
    """打印调用成本提示"""
    print(f"\n--- {COST_PER_CALL} ---")


# ── 版本检测（委托给 updater 模块）──────────────────────


def cmd_check_update(args):
    _updater.cmd_check_update()


def cmd_do_update(args):
    _updater.cmd_do_update()


def cmd_search(args):
    """法条语义检索"""
    body = {
        "query": args.query,
        "rewrite_flag": args.rewrite_flag,
        "return_num": args.return_num,
    }
    fatiao_filter = {}
    if args.effect1:
        fatiao_filter["effect1"] = args.effect1
    if args.sxx:
        fatiao_filter["sxx"] = args.sxx
    if args.law_start:
        fatiao_filter["law_start"] = args.law_start
    if args.law_end:
        fatiao_filter["law_end"] = args.law_end
    if fatiao_filter:
        body["fatiao_filter"] = fatiao_filter

    result, cached = api_post("/open/law_vector_search", body)
    data = result.get("extra", {}).get("fatiao", result.get("data", []))
    print(format_law_results(data))
    _print_footer(cached)


def cmd_keyword(args):
    """法条关键词检索"""
    body = {"keyword": args.query}
    if args.search_mode:
        body["search_mode"] = args.search_mode
    if args.fgmc:
        body["fgmc"] = args.fgmc
    if args.effect1:
        body["xljb_1"] = " ".join(args.effect1)
    if args.sxx:
        body["sxx"] = " ".join(args.sxx)
    for date_field in ("fbrq_start", "fbrq_end", "ssrq_start", "ssrq_end"):
        val = getattr(args, date_field, None)
        if val:
            body[date_field] = val
    if args.top_k:
        body["top_k"] = args.top_k
    result, cached = api_post("/open/rh_ft_search", body)
    data = result.get("data", [])
    print(format_law_results(data))
    _print_footer(cached)


def cmd_detail(args):
    """法条详情检索"""
    body = {"fgmc": args.query, "ftnum": args.ft_name}
    if args.reference_date:
        body["refer_date"] = args.reference_date
    result, cached = api_post("/open/rh_ft_detail", body)
    data = result.get("data")
    items = [data] if isinstance(data, dict) else (data or [])
    print(format_law_results(items))
    _print_footer(cached)


def cmd_case(args):
    """案例关键词检索"""
    body = {}
    if args.query:
        body["qw"] = args.query
    if args.search_mode:
        body["search_mode"] = args.search_mode
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
    for date_field in ("ja_start", "ja_end"):
        val = getattr(args, date_field, None)
        if val:
            body[date_field] = val
    if args.top_k:
        body["top_k"] = args.top_k

    # 普通案例专属参数
    if not args.authority_only:
        if args.fxgc:
            body["fxgc"] = args.fxgc
        if args.yyft:
            body["yyft"] = args.yyft
            if args.ft_search_mode:
                body["ft_search_mode"] = args.ft_search_mode

    # 根据 authority_only 路由到不同端点
    if args.authority_only:
        endpoint = "/open/rh_qwal_search"
    else:
        endpoint = "/open/rh_ptal_search"

    result, cached = api_post(endpoint, body)
    raw = result.get("data")
    data = raw.get("lst", []) if isinstance(raw, dict) else (raw or [])
    total = raw.get("total") if isinstance(raw, dict) else None
    if total is not None:
        print(f"共 {total} 条结果，显示前 {len(data)} 条\n")
    print(format_case_results(data))
    _print_footer(cached)


def cmd_case_semantic(args):
    """案例语义检索"""
    body = {
        "query": args.query,
        "rewrite_flag": args.rewrite_flag,
        "return_num": args.return_num,
    }
    wenshu_filter = {}
    if args.xzqh_p:
        wenshu_filter["xzqh_p"] = args.xzqh_p
    if args.fayuan:
        wenshu_filter["fayuan"] = args.fayuan
    if args.wenshu_type:
        wenshu_filter["wenshu_type"] = args.wenshu_type
    if args.wszl:
        wenshu_filter["wszl"] = args.wszl
    if args.authority_only:
        wenshu_filter["dianxing"] = True
    if args.cj:
        wenshu_filter["cj"] = args.cj
    for date_field in ("ja_start", "ja_end"):
        val = getattr(args, date_field, None)
        if val:
            wenshu_filter[date_field] = val
    if wenshu_filter:
        body["wenshu_filter"] = wenshu_filter

    result, cached = api_post("/open/case_vector_search", body)
    data = result.get("extra", {}).get("wenshu", result.get("data", []))
    print(format_case_results(data))
    _print_footer(cached)


def cmd_case_detail(args):
    """案例详情"""
    params = {"type": args.type}
    if args.id:
        params["id"] = args.id
    if args.ah:
        params["ah"] = args.ah
    if not args.id and not args.ah:
        print("错误：请提供 --id 或 --ah 参数", file=sys.stderr)
        sys.exit(1)
    result, cached = api_get("/open/rh_case_details", params)
    data = result.get("data", {})
    if isinstance(data, list):
        print(format_case_results(data))
    elif isinstance(data, dict):
        print(format_case_results([data]))
    _print_footer(cached)


def cmd_regulation(args):
    """法规关键词检索"""
    body = {}
    if args.query:
        body["keyword"] = args.query
    if args.search_mode:
        body["search_mode"] = args.search_mode
    if args.fgmc:
        body["fgmc"] = args.fgmc
    if args.effect1:
        body["xljb_1"] = " ".join(args.effect1)
    if args.sxx:
        body["sxx"] = " ".join(args.sxx)
    for date_field in ("fbrq_start", "fbrq_end", "ssrq_start", "ssrq_end"):
        val = getattr(args, date_field, None)
        if val:
            body[date_field] = val
    if args.top_k:
        body["top_k"] = args.top_k
    result, cached = api_post("/open/rh_fg_search", body)
    data = result.get("data", [])
    print(format_regulation_results(data))
    _print_footer(cached)


def cmd_regulation_detail(args):
    """法规详情"""
    body = {}
    if args.fgid:
        body["id"] = args.fgid
    if args.name:
        body["fgmc"] = args.name
    if not body:
        print("错误：请提供 --fgid 或 --name 参数", file=sys.stderr)
        sys.exit(1)
    if args.reference_date:
        body["refer_date"] = args.reference_date
    result, cached = api_post("/open/rh_fg_detail", body)
    data = result.get("data", {})
    if isinstance(data, list):
        print(format_regulation_results(data))
    elif isinstance(data, dict):
        print(format_regulation_results([data]))
    _print_footer(cached)


def cmd_enterprise(args):
    """企业名称检索"""
    params = {"name": args.query}
    if args.num:
        params["num"] = args.num
    result, cached = api_get("/open/rh_company_info", params)
    data = result.get("data", [])
    print(format_enterprise_results(data))
    _print_footer(cached)


def cmd_enterprise_detail(args):
    """企业详情"""
    params = {}
    if args.id:
        params["id"] = args.id
    if args.credit_code:
        params["tyshxydm"] = args.credit_code
    if not params:
        print("错误：请提供 --id 或 --credit-code 参数", file=sys.stderr)
        sys.exit(1)
    result, cached = api_get("/open/rh_company_detail", params)
    data = result.get("data", {})
    print(format_enterprise_results(data))
    _print_footer(cached)


def cmd_archive_list(args):
    """列出历史检索记录"""
    if not ARCHIVE_DIR.exists():
        print("尚无检索记录。")
        return

    files = sorted(ARCHIVE_DIR.glob("*.json"), reverse=True)
    keyword = args.keyword.lower() if args.keyword else None
    entries = []

    for f in files:
        if f.name == "version_check.json":
            continue
        try:
            data = json.loads(f.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        ts = data.get("timestamp", "")[:16]
        endpoint = data.get("endpoint", "")
        query = data.get("query", {})
        query_str = json.dumps(query, ensure_ascii=False)
        status = data.get("response", {}).get("status", "")

        if keyword:
            if keyword not in query_str.lower() and keyword not in endpoint.lower():
                continue

        entries.append({
            "file": f.name,
            "time": ts,
            "endpoint": endpoint,
            "query_summary": query_str[:80],
            "status": status,
        })

    if not entries:
        print("没有找到匹配的检索记录。")
        return

    for e in entries[:args.limit]:
        print(f"{e['time']}  {e['endpoint']}")
        print(f"  {e['query_summary']}")
        print()


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
    endpoint = args.endpoint
    use_cache = not args.no_cache
    if args.get:
        params = body
        result, cached = api_get(endpoint, params, use_cache=use_cache)
    else:
        result, cached = api_post(endpoint, body, use_cache=use_cache)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _print_footer(cached)


# ── 参数解析 ──────────────────────────────────────────────


def _add_law_filters(parser):
    """法条通用筛选参数"""
    parser.add_argument("--effect1", action="append", help="效力级别（可多次指定）")
    parser.add_argument("--sxx", action="append", help="时效性（可多次指定）")


def _add_case_filters(parser):
    """案例通用筛选参数"""
    parser.add_argument("--jarq-start", help="结案日期起点 yyyy-MM-dd")
    parser.add_argument("--jarq-end", help="结案日期终点 yyyy-MM-dd")


def build_parser():
    parser = argparse.ArgumentParser(
        description="元典法条检索命令行工具（开放平台版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  %(prog)s search "正当防卫的限度" --sxx 现行有效
  %(prog)s keyword "人工智能 监管" --effect1 法律 --effect1 行政法规
  %(prog)s detail "民法典" --ft-name "第十五条"
  %(prog)s case "买卖合同纠纷" --province 广西 --authority-only
  %(prog)s case-semantic "正当防卫的限度" --jarq-start 2020-01-01
  %(prog)s case-detail --ah "（2025）桂09民终192号"
  %(prog)s regulation "数据安全"
  %(prog)s enterprise "华为"
"""
    )
    sub = parser.add_subparsers(dest="command")

    # ── search ──
    p = sub.add_parser("search", help="法条语义检索")
    p.add_argument("query", help="自然语言问题")
    _add_law_filters(p)
    p.add_argument("--rewrite-flag", action="store_true", default=True, help="是否改写查询（默认 true）")
    p.add_argument("--no-rewrite", action="store_false", dest="rewrite_flag", help="禁用查询改写")
    p.add_argument("--return-num", type=int, default=45, help="返回数量（默认 45）")
    p.add_argument("--law-start", help="法条生效起始日期 yyyy-MM-dd")
    p.add_argument("--law-end", help="法条生效结束日期 yyyy-MM-dd")
    p.set_defaults(func=cmd_search)

    # ── keyword ──
    p = sub.add_parser("keyword", help="法条关键词检索")
    p.add_argument("query", help="关键词，多个用空格分隔")
    p.add_argument("--fgmc", help="法规名称过滤")
    p.add_argument("--effect1", action="append", help="效力级别（可多次指定）")
    p.add_argument("--sxx", action="append", help="时效性（可多次指定）")
    p.add_argument("--search-mode", choices=["and", "or"], default="and", help="多关键词逻辑")
    p.add_argument("--fbrq-start", help="发布日期起点 yyyy-MM-dd")
    p.add_argument("--fbrq-end", help="发布日期终点")
    p.add_argument("--ssrq-start", help="实施日期起点")
    p.add_argument("--ssrq-end", help="实施日期终点")
    p.add_argument("--top-k", type=int, help="返回条数上限（默认10，最大50）")
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
    p.add_argument("--jarq-start", help="结案日期起点 yyyy-MM-dd")
    p.add_argument("--jarq-end", help="结案日期终点 yyyy-MM-dd")
    p.add_argument("--top-k", type=int, help="返回条数上限（默认10，最大50）")
    p.add_argument("--fxgc", help="分析过程关键词")
    p.add_argument("--yyft", action="append", help="援引法条（可多次指定）")
    p.add_argument("--ft-search-mode", choices=["and", "or"], default="and", help="援引法条拼接模式")
    p.set_defaults(func=cmd_case)

    # ── case-semantic ──
    p = sub.add_parser("case-semantic", help="案例语义检索")
    p.add_argument("query", help="自然语言问题")
    p.add_argument("--authority-only", action="store_true", help="仅检索典型案例")
    p.add_argument("--xzqh-p", "--province", help="省份")
    p.add_argument("--fayuan", action="append", help="法院名称")
    p.add_argument("--wenshu-type", help="案件类型，如 民事案件")
    p.add_argument("--wszl", action="append", help="文书种类编码（1=判决书 2=裁定书 等）")
    p.add_argument("--cj", help="法院层级：最高/高级/中级/基层")
    p.add_argument("--rewrite-flag", action="store_true", default=True, help="是否改写查询")
    p.add_argument("--no-rewrite", action="store_false", dest="rewrite_flag", help="禁用查询改写")
    p.add_argument("--return-num", type=int, default=45, help="返回数量")
    p.add_argument("--jarq-start", help="结案日期起点 yyyy-MM-dd")
    p.add_argument("--jarq-end", help="结案日期终点 yyyy-MM-dd")
    p.set_defaults(func=cmd_case_semantic)

    # ── case-detail ──
    p = sub.add_parser("case-detail", help="案例详情")
    p.add_argument("--type", required=True, choices=["ptal", "qwal"], help="案例类型：ptal=普通案例 qwal=权威案例")
    p.add_argument("--id", help="案例 ID")
    p.add_argument("--ah", help="案号")
    p.set_defaults(func=cmd_case_detail)

    # ── regulation ──
    p = sub.add_parser("regulation", help="法规关键词检索")
    p.add_argument("query", nargs="?", default="", help="关键词")
    p.add_argument("--search-mode", choices=["and", "or"], default="and")
    p.add_argument("--fgmc", help="法规名称过滤")
    p.add_argument("--effect1", action="append", help="效力级别（可多次指定）")
    p.add_argument("--sxx", action="append", help="时效性（可多次指定）")
    p.add_argument("--fbrq-start", help="发布日期起点 yyyy-MM-dd")
    p.add_argument("--fbrq-end", help="发布日期终点")
    p.add_argument("--ssrq-start", help="实施日期起点")
    p.add_argument("--ssrq-end", help="实施日期终点")
    p.add_argument("--top-k", type=int, help="返回条数上限（默认10，最大50）")
    p.set_defaults(func=cmd_regulation)

    # ── regulation-detail ──
    p = sub.add_parser("regulation-detail", help="法规详情")
    p.add_argument("--fgid", help="法规 ID")
    p.add_argument("--name", help="法规名称")
    p.add_argument("--reference-date", help="参考日期 yyyy-MM-dd")
    p.set_defaults(func=cmd_regulation_detail)

    # ── enterprise ──
    p = sub.add_parser("enterprise", help="企业名称检索")
    p.add_argument("query", help="企业名称或股票简称")
    p.add_argument("--num", type=int, default=2, help="返回条数（默认2，最大50）")
    p.set_defaults(func=cmd_enterprise)

    # ── enterprise-detail ──
    p = sub.add_parser("enterprise-detail", help="企业详情")
    p.add_argument("--id", help="企业 ID")
    p.add_argument("--credit-code", help="统一社会信用代码")
    p.set_defaults(func=cmd_enterprise_detail)

    # ── raw ──
    p = sub.add_parser("raw", help="原始 JSON 输出（调试用）")
    p.add_argument("endpoint", help="API 路径，如 /open/law_vector_search")
    p.add_argument("query", help="查询内容")
    p.add_argument("--extra", help="额外 JSON 参数")
    p.add_argument("--get", action="store_true", help="使用 GET 方法")
    p.add_argument("--no-cache", action="store_true", help="跳过缓存，强制重新请求")
    p.set_defaults(func=cmd_raw)

    # ── check-update ──
    p = sub.add_parser("check-update", help="检查版本更新")
    p.set_defaults(func=cmd_check_update)

    # ── do-update ──
    p = sub.add_parser("do-update", help="下载更新本 skill 的文件（不影响其他目录）")
    p.set_defaults(func=cmd_do_update)

    # ── archive-list ──
    p = sub.add_parser("archive-list", help="列出历史检索记录")
    p.add_argument("--keyword", help="按关键词筛选（匹配查询内容或端点）")
    p.add_argument("--limit", type=int, default=20, help="显示条数（默认20）")
    p.set_defaults(func=cmd_archive_list)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 自动版本检测（check-update / do-update 子命令除外）
    if args.command not in ("check-update", "do-update", "archive-list"):
        try:
            _updater.check_for_update()
        except Exception:
            pass

    args.func(args)


if __name__ == "__main__":
    main()
