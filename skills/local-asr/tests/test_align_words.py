#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
test_align_words.py — align_words.py 纯函数单元测试(Task-026)

不加载模型:只测 clean_recognition(标点/英文词/长度差处理)与
align_reference_to_recognized(difflib 块映射/内插/单调/夹取)。
模型路径的真实端到端在任务卡验收记录(真实原片 11/11 段对齐)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# align_words 顶层 import funasr(硬依赖),单测环境可能没有 → 桩掉
import types
try:
    import funasr  # noqa: F401
except ImportError:
    sys.modules["funasr"] = types.ModuleType("funasr")
    sys.modules["funasr"].AutoModel = object

import align_words as aw  # noqa: E402


# ---------- clean_recognition ----------

def test_clean_recognition_strips_punctuation():
    """标点占 text 位但无 timestamp:剔除后一一对应。"""
    text = "临时想到一个事儿，就是。"
    ts = [[320, 480], [480, 640], [640, 800], [800, 960], [960, 1120],
          [1120, 1280], [1280, 1440], [1440, 1600], [1600, 1760],
          [1760, 1920]]  # 10 条 = 10 个有效字
    out_text, out_ts = aw.clean_recognition({"text": text, "timestamp": ts})
    assert out_text == "临时想到一个事儿就是", out_text
    assert len(out_ts) == 10
    assert out_ts[0] == (0.32, 0.48)


def test_clean_recognition_english_word_interpolates():
    """英文词多字符共享一条 ts(如 JI):比例插值,不报错不丢字。"""
    text = "JI生成的。"
    ts = [[100, 400], [400, 600], [600, 800], [800, 1000]]  # 4 条 vs 4 有效字符
    out_text, out_ts = aw.clean_recognition({"text": text, "timestamp": ts})
    assert out_text == "JI生成的"  # 5 有效字符
    assert len(out_ts) == 5  # 4 条 ts 比例插值到 5 字符
    # 长度差场景:ts 多于字符
    ts2 = [[100, 200], [200, 300], [300, 400]]
    out_text2, out_ts2 = aw.clean_recognition({"text": "JI成", "timestamp": ts2})
    assert out_text2 == "JI成"
    assert len(out_ts2) == 3
    # ts 少于字符
    out_text3, out_ts3 = aw.clean_recognition({"text": "JI生成", "timestamp": ts2})
    assert out_text3 == "JI生成" and len(out_ts3) == 4
    # 插值时间单调不减
    assert all(out_ts3[i][1] <= out_ts3[i + 1][0] + 1e-9 or
               out_ts3[i][1] <= out_ts3[i + 1][1] for i in range(3))


def test_clean_recognition_empty_cases():
    assert aw.clean_recognition({"text": "", "timestamp": []}) == ("", [])
    assert aw.clean_recognition({"text": "abc"}) == ("", [])
    assert aw.clean_recognition({"timestamp": [[1, 2]]}) == ("", [])


# ---------- align_reference_to_recognized ----------

def test_align_equal_text_maps_directly():
    ref = "不能用"
    rec = "不能用"
    ts = [(0.0, 0.3), (0.3, 0.6), (0.6, 1.0)]
    words = aw.align_reference_to_recognized(ref, rec, ts, 0.0, 1.0)
    assert [w["text"] for w in words] == ["不", "能", "用"]
    assert words[0]["start"] == 0.0 and words[2]["end"] == 1.0
    assert all(words[i]["end"] <= words[i + 1]["start"] + 1e-6
               for i in range(len(words) - 1))


def test_align_correction_maps():
    """参考有纠正词而识别为原错词:equal 块外的参考字符走邻接内插。"""
    ref = "AI生成"
    rec = "JI生成"  # JI→AI 两字符替换
    ts = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.7), (0.7, 1.0)]
    words = aw.align_reference_to_recognized(ref, rec, ts, 0.0, 1.0)
    assert "".join(w["text"] for w in words) == "AI生成"
    # 替换块 A/I 在识别前两字符时间附近内插
    assert 0.0 <= words[0]["start"] <= 0.45
    # 生成 二字与识别后两字符对齐
    assert abs(words[2]["start"] - 0.4) < 1e-6


def test_align_clamps_and_monotonic():
    """输出夹在段范围内且严格单调(插值边界不倒退)。"""
    ref = "很长的一段参考文本内容"
    rec = "识别文本"
    ts = [(0.1, 0.3), (0.4, 0.6), (0.65, 0.8), (0.85, 0.95)]
    words = aw.align_reference_to_recognized(ref, rec, ts, 2.0, 5.0)
    assert all(2.0 <= w["start"] and w["end"] <= 5.0 for w in words)
    for i in range(len(words) - 1):
        assert words[i]["end"] <= words[i + 1]["start"] + 1e-6


def test_align_extra_reference_chars_interpolate():
    """识别侧漏字(delete 块):参考多出字符在邻接边界内插,不丢字。"""
    ref = "千万不要觉得"
    rec = "千万觉得"  # 漏"不要"
    ts = [(0.0, 0.3), (0.3, 0.6), (0.6, 0.9), (0.9, 1.2)]
    words = aw.align_reference_to_recognized(ref, rec, ts, 0.0, 1.2)
    assert "".join(w["text"] for w in words) == "千万不要觉得"
    assert words[2]["start"] >= words[1]["end"] - 1e-6


if __name__ == "__main__":
    test_clean_recognition_strips_punctuation()
    test_clean_recognition_english_word_interpolates()
    test_clean_recognition_empty_cases()
    test_align_equal_text_maps_directly()
    test_align_correction_maps()
    test_align_clamps_and_monotonic()
    test_align_extra_reference_chars_interpolate()
    print(f"✅ {7} tests passed")
