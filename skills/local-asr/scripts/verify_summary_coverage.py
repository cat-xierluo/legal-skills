#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""摘要说话人归属与覆盖检查回归（Task-021）。

覆盖：
- 提取保留身份：MM:SS / HH:MM:SS 边界、实名/匿名混合、旧 speaker_N 格式
- 覆盖检查：漏人/重复凑数/杜撰发言人必须失败，完整合法摘要通过
- 不误报：正文提及人名、截图引用不凭空增加发言人
- fast 无说话人稿件：not_applicable（不假定通过也不误判失败）
- CLI verify/inject 对覆盖不完整以非零退出码传递给调用方
- formatter 负例（Task-021 F1）：缺失占位不充当覆盖、重复条目拒绝注入、
  推荐的"生成 JSON → 格式化 → 注入 → 验证"路径与 CLI 退出码一致

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

TWO_SPK_MD = """# 转录：两人对话.wav

## 转录内容

发言人1 00:00
第一人提问。

发言人2 00:30
第二人解答。
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


def _write_json(root: Path, data: dict, name: str = "summary.json") -> Path:
    path = root / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _speaker(order: str, name: str = "", text: str | None = None) -> dict:
    entry = {"speaker_order": order, "summary": f"{order}的观点。" if text is None else text}
    if name:
        entry["speaker_name"] = name
    return entry


def test_json_formatter_quality(root: Path) -> None:
    """Task-021 F1：推荐的"生成 JSON → 格式化 → 注入 → 验证"路径，缺失占位不充当覆盖。"""
    base = {
        "full_summary": "两人讨论了流程。",
        "highlights": ["要点"],
        "keywords": ["关键词"],
    }

    def run_inject(md_name: str, speakers: list, raw: dict | None = None) -> tuple:
        path = write_md(root, md_name, TWO_SPK_MD)
        data = dict(base)
        data["speaker_summary"] = speakers
        return path, summary.inject_from_file(path, _write_json(root, data, f"{md_name}.json"))

    # 两人稿 JSON 只给第一人：formatter 补的占位行不得算覆盖，verify 必须报漏人
    path, (success, message) = run_inject("fmt_missing.md", [_speaker("发言人1")])
    assert success, message
    content = path.read_text(encoding="utf-8")
    assert "发言人2：（摘要缺失，请补充。）" in content, "占位行保留可提示补齐"
    result = summary.verify_summary_in_file(path)
    assert result["speaker_coverage"] == "incomplete", result
    assert result["missing_speakers"] == ["发言人2"], result

    # CLI inject 同路径：质量失败非零退出（写入成功 ≠ 验收通过）
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "summary.py"), "inject", str(path),
         str(root / "fmt_missing.md.json")],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, proc.stdout
    assert "摘要质量未通过" in proc.stdout and "发言人2" in proc.stdout

    # 空 speaker_summary：两人全部缺失
    path, (success, _) = run_inject("fmt_empty.md", [])
    assert success
    result = summary.verify_summary_in_file(path)
    assert result["speaker_coverage"] == "incomplete"
    assert result["missing_speakers"] == ["发言人1", "发言人2"], result

    # summary 为空字符串：该条目无效，等同缺失
    path, (success, _) = run_inject("fmt_blank.md", [_speaker("发言人1", text="")])
    assert success
    result = summary.verify_summary_in_file(path)
    assert result["speaker_coverage"] == "incomplete"
    assert result["missing_speakers"] == ["发言人1", "发言人2"], result

    # 摘要内容只有占位文本：不充当覆盖
    path, (success, _) = run_inject(
        "fmt_placeholder.md",
        [_speaker("发言人1", text=summary.MISSING_SUMMARY_PLACEHOLDER), _speaker("发言人2", text="乙")],
    )
    assert success
    result = summary.verify_summary_in_file(path)
    assert result["speaker_coverage"] == "incomplete", result
    assert result["missing_speakers"] == ["发言人1"], result
    assert result["covered_speakers"] == ["发言人2"], result

    # 重复第一人凑人数：formatter 在归一化前拒绝，不写入半成品
    path, (success, message) = run_inject(
        "fmt_duplicate.md", [_speaker("发言人1", text="甲"), _speaker("发言人1", text="甲又")]
    )
    assert not success, "重复发言人条目必须拒绝注入"
    assert "发言人1" in message and "重复" in message, message
    assert summary.SUMMARY_START not in path.read_text(encoding="utf-8"), "被拒绝的数据不得写入文件"

    # 三人稿同样适用（漏两人）
    three_md = write_md(root, "three.md", LONG_MD)
    data = dict(base)
    data["speaker_summary"] = [_speaker("发言人1", text="甲")]
    success, _ = summary.inject_from_file(three_md, _write_json(root, data, "three.json"))
    assert success
    result = summary.verify_summary_in_file(three_md)
    assert result["speaker_coverage"] == "incomplete"
    assert result["missing_speakers"] == ["发言人2", "发言人3"], result

    # 完整合法 JSON（含姓名注记）正例：complete 且 CLI inject 退出 0
    path = write_md(root, "fmt_ok.md", TWO_SPK_MD)
    data = dict(base)
    data["speaker_summary"] = [_speaker("发言人1", name="杨律师"), _speaker("发言人2", name="客户")]
    ok_json = _write_json(root, data, "fmt_ok.json")
    success, message = summary.inject_from_file(path, ok_json)
    assert success, message
    result = summary.verify_summary_in_file(path)
    assert result["speaker_coverage"] == "complete", result
    assert "- 发言人1（杨律师）：" in path.read_text(encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "summary.py"), "inject", str(path), str(ok_json)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # 重复注入不破坏正文：正文发言与时间戳仍在
    assert "第一人提问。" in path.read_text(encoding="utf-8")

    # CLI verify 对 formatter 产出的漏人稿同样非零退出
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "summary.py"), "verify", str(root / "fmt_missing.md")],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0 and "发言人2" in proc.stdout
    print("formatter 负例：缺人/空/空摘要/仅占位/重复凑人数均被拦截，"
          "CLI inject 与 verify 退出码一致反映质量失败，正例与重复注入不受影响")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        test_extraction_keeps_speakers(root)
        test_coverage_check(root)
        test_cli_exit_code(root)
        test_prompt_injection_safe(root)
        test_json_formatter_quality(root)
    print("摘要说话人归属与覆盖回归通过（提取保留身份 / 覆盖正反例 / CLI 退出码 / 注入安全 / formatter 负例）")


if __name__ == "__main__":
    main()
