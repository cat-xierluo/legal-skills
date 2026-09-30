#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
align_words.py — 词级时间戳公共入口(Task-026)

给参考转录(律师 IP cut 标准 segments 或火山 utterances)补充字符级 words:
音频/视频 + transcript.json → transcript-with-words.json

时间轴契约:与 MOSS 转录一致——ffmpeg 归一化音频(16k 单声道 wav)轴,
起点=首个解码音频帧。输出在 asr meta 中显式声明。

对齐策略(可信才用,不制造伪对齐):
- 逐段切音频(±pad 余量)→ Paraformer(已缓存)识别得字符 timestamp;
- difflib 把参考文本与识别文本做块对齐;参考字符在匹配块内按识别字符
  时间线性映射,块首尾字符取块边界时间;
- 相似度低于阈值的段:words 缺省 + warnings 记录,保留原段不变。

用法(用本 skill venv 的 python 运行,依赖 funasr):
  ./venv/bin/python scripts/align_words.py <媒体> --transcript work/transcript.json \\
      --output work/transcript-words.json
可选: --pad 0.25(切段余量) --min-similarity 0.6
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

try:
    from funasr import AutoModel
except ImportError:
    print("❌ 缺少依赖: funasr", file=sys.stderr)
    print("   本入口需要本 skill 环境中的 funasr(Paraformer)。", file=sys.stderr)
    print("   请用 venv/bin/python 运行,或先执行: python3 scripts/setup.py", file=sys.stderr)
    raise SystemExit(1)

SAMPLE_RATE = 16000
MODELS = {
    "model": "speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "vad_model": "speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "punc_model": "punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
}
CACHE_ROOT = Path.home() / ".cache/modelscope/hub/models/iic"


def _resolve_cached_models() -> dict | None:
    resolved = {}
    for key, name in MODELS.items():
        p = CACHE_ROOT / name
        if not p.is_dir():
            return None
        resolved[key] = str(p)
    return resolved


def normalize_audio(media: str, out_wav: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", media,
         "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-acodec", "pcm_s16le",
         str(out_wav)],
        check=True, capture_output=True,
    )


def read_wav(path: Path):
    import wave
    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        data = w.readframes(n)
    import array
    a = array.array("h")
    a.frombytes(data)
    return a


def write_wav_slice(src: array.array, start_s: float, end_s: float, out: Path) -> None:
    import wave
    s = max(0, int(start_s * SAMPLE_RATE))
    e = min(len(src), int(end_s * SAMPLE_RATE))
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(src[s:e].tobytes())


def _iter_segments(transcript: dict):
    """产出 (raw_index, ordinal, seg, start, end)。

    B4 审计修复:raw_index 是原始数组下标(写回用,无效段跳过不位移后续段);
    ordinal 仅用于人类可读编号。"""
    raw = transcript.get("segments")
    if raw is None and "result" in transcript:
        raw = transcript["result"].get("utterances")
    ordinal = 0
    for raw_idx, seg in enumerate(raw or []):
        st = seg.get("start", seg.get("start_time"))
        en = seg.get("end", seg.get("end_time"))
        try:
            st, en = float(st), float(en)
        except (TypeError, ValueError):
            continue
        ordinal += 1
        yield raw_idx, ordinal, seg, st, en




# Paraformer 的 timestamp 只覆盖有效发音字符:标点/空白/特殊标记占 text 位
# 但没有对应条目。对齐前须剔除这些字符。
_NO_TS_CHARS = set("，。！？；：、,.!?;:…—~·\u3000 \t\n\"'\"'()（）[]【】<>《》「」『』")


def _ascii_groups(text: str) -> list:
    """把有效字符切成分组:连续 ASCII 字母数字串=一组(Paraformer 英文词
    多字符共享一条 timestamp),单个其他字符=一组。返回 [(start, end)] 字符区间。"""
    groups = []
    i = 0
    n = len(text)
    while i < n:
        if text[i].isascii() and text[i].isalnum():
            j = i
            while j < n and text[j].isascii() and text[j].isalnum():
                j += 1
            groups.append((i, j))
            i = j
        else:
            groups.append((i, i + 1))
            i += 1
    return groups


def clean_recognition(result: dict) -> tuple:
    """剔标点/特殊标记,返回 (有效字符, 每字符秒制时间, 是否含组内估计)。

    B2 审计修复:长度差只允许来自"英文/数字词多字符共享一条 timestamp"
    (按 ASCII 连续串分组,组数==ts 数时组内线性插值并标 estimate);
    组数不符直接返回空(不确定匹配交审),不再整句比例重采样制造伪时钟。"""
    text = str(result.get("text") or "")
    ts = [(a / 1000.0, b / 1000.0) for a, b in (result.get("timestamp") or [])]
    effective = [ch for ch in text if ch not in _NO_TS_CHARS and not ch.startswith("<|")]
    if not effective or not ts:
        return "", [], False
    eff = "".join(effective)
    groups = _ascii_groups(eff)
    if len(groups) != len(ts):
        return "", [], False
    times = []  # [(t0, t1, estimated)] —— F09:组内插值逐字符标记
    has_estimate = False
    for (g_start, g_end), (t0, t1) in zip(groups, ts):
        n_chars = g_end - g_start
        if n_chars == 1:
            times.append((t0, t1, False))  # 单字组:模型真实边界
        else:
            has_estimate = True
            span = (t1 - t0) / n_chars
            for k in range(n_chars):
                times.append((t0 + span * k, t0 + span * (k + 1), True))
    return eff, times, has_estimate


def align_reference_to_recognized(
    ref_text: str, rec_text: str, rec_ts: list,
    seg_start: float, seg_end: float,
) -> list:
    """把参考文本字符映射到识别字符的时间戳。

    B1 审计修复:块语义区分;F09(三轮审计)估计标记逐词贯穿——
    - equal:参考字符直接取识别字符时间(含识别侧插值来源的 estimated);
    - replace(两侧都有字符):参考字符映射到识别块 [i1,i2) 的真实起止区间
      (按位置比例),不再挤进前置间隙;参考字符数≠识别字符数时按位置分配
      的时间是估计(estimated=true),不自称真实边界;
    - insert(识别侧无对应):新增字符用前置邻接间隙内插,并标记 estimated。
    返回 [{text,start,end,estimated}](秒,段内相对时间)。"""
    rec_ts = [(tt[0], tt[1], tt[2] if len(tt) > 2 else False) for tt in rec_ts]
    sm = SequenceMatcher(None, rec_text, ref_text, autojunk=False)
    words = []
    n_rec_ts = len(rec_ts)

    def _block_range(i1, i2, j1, j2):
        """参考字符 j∈[j1,j2) 映射识别区间 [i1,i2) 的时间,按位置比例。"""
        n_rec = max(1, i2 - i1)
        n_ref = j2 - j1
        one_to_one = (n_ref == n_rec)
        for k in range(n_ref):
            frac0 = k / n_ref
            frac1 = (k + 1) / n_ref
            lo0 = rec_ts[min(i1 + int(frac0 * n_rec), n_rec_ts - 1)][0]
            hi1 = rec_ts[min(i1 + max(int(frac1 * n_rec) - 1, 0), n_rec_ts - 1)][1]
            if n_ref == 1:
                lo0 = rec_ts[min(i1, n_rec_ts - 1)][0]
                hi1 = rec_ts[min(max(i2 - 1, i1), n_rec_ts - 1)][1]
            # 一一对应:透传识别区间自身的估计标记;多对一/一对多:位置分配=估计
            est = rec_ts[min(i1 + k, n_rec_ts - 1)][2] if one_to_one else True
            yield ref_text[j1 + k], lo0, hi1, est

    def _gap_insert(j1, j2, i1):
        """insert 块:识别侧无对应字符,用邻接间隙内插。"""
        left = rec_ts[i1 - 1][1] if i1 > 0 else 0.0
        right = rec_ts[i1][0] if i1 < n_rec_ts else (seg_end - seg_start)
        span = max(right - left, 1e-3)
        n = max(1, j2 - j1)
        for k, j in enumerate(range(j1, j2)):
            yield ref_text[j], left + span * k / n, left + span * (k + 1) / n

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                rs, re_, est = rec_ts[i1 + k]
                words.append((ref_text[j1 + k], rs, re_, est))
        elif tag == "replace":
            if i2 > i1:
                for text_ch, t0, t1, est in _block_range(i1, i2, j1, j2):
                    words.append((text_ch, t0, t1, est))
            else:
                for text_ch, t0, t1 in _gap_insert(j1, j2, i1):
                    words.append((text_ch, t0, t1, True))
        elif tag == "insert":
            for text_ch, t0, t1 in _gap_insert(j1, j2, i1):
                words.append((text_ch, t0, t1, True))
        # delete: 识别多出的字符忽略
    # 夹到段范围并保证单调
    out = []
    prev = seg_start
    for text, t0, t1, est in words:
        t0 = min(max(seg_start + t0, prev), seg_end)
        t1 = min(max(seg_start + t1, t0 + 1e-3), seg_end)
        prev = t1
        out.append({"text": text, "start": round(t0, 3), "end": round(t1, 3),
                    "estimated": est})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="参考转录词级对齐(Task-026)")
    ap.add_argument("media", help="音频/视频文件")
    ap.add_argument("--transcript", required=True, help="参考转录 JSON(cut 标准)")
    ap.add_argument("--output", required=True, help="输出带 words 的转录 JSON")
    ap.add_argument("--pad", type=float, default=0.25, help="切段余量秒数")
    ap.add_argument("--min-similarity", type=float, default=0.6,
                    help="段对齐最低相似度,低于则该段 words 缺省")
    args = ap.parse_args()

    transcript = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    segments = list(_iter_segments(transcript))
    if not segments:
        print("❌ 参考转录没有可对齐的段(缺 segments/utterances 或时间字段)", file=sys.stderr)
        return 1

    models = _resolve_cached_models()
    if models is None:
        missing = [n for n in MODELS.values() if not (CACHE_ROOT / n).is_dir()]
        print("❌ 缺少已缓存模型:", file=sys.stderr)
        for m in missing:
            print(f"   {CACHE_ROOT / m}", file=sys.stderr)
        print("   先运行一次默认转录(MOSS 不需要这些)或: python3 scripts/setup.py", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="align_words_") as td:
        td = Path(td)
        wav = td / "audio.wav"
        normalize_audio(args.media, wav)
        samples = read_wav(wav)

        model = AutoModel(**models, disable_update=True, disable_pbar=True,
                          log_level="ERROR", device="cpu", ncpu=4)

        warnings: list[str] = []
        aligned_count = 0
        estimated_count = 0
        out_payload = json.loads(json.dumps(transcript))  # 深拷贝
        raw_out = out_payload.get("segments")
        if raw_out is None and "result" in out_payload:
            raw_out = out_payload["result"].get("utterances")
        out_iter = list(raw_out or [])
        # B4: 无效段显式记录,不让写回位移
        valid_raw_indices = {ri for ri, *_ in segments}
        for ri in range(len(out_iter)):
            if ri not in valid_raw_indices:
                warnings.append(f"段{ri + 1}: 缺时间字段,跳过对齐(不位移后续段)")

        for raw_idx, idx, seg, st, en in segments:
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            target = out_iter[raw_idx]  # B4: 按 raw 索引写回
            # B3: 切片与还原共用实际起点(负起点钳 0 后不再是 st-pad)
            actual_start = max(0.0, st - args.pad)
            actual_end = en + args.pad
            chunk = td / f"seg{raw_idx}.wav"
            write_wav_slice(samples, actual_start, actual_end, chunk)
            try:
                results = model.generate(input=str(chunk), batch_size_s=60)
            except Exception as exc:
                warnings.append(f"段{idx}: 识别失败 {type(exc).__name__}")
                continue
            rec_text, rec_ts, has_est = clean_recognition(results[0] if results else {})
            if not rec_text or not rec_ts:
                warnings.append(f"段{idx}: 识别无有效字符时间戳或字符/时间组数不符(交审)")
                continue
            sim = SequenceMatcher(None, rec_text, text, autojunk=False).ratio()
            if sim < args.min_similarity:
                warnings.append(
                    f"段{idx}: 参考与识别相似度 {sim:.2f} < {args.min_similarity},"
                    f"words 缺省(可信才用)")
                continue
            # chunk 内时间 → 段绝对时间(归一化轴),seg_start 用 actual_start(B3)
            words = align_reference_to_recognized(
                text, rec_text, rec_ts,
                seg_start=actual_start, seg_end=actual_end)
            # 夹回声明段范围(去掉 pad 影响)
            words = [
                {"text": w["text"],
                 "start": round(min(max(w["start"], st), en), 3),
                 "end": round(min(max(w["end"], st), en), 3),
                 **({"estimated": True} if w.get("estimated") else {})}
                for w in words
            ]
            if has_est or any(w.get("estimated") for w in words):
                estimated_count += 1
            target["words"] = words
            aligned_count += 1

    meta = out_payload.setdefault("asr", {})
    meta.setdefault("engine", "undeclared")
    meta["word_timestamps"] = {
        "available": aligned_count > 0,
        "granularity": "character",
        "unit": "seconds",
        "source": "align_words.py(paraforcer direct AutoModel)",
        "aligned_segments": aligned_count,
        "segments_with_estimated_chars": estimated_count,
        "total_segments": len(segments),
        "time_base": "normalized-audio",
        "note": (
            "ASCII 词多字符共享一条识别 timestamp 时组内时间为线性估计"
            "(word.estimated=true);对齐失败/相似度不足的段 words 缺省,见 "
            "word_alignment_warnings——不制造伪精确边界"
        ),
    }
    meta.setdefault("time_base", "normalized-audio")
    meta.setdefault("time_unit", "seconds")
    if warnings:
        out_payload["word_alignment_warnings"] = warnings

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"✅ 对齐 {aligned_count}/{len(segments)} 段 → {out}")
    for w in warnings:
        print(f"   ⚠️  {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
