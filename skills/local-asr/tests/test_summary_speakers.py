#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
test_summary_speakers.py — summary.py 发言人标签提取单元测试

不依赖模型与文件 IO：只测 _extract_speaker_orders 对 local-asr 合并段格式、
听悟 lab 板块（议程引用行 / 幻灯片时间戳行 / 章节标题行）的标签识别。
背景：tingwu 转录稿的「> 00:00 - 03:13」议程引用行行尾也是时间戳，
曾被视为发言人标签，导致 verify 的发言人覆盖校验永远失败。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import summary as sm  # noqa: E402


TINGWU_LIKE = """# 转录：示例.mp4

> 时长: 140分37秒 | 字数: 35951 | 引擎: 听悟

## 转录内容

发言人1 00:03
我们这个课程的主题就是 Agent 加法律工作的 AI 变革。

![PPT 幻灯片 1](./example_slides/slide_001.webp)
> *01:17*

发言人2 18:45
确实有打开文件。

## 议程摘要

### 法律AI工作平台与技能开发
> 00:00 - 03:13

### AI时代工作流程转型
> 03:13 - 11:03

## PPT 章节标题

1. 法律AI工作平台与技能开发 (00:00 - 03:13)
"""


def test_merged_segment_speakers_extracted_in_order():
    labels = sm._extract_speaker_orders(TINGWU_LIKE)
    assert labels == ["发言人1", "发言人2"], labels


def test_tingwu_agenda_blockquote_not_speaker():
    """议程引用行（"> 00:00 - 03:13"）不是发言行，不得进入标签集合。"""
    labels = sm._extract_speaker_orders(TINGWU_LIKE)
    assert not any(l.lstrip().startswith(">") for l in labels), labels


def test_old_style_speaker_normalized():
    text = "speaker_0: 你好\nspeaker_1 00:05 世界\n"
    labels = sm._extract_speaker_orders(text)
    assert labels == ["发言人1", "发言人2"], labels


def test_plain_text_mentions_are_not_speakers():
    text = "正文里提到 张主任 说了一句话，但没有行首时间戳。\n随便一行 00:00\n"
    # 「随便一行 00:00」是行首标签+时间戳结构，应识别；正文提及不算
    labels = sm._extract_speaker_orders(text)
    assert labels == ["随便一行"], labels


def test_get_transcription_text_skips_lab_blockquote():
    """prompt 文本提取：听悟 lab 议程/幻灯片引用行不进入说话人归属。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        md = Path(td) / "t.md"
        md.write_text(TINGWU_LIKE, encoding="utf-8")
        text = sm.get_transcription_text(md)
    lines = text.split("\n")
    # 议程引用行不再被当作 current_speaker（曾产出 "> 00:00 -：### ..."）
    assert not any(l.startswith("> ") for l in lines), lines
    assert not any("：" in l and l.split("：", 1)[0].startswith(">") for l in lines), lines
    # 真实发言归属保持；幻灯片引用时间戳行（"> *01:17*"）也整行跳过
    assert any(l.startswith("发言人1：") for l in lines), lines
    assert any(l.startswith("发言人2：") for l in lines), lines
    assert not any("*01:17*" in l for l in lines), lines


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print(f"✅ {len(tests)} tests passed")
