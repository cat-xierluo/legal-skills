#!/usr/bin/env python3
"""将通义听悟 API 返回的 JSON 结果转换为 funasr-transcribe 兼容的 Markdown 格式"""

import json
from datetime import datetime
from pathlib import Path


def format_timestamp(ms):
    """毫秒 → MM:SS 或 HH:MM:SS"""
    total_sec = max(0, ms) // 1000
    h, remainder = divmod(total_sec, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_result(result_data):
    """解析听悟 result JSON 字符串为结构化段落列表"""
    if isinstance(result_data, str):
        result_data = json.loads(result_data)

    pages = []
    if "pg" in result_data:
        pages = result_data["pg"]
    else:
        for key, value in result_data.items():
            if isinstance(value, list):
                pages.extend(value)

    paragraphs = []
    for page in pages:
        if not isinstance(page, dict) or "sc" not in page:
            continue
        segments = page["sc"]
        if not segments:
            continue

        # ui 是段落级说话人ID（"1"/"2"/...），si 是句子级递增编号
        page_speaker = int(page.get("ui", 0)) or None
        current_start = segments[0].get("bt", 0)
        current_text = []

        for seg in segments:
            text = seg.get("tc", "")
            current_text.append(text)

        if current_text:
            paragraphs.append({
                "speaker": page_speaker,
                "start_ms": current_start,
                "text": "".join(current_text),
            })

    return paragraphs


def merge_speaker_segments(paragraphs, max_gap_ms=30000):
    """合并连续相同说话人的短句（30 秒窗口内）"""
    if not paragraphs:
        return paragraphs

    merged = [paragraphs[0]]
    for p in paragraphs[1:]:
        last = merged[-1]
        if (p["speaker"] == last["speaker"]
                and p["start_ms"] - last["start_ms"] <= max_gap_ms):
            last["text"] += p["text"]
        else:
            merged.append(p)
    return merged


def consolidate_speakers(paragraphs, max_speakers=None):
    """将 Tingwu 的轮次 ID（si）合并为实际说话人。

    Tingwu 的 si 是递增轮次编号，不是说话人编号。
    对于 2 人对话，按奇偶交替映射到 发言人1/发言人2。
    对于多人场景，保留原始 si 但合并相近的段。
    """
    if not paragraphs:
        return paragraphs

    unique_si = sorted(set(p["speaker"] for p in paragraphs))

    if max_speakers and max_speakers == 2 and len(unique_si) > 2:
        # 2人模式：奇偶交替映射
        for p in paragraphs:
            p["speaker"] = (p["speaker"] - 1) % 2 + 1
    elif max_speakers and max_speakers == 1:
        # 单人模式：全部合并
        for p in paragraphs:
            p["speaker"] = 1

    return paragraphs


def normalize_speakers(paragraphs):
    """将说话人 ID 映射为 发言人1, 发言人2..."""
    speaker_map = {}
    counter = 1
    for p in paragraphs:
        sid = p["speaker"]
        if sid not in speaker_map:
            speaker_map[sid] = f"发言人{counter}"
            counter += 1
        p["speaker_name"] = speaker_map[sid]


def interleave_ppt_slides(paragraphs, slides):
    """将 PPT 幻灯片按时间戳插入到转录段落中。

    算法：对每张幻灯片（时间 T），找到第一条 start_ms >= T 的段落，
    在该段落前插入幻灯片图片引用。
    """
    if not slides or not paragraphs:
        return paragraphs

    slides_by_time = sorted(slides, key=lambda s: s["time"])
    para_idx = 0

    interleaved = []
    for slide in slides_by_time:
        # 找到第一条 start_ms >= slide.time 的段落
        while para_idx < len(paragraphs) and paragraphs[para_idx]["start_ms"] < slide["time"]:
            interleaved.append(paragraphs[para_idx])
            para_idx += 1
        # 插入幻灯片标记
        interleaved.append({"_ppt_slide": True, **slide})
    # 追加剩余段落
    interleaved.extend(paragraphs[para_idx:])
    return interleaved


def result_to_markdown(result_data, file_name, duration=None, word_count=None,
                       max_speakers=None, ppt_slides=None, slides_dir_name="slides",
                       slides_ext=".png"):
    """将听悟转录结果转换为 funasr 兼容的 Markdown"""
    paragraphs = parse_result(result_data)
    paragraphs = consolidate_speakers(paragraphs, max_speakers=max_speakers)
    paragraphs = merge_speaker_segments(paragraphs)
    normalize_speakers(paragraphs)

    if ppt_slides:
        paragraphs = interleave_ppt_slides(paragraphs, ppt_slides)

    lines = [f"# 转录：{file_name}", ""]
    if duration:
        m, s = divmod(duration, 60)
        lines.append(f"> 时长: {m:.0f}分{s:.0f}秒 | 字数: {word_count or 'N/A'} | 引擎: 听悟")
        lines.append("")
    lines.append("## 转录内容")
    lines.append("")

    for p in paragraphs:
        if p.get("_ppt_slide"):
            idx = p.get("index", 0)
            img_rel = f"./{slides_dir_name}/slide_{idx:03d}{slides_ext}"
            ts = format_timestamp(p["time"])
            lines.append(f"![PPT 幻灯片 {idx}]({img_rel})")
            lines.append(f"> *{ts}*")
            lines.append("")
        else:
            ts = format_timestamp(p["start_ms"])
            lines.append(f"{p['speaker_name']} {ts}")
            lines.append(f"{p['text']}")
            lines.append("")

    return "\n".join(lines)


def lab_to_markdown(lab_data):
    """将 getLabInfo 返回的数据格式化为 Markdown（追加到转录末尾）"""
    if not lab_data or not isinstance(lab_data, dict):
        return ""

    cards = lab_data.get("labCards", [])
    card_map = {}
    for card in cards:
        name = card.get("basicInfo", {}).get("name", "")
        card_map[name] = card

    lines = ["", "---", ""]

    # 关键词
    keywords_card = card_map.get("关键词")
    if keywords_card:
        for content in keywords_card.get("contents", []):
            if content.get("type") == "tag":
                words = [v["value"] for v in content.get("contentValues", [])]
                if words:
                    lines.append("## 关键词")
                    lines.append("")
                    lines.append("、".join(words))
                    lines.append("")

    # 议程
    agenda_card = card_map.get("议程")
    if agenda_card:
        for content in agenda_card.get("contents", []):
            items = content.get("contentValues", [])
            if items:
                lines.append("## 议程摘要")
                lines.append("")
                for item in items:
                    if not item.get("value"):
                        continue
                    start = format_timestamp(item.get("time", 0))
                    end = format_timestamp(item.get("endTime", 0))
                    lines.append(f"### {item['value']}")
                    lines.append(f"> {start} - {end}")
                    lines.append("")
                    summary = item.get("summary")
                    if summary:
                        lines.append(summary.strip())
                        lines.append("")

    # 重点内容
    keypoints_card = card_map.get("重点内容")
    if keypoints_card:
        for content in keypoints_card.get("contents", []):
            items = content.get("contentValues", [])
            if items:
                lines.append("## 重点内容")
                lines.append("")
                for item in items:
                    if not item.get("value"):
                        continue
                    ts = format_timestamp(item.get("time", 0))
                    lines.append(f"- \"{item['value']}\" ({ts})")
                lines.append("")

    # QA 问答
    qa_card = card_map.get("qa问答")
    if qa_card:
        for content in qa_card.get("contents", []):
            items = content.get("contentValues", [])
            if items:
                lines.append("## Q&A 问答")
                lines.append("")
                for item in items:
                    question = item.get("title", "").strip()
                    answer = item.get("value", "").strip()
                    if question:
                        lines.append(f"**Q: {question}**")
                    if answer:
                        lines.append(f"A: {answer}")
                    lines.append("")

    # PPT 标题（视频场景）
    ppt_card = card_map.get("ppt列表标题")
    if ppt_card:
        for content in ppt_card.get("contents", []):
            items = content.get("contentValues", [])
            if items:
                lines.append("## PPT 章节标题")
                lines.append("")
                for item in items:
                    if not item.get("value"):
                        continue
                    start = format_timestamp(item.get("time", 0))
                    end = format_timestamp(item.get("endTime", 0))
                    lines.append(f"{item['id']}. {item['value']} ({start} - {end})")
                lines.append("")

    result = "\n".join(lines)
    return result if len(result) > 20 else ""


def save_archive(file_path, markdown_content, trans_id, result_data, archive_root):
    """保存转录结果到归档目录"""
    now = datetime.now()
    dir_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{Path(file_path).stem}"
    archive_dir = Path(archive_root) / dir_name
    archive_dir.mkdir(parents=True, exist_ok=True)

    md_path = archive_dir / f"{Path(file_path).stem}.md"
    md_path.write_text(markdown_content, encoding="utf-8")

    meta = {
        "source_file": str(file_path),
        "output_markdown": str(md_path),
        "archive_path": str(archive_dir),
        "timestamp": now.isoformat(),
        "engine": "tingwu",
        "task_id": trans_id,
        "duration": result_data.get("duration"),
        "word_count": result_data.get("wordCount"),
    }
    meta_path = archive_dir / "transcription_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return md_path, archive_dir
