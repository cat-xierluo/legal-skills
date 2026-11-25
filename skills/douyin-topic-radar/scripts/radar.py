#!/usr/bin/env python3
"""抖音选题雷达：生成浏览器采集脚本、归一化结果、计算信号、产出短名单。

只用 Python 标准库。所有写入都落在用户指定的 workspace，不触碰浏览器配置，
不发起任何网络请求；真正的抓取由 ego-browser 执行生成的驱动脚本完成。
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
RAW_SCHEMA = "douyin-topic-radar/raw/1"
OBSERVATION_SCHEMA = "douyin-topic-radar/observation/1"
SIGNALS_SCHEMA = "douyin-topic-radar/signals/1"
SHORTLIST_SCHEMA = "douyin-topic-radar/shortlist/1"
DEFAULT_WORKSPACE = Path.home() / ".local/state/douyin-topic-radar"
MODES = ("comprehensive", "latest", "top")
MODE_LABELS = {
    "comprehensive": "综合排序深滚",
    "latest": "最新发布 + 一周内",
    "top": "最多点赞",
}
CAVEATS = [
    "所有数字都是浏览器可见的观察值：受登录状态、个性化推荐、滚动深度和采集时点影响，不是平台官方流量数据。",
    "抖音不公开搜索量，这里用结果条数、互动分布和近期占比近似话题热度，不能换算成曝光或播放量。",
    "只采集本次滚动能到达的卡片，样本不等于该关键词的全量作品。",
    "作品 ID 来自页面组件数据；读不到 ID 的卡片只参与聚合，不进入短名单，也无法下载。",
    "搜索结果页的作者粉丝数、获赞数常为 0，报告按缺失显示；需要准确值时另行访问作者主页核对。",
]


def slugify(text: str) -> str:
    kept = []
    for char in text.strip():
        if char.isalnum() or char in "-_":
            kept.append(char.lower())
        else:
            kept.append("-")
    slug = re.sub(r"-+", "-", "".join(kept)).strip("-")
    return slug or "topic"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise SystemExit(f"{path}:{number} 不是合法 JSON：{error}") from error
    return records


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * ratio
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values: list[float]) -> dict:
    present = [value for value in values if isinstance(value, (int, float))]
    return {
        "n": len(present),
        "p50": round(percentile(present, 0.5) or 0),
        "p75": round(percentile(present, 0.75) or 0),
        "p90": round(percentile(present, 0.9) or 0),
        "max": round(max(present)) if present else None,
        "mean": round(sum(present) / len(present)) if present else None,
    }


def escape_cell(text: str | None, limit: int = 60) -> str:
    if not text:
        return "-"
    flattened = re.sub(r"\s+", " ", str(text)).strip()
    if len(flattened) > limit:
        flattened = flattened[: limit - 1] + "…"
    return flattened.replace("|", "\\|")


def format_int(value) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return f"{int(value):,}"


def format_ratio(value) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.0f}%"


def format_optional(value) -> str:
    """搜索页作者粉丝/获赞常为 0，按缺失处理，避免把空值读成真实 0。"""
    if not isinstance(value, (int, float)) or value <= 0:
        return "-"
    return f"{int(value):,}"


def format_local_time(value: str | None) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M %Z")


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


def build_driver(
    keyword: str,
    mode: str,
    rounds: int,
    out_path: Path,
    page: str,
    space_id: int | None,
    finish: bool,
    scroll_step: int,
) -> str:
    template = (ASSETS / "collect_driver.mjs").read_text(encoding="utf-8")
    collector = (ASSETS / "collect_cards.js").read_text(encoding="utf-8")
    replacements = {
        "__SPACE_ID__": json.dumps(space_id),
        "__KEYWORD__": json.dumps(keyword, ensure_ascii=False),
        "__MODE__": json.dumps(mode),
        "__ROUNDS__": str(rounds),
        "__SCROLL_STEP__": str(scroll_step),
        "__OUT__": json.dumps(str(out_path), ensure_ascii=False),
        "__PAGE__": json.dumps(page),
        "__FINISH__": "1" if finish else "0",
        "__COLLECTOR__": json.dumps(collector, ensure_ascii=False),
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    return template


def command_driver(args: argparse.Namespace) -> int:
    if args.mode not in MODES:
        raise SystemExit(f"未知模式 {args.mode}，可选：{', '.join(MODES)}")
    keyword = args.keyword.strip()
    if not keyword:
        raise SystemExit("关键词不能为空")
    workspace = Path(args.workspace).expanduser()
    raw_dir = workspace / "raw"
    raw_path = raw_dir / f"{slugify(keyword)}-{args.mode}.json"
    driver_dir = workspace / "drivers"
    driver_dir.mkdir(parents=True, exist_ok=True)
    driver_path = driver_dir / f"{slugify(keyword)}-{args.mode}.mjs"
    source = build_driver(
        keyword=keyword,
        mode=args.mode,
        rounds=args.rounds,
        out_path=raw_path.resolve(),
        page=args.page,
        space_id=args.space_id,
        finish=args.finish,
        scroll_step=args.scroll_step,
    )
    driver_path.write_text(source, encoding="utf-8")
    print(
        json.dumps(
            {
                "driver": str(driver_path),
                "raw": str(raw_path),
                "keyword": keyword,
                "mode": args.mode,
                "rounds": args.rounds,
                "run": f'ego-browser nodejs < "{driver_path}"',
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


# --------------------------------------------------------------------------
# normalize
# --------------------------------------------------------------------------


def load_raw_files(paths: list[str]) -> list[dict]:
    files: list[Path] = []
    for pattern in paths:
        matched = sorted(glob.glob(pattern, recursive=True))
        if not matched and Path(pattern).is_file():
            matched = [pattern]
        files.extend(Path(item) for item in matched)
    raws = []
    seen = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != RAW_SCHEMA:
            raise SystemExit(f"{path} 不是 {RAW_SCHEMA} 采集文件")
        raws.append(payload)
    if not raws:
        raise SystemExit("没有找到采集文件；先运行 radar.py driver 并执行生成的脚本")
    return raws


def command_normalize(args: argparse.Namespace) -> int:
    raws = load_raw_files(args.raw)
    reference = now_utc()
    observations: dict[str, dict] = {}
    unlinked = 0
    related: list[str] = []
    keywords: list[str] = []
    modes: list[str] = []
    collected_at = None

    for raw in raws:
        keyword = raw.get("keyword") or ""
        mode = raw.get("mode") or ""
        if keyword and keyword not in keywords:
            keywords.append(keyword)
        if mode and mode not in modes:
            modes.append(mode)
        collected_at = max(
            collected_at or "", raw.get("collected_at") or ""
        )
        for term in raw.get("related_searches") or []:
            if term and term not in related:
                related.append(term)
        for card in raw.get("cards") or []:
            aweme_id = card.get("aweme_id")
            if not aweme_id:
                unlinked += 1
                continue
            create_time = card.get("create_time")
            age_days = (
                round((reference.timestamp() - create_time) / 86400, 2)
                if isinstance(create_time, (int, float))
                else None
            )
            record = {
                "schema": OBSERVATION_SCHEMA,
                "aweme_id": aweme_id,
                "url": card.get("url")
                or f"https://www.douyin.com/video/{aweme_id}",
                "desc": card.get("desc") or "",
                "author": card.get("author") or {},
                "stats": card.get("stats") or {},
                "duration_s": card.get("duration_s"),
                "create_time": create_time,
                "create_time_iso": (
                    datetime.fromtimestamp(create_time, timezone.utc).isoformat()
                    if isinstance(create_time, (int, float))
                    else None
                ),
                "age_days": age_days,
                "hashtags": card.get("hashtags") or [],
                "is_ads": bool(card.get("is_ads")),
                "is_slides": bool(card.get("is_slides")),
                "source": card.get("source"),
                "keywords": [keyword] if keyword else [],
                "modes": [mode] if mode else [],
                "hits": 1,
            }
            existing = observations.get(aweme_id)
            if existing is None:
                observations[aweme_id] = record
                continue
            existing["hits"] = existing.get("hits", 0) + 1
            for field, value in (("keywords", keyword), ("modes", mode)):
                if value and value not in existing[field]:
                    existing[field].append(value)
            if not existing.get("create_time") and record.get("create_time"):
                existing["create_time"] = record["create_time"]
                existing["create_time_iso"] = record["create_time_iso"]
                existing["age_days"] = record["age_days"]

    ordered = sorted(
        observations.values(),
        key=lambda item: (
            -(item.get("stats", {}).get("digg") or 0),
            item.get("aweme_id") or "",
        ),
    )
    workspace = Path(args.workspace).expanduser()
    observations_path = workspace / "observations.jsonl"
    write_jsonl(observations_path, ordered)

    meta = {
        "schema": "douyin-topic-radar/meta/1",
        "topic": args.topic or "、".join(keywords),
        "keywords": keywords,
        "modes": modes,
        "raw_files": [str(Path(path).resolve()) for path in args.raw],
        "collected_at": collected_at or reference.isoformat(),
        "normalized_at": reference.isoformat(),
        "observations": len(ordered),
        "unlinked_cards": unlinked,
        "related_searches": related,
        "raw_card_total": sum(len(raw.get("cards") or []) for raw in raws),
    }
    write_json(workspace / "meta.json", meta)
    print(
        json.dumps(
            {
                "observations": len(ordered),
                "unlinked_cards": unlinked,
                "keywords": keywords,
                "modes": modes,
                "related_searches": len(related),
                "out": str(observations_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


# --------------------------------------------------------------------------
# rank
# --------------------------------------------------------------------------


RECENCY_BUCKETS = (("7d", 7), ("30d", 30), ("90d", 90))
RECENCY_LABELS = {"7d": "≤7 天", "30d": "≤30 天", "90d": "≤90 天", ">90d": ">90 天"}


def recency_score(age_days) -> float:
    if age_days is None:
        return 0.3
    if age_days <= 7:
        return 1.0
    if age_days <= 30:
        return 0.7
    if age_days <= 90:
        return 0.4
    return 0.1


def compute_signals(
    observations: list[dict], meta: dict, topic: str
) -> dict:
    known_ages = [item["age_days"] for item in observations if item.get("age_days") is not None]
    buckets = {}
    for label, days in RECENCY_BUCKETS:
        count = sum(1 for age in known_ages if age <= days)
        buckets[label] = {
            "count": count,
            "ratio": round(count / len(known_ages), 4) if known_ages else None,
        }
    buckets[">90d"] = {
        "count": sum(1 for age in known_ages if age > 90),
        "ratio": (
            round(sum(1 for age in known_ages if age > 90) / len(known_ages), 4)
            if known_ages
            else None
        ),
    }

    stats = [item.get("stats") or {} for item in observations]
    engagement = {
        field: distribution([entry.get(field) for entry in stats])
        for field in ("digg", "comment", "collect", "share")
    }

    tag_counts: dict[str, list[int]] = {}
    for item in observations:
        digg = (item.get("stats") or {}).get("digg")
        for tag in item.get("hashtags") or []:
            tag_counts.setdefault(tag, []).append(
                digg if isinstance(digg, (int, float)) else 0
            )
    hashtags = sorted(
        (
            {
                "name": name,
                "count": len(values),
                "median_digg": round(percentile(values, 0.5) or 0),
            }
            for name, values in tag_counts.items()
        ),
        key=lambda item: (-item["count"], -item["median_digg"], item["name"]),
    )

    authors: dict[str, dict] = {}
    for item in observations:
        author = item.get("author") or {}
        key = author.get("uid") or author.get("nickname") or "未知作者"
        digg = (item.get("stats") or {}).get("digg")
        entry = authors.setdefault(
            key,
            {
                "nickname": author.get("nickname") or "未知作者",
                "follower_count": author.get("follower_count"),
                "total_favorited": author.get("total_favorited"),
                "videos": 0,
                "diggs": [],
            },
        )
        entry["videos"] += 1
        entry["diggs"].append(digg if isinstance(digg, (int, float)) else 0)
    author_rows = sorted(
        (
            {
                "nickname": entry["nickname"],
                "videos": entry["videos"],
                "follower_count": entry["follower_count"],
                "total_favorited": entry["total_favorited"],
                "median_digg": round(percentile(entry["diggs"], 0.5) or 0),
            }
            for entry in authors.values()
        ),
        key=lambda item: (-item["videos"], -item["median_digg"], item["nickname"]),
    )

    unique_authors = len({(item.get("author") or {}).get("nickname") for item in observations})
    return {
        "schema": SIGNALS_SCHEMA,
        "topic": topic,
        "generated_at": now_utc().isoformat(),
        "keywords": meta.get("keywords") or [],
        "modes": meta.get("modes") or [],
        "collected_at": meta.get("collected_at"),
        "observations": len(observations),
        "unique_authors": unique_authors,
        "unlinked_cards": meta.get("unlinked_cards", 0),
        "recency": {
            "known": len(known_ages),
            "unknown": len(observations) - len(known_ages),
            "buckets": buckets,
        },
        "engagement": engagement,
        "hashtags": hashtags,
        "authors": author_rows,
        "related_searches": meta.get("related_searches") or [],
        "caveats": CAVEATS,
    }


def topic_leads(signals: dict) -> list[str]:
    leads: list[str] = []
    recency = signals.get("recency", {}).get("buckets", {})
    ratio_30 = (recency.get("30d") or {}).get("ratio")
    if ratio_30 is not None and ratio_30 >= 0.5:
        leads.append(
            f"近 30 天作品占 {format_ratio(ratio_30)}，话题仍在持续更新，适合做时效型内容。"
        )
    elif ratio_30 is not None and ratio_30 < 0.2:
        leads.append(
            f"近 30 天作品仅占 {format_ratio(ratio_30)}，存量内容为主，适合做体系化长青选题。"
        )

    tags = signals.get("hashtags") or []
    strong = [tag for tag in tags if tag["count"] >= 3]
    if strong:
        top = strong[0]
        leads.append(
            f"「{top['name']}」出现 {top['count']} 次、互动中位数 {format_int(top['median_digg'])}，"
            "是样本里最集中的切入口。"
        )

    digg = (signals.get("engagement", {}).get("digg") or {}).get("p50") or 0
    collect = (signals.get("engagement", {}).get("collect") or {}).get("p50") or 0
    comment = (signals.get("engagement", {}).get("comment") or {}).get("p50") or 0
    if digg and collect / digg >= 0.5:
        leads.append(
            f"收藏中位数是点赞的 {collect / digg:.1f} 倍，收藏意愿强，适合清单、工具、避坑指南类选题。"
        )
    if digg and comment / digg >= 0.1:
        leads.append(
            f"评论中位数是点赞的 {comment / digg:.2f} 倍，讨论度高，适合争议点、答疑型选题。"
        )

    questions = [
        term
        for term in signals.get("related_searches") or []
        if any(word in term for word in ("如何", "怎么", "为什么", "哪些", "吗", "？", "?"))
    ]
    if questions:
        leads.append(
            "相关搜索里有明确的问题式需求：" + "、".join(f"「{term}」" for term in questions[:3]) + "。"
        )

    if not leads:
        leads.append("样本信号不足，建议扩大关键词或增加滚动轮次后重新判断。")
    return leads


def render_report(
    signals: dict, observations: list[dict], shortlist: list[dict] | None = None
) -> str:
    recency = signals["recency"]
    engagement = signals["engagement"]
    lines = [
        f"# {signals['topic']} · 抖音选题雷达",
        "",
        f"- 采集时间：{format_local_time(signals.get('collected_at'))}",
        f"- 关键词：{'、'.join(signals.get('keywords') or [])}",
        f"- 采集模式：{'、'.join(MODE_LABELS.get(m, m) for m in signals.get('modes') or [])}",
        f"- 样本：{signals['observations']} 条作品 / {signals['unique_authors']} 位作者",
        "",
        "## 口径与局限",
        "",
    ]
    lines.extend(f"- {caveat}" for caveat in CAVEATS)
    lines.append("")
    lines.append("## 概览")
    lines.append("")
    lines.append(
        table(
            ["指标", "数值"],
            [
                ["作品样本", format_int(signals["observations"])],
                ["去重作者", format_int(signals["unique_authors"])],
                ["点赞中位数", format_int(engagement["digg"]["p50"])],
                ["点赞 P90", format_int(engagement["digg"]["p90"])],
                ["评论中位数", format_int(engagement["comment"]["p50"])],
                ["收藏中位数", format_int(engagement["collect"]["p50"])],
                ["分享中位数", format_int(engagement["share"]["p50"])],
                ["无法读取 ID 的卡片", format_int(signals.get("unlinked_cards"))],
            ],
        )
    )
    lines.append("")
    lines.append("## 时间分布")
    lines.append("")
    lines.append(
        table(
            ["区间", "条数", "占已知发布时间样本"],
            [
                [
                    RECENCY_LABELS.get(label, label),
                    format_int(bucket["count"]),
                    format_ratio(bucket["ratio"]),
                ]
                for label, bucket in recency["buckets"].items()
            ]
            + [["未知", format_int(recency["unknown"]), "-"]],
        )
    )
    lines.append("")
    lines.append("## 互动分布")
    lines.append("")
    lines.append(
        table(
            ["指标", "样本", "中位数", "P75", "P90", "最大值", "均值"],
            [
                [
                    label,
                    format_int(engagement[field]["n"]),
                    format_int(engagement[field]["p50"]),
                    format_int(engagement[field]["p75"]),
                    format_int(engagement[field]["p90"]),
                    format_int(engagement[field]["max"]),
                    format_int(engagement[field]["mean"]),
                ]
                for label, field in (
                    ("点赞", "digg"),
                    ("评论", "comment"),
                    ("收藏", "collect"),
                    ("分享", "share"),
                )
            ],
        )
    )
    lines.append("")
    lines.append("## 高频话题标签")
    lines.append("")
    lines.append(
        table(
            ["标签", "出现次数", "点赞中位数"],
            [
                [escape_cell(tag["name"], 40), format_int(tag["count"]), format_int(tag["median_digg"])]
                for tag in (signals.get("hashtags") or [])[:15]
            ]
            or [["-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("## 主要创作者")
    lines.append("")
    lines.append(
        table(
            ["作者", "样本作品数", "粉丝", "获赞", "点赞中位数"],
            [
                [
                    escape_cell(author["nickname"], 30),
                    format_int(author["videos"]),
                    format_optional(author["follower_count"]),
                    format_optional(author["total_favorited"]),
                    format_int(author["median_digg"]),
                ]
                for author in (signals.get("authors") or [])[:12]
            ]
            or [["-", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("## 高互动作品")
    lines.append("")
    top = sorted(
        observations,
        key=lambda item: -((item.get("stats") or {}).get("digg") or 0),
    )[:20]
    lines.append(
        table(
            ["#", "作品", "作者", "点赞", "评论", "发布", "链接"],
            [
                [
                    str(index),
                    escape_cell(item.get("desc"), 40),
                    escape_cell((item.get("author") or {}).get("nickname"), 16),
                    format_int((item.get("stats") or {}).get("digg")),
                    format_int((item.get("stats") or {}).get("comment")),
                    f"{item['age_days']:.0f} 天前"
                    if isinstance(item.get("age_days"), (int, float))
                    else "-",
                    f"https://www.douyin.com/video/{item['aweme_id']}",
                ]
                for index, item in enumerate(top, start=1)
            ],
        )
    )
    lines.append("")
    lines.append("## 候选短名单")
    lines.append("")
    lines.append(
        table(
            ["#", "作品", "作者", "点赞", "评论", "发布", "链接"],
            [
                [
                    str(item["rank"]),
                    escape_cell(item.get("desc"), 40),
                    escape_cell(item.get("author"), 16),
                    format_int(item.get("digg")),
                    format_int(item.get("comment")),
                    f"{item['age_days']:.0f} 天前"
                    if isinstance(item.get("age_days"), (int, float))
                    else "-",
                    f"https://www.douyin.com/video/{item['aweme_id']}",
                ]
                for item in (shortlist or [])
            ]
            or [["-", "-", "-", "-", "-", "-", "-"]],
        )
    )
    lines.append("")
    lines.append("## 相关搜索")
    lines.append("")
    related = signals.get("related_searches") or []
    lines.append(
        "、".join(f"「{term}」" for term in related) if related else "本次未采集到相关搜索。"
    )
    lines.append("")
    lines.append("## 选题线索（机器初筛，需人工判断）")
    lines.append("")
    lines.extend(f"- {lead}" for lead in topic_leads(signals))
    lines.append("")
    return "\n".join(lines)


def command_rank(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser()
    observations = load_jsonl(workspace / "observations.jsonl")
    meta = json.loads((workspace / "meta.json").read_text(encoding="utf-8"))
    if not observations:
        raise SystemExit("observations.jsonl 为空，先完成采集与归一化")
    topic = args.topic or meta.get("topic") or "未命名主题"
    signals = compute_signals(observations, meta, topic)
    write_json(workspace / "signals.json", signals)
    shortlist = select_shortlist(observations, signals, args.top, args.per_author)
    report = render_report(signals, observations, shortlist)
    report_path = workspace / "candidates.md"
    report_path.write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "topic": topic,
                "observations": signals["observations"],
                "shortlist": len(shortlist),
                "signals": str(workspace / "signals.json"),
                "report": str(report_path),
                "leads": topic_leads(signals),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


# --------------------------------------------------------------------------
# shortlist
# --------------------------------------------------------------------------


def select_shortlist(
    observations: list[dict], signals: dict, top: int, per_author: int
) -> list[dict]:
    diggs = [
        (item.get("stats") or {}).get("digg")
        for item in observations
        if isinstance((item.get("stats") or {}).get("digg"), (int, float))
    ]
    digg_p50 = percentile(diggs, 0.5) or 0
    digg_p90 = percentile(diggs, 0.9) or 0
    spread = max(digg_p90 - digg_p50, 1)

    def score(item: dict) -> float:
        stats = item.get("stats") or {}
        digg = stats.get("digg") if isinstance(stats.get("digg"), (int, float)) else 0
        interaction = sum(
            stats.get(field) or 0
            for field in ("comment", "collect", "share")
            if isinstance(stats.get(field), (int, float))
        )
        digg_norm = max(0.0, min(1.0, (digg - digg_p50) / spread))
        return 0.55 * digg_norm + 0.2 * min(interaction / max(digg, 1), 1.0) + 0.25 * recency_score(
            item.get("age_days")
        )

    ranked = sorted(observations, key=lambda item: (-score(item), item["aweme_id"]))
    picked: list[dict] = []
    per_author_count: dict[str, int] = {}
    for item in ranked:
        author = (item.get("author") or {}).get("nickname") or "未知作者"
        if per_author_count.get(author, 0) >= per_author:
            continue
        per_author_count[author] = per_author_count.get(author, 0) + 1
        stats = item.get("stats") or {}
        picked.append(
            {
                "schema": SHORTLIST_SCHEMA,
                "rank": len(picked) + 1,
                "aweme_id": item["aweme_id"],
                "url": item.get("url")
                or f"https://www.douyin.com/video/{item['aweme_id']}",
                "desc": item.get("desc"),
                "author": (item.get("author") or {}).get("nickname"),
                "digg": stats.get("digg"),
                "comment": stats.get("comment"),
                "collect": stats.get("collect"),
                "age_days": item.get("age_days"),
                "hashtags": item.get("hashtags") or [],
                "score": round(score(item), 4),
                "reason": "点赞分位 + 互动深度 + 近期性加权，同一作者最多 "
                + str(per_author)
                + " 条",
            }
        )
        if len(picked) >= top:
            break
    return picked


def command_shortlist(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser()
    observations = load_jsonl(workspace / "observations.jsonl")
    signals_path = workspace / "signals.json"
    signals = (
        json.loads(signals_path.read_text(encoding="utf-8"))
        if signals_path.exists()
        else {}
    )
    picked = select_shortlist(observations, signals, args.top, args.per_author)
    write_json(workspace / "shortlist.json", picked)
    links_path = workspace / (args.links or "links.txt")
    links_path.write_text(
        "".join(f"{item['url']}\n" for item in picked), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "selected": len(picked),
                "shortlist": str(workspace / "shortlist.json"),
                "links": str(links_path),
                "authors": len({item["author"] for item in picked}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------


def command_verify(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser()
    errors: list[str] = []
    required = ["meta.json", "observations.jsonl", "signals.json", "candidates.md", "shortlist.json"]
    for name in required:
        if not (workspace / name).is_file():
            errors.append(f"缺少 {name}")
    if errors:
        for error in errors:
            print("FAIL " + error, file=sys.stderr)
        return 1

    observations = load_jsonl(workspace / "observations.jsonl")
    ids = [item.get("aweme_id") for item in observations]
    if len(ids) != len(set(ids)):
        errors.append("observations.jsonl 存在重复 aweme_id")
    if any(not item.get("aweme_id") for item in observations):
        errors.append("observations.jsonl 存在缺少 aweme_id 的记录")

    signals = json.loads((workspace / "signals.json").read_text(encoding="utf-8"))
    if signals.get("observations") != len(observations):
        errors.append(
            f"signals.json 记录 {signals.get('observations')} 条，实际 {len(observations)} 条"
        )

    shortlist = json.loads((workspace / "shortlist.json").read_text(encoding="utf-8"))
    id_set = set(ids)
    for item in shortlist:
        if item.get("aweme_id") not in id_set:
            errors.append(f"shortlist 引用了不存在的作品 {item.get('aweme_id')}")
        if not re.fullmatch(r"https://www\.douyin\.com/video/\d+", item.get("url") or ""):
            errors.append(f"shortlist 链接格式异常 {item.get('url')}")

    report = (workspace / "candidates.md").read_text(encoding="utf-8")
    for item in shortlist:
        if item["aweme_id"] not in report:
            errors.append(f"candidates.md 未包含短名单作品 {item['aweme_id']}")

    links_path = workspace / (args.links or "links.txt")
    if not links_path.is_file():
        errors.append(f"缺少 {links_path.name}")
    else:
        links = [
            line.strip()
            for line in links_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if len(links) != len(shortlist):
            errors.append(f"links.txt 有 {len(links)} 行，短名单有 {len(shortlist)} 条")
        for link in links:
            if not re.fullmatch(r"https://www\.douyin\.com/video/\d+", link):
                errors.append(f"links.txt 链接格式异常 {link}")

    if errors:
        for error in errors:
            print("FAIL " + error, file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "observations": len(observations),
                "shortlist": len(shortlist),
                "links": len(shortlist),
                "report_bytes": (workspace / "candidates.md").stat().st_size,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


# --------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------


def command_download(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser()
    links_path = Path(args.links).expanduser() if args.links else workspace / "links.txt"
    if not links_path.is_file():
        raise SystemExit(f"找不到链接清单 {links_path}")
    links = [
        line.strip()
        for line in links_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not links:
        raise SystemExit("链接清单为空")
    target = Path(args.out_dir).expanduser() if args.out_dir else workspace / "downloads"
    tool = args.tool

    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "plan",
                    "tool": tool,
                    "count": len(links),
                    "out_dir": str(target),
                    "command": f'{tool} --no-playlist -P "{target}" -o "%(id)s.%(ext)s" "<url>"',
                    "next": "确认后加 --execute 执行；下载失败会逐条记录，不中断整批。",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    target.mkdir(parents=True, exist_ok=True)
    results = []
    for index, link in enumerate(links, start=1):
        command = [
            tool,
            "--no-playlist",
            "-P",
            str(target),
            "-o",
            "%(id)s.%(ext)s",
            link,
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        results.append(
            {
                "index": index,
                "url": link,
                "returncode": completed.returncode,
                "ok": completed.returncode == 0,
                "stderr_tail": (completed.stderr or "")[-400:],
            }
        )
    receipt = {
        "schema": "douyin-topic-radar/download/1",
        "tool": tool,
        "out_dir": str(target),
        "total": len(results),
        "succeeded": sum(1 for item in results if item["ok"]),
        "failed": sum(1 for item in results if not item["ok"]),
        "results": results,
    }
    write_json(workspace / "download_receipt.json", receipt)
    print(
        json.dumps(
            {key: receipt[key] for key in ("total", "succeeded", "failed")},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if receipt["failed"] == 0 else 1


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radar.py",
        description="抖音选题雷达：关键词检索、结构化采集、信号计算与短名单生成。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    driver = sub.add_parser("driver", help="生成 ego-browser 采集脚本")
    driver.add_argument("--keyword", required=True, help="搜索关键词")
    driver.add_argument(
        "--mode",
        default="comprehensive",
        choices=MODES,
        help="comprehensive=综合排序深滚；latest=最新发布+一周内；top=最多点赞",
    )
    driver.add_argument("--rounds", type=int, default=6, help="滚动轮次，每轮约新增 10-20 条")
    driver.add_argument("--scroll-step", type=int, default=2800, help="每次滚动像素")
    driver.add_argument("--page", default="p1", help="复用的页面标签")
    driver.add_argument("--space-id", type=int, default=None, help="已有 TaskSpace ID")
    driver.add_argument(
        "--finish",
        action="store_true",
        help="采集结束后关闭 TaskSpace（同批最后一个脚本再用）",
    )
    driver.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="输出工作目录")
    driver.set_defaults(func=command_driver)

    normalize = sub.add_parser("normalize", help="归一化采集结果")
    normalize.add_argument("--raw", nargs="+", required=True, help="采集 JSON 文件或通配符")
    normalize.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    normalize.add_argument("--topic", default=None, help="主题名，默认取关键词")
    normalize.set_defaults(func=command_normalize)

    rank = sub.add_parser("rank", help="计算信号并生成报告")
    rank.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    rank.add_argument("--topic", default=None)
    rank.add_argument("--top", type=int, default=12, help="报告内短名单条数")
    rank.add_argument("--per-author", type=int, default=2, help="同一作者最多入选条数")
    rank.set_defaults(func=command_rank)

    shortlist = sub.add_parser("shortlist", help="生成短名单与链接清单")
    shortlist.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    shortlist.add_argument("--top", type=int, default=12, help="短名单条数")
    shortlist.add_argument("--per-author", type=int, default=2, help="同一作者最多入选条数")
    shortlist.add_argument("--links", default="links.txt", help="链接清单文件名")
    shortlist.set_defaults(func=command_shortlist)

    verify = sub.add_parser("verify", help="交叉校验产物一致性")
    verify.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    verify.add_argument("--links", default="links.txt")
    verify.set_defaults(func=command_verify)

    download = sub.add_parser("download", help="按链接清单下载作品")
    download.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    download.add_argument("--links", default=None, help="链接清单路径，默认 workspace/links.txt")
    download.add_argument("--out-dir", default=None, help="下载目录，默认 workspace/downloads")
    download.add_argument("--tool", default="yt-dlp", help="下载器命令")
    download.add_argument(
        "--execute",
        action="store_true",
        help="真正执行下载；缺省只打印计划",
    )
    download.set_defaults(func=command_download)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
