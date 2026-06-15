#!/usr/bin/env python3
"""元典法条检索 API 命令行工具（开放平台版）"""

import argparse
import hashlib
import json
import os
import re
import shutil
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
CURRENT_VERSION = "1.7.4"

# 通用更新模块实例（从 SKILL.md frontmatter 自动推导更新地址）
_updater = SkillUpdater.from_skill_md(SKILL_ROOT)


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


def load_strategy():
    """从环境变量或 .env 文件加载检索策略，默认 balanced"""
    strategy = os.environ.get("YD_STRATEGY", "").strip().lower()
    if strategy:
        return strategy
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "YD_STRATEGY":
                    return v.strip().lower()
    return "balanced"


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


YD_BASE = "https://ydzk.chineselaw.com"


def _normalize_url(raw):
    """将相对 URL 转为完整 URL，已经是完整的直接返回"""
    if not raw:
        return None
    if raw.startswith("http"):
        return raw
    return f"{YD_BASE}{raw}"


def _enrich_source_urls(endpoint, response):
    """从 API 响应中提取/构造来源 URL 列表"""
    urls = []
    if not isinstance(response, dict):
        return urls

    # ── 法条语义检索 law_vector_search ──
    if endpoint == "/open/law_vector_search":
        for item in _iter_items(response, "extra.fatiao"):
            fgid = item.get("fgid", "")
            num = item.get("num", "")
            title = item.get("fgtitle", "")
            if fgid:
                url = f"{YD_BASE}/zxt/statuteDetail/detailPage/{fgid}"
                if num:
                    tid = num.replace("第", "").replace("条", "")
                    url += f"?text={tid}"
                urls.append({"title": f"{title} {num}", "type": "法条", "url": url})

    # ── 法条详情 rh_ft_detail ──
    elif endpoint == "/open/rh_ft_detail":
        data = response.get("data")
        if isinstance(data, dict):
            raw = data.get("url", "")
            url = _normalize_url(raw)
            if url:
                urls.append({"title": data.get("title", ""), "type": "法条", "url": url})

    # ── 法条关键词检索 rh_ft_search ──
    elif endpoint == "/open/rh_ft_search":
        for item in _iter_items(response, "data"):
            raw = item.get("url", "")
            url = _normalize_url(raw)
            if not url:
                fgid = item.get("fgid", "")
                if fgid:
                    tid = item.get("tid", "")
                    url = f"{YD_BASE}/zxt/statuteDetail/detailPage/{fgid}"
                    if tid:
                        url += f"?text={tid}"
            if url:
                urls.append({"title": item.get("title", item.get("ftmc", "")), "type": "法条", "url": url})

    # ── 法规详情 rh_fg_detail ──
    elif endpoint == "/open/rh_fg_detail":
        data = response.get("data")
        if isinstance(data, dict):
            raw = data.get("url", "")
            url = _normalize_url(raw)
            fgid = data.get("id") or data.get("fgid", "")
            if not url and fgid:
                url = f"{YD_BASE}/zxt/statuteDetail/detailPage/{fgid}"
            if url:
                urls.append({"title": data.get("title", data.get("fgmc", "")), "type": "法规", "url": url})

    # ── 案例语义检索 case_vector_search ──
    elif endpoint == "/open/case_vector_search":
        for item in _iter_items(response, "extra.wenshu"):
            scid = item.get("scid", "")
            if scid:
                urls.append({
                    "title": f"{item.get('title', '')}（{item.get('ah', '')}）",
                    "type": "案例",
                    "url": f"{YD_BASE}/ydzk/caseDetail/case/{scid}",
                })

    # ── 案例关键词检索 rh_ptal_search ──
    elif endpoint == "/open/rh_ptal_search":
        for item in _iter_items(response, "data.lst"):
            raw = item.get("url", "")
            url = _normalize_url(raw)
            cid = item.get("id", "")
            if not url and cid:
                url = f"{YD_BASE}/ydzk/caseDetail/case/{cid}"
            if url:
                urls.append({
                    "title": f"{item.get('title', '')}（{item.get('ah', '')}）",
                    "type": "案例",
                    "url": url,
                })

    # ── 案例详情 rh_case_details ──
    elif endpoint == "/open/rh_case_details":
        for item in _iter_items(response, "data"):
            raw = item.get("url", "")
            url = _normalize_url(raw)
            if url:
                urls.append({
                    "title": f"{item.get('title', '')}（{item.get('ah', '')}）",
                    "type": "案例",
                    "url": url,
                })

    # ── 企业检索 rh_enterpriseSearch ──
    elif endpoint == "/open/rh_enterpriseSearch":
        for item in _iter_items(response, "data"):
            raw = item.get("url", "")
            url = _normalize_url(raw)
            if url:
                urls.append({"title": item.get("企业名称", ""), "type": "企业", "url": url})

    # ── 企业基本信息 rh_enterpriseBaseInfo ──
    elif endpoint == "/open/rh_enterpriseBaseInfo":
        data = response.get("data")
        if isinstance(data, dict):
            raw = data.get("url", "")
            url = _normalize_url(raw)
            if url:
                urls.append({"title": data.get("企业名称", ""), "type": "企业", "url": url})

    return urls


def _iter_items(response, dotpath):
    """按 dotpath（如 'extra.fatiao'）从 response 中迭代列表"""
    obj = response
    for key in dotpath.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return []
    if isinstance(obj, list):
        return obj
    return []


def _archive_save(endpoint, payload, response):
    """将查询和响应归档"""
    ARCHIVE_DIR.mkdir(exist_ok=True)
    fingerprint = _query_fingerprint(endpoint, payload)
    filename = _make_archive_name(endpoint, payload)
    path = ARCHIVE_DIR / filename

    source_urls = _enrich_source_urls(endpoint, response)

    record = {
        "id": filename.replace(".json", ""),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "endpoint": endpoint,
        "query": payload,
        "fingerprint": fingerprint,
        "source_urls": source_urls,
        "response": response,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
    return str(path)


def _archive_write_report(archive_path, formatted_text, cost_label,
                          no_report=False, no_cwd_report=False):
    """根据归档记录 + 格式化文本生成结构化 .md 报告，落盘到 archive + 用户工作目录。

    Args:
        archive_path: archive/*.json 的绝对路径（cache hit 时为 None，函数直接返回）
        formatted_text: cmd_* 已经格式化好的 Markdown 内容（即 stdout 主输出）
        cost_label: 例如 "10 积分" / "50 积分"
        no_report: True 时整个跳过（不写 archive / 也不写 CWD）
        no_cwd_report: True 时只跳过 CWD 副本

    Returns:
        (archive_md_path, cwd_md_path_or_None)
        - archive 路径永远写入（如果 archive_path 有效且 no_report=False）
        - CWD 路径 best-effort，失败 stderr 警告并返回 None
    """
    if no_report or not archive_path:
        return None, None

    json_path = Path(archive_path)
    record = json.loads(json_path.read_text("utf-8"))

    # 提取 query_summary: 从文件名扣除时间戳部分 (e.g. "20260419_152314_民法典.json" -> "民法典")
    stem = json_path.stem
    parts = stem.split("_", 2)
    query_summary = parts[2] if len(parts) >= 3 else stem

    # 提取 query 关键字段，拼成可读字符串
    query_str_parts = []
    for key in ("query", "keyword", "qw", "fgmc", "name", "ah"):
        val = record.get("query", {}).get(key, "")
        if val:
            query_str_parts.append(f"{key}={val}")
    query_keyword_str = " · ".join(query_str_parts) if query_str_parts else "(无关键词)"

    # 引用来源：按 type 分组
    source_urls = record.get("source_urls", []) or []
    if source_urls:
        grouped = {}
        for su in source_urls:
            grouped.setdefault(su.get("type", "其他"), []).append(su)
        sources_lines = []
        for type_name, items in grouped.items():
            sources_lines.append(f"**{type_name}（{len(items)}）**")
            sources_lines.append("")
            for su in items:
                title = su.get("title", "")
                url = su.get("url", "")
                if url:
                    sources_lines.append(f"- [{title}]({url})")
                else:
                    sources_lines.append(f"- {title}")
            sources_lines.append("")
        sources_md = "\n".join(sources_lines).rstrip()
    else:
        sources_md = "_（本次检索无引用来源）_"

    # 拼接完整报告
    timestamp = record.get("timestamp", "")
    md_content = (
        f"# 检索报告 · {query_summary}\n"
        f"\n"
        f"## 元信息\n"
        f"\n"
        f"- 检索时间：{timestamp}\n"
        f"- 检索关键词：{query_keyword_str}\n"
        f"- 积分消耗：{cost_label}\n"
        f"- 报告 ID：`{stem}`\n"
        f"- 原始数据：`archive/{json_path.name}`\n"
        f"- 数据来源：元典开放平台 open.chineselaw.com\n"
        f"\n"
        f"## 检索结果\n"
        f"\n"
        f"{formatted_text.rstrip()}\n"
        f"\n"
        f"## 引用来源\n"
        f"\n"
        f"{sources_md}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"*本报告由 yuandian-law-search 技能自动生成于 {timestamp}*\n"
    )

    # 1) archive 副本（必写）
    archive_md_path = json_path.with_suffix(".md")
    archive_md_path.write_text(md_content, "utf-8")

    # 2) CWD 副本（best-effort，--no-cwd-report 时跳过）
    #    优先用 yd-run 透传的用户原始工作目录（YD_USER_CWD），
    #    退而求其次用 Python 当前工作目录（Path.cwd() 在 yd-run 内部会被 cd 改成 skill 根）
    cwd_md_str = None
    if not no_cwd_report:
        cwd_target = os.environ.get("YD_USER_CWD") or str(Path.cwd())
        try:
            cwd_md_path = Path(cwd_target) / archive_md_path.name
            cwd_md_path.write_text(md_content, "utf-8")
            cwd_md_str = str(cwd_md_path)
        except OSError as e:
            print(
                f"警告：报告副本写入工作目录失败 ({e})，仅 archive/ 副本可用",
                file=sys.stderr,
            )

    return str(archive_md_path), cwd_md_str


def api_post(endpoint, body, use_cache=True):
    """发送 POST 请求到元典开放平台 API（支持归档查重）

    Returns:
        (result, cached, archive_path) 三元组
        - cached: True 表示命中 archive，未发起实际请求
        - archive_path: cache miss 时为新落盘的 .json 路径；cache hit 时为 None
    """
    if use_cache:
        cached, _ = _archive_lookup(endpoint, body)
        if cached is not None:
            return cached, True, None

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

    archive_path = None
    if use_cache:
        archive_path = _archive_save(endpoint, body, result)
    return result, False, archive_path


def api_get(endpoint, params=None, use_cache=True):
    """发送 GET 请求到元典开放平台 API（支持归档查重）

    Returns:
        (result, cached, archive_path) 三元组（语义同 api_post）
    """
    if use_cache:
        cached, _ = _archive_lookup(endpoint, params or {})
        if cached is not None:
            return cached, True, None

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

    archive_path = None
    if use_cache:
        archive_path = _archive_save(endpoint, params or {}, result)
    return result, False, archive_path


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


# ── 企业分项列表类型映射 ────────────────────────────────────

ENTERPRISE_LIST_TYPES = {
    "invest": ("/open/rh_enterpriseOutInvest", "对外投资"),
    "brand": ("/open/rh_enterpriseBrand", "商标"),
    "patent": ("/open/rh_enterprisePatent", "专利"),
    "soft-right": ("/open/rh_enterpriseSoftRight", "软件著作权"),
    "works-right": ("/open/rh_enterpriseWorksRight", "作品著作权"),
    "icp": ("/open/rh_enterpriseIcp", "网站备案"),
    "change-info": ("/open/rh_enterpriseChangeInfo", "变更记录"),
    "writ-agg": ("/open/rh_enterpriseWritAgg", "涉诉信息统计"),
    "writ-list": ("/open/rh_enterpriseWritList", "涉诉文书"),
    "court-session": ("/open/rh_enterpriseCourtSessionNotice", "开庭公告"),
    "court-notice": ("/open/rh_enterpriseCourtNotice", "法院公告"),
    "execution": ("/open/rh_enterpriseExecutions", "失信被执行人"),
    "executed-person": ("/open/rh_enterpriseExecutedPerson", "被执行人"),
    "frozen-equity": ("/open/rh_enterpriseFrozenEquity", "股权冻结"),
    "punishment": ("/open/rh_enterprisePunishment", "行政处罚"),
    "pledge": ("/open/rh_enterprisePledge", "股权出质"),
    "guaranty": ("/open/rh_enterpriseGuaranty", "对外担保"),
    "abnormal": ("/open/rh_enterpriseAbnormalOperation", "经营异常"),
    "tax": ("/open/rh_enterpriseCorporateTax", "欠税公告"),
    "serious-illegal": ("/open/rh_enterpriseSeriousIllegal", "严重违法"),
}


def format_enterprise_list_results(data, label):
    """格式化企业分项列表结果为 Markdown"""
    if not data:
        return f"未找到{label}相关记录。"
    if isinstance(data, dict):
        data = [data]

    lines = []
    for i, item in enumerate(data, 1):
        # 尝试从常见字段中提取标题
        title = ""
        for key in ("name", "名称", "企业名称", "商标名称", "专利名称", "软件名称",
                     "作品名称", "域名", "案号", "公告类型", "变更项目",
                     "被执行人名称", "处罚决定书文号", "出质人", "担保人",
                     "列入原因", "欠税税种", "违法行为"):
            val = item.get(key, "")
            if val:
                title = str(val)
                break
        lines.append(f"### {i}. {title or label}")
        lines.append("")

        meta = []
        for key, label_text in item.items():
            val = item.get(key, "")
            if val and key not in ("id",) and str(val).strip():
                meta.append(f"{key}: {val}")
        if meta:
            # 限制显示字段数量，避免输出过长
            for m in meta[:8]:
                lines.append(f"- {m}")
            lines.append("")

    return "\n".join(lines)


def format_hall_detect_results(data):
    """格式化幻觉检测结果为 Markdown"""
    if not data:
        return "检测结果为空。"

    lines = []

    # 高亮文本
    highlighted = data.get("highlighted_text", "")
    if highlighted:
        lines.append("## 检测文本（标注版）")
        lines.append("")
        lines.append(highlighted)
        lines.append("")

    # 法规检测结果
    regulations = data.get("regulations", [])
    if regulations:
        lines.append(f"## 法规检测（共 {len(regulations)} 条）")
        lines.append("")
        for i, reg in enumerate(regulations, 1):
            name = reg.get("name", "")
            clause = reg.get("clause", "")
            law_exists = reg.get("law_exists")
            exists_label = "存在" if law_exists else "不存在（疑似幻觉）"
            lines.append(f"### {i}. {name} {clause} — {exists_label}")
            lines.append("")

            if reg.get("content"):
                lines.append(f"> {reg['content']}")
                lines.append("")

            if reg.get("url"):
                lines.append(f"链接: {reg['url']}")
                lines.append("")

            sc = reg.get("semantic_compare", {})
            if sc and not sc.get("skipped"):
                conclusion = sc.get("结论", "")
                similarity = sc.get("语义相似度", "")
                lines.append(f"语义比对: {conclusion}（相似度: {similarity}）")
                if sc.get("说明"):
                    lines.append(f"说明: {sc['说明']}")
                if sc.get("要点"):
                    for point in sc["要点"]:
                        lines.append(f"- {point}")
                lines.append("")

    # 案例检测结果
    cases = data.get("cases", [])
    if cases:
        lines.append(f"## 案例检测（共 {len(cases)} 条）")
        lines.append("")
        for i, case in enumerate(cases, 1):
            name = case.get("name", "")
            case_number = case.get("case_number", "")
            lines.append(f"### {i}. {name}（{case_number}）")
            lines.append("")

            meta = []
            if case.get("case_type"):
                meta.append(f"案件类型: {case['case_type']}")
            if case.get("court"):
                meta.append(f"法院: {case['court']}")
            if case.get("judgment_date"):
                meta.append(f"裁判日期: {case['judgment_date']}")
            if meta:
                lines.append(" | ".join(meta))
                lines.append("")

            if case.get("url"):
                lines.append(f"链接: {case['url']}")
                lines.append("")
            if case.get("basic_facts"):
                text = str(case["basic_facts"])
                if len(text) > 300:
                    text = text[:300] + "..."
                lines.append(f"基本事实: {text}")
                lines.append("")
            if case.get("judgment_key_points"):
                text = str(case["judgment_key_points"])
                if len(text) > 300:
                    text = text[:300] + "..."
                lines.append(f"裁判要点: {text}")
                lines.append("")

    if not regulations and not cases:
        lines.append("未检测到法规或案例引用。")

    return "\n".join(lines)


# ── ingest：从 MCP / 外部数据源消费 JSON，走与直接 API 相同的归档流程 ──────


def _ingest_extract_single_or_list(response):
    """data 是单个 dict 或 list 时，归一为 list。"""
    data = response.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _ingest_extract_lst_or_list(response):
    """data 是 {lst: [...]} 或裸 list 时，归一为 list。"""
    raw = response.get("data")
    if isinstance(raw, dict):
        return raw.get("lst", raw.get("list", []))
    if isinstance(raw, list):
        return raw
    return []


def _ingest_format_raw_json(response):
    """未知 endpoint 的兜底：把整个 response 包装成 JSON 代码块。"""
    return f"```json\n{json.dumps(response, ensure_ascii=False, indent=2)}\n```"


# endpoint → (类别, data 提取函数, formatter)
# - "类别" 用于 consolidate 分组（和 ENDPOINT_CATEGORY 一致）
# - 提取函数：response → 列表/字典
# - formatter：列表/字典 → Markdown 字符串
INGEST_ROUTING = {
    # ── 法条（4 个）──
    "/open/law_vector_search": (
        "law",
        lambda r: r.get("extra", {}).get("fatiao", r.get("data", [])),
        format_law_results,
    ),
    "/open/rh_ft_search": (
        "law",
        lambda r: r.get("data", []),
        format_law_results,
    ),
    "/open/rh_ft_detail": (
        "law",
        _ingest_extract_single_or_list,
        format_law_results,
    ),
    # ── 法规（2 个）──
    "/open/rh_fg_search": (
        "regulation",
        lambda r: r.get("data", []),
        format_regulation_results,
    ),
    "/open/rh_fg_detail": (
        "regulation",
        _ingest_extract_single_or_list,
        format_regulation_results,
    ),
    # ── 案例（4 个）──
    "/open/case_vector_search": (
        "case",
        lambda r: r.get("extra", {}).get("wenshu", r.get("data", [])),
        format_case_results,
    ),
    "/open/rh_ptal_search": (
        "case",
        _ingest_extract_lst_or_list,
        format_case_results,
    ),
    "/open/rh_qwal_search": (
        "case",
        _ingest_extract_lst_or_list,
        format_case_results,
    ),
    "/open/rh_case_details": (
        "case",
        _ingest_extract_single_or_list,
        format_case_results,
    ),
    # ── 企业主接口（4 个）──
    "/open/rh_enterpriseSearch": (
        "enterprise",
        lambda r: r.get("data", []),
        format_enterprise_results,
    ),
    "/open/rh_company_info": (
        "enterprise",
        _ingest_extract_lst_or_list,
        format_enterprise_results,
    ),
    "/open/rh_company_detail": (
        "enterprise",
        _ingest_extract_single_or_list,
        format_enterprise_results,
    ),
    "/open/rh_enterpriseBaseInfo": (
        "enterprise",
        _ingest_extract_single_or_list,
        format_enterprise_results,
    ),
    # ── 企业分项列表（22 个，自动从 endpoint 推断 label）──
    "/open/rh_enterpriseOutInvest": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "对外投资"),
    ),
    "/open/rh_enterpriseBrand": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "商标"),
    ),
    "/open/rh_enterprisePatent": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "专利"),
    ),
    "/open/rh_enterpriseSoftRight": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "软件著作权"),
    ),
    "/open/rh_enterpriseWorksRight": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "作品著作权"),
    ),
    "/open/rh_enterpriseIcp": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "网站备案"),
    ),
    "/open/rh_enterpriseChangeInfo": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "变更记录"),
    ),
    "/open/rh_enterpriseWritAgg": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "涉诉信息"),
    ),
    "/open/rh_enterpriseWritList": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "涉诉文书"),
    ),
    "/open/rh_enterpriseCourtSessionNotice": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "开庭公告"),
    ),
    "/open/rh_enterpriseCourtNotice": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "法院公告"),
    ),
    "/open/rh_enterpriseExecutions": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "失信被执行人"),
    ),
    "/open/rh_enterpriseExecutedPerson": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "被执行人"),
    ),
    "/open/rh_enterpriseFrozenEquity": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "股权冻结"),
    ),
    "/open/rh_enterprisePunishment": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "行政处罚"),
    ),
    "/open/rh_enterprisePledge": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "股权出质"),
    ),
    "/open/rh_enterpriseGuaranty": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "对外担保"),
    ),
    "/open/rh_enterpriseAbnormalOperation": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "经营异常"),
    ),
    "/open/rh_enterpriseCorporateTax": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "欠税公告"),
    ),
    "/open/rh_enterpriseSeriousIllegal": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "严重违法"),
    ),
    "/open/rh_enterpriseAnnualReport": (
        "enterprise",
        _ingest_extract_lst_or_list,
        lambda data: format_enterprise_list_results(data, "企业年报"),
    ),
    # ── 特殊 ──
    "/open/hall_detect": (
        "other",
        lambda r: r.get("data", r),
        format_hall_detect_results,
    ),
    "/open/rh_enterpriseAggregationSummary": (
        "other",
        lambda r: r.get("data", r),
        _ingest_format_raw_json,
    ),
}


def cmd_ingest(args):
    """从 MCP / 外部 JSON 源消费数据，走与直接 API 相同的归档 + .md 流程。

    使用场景：agent 调 mcp__yuandian__* 工具拿到 JSON，把 JSON 喂给本命令，
    即可走完归档 + 结构化报告 + 后续 consolidate 全流程。
    """
    # 1. 读 JSON
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"错误：--input 文件不存在：{input_path}", file=sys.stderr)
            sys.exit(1)
        try:
            response = json.loads(input_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"错误：JSON 解析失败：{e}", file=sys.stderr)
            sys.exit(1)
    else:
        # 从 stdin 读
        if sys.stdin.isatty():
            print("错误：--input 未指定且 stdin 是 TTY，请提供 --input <file> 或通过 pipe 喂 JSON", file=sys.stderr)
            print("  示例：cat result.json | yd-run ingest --query \"违约金\" --endpoint /open/law_vector_search", file=sys.stderr)
            sys.exit(1)
        try:
            response = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            print(f"错误：stdin JSON 解析失败：{e}", file=sys.stderr)
            sys.exit(1)

    if not isinstance(response, dict):
        print(f"错误：JSON 顶层必须是 dict（API 响应格式），实际是 {type(response).__name__}", file=sys.stderr)
        sys.exit(1)

    # 1.5 识别 MCP 响应（带 jsonrpc 包装层），提取 structuredContent.data 作为内层响应
    # MCP structuredContent = {requestId, ..., data: {msg, code, extra: {...}, ...}}
    # 直接 API response = {code, data: {...}, extra: {...}, message, status}
    # 取 sc.data 后与直接 API 格式对齐（都含 extra.fatiao 等字段）
    if "jsonrpc" in response and "result" in response:
        sc = response["result"].get("structuredContent")
        if sc and "data" in sc:
            print("检测到 MCP 响应（jsonrpc 包装），已提取 result.structuredContent.data", file=sys.stderr)
            response = sc["data"]
        elif sc:
            print("检测到 MCP 响应（jsonrpc 包装），但 structuredContent 无 data 字段", file=sys.stderr)
            response = sc

    # 2. 路由：按 endpoint 找提取函数和 formatter
    if args.endpoint not in INGEST_ROUTING:
        # 未知 endpoint：兜底用 raw JSON 包装
        category = "other"
        data = response.get("data", response)
        formatted = _ingest_format_raw_json(response)
        print(f"提示：endpoint {args.endpoint} 未在 INGEST_ROUTING 中，按 raw JSON 包装处理", file=sys.stderr)
    else:
        category, extract_fn, format_fn = INGEST_ROUTING[args.endpoint]
        data = extract_fn(response)
        formatted = format_fn(data)

    # 3. 构造 archive 记录
    # payload 用 {"query": query} 作为占位，与直接 API 的 query 字段对齐
    payload = {"query": args.query}
    fingerprint = _query_fingerprint(args.endpoint, payload)
    source_urls = _enrich_source_urls(args.endpoint, response)
    filename = _make_archive_name(args.endpoint, payload)
    json_path = ARCHIVE_DIR / filename
    record = {
        "id": filename.replace(".json", ""),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "endpoint": args.endpoint,
        "query": payload,
        "fingerprint": fingerprint,
        "source_urls": source_urls,
        "response": response,
        "ingest": True,  # 标记：从 MCP / 外部源消费，非直接 API
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")

    # 4. 走 _archive_write_report 生成 .md（archive + CWD）
    archive_md, cwd_md = _archive_write_report(
        str(json_path), formatted, args.cost,
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )

    # 5. 打印 footer
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


# ── 子命令处理 ──────────────────────────────────────────────


def _resolve_keyword_search_mode(args, expanded):
    """关键词类检索默认 AND；扩展检索在未显式指定时切 OR。"""
    if args.search_mode:
        return args.search_mode
    return "or" if expanded else "and"


def _print_footer(cost_label=None, archive_md=None, cwd_md=None):
    """打印调用成本提示 + 报告路径

    Args:
        cost_label: 自定义成本字符串（默认走 COST_PER_CALL）
        archive_md: archive 报告路径
        cwd_md: 工作目录报告路径（写入失败时为 None）
    """
    if cost_label is None:
        cost_label = COST_PER_CALL
    print(f"\n--- {cost_label} ---")
    if archive_md:
        print(f"报告已保存：")
        print(f"  - archive: {archive_md}")
        if cwd_md:
            print(f"  - 工作目录: {cwd_md}")


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

    result, cached, archive_path = api_post("/open/law_vector_search", body)
    data = result.get("extra", {}).get("fatiao", result.get("data", []))
    formatted = format_law_results(data)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


def cmd_keyword(args):
    """法条关键词检索"""
    # 处理 --expand 扩展关键词
    keyword = args.query
    expanded = False
    if args.expand:
        expanded_terms = [t.strip() for t in args.expand.split(",") if t.strip()]
        if expanded_terms:
            keyword = f"{keyword} {' '.join(expanded_terms)}"
            expanded = True
            # 有扩展词时自动切换为 OR 模式（如果用户未显式指定 search_mode）
            if not args.search_mode:
                print(f"[扩展检索] 已将关键词扩展为: {keyword}（OR 模式）")
            else:
                print(f"[扩展检索] 已将关键词扩展为: {keyword}")

    search_mode = _resolve_keyword_search_mode(args, expanded)
    body = {"keyword": keyword}
    if search_mode:
        body["search_mode"] = search_mode
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
    result, cached, archive_path = api_post("/open/rh_ft_search", body)
    data = result.get("data", [])
    formatted = format_law_results(data)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


def cmd_detail(args):
    """法条详情检索"""
    body = {"fgmc": args.query, "ftnum": args.ft_name}
    if args.reference_date:
        body["refer_date"] = args.reference_date
    result, cached, archive_path = api_post("/open/rh_ft_detail", body)
    data = result.get("data")
    items = [data] if isinstance(data, dict) else (data or [])
    formatted = format_law_results(items)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


def cmd_case(args):
    """案例关键词检索"""
    body = {}
    # 处理 --expand 扩展关键词
    query = args.query
    expanded = False
    if args.expand:
        expanded_terms = [t.strip() for t in args.expand.split(",") if t.strip()]
        if expanded_terms:
            query = f"{query} {' '.join(expanded_terms)}" if query else " ".join(expanded_terms)
            expanded = True
            # 有扩展词时自动切换为 OR 模式（如果用户未显式指定 search_mode）
            if not args.search_mode:
                print(f"[扩展检索] 已将关键词扩展为: {query}（OR 模式）")
            else:
                print(f"[扩展检索] 已将关键词扩展为: {query}")

    search_mode = _resolve_keyword_search_mode(args, expanded)
    if query:
        body["qw"] = query
    if search_mode:
        body["search_mode"] = search_mode
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

    result, cached, archive_path = api_post(endpoint, body)
    raw = result.get("data")
    data = raw.get("lst", []) if isinstance(raw, dict) else (raw or [])
    total = raw.get("total") if isinstance(raw, dict) else None
    header = ""
    if total is not None:
        header = f"共 {total} 条结果，显示前 {len(data)} 条\n"
        print(header, end="")
    formatted = format_case_results(data)
    print(formatted)
    report_body = (header + formatted) if header else formatted
    archive_md, cwd_md = _archive_write_report(
        archive_path, report_body, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


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
    for date_field in ("jarq_start", "jarq_end"):
        val = getattr(args, date_field, None)
        if val:
            wenshu_filter[date_field] = val
    if wenshu_filter:
        body["wenshu_filter"] = wenshu_filter

    result, cached, archive_path = api_post("/open/case_vector_search", body)
    data = result.get("extra", {}).get("wenshu", result.get("data", []))
    formatted = format_case_results(data)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


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
    result, cached, archive_path = api_get("/open/rh_case_details", params)
    data = result.get("data", {})
    if isinstance(data, list):
        formatted = format_case_results(data)
    elif isinstance(data, dict):
        formatted = format_case_results([data])
    else:
        formatted = ""
    if formatted:
        print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


def cmd_regulation(args):
    """法规关键词检索"""
    body = {}
    # 处理 --expand 扩展关键词
    keyword = args.query
    expanded = False
    if args.expand:
        expanded_terms = [t.strip() for t in args.expand.split(",") if t.strip()]
        if expanded_terms:
            keyword = f"{keyword} {' '.join(expanded_terms)}"
            expanded = True
            if not args.search_mode:
                print(f"[扩展检索] 已将关键词扩展为: {keyword}（OR 模式）")
            else:
                print(f"[扩展检索] 已将关键词扩展为: {keyword}")

    search_mode = _resolve_keyword_search_mode(args, expanded)
    if keyword:
        body["keyword"] = keyword
    if search_mode:
        body["search_mode"] = search_mode
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
    result, cached, archive_path = api_post("/open/rh_fg_search", body)
    data = result.get("data", [])
    formatted = format_regulation_results(data)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


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
    result, cached, archive_path = api_post("/open/rh_fg_detail", body)
    data = result.get("data", {})
    if isinstance(data, list):
        formatted = format_regulation_results(data)
    elif isinstance(data, dict):
        formatted = format_regulation_results([data])
    else:
        formatted = ""
    if formatted:
        print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


def cmd_enterprise(args):
    """企业名称检索"""
    params = {"name": args.query}
    if args.num:
        params["num"] = args.num
    result, cached, archive_path = api_get("/open/rh_company_info", params)
    raw = result.get("data")
    data = raw.get("lst", []) if isinstance(raw, dict) else (raw or [])
    total = raw.get("total") if isinstance(raw, dict) else None
    header = ""
    if total is not None:
        header = f"共 {total} 条结果，显示前 {len(data)} 条\n"
        print(header, end="")
    formatted = format_enterprise_results(data)
    print(formatted)
    report_body = (header + formatted) if header else formatted
    archive_md, cwd_md = _archive_write_report(
        archive_path, report_body, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


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
    result, cached, archive_path = api_get("/open/rh_company_detail", params)
    data = result.get("data", {})
    formatted = format_enterprise_results(data)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


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


def cmd_backfill_urls(_args):
    """回填现有 archive 记录的 source_urls"""
    if not ARCHIVE_DIR.exists():
        print("archive 目录不存在。")
        return

    files = sorted(ARCHIVE_DIR.glob("*.json"))
    updated = 0
    skipped = 0

    for f in files:
        if f.name == "version_check.json":
            continue
        try:
            record = json.loads(f.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        endpoint = record.get("endpoint", "")
        response = record.get("response", {})
        existing = record.get("source_urls")

        new_urls = _enrich_source_urls(endpoint, response)

        if new_urls and new_urls != existing:
            record["source_urls"] = new_urls
            # 保持字段顺序：把 source_urls 放在 response 之前
            ordered = {}
            for k in ("id", "timestamp", "endpoint", "query", "fingerprint", "source_urls", "response"):
                if k in record:
                    ordered[k] = record[k]
            f.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), "utf-8")
            updated += 1
            print(f"  已更新: {f.name} ({len(new_urls)} 条 URL)")
        else:
            skipped += 1

    print(f"\n完成: 更新 {updated} 个文件，跳过 {skipped} 个文件")


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
        result, cached, archive_path = api_get(endpoint, params, use_cache=use_cache)
    else:
        result, cached, archive_path = api_post(endpoint, body, use_cache=use_cache)
    formatted = json.dumps(result, ensure_ascii=False, indent=2)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, f"```json\n{formatted}\n```\n", "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(archive_md=archive_md, cwd_md=cwd_md)


def cmd_strategy(args):
    """显示当前检索策略"""
    labels = {"balanced": "均衡", "economical": "省钱", "aggressive": "激进"}
    s = load_strategy()
    print(f"当前策略：{labels.get(s, s)}（{s}）")


def cmd_hall_detect(args):
    """法规/法条/案例幻觉检测"""
    body = {"text": args.text}
    use_cache = not args.no_cache
    result, cached, archive_path = api_post("/open/hall_detect", body, use_cache=use_cache)
    data = result.get("data", result)
    formatted = format_hall_detect_results(data)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "50 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(cost_label="本次调用消耗 50 积分", archive_md=archive_md, cwd_md=cwd_md)


def cmd_enterprise_search(args):
    """企业检索（轻量候选列表）"""
    params = {"name": args.name}
    if args.top_k:
        params["top_k"] = args.top_k
    use_cache = not args.no_cache
    result, cached, archive_path = api_get("/open/rh_enterpriseSearch", params, use_cache=use_cache)
    data = result.get("data", [])
    if isinstance(data, dict):
        data = [data]
    formatted = format_enterprise_results(data)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, formatted, "1 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(cost_label="本次调用消耗 1 积分", archive_md=archive_md, cwd_md=cwd_md)


def cmd_enterprise_base(args):
    """企业基本信息"""
    params = {}
    if args.id:
        params["id"] = args.id
    if args.uscc:
        params["uscc"] = args.uscc
    if not params:
        print("错误：请提供 --id 或 --uscc 参数", file=sys.stderr)
        sys.exit(1)
    use_cache = not args.no_cache
    result, cached, archive_path = api_get("/open/rh_enterpriseBaseInfo", params, use_cache=use_cache)
    data = result.get("data", {})
    formatted = json.dumps(data, ensure_ascii=False, indent=2)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, f"```json\n{formatted}\n```\n", "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(cost_label="本次调用消耗 10 积分", archive_md=archive_md, cwd_md=cwd_md)


def cmd_enterprise_summary(args):
    """企业聚合总览"""
    body = {}
    if args.id:
        body["id"] = args.id
    if args.uscc:
        body["uscc"] = args.uscc
    if not body:
        print("错误：请提供 --id 或 --uscc 参数", file=sys.stderr)
        sys.exit(1)
    use_cache = not args.no_cache
    result, cached, archive_path = api_post("/open/rh_enterpriseAggregationSummary", body, use_cache=use_cache)
    data = result.get("data", {})
    formatted = json.dumps(data, ensure_ascii=False, indent=2)
    print(formatted)
    archive_md, cwd_md = _archive_write_report(
        archive_path, f"```json\n{formatted}\n```\n", "10 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(cost_label="本次调用消耗 10 积分", archive_md=archive_md, cwd_md=cwd_md)


def cmd_enterprise_list(args):
    """企业分项列表查询"""
    if args.type not in ENTERPRISE_LIST_TYPES:
        print(f"未知类型: {args.type}", file=sys.stderr)
        print(f"可用类型: {', '.join(ENTERPRISE_LIST_TYPES.keys())}", file=sys.stderr)
        sys.exit(1)

    endpoint, label = ENTERPRISE_LIST_TYPES[args.type]
    params = {"page": args.page, "size": args.size}
    if args.id:
        params["id"] = args.id
    if args.uscc:
        params["uscc"] = args.uscc
    if not args.id and not args.uscc:
        print("错误：请提供 --id 或 --uscc 参数", file=sys.stderr)
        sys.exit(1)
    use_cache = not args.no_cache
    result, cached, archive_path = api_get(endpoint, params, use_cache=use_cache)

    raw = result.get("data")
    if isinstance(raw, dict):
        items = raw.get("lst", raw.get("list", []))
        total = raw.get("total")
        header = ""
        if total is not None:
            header = f"共 {total} 条结果，当前第 {args.page} 页（每页 {args.size} 条）\n"
            print(header, end="")
    elif isinstance(raw, list):
        items = raw
        header = ""
    else:
        items = []
        header = ""

    formatted = format_enterprise_list_results(items, label)
    print(formatted)
    cost = 10 if args.type in ("writ-agg", "writ-list") else 5
    cost_label = f"本次调用消耗 {cost} 积分"
    report_body = (header + formatted) if header else formatted
    archive_md, cwd_md = _archive_write_report(
        archive_path, report_body, f"{cost} 积分",
        no_report=args.no_report, no_cwd_report=args.no_cwd_report,
    )
    _print_footer(cost_label=cost_label, archive_md=archive_md, cwd_md=cwd_md)


# ── consolidate：把多次 per-call 报告汇总成法律检索报告 ──────────────


ENDPOINT_CATEGORY = {
    "/open/law_vector_search": "法律依据",
    "/open/rh_ft_search": "法律依据",
    "/open/rh_ft_detail": "法律依据",
    "/open/case_vector_search": "司法案例",
    "/open/rh_ptal_search": "司法案例",
    "/open/rh_qwal_search": "司法案例",
    "/open/rh_case_details": "司法案例",
    "/open/rh_fg_search": "行政法规",
    "/open/rh_fg_detail": "行政法规",
}

CATEGORY_ORDER = ["法律依据", "司法案例", "行政法规"]
CATEGORY_HEADING = {
    "法律依据": "### 6.1 法律依据",
    "司法案例": "### 6.2 司法案例",
    "行政法规": "### 6.3 行政法规",
}
YUANDIAN_MD_PATTERN = re.compile(r"^\d{8}_\d{6}_.+\.md$")


def _consolidate_report_link(path):
    """返回可回溯的本地文件链接；失败时退回文件名。"""
    if not path:
        return ""
    try:
        return path.resolve().as_uri()
    except (OSError, ValueError):
        return path.name


def _consolidate_build_support_table(records, limit=12):
    """生成结论区的核心依据速查表，让读者先看到支撑材料地图。"""
    role_by_category = {
        "法律依据": "确认规范依据",
        "司法案例": "类案裁判观点",
        "行政法规": "补充监管规则",
    }
    rows = []
    for record in records[:limit]:
        category = record.get("category") or "其他"
        role = role_by_category.get(category, "核实或背景材料")
        md_path = record.get("md_path")
        md_link = _consolidate_report_link(md_path) if md_path else ""
        report_link = f"[查看底稿]({md_link})" if md_link else "（无底稿）"
        rows.append(
            f"| {category} | {record.get('query_summary', '')} | {role} | {report_link} |"
        )

    if not rows:
        return "_（本次报告未纳入可展示的检索底稿）_"

    table = "\n".join([
        "| 类型 | 检索方向 | 对结论的作用 | 底稿 |",
        "|------|----------|--------------|------|",
        *rows,
    ])
    extra_count = max(len(records) - limit, 0)
    if extra_count:
        table += f"\n\n_另有 {extra_count} 条底稿见第七节检索明细。_"
    return table


def _consolidate_slugify(s):
    """把标题转成安全的目录名：保留中文，去掉文件不安全字符，多空白压成 _。"""
    if not s:
        return ""
    s = re.sub(r'[/\\:*?"<>|？]', '_', s)
    s = re.sub(r'\s+', '_', s.strip())
    return s[:80]


def _consolidate_resolve_includes(include_str, cwd):
    """解析 --include 逗号分隔的查询子串，匹配 CWD 中所有 yuandian 报告 .md。

    Returns: list of (md_path, json_path_or_None, query_summary) tuples，按时间戳升序。
    """
    patterns = [p.strip() for p in include_str.split(",") if p.strip()]
    if not patterns:
        return []

    archive_dir = SKILL_ROOT / "archive"
    matched = []

    for md_path in cwd.glob("*.md"):
        if not YUANDIAN_MD_PATTERN.match(md_path.name):
            continue
        for pattern in patterns:
            if pattern in md_path.name:
                json_path = archive_dir / md_path.name.replace(".md", ".json")
                json_p = json_path if json_path.exists() else None
                # 提取 query_summary（从文件名扣除时间戳）
                stem = md_path.stem
                parts = stem.split("_", 2)
                query_summary = parts[2] if len(parts) >= 3 else stem
                matched.append((md_path, json_p, query_summary))
                break

    return sorted(matched, key=lambda x: x[0].name)


def _consolidate_extract_body(md_path):
    """从 per-call .md 提取 '## 检索结果' 到 '## 引用来源' 之间的正文。

    同时去掉 per-call 报告里的 '共 X 条结果' 提示行（consolidate 中冗余，
    因为检索明细表里已经能看到每条的命中数）。
    """
    try:
        content = md_path.read_text("utf-8")
    except OSError:
        return ""
    start_marker = "## 检索结果"
    end_marker = "## 引用来源"
    start_idx = content.find(start_marker)
    if start_idx < 0:
        return content
    end_idx = content.find(end_marker, start_idx)
    if end_idx < 0:
        end_idx = len(content)
    body = content[start_idx + len(start_marker):end_idx]
    # 去掉 per-call 的"共 X 条结果..."提示行
    body = re.sub(r"^共\s+\d+\s+条结果[，,]\s*显示前\s+\d+\s+条\s*\n+", "", body, flags=re.MULTILINE)
    body = re.sub(r"^共\s+\d+\s+条结果，当前第\s+\d+\s+页（每页\s+\d+\s+条）\s*\n+", "", body, flags=re.MULTILINE)
    return body.strip()


def _consolidate_extract_meta(json_path):
    """从 per-call .json 提取元信息（时间/接口）。"""
    if json_path is None:
        return {}
    try:
        record = json.loads(json_path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        "endpoint": record.get("endpoint", ""),
        "timestamp": record.get("timestamp", ""),
    }


def _consolidate_extract_cost_from_md(md_path):
    """从 per-call .md 提取 '积分消耗：X 积分' 字段。"""
    try:
        content = md_path.read_text("utf-8")
    except OSError:
        return "?"
    m = re.search(r"积分消耗：(\S+\s*\S+?)\s*$", content, re.MULTILINE)
    return m.group(1) if m else "?"


def cmd_consolidate(args):
    """把多次检索的 per-call 报告汇总成一份法律检索报告，并归类到项目子目录"""
    cwd = Path(os.environ.get("YD_USER_CWD") or str(Path.cwd()))
    include_str = args.include
    if not include_str:
        print("错误：--include 必填，逗号分隔的查询子串（如 '违约金,高空抛物'）", file=sys.stderr)
        sys.exit(1)

    pairs = _consolidate_resolve_includes(include_str, cwd)
    if not pairs:
        print(f"错误：未在 {cwd} 中匹配到任何 yuandian 报告", file=sys.stderr)
        print(f"  - --include：{include_str}", file=sys.stderr)
        print(f"  - 匹配规则：*<子串>*.md 且符合 <8位时间戳>_<6位时间戳>_<查询>.md 命名", file=sys.stderr)
        sys.exit(1)

    # 解析项目子目录名
    title = args.title or "法律检索报告"
    if args.project:
        project_name = args.project
    elif args.title:
        project_name = _consolidate_slugify(args.title) or f"untitled-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    else:
        project_name = f"untitled-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    project_dir = SKILL_ROOT / "archive" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # 移动 per-call .md 和 .json 到项目子目录
    # - .md: 从 archive/ 根目录的"v1.4.0 副本"移动（v1.4.0 同时也写了 CWD 副本，工作副本不丢）
    #        老 per-call（v1.4.0 之前的 .json 没有 .md 副本）则从 CWD 复制
    # - .json: 从 archive/ 根目录移动
    moved_md = 0
    copied_md = 0
    moved_json = 0
    project_pairs = []
    for md_path, json_path, query_summary in pairs:
        project_md = project_dir / md_path.name
        if md_path.resolve() == project_md.resolve():
            pass  # 已经在子目录里（重复运行 consolidate）
        else:
            archive_md = SKILL_ROOT / "archive" / md_path.name
            if archive_md.exists() and archive_md.resolve() != project_md.resolve():
                shutil.move(str(archive_md), str(project_md))
                moved_md += 1
            else:
                # archive/ 根没有 .md 副本（v1.4.0 之前的旧 per-call），从 CWD 复制
                shutil.copy2(md_path, project_md)
                copied_md += 1
        if json_path and json_path.exists():
            project_json = project_dir / json_path.name
            if json_path.resolve() != project_json.resolve():
                shutil.move(str(json_path), str(project_json))
                moved_json += 1
            json_path = project_json
        elif (project_dir / md_path.name.replace(".md", ".json")).exists():
            json_path = project_dir / md_path.name.replace(".md", ".json")
        else:
            json_path = None
        project_pairs.append((project_md, json_path, query_summary))
    pairs = project_pairs

    # 按 endpoint 类别分组
    by_category = {cat: [] for cat in CATEGORY_ORDER}
    other_records = []
    all_records = []

    for md_path, json_path, query_summary in pairs:
        meta = _consolidate_extract_meta(json_path) if json_path else {}
        endpoint = meta.get("endpoint", "")
        category_key = ENDPOINT_CATEGORY.get(endpoint)
        body = _consolidate_extract_body(md_path)
        record = {
            "md_path": md_path,
            "json_path": json_path,
            "query_summary": query_summary,
            "endpoint": endpoint,
            "timestamp": meta.get("timestamp", ""),
            "cost": _consolidate_extract_cost_from_md(md_path),
            "body": body,
            "category": category_key or "其他",
        }
        if category_key in by_category:
            by_category[category_key].append(record)
        else:
            other_records.append(record)
        all_records.append(record)

    # 渲染报告
    timestamp = datetime.now().isoformat(timespec="seconds")

    # 检索目的
    if args.purpose:
        purpose_section = args.purpose
    else:
        topics = [q for _, _, q in pairs]
        topics_str = "、".join(topics)
        purpose_section = f"本次检索围绕 **{topics_str}** 等方向展开。"

    # 检索结论
    if args.conclusion:
        conclusion_section = args.conclusion
    else:
        conclusion_section = (
            "（未传入 --conclusion。面向客户、法官或内部复核交付时，"
            "请在此补写一句话结论：可否主张、主要依据、关键风险。）"
        )

    risks_section = args.risks or (
        "（请结合第四节分析补充：不利类案、法律适用分歧、效力时点、"
        "地域裁判差异、证据缺口或仍需人工复核的问题。）"
    )
    next_actions_section = args.next_actions or (
        "（请补充可执行步骤：补强证据、追加检索、调整诉讼请求、"
        "准备抗辩或向客户确认事实。）"
    )
    support_table = _consolidate_build_support_table(all_records)

    # 检索结果（按类别）
    result_sections = []
    for cat in CATEGORY_ORDER:
        records = by_category[cat]
        if not records:
            continue
        heading = CATEGORY_HEADING[cat]
        bodies = "\n\n---\n\n".join(r["body"] for r in records if r["body"])
        if bodies:
            result_sections.append(f"{heading}\n\n{bodies}")

    if other_records:
        other_bodies = "\n\n---\n\n".join(r["body"] for r in other_records if r["body"])
        if other_bodies:
            result_sections.append(f"### 6.4 其他核实材料\n\n{other_bodies}")

    # 检索明细表（链接指向项目子目录里的副本，json 仍用 file://）
    detail_rows = []
    for i, (md_path, json_path, query_summary) in enumerate(pairs, 1):
        meta = _consolidate_extract_meta(json_path) if json_path else {}
        ts = meta.get("timestamp", "")[:16].replace("T", " ")
        endpoint = meta.get("endpoint", "").replace("/open/", "")
        cost = _consolidate_extract_cost_from_md(md_path)
        md_link = _consolidate_report_link(md_path) if md_path.exists() else md_path.name
        if json_path and json_path.exists():
            json_link = _consolidate_report_link(json_path)
        else:
            json_link = ""
        report_links = f"[md]({md_link})"
        report_links += f" · [json]({json_link})" if json_link else " · （无 .json）"
        detail_rows.append(
            f"| {i} | {ts} | {query_summary} | `{endpoint}` | {cost} | {report_links} |"
        )
    detail_table = "\n".join(detail_rows)

    # 拼装
    md_content = (
        f"# 法律检索报告 · {title}\n"
        f"\n"
        f"> 生成时间：{timestamp}\n"
        f"> 检索主体：AI Agent / yuandian-law-search\n"
        f"> 检索平台：元典开放平台 open.chineselaw.com\n"
        f"> 引用检索明细：{len(pairs)} 条\n"
        f"> 项目包：`archive/{project_name}/`\n"
        f"\n"
        f"## 一、案情简介\n"
        f"\n"
        f"{args.case}\n"
        f"\n"
        f"## 二、检索目的与问题\n"
        f"\n"
        f"{purpose_section}\n"
        f"\n"
        f"## 三、检索结论\n"
        f"\n"
        f"### 3.1 一句话定性\n"
        f"\n"
        f"{conclusion_section}\n"
        f"\n"
        f"### 3.2 核心依据速查\n"
        f"\n"
        f"{support_table}\n"
        f"\n"
        f"### 3.3 风险与不确定性\n"
        f"\n"
        f"{risks_section}\n"
        f"\n"
        f"### 3.4 后续行动\n"
        f"\n"
        f"{next_actions_section}\n"
        f"\n"
        f"## 四、分析与判断\n"
        f"\n"
        f"{args.analysis}\n"
        f"\n"
        f"## 五、检索思路与方法\n"
        f"\n"
        f"{args.strategy}\n"
        f"\n"
        f"### 5.1 检索范围\n"
        f"\n"
        f"| 项目 | 内容 |\n"
        f"|------|------|\n"
        f"| 纳入规则 | `{include_str}` |\n"
        f"| 检索平台 | 元典开放平台 |\n"
        f"| 生成时间 | {timestamp} |\n"
        f"| 项目包 | `archive/{project_name}/` |\n"
        f"\n"
        f"## 六、检索结果\n"
        f"\n"
        f"{chr(10).join(result_sections) if result_sections else '_（本次检索未匹配到法律/案例/法规类别）_'}\n"
        f"\n"
        f"## 七、检索明细\n"
        f"\n"
        f"| # | 时间 | 检索词 | 接口 | 积分 | 报告 |\n"
        f"|---|------|--------|------|------|------|\n"
        f"{detail_table}\n"
        f"\n"
        f"---\n"
        f"\n"
        f"*本报告由 yuandian-law-search 技能 `consolidate` 子命令生成*\n"
    )

    # 主交付物：写入项目子目录
    report_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_法律检索报告.md"
    project_report_path = project_dir / report_filename
    project_report_path.write_text(md_content, "utf-8")

    # 同时在 CWD 也写一份（除非 --output 指定）
    cwd_copy = None
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_content, "utf-8")
    else:
        cwd_copy = cwd / report_filename
        cwd_copy.write_text(md_content, "utf-8")

    print(f"已生成项目包：{project_dir}")
    print(f"  - 项目名称：{project_name}")
    print(f"  - 法律检索报告：{project_report_path}")
    if cwd_copy:
        print(f"  - CWD 副本：{cwd_copy}")
    print(f"  - per-call .md：移动 {moved_md} 份 + 复制 {copied_md} 份到项目子目录（CWD 保留工作副本）")
    print(f"  - per-call .json：移动 {moved_json} 份到项目子目录（archive 根目录已清理）")
    print(f"  - 检索明细：{len(pairs)} 条")
    for cat in CATEGORY_ORDER:
        n = len(by_category[cat])
        if n:
            print(f"  - {cat}：{n} 条")
    if other_records:
        print(f"  - 其他（未分类）：{len(other_records)} 条")


# ── 参数解析 ──────────────────────────────────────────────


def _add_law_filters(parser):
    """法条通用筛选参数"""
    parser.add_argument("--effect1", action="append", help="效力级别（可多次指定）")
    parser.add_argument("--sxx", action="append", help="时效性（可多次指定）")


def build_parser():
    _strategy = load_strategy()

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
  %(prog)s hall-detect "根据《中华人民共和国数据保护法》第35条规定..."
  %(prog)s enterprise-search "华为" --top-k 5
  %(prog)s enterprise-base --uscc "9144030071526726XG"
  %(prog)s enterprise-summary --uscc "9144030071526726XG"
  %(prog)s enterprise-list --type writ-list --uscc "9144030071526726XG" --page 1 --size 10
"""
    )
    parser.add_argument("--no-report", action="store_true",
                        help="跳过 .md 检索报告生成（archive + CWD），仅写 archive JSON")
    parser.add_argument("--no-cwd-report", action="store_true",
                        help="仅跳过工作目录副本，仍写 archive/ 报告（默认同时写两份）")
    sub = parser.add_subparsers(dest="command")

    # ── search ──
    p = sub.add_parser("search", help="法条语义检索")
    p.add_argument("query", help="自然语言问题")
    _add_law_filters(p)
    p.add_argument("--rewrite-flag", action="store_true", default=True, help="是否改写查询（默认 true）")
    p.add_argument("--no-rewrite", action="store_false", dest="rewrite_flag", help="禁用查询改写")
    p.add_argument("--return-num", type=int, default=20 if _strategy == "economical" else 45, help="返回数量")
    p.add_argument("--law-start", help="法条生效起始日期 yyyy-MM-dd")
    p.add_argument("--law-end", help="法条生效结束日期 yyyy-MM-dd")
    p.set_defaults(func=cmd_search)

    # ── keyword ──
    p = sub.add_parser("keyword", help="法条关键词检索")
    p.add_argument("query", help="关键词，多个用空格分隔")
    p.add_argument("--expand", help="扩展关键词，逗号分隔（如 '知识产权管辖,级别管辖'），自动追加到原始查询")
    p.add_argument("--fgmc", help="法规名称过滤")
    p.add_argument("--effect1", action="append", help="效力级别（可多次指定）")
    p.add_argument("--sxx", action="append", help="时效性（可多次指定）")
    p.add_argument("--search-mode", choices=["and", "or"], default=None, help="多关键词逻辑；默认 and，带 --expand 且未指定时自动 or")
    p.add_argument("--fbrq-start", help="发布日期起点 yyyy-MM-dd")
    p.add_argument("--fbrq-end", help="发布日期终点")
    p.add_argument("--ssrq-start", help="实施日期起点")
    p.add_argument("--ssrq-end", help="实施日期终点")
    p.add_argument("--top-k", type=int, default=20 if _strategy == "aggressive" else None, help="返回条数上限")
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
    p.add_argument("--expand", help="扩展关键词，逗号分隔（如 '质量纠纷,违约责任'），自动追加到原始查询")
    p.add_argument("--search-mode", choices=["and", "or"], default=None, help="多关键词逻辑；默认 and，带 --expand 且未指定时自动 or")
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
    p.add_argument("--top-k", type=int, default=20 if _strategy == "aggressive" else None, help="返回条数上限")
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
    p.add_argument("--return-num", type=int, default=20 if _strategy == "economical" else 45, help="返回数量")
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
    p.add_argument("query", help="关键词")
    p.add_argument("--expand", help="扩展关键词，逗号分隔，自动追加到原始查询")
    p.add_argument("--search-mode", choices=["and", "or"], default=None, help="多关键词逻辑；默认 and，带 --expand 且未指定时自动 or")
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

    # ── ingest ──
    p = sub.add_parser("ingest", help="从 MCP / 外部 JSON 源消费数据，走与直接 API 相同的归档 + .md 流程")
    p.add_argument("--query", required=True, help="查询关键词（用于文件名 + 元信息）")
    p.add_argument("--endpoint", required=True, help="对应 API 路径，如 /open/law_vector_search；用于 routing 到对应 formatter")
    p.add_argument("--input", help="包含 API 响应 JSON 的文件路径；省略则从 stdin 读")
    p.add_argument("--cost", default="10 积分", help="成本标签（默认 '10 积分'）")
    p.add_argument("--no-report", action="store_true", help="跳过 .md 报告生成")
    p.add_argument("--no-cwd-report", action="store_true", help="仅跳过工作目录副本")
    p.set_defaults(func=cmd_ingest)

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

    # ── backfill-urls ──
    p = sub.add_parser("backfill-urls", help="回填现有 archive 的 source_urls")
    p.set_defaults(func=cmd_backfill_urls)

    # ── strategy ──
    p = sub.add_parser("strategy", help="显示当前检索策略")
    p.set_defaults(func=cmd_strategy)

    # ── consolidate ──
    p = sub.add_parser("consolidate", help="把多次检索的 per-call 报告汇总成一份法律检索报告")
    p.add_argument("--title", help="报告标题（默认 '法律检索报告'）")
    p.add_argument("--project", help="项目子目录名（默认从 --title slugify；用于 archive/<project>/ 归类）")
    p.add_argument("--case", required=True, help="案情简介（一、案情简介）")
    p.add_argument("--strategy", required=True, help="检索思路与方法（五、检索思路与方法）")
    p.add_argument("--analysis", required=True, help="分析与判断（四、分析与判断）")
    p.add_argument("--include", required=True, help="要包含的 per-call 报告（逗号分隔的查询子串）")
    p.add_argument("--purpose", help="检索目的与问题（二、可选；不传则基于检索词自动推断）")
    p.add_argument("--conclusion", help="检索结论（三、强烈建议传入；不传则保留补写提示）")
    p.add_argument("--risks", help="风险与不确定性（三、可选；用于 3.3）")
    p.add_argument("--next-actions", help="后续行动（三、可选；用于 3.4）")
    p.add_argument("--output", help="输出文件路径（默认同时写 CWD 和 archive/<project>/；指定则只写到指定路径）")
    p.set_defaults(func=cmd_consolidate)

    # ── hall-detect ──
    p = sub.add_parser("hall-detect", help="法规/法条/案例幻觉检测")
    p.add_argument("text", help="待检测文本")
    p.add_argument("--no-cache", action="store_true", help="跳过缓存，强制重新请求")
    p.set_defaults(func=cmd_hall_detect)

    # ── enterprise-search ──
    p = sub.add_parser("enterprise-search", help="企业检索（轻量候选列表，1积分）")
    p.add_argument("name", help="企业名称检索词")
    p.add_argument("--top-k", type=int, help="返回条数上限（默认10，范围1-50）")
    p.add_argument("--no-cache", action="store_true", help="跳过缓存，强制重新请求")
    p.set_defaults(func=cmd_enterprise_search)

    # ── enterprise-base ──
    p = sub.add_parser("enterprise-base", help="企业基本信息")
    p.add_argument("--id", help="企业 ID")
    p.add_argument("--uscc", help="统一社会信用代码")
    p.add_argument("--no-cache", action="store_true", help="跳过缓存，强制重新请求")
    p.set_defaults(func=cmd_enterprise_base)

    # ── enterprise-summary ──
    p = sub.add_parser("enterprise-summary", help="企业聚合总览")
    p.add_argument("--id", help="企业 ID")
    p.add_argument("--uscc", help="统一社会信用代码")
    p.add_argument("--no-cache", action="store_true", help="跳过缓存，强制重新请求")
    p.set_defaults(func=cmd_enterprise_summary)

    # ── enterprise-list ──
    p = sub.add_parser("enterprise-list", help="企业分项列表查询")
    p.add_argument("--type", required=True,
                   choices=list(ENTERPRISE_LIST_TYPES.keys()),
                   help="查询类型")
    p.add_argument("--id", help="企业 ID")
    p.add_argument("--uscc", help="统一社会信用代码")
    p.add_argument("--page", type=int, default=1, help="页码（默认 1）")
    p.add_argument("--size", type=int, default={"economical": 10, "aggressive": 50}.get(_strategy, 30), help="每页条数（默认 30，economical 10，aggressive 50）")
    p.add_argument("--no-cache", action="store_true", help="跳过缓存，强制重新请求")
    p.set_defaults(func=cmd_enterprise_list)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 自动版本检测（check-update / do-update 子命令除外）
    if args.command not in ("check-update", "do-update", "archive-list", "backfill-urls", "strategy"):
        try:
            _updater.check_for_update()
        except Exception:
            pass

    args.func(args)


if __name__ == "__main__":
    main()
