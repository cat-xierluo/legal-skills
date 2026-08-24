#!/usr/bin/env python3
"""lecture-review 统计脚本：从 raw 转录稿提取确定性指标，输出 JSON 供 agent 解读。

只做机械计算（词频/语速/段长/停顿），不做语义判断（句式/跑题/承诺回收由 agent 通读完成）。

用法：
  python3 analyze_stats.py <转录稿路径> [--speaker 发言人2|姓名] [--markers marker_words.yaml] [--out stats.json]
"""

import argparse
import json
import re
import sys
from collections import Counter

# 与 config/marker_words.yaml 保持一致的内置默认表（读取 YAML 失败时兜底）
DEFAULT_MARKERS = [
    "这个", "那个", "就是", "就是说", "也就是说", "等于说",
    "然后", "其实", "相当于", "说白了", "换句话说",
    "对吧", "对不对", "是不是", "知道吧", "好不好", "明白吧",
]
DEFAULT_STARTERS = ["然后", "好", "那", "就是", "所以", "但是", "当然", "我们"]
DEFAULT_AUDIENCE = ["大家", "各位", "你们"]

# 听悟: `发言人1 04:15`；加粗变体: `**发言人 1  00:33:09**`
SPEAKER_RE = re.compile(
    r"^(?:\*\*)?\s*(?:发言人|说话人|Speaker)\s*([0-9一二三四五六七八九十A-Za-z]+)"
    r"\s*[:：]?\s*(\d{1,3}:\d{2}(?::\d{2})?)?\s*(?:\*\*)?\s*$"
)
SLIDE_RE = re.compile(r"^!\[.*?\]\(.*?\)\s*$")
SLIDE_TS_RE = re.compile(r"^>\s*\*?(\d{1,3}:\d{2}(?::\d{2})?)\*?\s*$")


def ts_to_sec(t):
    parts = [int(p) for p in t.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def visible_chars(s):
    """CJK + 字母数字，不含标点空白——语速与频度的统一分母。"""
    return len(re.findall(r"[一-鿿A-Za-z0-9]", s))


def load_markers(path):
    """极简 YAML 读取：只认本 skill 词表的结构，避免 PyYAML 依赖。"""
    markers, starters, audience = list(DEFAULT_MARKERS), list(DEFAULT_STARTERS), list(DEFAULT_AUDIENCE)
    if not path:
        return markers, starters, audience
    try:
        section = None
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            m = re.match(r"-\s*\{[^}]*word:\s*([^,}\s]+)", line)
            if m:
                markers.append(m.group(1))
                continue
            if line.startswith("sentence_starters:"):
                section, val = "starters", line.split(":", 1)[1]
            elif line.startswith("audience_address:"):
                section, val = "audience", line.split(":", 1)[1]
            elif section and line.startswith("- "):
                val = line[1:].strip()
            else:
                continue
            if section and val.strip():
                target = starters if section == "starters" else audience
                for w in re.findall(r"[一-鿿A-Za-z]+", val):
                    if w not in target:
                        target.append(w)
    except OSError:
        sys.stderr.write(f"[warn] 词表读取失败，使用内置默认表: {path}\n")
    # 去重，保持顺序
    markers = list(dict.fromkeys(markers))
    return markers, starters, audience


def count_markers(text, markers):
    """最长优先去重叠计数：『也就是说』只计入自身，不再喂给『就是』。"""
    pattern = "|".join(re.escape(m) for m in sorted(markers, key=len, reverse=True))
    return Counter(re.findall(pattern, text))


def parse_blocks(lines):
    """把行流切成 [{speaker, ts, text}] 段落 + 幻灯片锚点列表。"""
    blocks, slides = [], []
    cur = None
    pending_slide = False
    for raw in lines:
        line = raw.rstrip("\n")
        sm = SPEAKER_RE.match(line)
        if sm:
            cur = {
                "speaker": sm.group(1),
                "ts": ts_to_sec(sm.group(2)) if sm.group(2) else None,
                "text_lines": [],
            }
            blocks.append(cur)
            pending_slide = False
            continue
        if SLIDE_RE.match(line):
            pending_slide = True
            continue
        tm = SLIDE_TS_RE.match(line)
        if tm and pending_slide:
            slides.append(ts_to_sec(tm.group(1)))
            pending_slide = False
            continue
        if cur is not None:
            cur["text_lines"].append(line)
    for pos, b in enumerate(blocks):
        b["text"] = "\n".join(b["text_lines"]).strip()
        b["chars"] = visible_chars(b["text"])
        b["pos"] = pos
    return blocks, slides


def split_sentences(text):
    return [s for s in re.split(r"[。！？；!?;\n]+", text) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--speaker", help="指定主讲（发言人编号或姓名）；缺省取字数最多者")
    ap.add_argument("--markers", help="marker_words.yaml 路径")
    ap.add_argument("--count", help="临时词按需计数（逗号分隔）——agent 通读发现新模式后拿来量化验证")
    ap.add_argument("--out", help="JSON 输出路径；缺省打印 stdout")
    args = ap.parse_args()

    markers, starters, audience = load_markers(args.markers)
    lines = open(args.file, encoding="utf-8").read().splitlines(keepends=True)
    blocks, slides = parse_blocks(lines)
    if not blocks:
        sys.exit("[error] 未识别到任何发言人段落，检查转录格式")

    has_ts = all(b["ts"] is not None for b in blocks) and len(blocks) > 1
    t0 = blocks[0]["ts"] if has_ts else None
    t1 = blocks[-1]["ts"] if has_ts else None
    total_sec = (t1 - t0) if has_ts else None

    # ---- 讲师隔离 ----
    by_speaker = {}
    for b in blocks:
        by_speaker.setdefault(b["speaker"], []).append(b)
    chars_by_speaker = {s: sum(b["chars"] for b in bs) for s, bs in by_speaker.items()}
    if args.speaker:
        target = None
        for s, bs in by_speaker.items():
            if args.speaker in s or any(args.speaker in b["text"][:120] for b in bs[:5]):
                target = s
                break
        if target is None:
            sys.exit(f"[error] 未找到发言人 {args.speaker}；现有: {list(by_speaker)}")
    else:
        target = max(chars_by_speaker, key=chars_by_speaker.get)

    mine = by_speaker[target]
    my_chars = sum(b["chars"] for b in mine)
    excluded = {s: {"chars": c, "blocks": len(by_speaker[s]), "first_ts": by_speaker[s][0]["ts"]}
                for s, c in chars_by_speaker.items() if s != target}

    # ---- 口癖（整体 + 前/中/后三段）----
    full_text = "\n".join(b["text"] for b in mine)
    mc = count_markers(full_text, markers)
    thirds = [[], [], []]
    if has_ts and total_sec:
        for b in mine:
            idx = min(2, int((b["ts"] - t0) / (total_sec / 3))) if total_sec > 0 else 1
            thirds[idx].append(b)
    marker_stats = []
    for word, n in mc.most_common():
        per_10k = round(n * 10000 / my_chars, 1) if my_chars else 0
        dist = [sum(count_markers(b["text"], [word])[word] for b in t) for t in thirds] if thirds[0] or thirds[2] else None
        marker_stats.append({"word": word, "count": n, "per_10k": per_10k, "thirds": dist})
    ad_hoc = []
    if args.count:
        for word in [w.strip() for w in args.count.split(",") if w.strip()]:
            n = count_markers(full_text, [word])[word]
            dist = [sum(count_markers(b["text"], [word])[word] for b in t) for t in thirds] if thirds[0] or thirds[2] else None
            ad_hoc.append({"word": word, "count": n,
                           "per_10k": round(n * 10000 / my_chars, 1) if my_chars else 0, "thirds": dist})

    # ---- 语速 ----
    rate = None
    if has_ts:
        rates = []
        for b in mine:
            nxt = None
            for nb in blocks[b["pos"] + 1:]:
                if nb["ts"] is not None:
                    nxt = nb["ts"]
                    break
            gap = (nxt - b["ts"]) if nxt is not None else (t1 - b["ts"])
            if gap and gap > 0 and b["chars"] > 20:  # 短确认句不算语速样本
                rates.append(round(b["chars"] / gap * 60, 1))
        if rates:
            rate = {
                "mean_per_min": round(sum(rates) / len(rates), 1),
                "min": min(rates), "max": max(rates), "samples": len(rates),
            }

    # ---- 长停顿（全场时间轴，>90s 的空档，讲师视角标注前后段）----
    pauses = []
    if has_ts:
        for i in range(len(blocks) - 1):
            a, b = blocks[i], blocks[i + 1]
            if a["ts"] is not None and b["ts"] is not None and b["ts"] - a["ts"] > 90:
                pauses.append({
                    "from": a["speaker"], "to": b["speaker"],
                    "gap_sec": b["ts"] - a["ts"], "at": a["ts"],
                    "before_head": a["text"][:40], "after_head": b["text"][:40],
                })

    # ---- 长句 / 起手式 / 求确认 / 喊话 / 承诺候选 ----
    long_sents = []
    for b in mine:
        for s in split_sentences(b["text"]):
            c = visible_chars(s)
            if c > 80:
                long_sents.append({"chars": c, "head": s.strip()[:60], "ts": b["ts"]})
    starter_counts = Counter()
    runs, run_word, run_len = [], None, 0
    for b in mine:
        head = b["text"].lstrip("*# >-")
        w = next((s for s in sorted(starters, key=len, reverse=True) if head.startswith(s)), None)
        if w:
            starter_counts[w] += 1
        if w is None:
            run_word, run_len = None, 0
        elif w == run_word:
            run_len += 1
        else:
            run_word, run_len = w, 1
        if run_len == 3:
            runs.append({"starter": w, "note": f"连续≥3段以「{w}」开头", "last_ts": b["ts"]})
    confirm_total = sum(n for w, n in mc.items() if w in ("对吧", "对不对", "是不是", "知道吧", "好不好", "明白吧"))
    aud = count_markers(full_text, audience)
    promises = []
    for b in mine:
        for s in split_sentences(b["text"]):
            if re.search(r"(一会儿|待会儿|等一下|稍后|后面|待会儿|接下来).{0,12}(会|再|给大家|给大伙)", s) and re.search(r"(讲|演示|展示|说|看|发|分享|介绍)", s):
                promises.append({"head": s.strip()[:60], "ts": b["ts"]})

    result = {
        "file": args.file, "selected_speaker": target, "has_timestamps": has_ts,
        "duration_sec": total_sec, "my_chars": my_chars, "my_blocks": len(mine),
        "excluded_speakers": excluded,
        "marker_words": marker_stats[:20],
        "ad_hoc_counts": ad_hoc,
        "rate": rate, "long_pauses": pauses,
        "long_sentences": {"count": len(long_sents), "examples": long_sents[:10]},
        "starter_top": starter_counts.most_common(8), "starter_runs": runs,
        "confirm_markers_total": confirm_total,
        "audience_address": dict(aud), "promise_candidates": promises[:30],
        "slides_ts": slides,
    }
    out = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(out)
        print(f"[ok] {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
