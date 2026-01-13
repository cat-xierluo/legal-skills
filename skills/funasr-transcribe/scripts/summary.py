"""
FunASR 转录总结工具 - Claude Code 环境专用
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

SUMMARY_START = "<!-- AI-SUMMARY:START -->"
SUMMARY_END = "<!-- AI-SUMMARY:END -->"

DEFAULT_SYSTEM_PROMPT = (
    "你是一位擅长处理口语化中文对话的专业纪要分析师。请从非结构化逐字稿中提炼事件脉络、各方观点、关键数据和行动建议，保持客观，不捏造信息。"
)


# ============================================================================
# 辅助函数
# ============================================================================

def _format_list(values: Any) -> list[str]:
    """格式化列表数据"""
    if isinstance(values, list):
        return [str(v).strip() for v in values if str(v).strip()]
    if isinstance(values, str):
        return [item.strip() for item in re.split(r"[、;；,，]\s*", values) if item.strip()]
    return []


def _extract_speaker_orders(markdown_text: str) -> list[str]:
    """从 Markdown 文本中提取发言人编号列表"""
    orders: list[str] = []
    # 匹配 speaker_0, speaker_1 等格式
    for match in re.finditer(r"^speaker_(\d+)", markdown_text, re.MULTILINE):
        order = f"发言人{match.group(1)}"
        if order not in orders:
            orders.append(order)
    return orders


def _format_full_summary(text: str) -> str:
    """格式化全文总结,添加段落分隔"""
    cleaned = text.strip()
    if "\n\n" in cleaned:
        return cleaned
    sentences = [s for s in re.split(r"(?<=[。！？])\s*", cleaned) if s]
    if not sentences:
        return cleaned
    paragraphs: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        current.append(sentence)
        if len(current) >= 2:
            paragraphs.append("".join(current))
            current = []
    if current:
        paragraphs.append("".join(current))
    return "\n\n".join(paragraphs)


def _inject_summary(original: str, summary_block: str) -> str:
    """将总结注入到原始文本中"""
    summary_block = summary_block.strip() + "\n\n"

    # 如果已有总结标记,替换它
    if SUMMARY_START in original and SUMMARY_END in original:
        pattern = re.compile(
            re.escape(SUMMARY_START) + r".*?" + re.escape(SUMMARY_END),
            flags=re.DOTALL,
        )
        replaced = pattern.sub(summary_block.rstrip(), original, count=1)
        return replaced if replaced != original else summary_block + original

    # 在"## 转录内容"前插入
    marker = "\n## 转录内容"
    idx = original.find(marker)
    if idx != -1:
        before = original[:idx].rstrip()
        after = original[idx:]
        return before + "\n\n" + summary_block + after.lstrip("\n")

    # 在标题后插入
    header_match = re.search(r"^# .*$", original, re.MULTILINE)
    if header_match:
        end = header_match.end()
        before = original[:end].rstrip()
        after = original[end:]
        after_body = after.lstrip("\n")
        if "## 转录内容" not in after_body:
            after_body = "## 转录内容\n\n" + after_body
        return before + "\n\n" + summary_block + after_body

    # 默认添加到开头
    return summary_block + original.lstrip()


# ============================================================================
# 总结构建
# ============================================================================

def _build_summary_markdown(
    data: Dict[str, Any],
    expected_orders: list[str] | None = None,
) -> str:
    """
    构建 Markdown 格式的总结

    Args:
        data: 总结数据 (full_summary, speaker_summary, highlights, keywords)
        expected_orders: 期望的发言人顺序列表
    """
    full_summary = str(data.get("full_summary", "")).strip()
    highlights = _format_list(data.get("highlights") or data.get("key_points"))
    keywords = _format_list(data.get("keywords"))

    # 处理发言人总结
    speaker_entries = data.get("speaker_summary") or data.get("speaker_summaries") or []
    normalized: Dict[str, Dict[str, str]] = {}
    if isinstance(speaker_entries, list):
        for entry in speaker_entries:
            if isinstance(entry, dict):
                order = str(entry.get("speaker_order") or entry.get("speaker") or "").strip()
                name = str(entry.get("speaker_name") or entry.get("name") or entry.get("speaker") or "").strip()
                summary = str(entry.get("summary") or entry.get("content") or "").strip()
                if order and summary:
                    normalized[order] = {"name": name or "未知", "summary": summary}
            elif isinstance(entry, str) and entry.strip():
                normalized[entry.strip()] = {"name": entry.strip(), "summary": entry.strip()}

    # 格式化发言人列表
    formatted_speakers: list[str] = []
    orders = expected_orders or list(normalized.keys())
    if not orders and normalized:
        orders = list(normalized.keys())

    for idx, order in enumerate(orders, start=1):
        info = normalized.get(order) or {}
        summary = info.get("summary") or "（摘要缺失，请补充。）"
        label = order if order.startswith("发言人") else f"发言人{idx}"
        formatted_speakers.append(f"- {label}：{summary}")

    # 添加未包含在预期顺序中的发言人
    for order, info in normalized.items():
        if order in orders:
            continue
        summary = info.get("summary") or "（摘要缺失，请补充。）"
        formatted_speakers.append(f"- {order}：{summary}")

    # 构建完整的 Markdown
    lines = [SUMMARY_START, "## AI 摘要"]

    if full_summary:
        lines.append("### 全文总结")
        lines.append(_format_full_summary(full_summary))

    if formatted_speakers:
        lines.append("### 发言人总结")
        lines.extend(formatted_speakers)

    if highlights:
        lines.append("### 重点内容")
        for item in highlights:
            lines.append(f"- {item}")

    if keywords:
        lines.append("### 关键词")
        lines.append(", ".join(keywords))

    lines.append(SUMMARY_END)
    return "\n".join(lines).strip() + "\n\n"


# ============================================================================
# Claude Code 环境专用功能
# ============================================================================

def get_transcription_text(md_path: Path) -> str:
    """从转录文件中提取纯文本内容"""
    text = md_path.read_text(encoding="utf-8")

    # 提取"转录内容"部分，去除时间戳和说话人标记
    marker = "\n## 转录内容"
    idx = text.find(marker)
    if idx != -1:
        content_section = text[idx + len(marker):].strip()
        lines = []
        for line in content_section.split('\n'):
            if line.strip():
                # 移除时间戳和说话人标记（格式：发言人1 00:00:00）
                line = re.sub(r'^发言人?\d+\s+\d{2}:\d{2}:\d{2}\s*', '', line)
                # 移除旧格式的时间戳标记
                line = re.sub(r'\*\*\[[0-9]{2}:[0-9]{2}:[0-9]{2} - [0-9]{2}:[0-9]{2}\].*?\*\*', '', line)
                line = re.sub(r'\*\*\[.*?\]\*\*', '', line)
                line = line.strip()
                if line:
                    lines.append(line)
        return '\n'.join(lines)

    # 如果找不到"转录内容"，返回整个文本
    return text


def create_summary_prompt(text: str) -> str:
    """创建用于 Claude Code 的总结提示词"""
    prompt = f"""你是一位擅长处理口语化中文对话的专业纪要分析师。请从非结构化逐字稿中提炼事件脉络、各方观点、关键数据和行动建议，保持客观，不捏造信息。

请阅读以下逐字稿，输出 JSON 结果，其结构必须为：
{{
  "full_summary": "至少400字，分成2-3段，交代背景、问题、关键事实、数据、风险与行动建议",
  "speaker_summary": [
    {{
      "speaker_order": "发言人1",
      "speaker_name": "如能识别请写姓名，否则写未知",
      "summary": "至少180字，涵盖该发言人的观点、依据、数据、态度与潜在影响"
    }},
    ...
  ],
  "highlights": ["6-10条重点，每条60-100字，明确事实/数据/结论/行动"],
  "keywords": ["5-8个关键词"]
}}

请确保逐字稿中出现的每一位发言人（发言人1、发言人2……）都提供总结，不得遗漏或虚构。

以下是完整文本：
{text}

请输出 JSON 格式的总结。"""
    return prompt


def inject_summary_to_file(md_path: Path, summary_text: str) -> None:
    """将总结注入到 Markdown 文件中"""
    text = md_path.read_text(encoding="utf-8")

    # 确保总结有标记
    if not summary_text.strip().startswith('<!-- AI-SUMMARY:START -->'):
        summary_text = f"<!-- AI-SUMMARY:START -->\n{summary_text}\n<!-- AI-SUMMARY:END -->"

    # 检查是否已有总结
    if SUMMARY_START in text and SUMMARY_END in text:
        pattern = re.compile(
            re.escape(SUMMARY_START) + r".*?" + re.escape(SUMMARY_END),
            flags=re.DOTALL,
        )
        text = pattern.sub(summary_text.strip() + "\n\n", text, count=1)
    else:
        # 插入新总结
        text = _inject_summary(text, summary_text)

    md_path.write_text(text, encoding="utf-8")


def summarize_file_for_claude(md_path: Path) -> tuple[bool, str, str]:
    """
    为 Claude Code 环境创建总结

    Args:
        md_path: Markdown 文件路径

    Returns:
        tuple: (是否成功, 提示信息/提示词, 提取的文本)
    """
    try:
        # 提取转录文本
        text = get_transcription_text(md_path)
        if not text:
            return False, "转录文件为空", ""

        # 创建提示词
        prompt = create_summary_prompt(text)

        return True, prompt, text

    except Exception as e:
        return False, f"提取转录文本失败: {str(e)}", ""
