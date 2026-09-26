#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""摘要说话人归属与覆盖检查回归（Task-021）。

覆盖：
- 提取保留身份：MM:SS / HH:MM:SS 边界、实名/匿名混合、旧 speaker_N 格式
- 覆盖检查：漏人/重复凑数/杜撰发言人必须失败，完整合法摘要通过
- 不误报：正文提及人名、截图引用不凭空增加发言人
- fast 无说话人稿件：not_applicable（不假定通过也不误判失败）
- CLI verify 对覆盖不完整以非零退出码传递给调用方

不依赖模型推理，全部用合成 Markdown 与受控摘要数据。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(SCRIPT_DIR))
import summary


def write_md(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


MIXED_MD = """# 转录：咨询录音.m4a

> 说话人识别：S01 → 杨律师（声纹相似度 0.82）

## AI 摘要占位

## 转录内容

杨律师 00:00
我询问办理流程。张女士的材料也带来了。

发言人2 59:59
我介绍所需材料。

![](slides/slide_001_02m49s.jpg)

发言人3 01:00:00
好的，收到。

发言人2 01:00:04
那张判决书带了吗。
"""

LONG_MD = """# 转录：长会议.wav

## 转录内容

发言人1 59:59
第一段。

发言人2 01:00:00
第二段。

发言人3 01:00:04
第三段。
"""

OLD_FORMAT_MD = """# 转录：旧稿.wav

## 转录内容

speaker_0 00:00
旧版第一人。

speaker_1 00:30
旧版第二人。
"""

FAST_MD = """# 转录：单人课程.m4a

## 转录内容

00:00
只有一个人的课程内容。

01:30
继续讲解。
"""


def summary_block(speakers: list[tuple[str, str]]) -> str:
    lines = [summary.SUMMARY_START, "## AI 摘要", "### 全文总结", "概述全文。", "### 发言人总结"]
    for label, text in speakers:
        lines.append(f"- {label}：{text}")
    lines += ["### 重点内容", "- 要点一", "### 关键词", "材料, 流程", summary.SUMMARY_END]
    return "\n".join(lines) + "\n\n"


def test_extraction_keeps_speakers(root: Path) -> None:
    # 实名/匿名混合 + 小时边界：归属逐行保留
    mixed = write_md(root, "mixed.md", MIXED_MD)
    text = summary.get_transcription_text(mixed)
    assert "杨律师：我询问办理流程。张女士的材料也带来了。" in text
    assert "发言人2：我介绍所需材料。" in text
    assert "发言人3：好的，收到。" in text
    assert "发言人2：那张判决书带了吗。" in text
    # 59:59/01:00:00/01:00:04 标签不再被整体删除
    assert "01:00:04" not in text and "59:59" not in text

    expected = summary._extract_speaker_orders(mixed.read_text(encoding="utf-8"))
    assert expected == ["杨律师", "发言人2", "发言人3"], expected
    # 正文提及"张女士"没有被当成发言人；截图引用不产生发言人

    # 旧 speaker_N 格式归一
    old = write_md(root, "old.md", OLD_FORMAT_MD)
    assert summary._extract_speaker_orders(old.read_text(encoding="utf-8")) == ["发言人1", "发言人2"]
    old_text = summary.get_transcription_text(old)
    assert "发言人1：旧版第一人。" in old_text and "发言人2：旧版第二人。" in old_text
    print("提取保留身份：MM:SS/HH:MM:SS 边界、实名/匿名混合、旧 speaker_N 均保留归属")


def test_coverage_check(root: Path) -> None:
    long_md = write_md(root, "long.md", LONG_MD)
    expected = summary._extract_speaker_orders(LONG_MD)
    assert expected == ["发言人1", "发言人2", "发言人3"]

    # 完整合法摘要：通过
    path = write_md(root, "ok.md", LONG_MD)
    summary.inject_summary_to_file(path, summary_block(
        [("发言人1", "第一人观点"), ("发言人2", "第二人观点"), ("发言人3", "第三人观点")]
    ))
    result = summary.verify_summary_in_file(path)
    assert result["has_all_sections"] and result["speaker_coverage"] == "complete", result
    assert not result["missing_speakers"] and not result["unexpected_speakers"]

    # 三人稿漏任一位：章节齐全但覆盖不完整
    path = write_md(root, "missing.md", LONG_MD)
    summary.inject_summary_to_file(path, summary_block([("发言人1", "甲"), ("发言人3", "丙")]))
    result = summary.verify_summary_in_file(path)
    assert result["has_all_sections"], "章节仍然齐全，漏人必须由覆盖检查发现"
    assert result["speaker_coverage"] == "incomplete"
    assert result["missing_speakers"] == ["发言人2"], result

    # 重复一位凑人数：仍然发现缺人
    path = write_md(root, "dup.md", LONG_MD)
    summary.inject_summary_to_file(path, summary_block([("发言人1", "甲"), ("发言人2", "乙"), ("发言人2", "又乙")]))
    result = summary.verify_summary_in_file(path)
    assert result["speaker_coverage"] == "incomplete" and result["missing_speakers"] == ["发言人3"]

    # 杜撰新发言人：被发现
    path = write_md(root, "fabricated.md", LONG_MD)
    summary.inject_summary_to_file(path, summary_block(
        [("发言人1", "甲"), ("发言人2", "乙"), ("发言人3", "丙"), ("发言人4", "杜撰")]
    ))
    result = summary.verify_summary_in_file(path)
    assert result["speaker_coverage"] == "incomplete"
    assert result["unexpected_speakers"] == ["发言人4"], result

    # 实名标签摘要（带姓名注记）与预期集合一致
    mixed = write_md(root, "mixed2.md", MIXED_MD)
    summary.inject_summary_to_file(mixed, summary_block(
        [("杨律师（律师）", "本人"), ("发言人2", "客户"), ("发言人3", "客户")]
    ))
    result = summary.verify_summary_in_file(mixed)
    assert result["speaker_coverage"] == "complete", result

    # fast 无说话人：not_applicable，不误判失败也不假定覆盖
    fast = write_md(root, "fast.md", FAST_MD)
    summary.inject_summary_to_file(fast, summary_block([("发言人1", "唯一发言人")]))
    result = summary.verify_summary_in_file(fast)
    assert result["speaker_coverage"] == "not_applicable", result
    assert result["expected_speakers"] == []
    print("覆盖检查：漏人/重复凑数/杜撰均被发现，完整摘要与实名注记通过，fast 稿 not_applicable")


def test_cli_exit_code(root: Path) -> None:
    missing = write_md(root, "cli_missing.md", LONG_MD)
    summary.inject_summary_to_file(missing, summary_block([("发言人1", "甲"), ("发言人2", "乙")]))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "summary.py"), "verify", str(missing)],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, "漏人摘要的 verify 必须非零退出"
    assert "遗漏发言人" in proc.stdout and "发言人3" in proc.stdout

    ok = write_md(root, "cli_ok.md", LONG_MD)
    summary.inject_summary_to_file(ok, summary_block(
        [("发言人1", "甲"), ("发言人2", "乙"), ("发言人3", "丙")]
    ))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "summary.py"), "verify", str(ok)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "发言人覆盖完整" in proc.stdout
    print("CLI 退出码：漏人摘要非零退出并指明缺谁，完整摘要退出 0")


def test_prompt_injection_safe(root: Path) -> None:
    # 摘要注入不破坏转录正文与实名标注
    mixed = write_md(root, "inject.md", MIXED_MD)
    payload = {
        "full_summary": "这是总结。" * 50,
        "speaker_summary": [
            {"speaker_order": "杨律师", "speaker_name": "律师", "summary": "本人提问流程。"},
            {"speaker_order": "发言人2", "speaker_name": "未知", "summary": "对方介绍材料。"},
            {"speaker_order": "发言人3", "speaker_name": "未知", "summary": "对方确认收到。"},
        ],
        "highlights": ["要点"],
        "keywords": ["关键词"],
    }
    success, message = summary.inject_from_file(mixed, _write_json(root, payload))
    assert success, message
    content = mixed.read_text(encoding="utf-8")
    assert "我询问办理流程。" in content and "那张判决书带了吗。" in content
    assert "杨律师 00:00" in content and "发言人3 01:00:00" in content
    result = summary.verify_summary_in_file(mixed)
    assert result["speaker_coverage"] == "complete", result
    # 提示词要求逐字使用稿件标签
    prompt = summary.create_summary_prompt("杨律师 00:00\n内容\n")
    assert "逐字" in prompt and "speaker_order" in prompt
    print("注入安全：正文与实名标注未损坏，JSON 摘要按稿件标签注入且覆盖完整")


def _write_json(root: Path, data: dict) -> Path:
    path = root / "summary.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        test_extraction_keeps_speakers(root)
        test_coverage_check(root)
        test_cli_exit_code(root)
        test_prompt_injection_safe(root)
    print("摘要说话人归属与覆盖回归通过（提取保留身份 / 覆盖正反例 / CLI 退出码 / 注入安全）")


if __name__ == "__main__":
    main()
