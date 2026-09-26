"""
FunASR 转录总结工具 - Claude Code / Agent 环境专用

支持：
- 从转录文件中提取文本并生成总结提示词
- 将总结注入到 Markdown 文件
- 验证文件中是否存在总结
- CLI 接口：python3 summary.py inject <md_path> <summary_file>
             python3 summary.py verify <md_path>
"""
from __future__ import annotations

import json
import re
import sys
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


# 发言行：行首"标签 + 时间戳"（合并段格式：`发言人1 00:00` / `杨律师 00:02:49`）。
# 空白限定为同行空格/制表符（\s 会匹配换行，导致标签跨行吞掉下一行的时间戳）。
# 正文行不会整行以时间戳结尾，且只有真实发言行带行首标签，正文提及人名不会误报。
SPEAKER_LINE_RE = re.compile(r"^(?P<label>.+?)[ \t]+(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)[ \t]*$", re.MULTILINE)
TIMESTAMP_ONLY_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
OLD_SPEAKER_LINE_RE = re.compile(r"^speaker_(\d+)(?::|\s|$)")


def _extract_speaker_orders(markdown_text: str) -> list[str]:
    """从 Markdown 文本中提取发言人标签集合（保持出现顺序）。

    支持：行首"标签 + 时间戳"（发言人N / 实名 / 匿名编号，Task-021 契约）
    与旧版 speaker_N 行首格式（归一为 发言人N+1）。
    只认发言行结构，不从普通正文出现的人名猜测发言人。
    """
    orders: list[str] = []
    for match in SPEAKER_LINE_RE.finditer(markdown_text):
        label = match.group("label").strip()
        if not label or TIMESTAMP_ONLY_RE.fullmatch(label):
            continue
        # 旧版 speaker_N 标签归一为 发言人N+1，避免与新格式重复入列
        old_style = re.fullmatch(r"speaker_(\d+)", label)
        if old_style:
            label = f"发言人{int(old_style.group(1)) + 1}"
        if label not in orders:
            orders.append(label)
    for match in re.finditer(r"^speaker_(\d+)", markdown_text, re.MULTILINE):
        order = f"发言人{int(match.group(1)) + 1}"
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

    # 格式化发言人列表：order 保留稿件中的原始标签（发言人N / 实名）
    formatted_speakers: list[str] = []
    orders = expected_orders or list(normalized.keys())
    if not orders and normalized:
        orders = list(normalized.keys())

    for order in orders:
        info = normalized.get(order) or {}
        summary = info.get("summary") or "（摘要缺失，请补充。）"
        name = info.get("name") or ""
        suffix = f"（{name}）" if name and name != "未知" else ""
        formatted_speakers.append(f"- {order}{suffix}：{summary}")

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
    """从转录文件中提取纯文本内容，保留每位发言的说话人归属。

    每行输出为 `标签：正文`（标签为发言人N / 实名 / 匿名编号；Task-021：摘要
    预处理不得先删掉归属）。无说话人的行（fast/纯时间戳行）原样保留。
    """
    text = md_path.read_text(encoding="utf-8")

    # 提取"转录内容"部分，去除时间戳但保留说话人标签
    marker = "\n## 转录内容"
    idx = text.find(marker)
    if idx != -1:
        content_section = text[idx + len(marker):].strip()
        lines = []
        current_speaker: str | None = None
        for line in content_section.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            # 移除旧格式的时间戳标记
            line = re.sub(r'\*\*\[[0-9]{2}:[0-9]{2}:[0-9]{2} - [0-9]{2}:[0-9]{2}\].*?\*\*', '', line)
            line = re.sub(r'\*\*\[.*?\]\*\*', '', line)
            line = line.strip()
            if not line:
                continue
            speaker_match = OLD_SPEAKER_LINE_RE.match(line)
            if speaker_match:
                current_speaker = f"发言人{int(speaker_match.group(1)) + 1}"
                line = OLD_SPEAKER_LINE_RE.sub('', line).strip()
                if not line:
                    continue
                lines.append(f"{current_speaker}：{line}")
                continue
            line_match = SPEAKER_LINE_RE.match(line)
            if line_match and not TIMESTAMP_ONLY_RE.fullmatch(line_match.group("label")):
                current_speaker = line_match.group("label").strip()
                continue
            if TIMESTAMP_ONLY_RE.fullmatch(stripped):
                current_speaker = None
                continue
            if current_speaker:
                lines.append(f"{current_speaker}：{line}")
            else:
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
      "speaker_order": "逐字使用逐字稿中行首的发言标签，例如 发言人1 或实名",
      "speaker_name": "如能识别请写姓名，否则写未知",
      "summary": "至少180字，涵盖该发言人的观点、依据、数据、态度与潜在影响"
    }},
    ...
  ],
  "highlights": ["6-10条重点，每条60-100字，明确事实/数据/结论/行动"],
  "keywords": ["5-8个关键词"]
}}

要求：
- speaker_summary 必须覆盖逐字稿中出现的每一位发言人，不得遗漏、重复或虚构。
- speaker_order 必须逐字使用逐字稿行首的发言标签（如"发言人1"、"杨律师"），不得改写、合并或新造标签。
- 每条总结只基于该发言人的实际发言，不得把他人观点归属给该发言人。

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


def generate_summary_via_api(md_path: Path) -> tuple[bool, str]:
    """
    在 Claude Code 环境中生成总结

    当检测到在 Claude Code 环境中时，输出结构化的总结请求，
    Claude Code 会自动识别并处理这个请求，利用其原生的 AI 能力生成总结。

    Args:
        md_path: Markdown 文件路径

    Returns:
        tuple: (是否成功, 消息)
    """
    try:
        # 提取转录文本
        text = get_transcription_text(md_path)
        if not text:
            return False, "转录文件为空"

        # 创建提示词
        prompt = create_summary_prompt(text)

        # 输出结构化请求，Claude Code 会自动识别并处理
        print("\n" + "=" * 70)
        print("🤖 AI_SUMMARY_REQUEST")
        print("=" * 70)
        print(f"FILE: {md_path}")
        print(f"LENGTH: {len(text)}")
        print("=" * 70)
        print("PROMPT_START")
        print(prompt)
        print("PROMPT_END")
        print("=" * 70)

        # 将提示词写入临时文件，供 Claude Code 读取并处理
        prompt_file = md_path.parent / f".summary_prompt_{md_path.stem}.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        return True, f"总结请求已生成: {prompt_file}"

    except Exception as e:
        return False, f"生成总结请求失败: {str(e)}"


# ============================================================================
# 验证功能
# ============================================================================

def _extract_summary_speaker_labels(summary_block: str) -> list[str]:
    """从摘要块的"### 发言人总结"小节提取实际覆盖的发言人标签（保持顺序、去重）。"""
    covered: list[str] = []
    section = re.search(r"###\s*发言人总结(.*?)(?=\n### |\Z)", summary_block, re.DOTALL)
    if not section:
        return covered
    for item in re.finditer(r"^-\s*(.+?)：", section.group(1), re.MULTILINE):
        # 兼容 `- 标签（姓名）：` 形式，剥掉括号注记后比对
        label = re.sub(r"（[^（）]*）\s*$", "", item.group(1).strip()).strip()
        if label and label not in covered:
            covered.append(label)
    return covered


def verify_summary_in_file(md_path: Path) -> Dict[str, Any]:
    """验证 Markdown 文件中是否已注入 AI 摘要，并检查发言人覆盖。

    区分三种结论（Task-021）：
    - has_all_sections：只说明"有摘要块且章节标题齐全"，不等于内容完整；
    - speaker_coverage：complete = 稿件每位发言人都出现在摘要中且无杜撰；
      incomplete = 漏人/杜撰；not_applicable = 稿件无发言行结构，无法验证（不假定通过）。
    """
    if not md_path.exists():
        return {
            "has_summary": False,
            "summary_length": 0,
            "has_all_sections": False,
            "missing_sections": ["文件不存在"],
            "speaker_coverage": "not_applicable",
            "expected_speakers": [],
            "covered_speakers": [],
            "missing_speakers": [],
            "unexpected_speakers": [],
        }

    text = md_path.read_text(encoding="utf-8")

    # 检查标记
    has_start = SUMMARY_START in text
    has_end = SUMMARY_END in text

    if not (has_start and has_end):
        return {
            "has_summary": False,
            "summary_length": 0,
            "has_all_sections": False,
            "missing_sections": ["AI-SUMMARY 标记"],
            "speaker_coverage": "not_applicable",
            "expected_speakers": _extract_speaker_orders(text),
            "covered_speakers": [],
            "missing_speakers": [],
            "unexpected_speakers": [],
        }

    # 提取摘要块
    pattern = re.compile(
        re.escape(SUMMARY_START) + r"(.*?)" + re.escape(SUMMARY_END),
        flags=re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return {
            "has_summary": False,
            "summary_length": 0,
            "has_all_sections": False,
            "missing_sections": ["摘要内容"],
            "speaker_coverage": "not_applicable",
            "expected_speakers": _extract_speaker_orders(text),
            "covered_speakers": [],
            "missing_speakers": [],
            "unexpected_speakers": [],
        }

    summary_block = match.group(1)

    # 检查必需章节
    required_sections = ["全文总结", "发言人总结", "重点内容", "关键词"]
    missing = [s for s in required_sections if s not in summary_block]

    # 发言人覆盖：期望集合来自稿件正文（剔除摘要块），实际集合来自摘要发言人小节
    expected_speakers = _extract_speaker_orders(pattern.sub("", text))
    covered_speakers = _extract_summary_speaker_labels(summary_block)
    missing_speakers = [s for s in expected_speakers if s not in covered_speakers]
    unexpected_speakers = [s for s in covered_speakers if s not in expected_speakers]
    if not expected_speakers:
        speaker_coverage = "not_applicable"
    elif missing_speakers or unexpected_speakers:
        speaker_coverage = "incomplete"
    else:
        speaker_coverage = "complete"

    return {
        "has_summary": True,
        "summary_length": len(summary_block.strip()),
        "has_all_sections": len(missing) == 0,
        "missing_sections": missing,
        "speaker_coverage": speaker_coverage,
        "expected_speakers": expected_speakers,
        "covered_speakers": covered_speakers,
        "missing_speakers": missing_speakers,
        "unexpected_speakers": unexpected_speakers,
    }


def inject_from_file(md_path: Path, summary_file: Path) -> tuple[bool, str]:
    """从文件读取总结内容并注入到 Markdown 文件

    支持 JSON 和纯文本格式：
    - JSON: 解析为结构化数据后格式化为 Markdown
    - 纯文本: 直接作为 Markdown 注入

    Args:
        md_path: 目标 Markdown 文件路径
        summary_file: 总结内容文件路径

    Returns:
        tuple: (是否成功, 消息)
    """
    if not md_path.exists():
        return False, f"目标文件不存在: {md_path}"
    if not summary_file.exists():
        return False, f"总结文件不存在: {summary_file}"

    raw = summary_file.read_text(encoding="utf-8").strip()
    if not raw:
        return False, "总结文件为空"

    # 尝试解析为 JSON
    content_to_inject = None
    try:
        # 去除可能的 markdown code fence
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()

        # 尝试找到 JSON 对象
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            data = json.loads(json_match.group())

            # 提取期望的发言人顺序
            md_text = md_path.read_text(encoding="utf-8")
            expected_orders = _extract_speaker_orders(md_text)

            content_to_inject = _build_summary_markdown(data, expected_orders)
    except (json.JSONDecodeError, KeyError, TypeError):
        pass  # 非 JSON 格式，当作纯文本处理

    if content_to_inject is None:
        # 纯文本格式，直接注入
        content_to_inject = raw

    inject_summary_to_file(md_path, content_to_inject)

    # 验证注入结果（含发言人覆盖；incomplete 时如实报告，调用方不得当作已验收交付）
    result = verify_summary_in_file(md_path)
    if not result["has_summary"]:
        return False, "注入后验证失败，总结未写入文件"
    message = f"总结已注入 ({result['summary_length']} 字符)"
    coverage = result.get("speaker_coverage", "not_applicable")
    if coverage == "incomplete":
        if result["missing_speakers"]:
            message += f"；⚠️ 摘要遗漏发言人: {', '.join(result['missing_speakers'])}"
        if result["unexpected_speakers"]:
            message += f"；⚠️ 摘要出现稿件中不存在的发言人: {', '.join(result['unexpected_speakers'])}"
    elif coverage == "not_applicable":
        message += "；发言人覆盖无法验证（稿件无发言行结构）"
    else:
        message += "；发言人覆盖完整"
    return True, message


# ============================================================================
# CLI 接口
# ============================================================================

def main():
    """CLI 入口点"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 summary.py inject <md_path> <summary_file>  - 从文件注入总结")
        print("  python3 summary.py verify <md_path>                 - 验证总结是否存在")
        print("  python3 summary.py prompt <md_path>                 - 生成总结提示词")
        sys.exit(1)

    command = sys.argv[1]

    if command == "inject":
        if len(sys.argv) < 4:
            print("用法: python3 summary.py inject <md_path> <summary_file>")
            sys.exit(1)
        md_path = Path(sys.argv[2])
        summary_file = Path(sys.argv[3])
        success, msg = inject_from_file(md_path, summary_file)
        if success:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")
            sys.exit(1)

    elif command == "verify":
        if len(sys.argv) < 3:
            print("用法: python3 summary.py verify <md_path>")
            sys.exit(1)
        md_path = Path(sys.argv[2])
        result = verify_summary_in_file(md_path)
        coverage = result.get("speaker_coverage", "not_applicable")
        if result["has_summary"] and result["has_all_sections"] and coverage != "incomplete":
            sections_status = "完整" if result["has_all_sections"] else f"缺少: {', '.join(result['missing_sections'])}"
            print(f"✅ 摘要已存在 ({result['summary_length']} 字符, 章节{sections_status})")
            if coverage == "complete":
                print(f"✅ 发言人覆盖完整: {', '.join(result['covered_speakers'])}")
            elif coverage == "not_applicable":
                print("⚠️  发言人覆盖无法验证：稿件中没有发言行结构（不判定通过）")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 摘要不完整 (缺少: {', '.join(result['missing_sections'])})")
            if coverage == "incomplete":
                if result["missing_speakers"]:
                    print(f"❌ 摘要遗漏发言人: {', '.join(result['missing_speakers'])}")
                if result["unexpected_speakers"]:
                    print(f"❌ 摘要出现稿件中不存在的发言人: {', '.join(result['unexpected_speakers'])}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(1)

    elif command == "prompt":
        if len(sys.argv) < 3:
            print("用法: python3 summary.py prompt <md_path>")
            sys.exit(1)
        md_path = Path(sys.argv[2])
        success, prompt, text = summarize_file_for_claude(md_path)
        if success:
            print(prompt)
        else:
            print(f"❌ {prompt}")
            sys.exit(1)

    else:
        print(f"未知命令: {command}")
        print("可用命令: inject, verify, prompt")
        sys.exit(1)


if __name__ == "__main__":
    main()
