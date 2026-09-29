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
    raw = transcript.get("segments")
    if raw is None and "result" in transcript:
        raw = transcript["result"].get("utterances")
    for idx, seg in enumerate(raw or [], start=1):
        st = seg.get("start", seg.get("start_time"))
        en = seg.get("end", seg.get("end_time"))
        try:
            st, en = float(st), float(en)
        except (TypeError, ValueError):
            continue
        yield idx, seg, st, en


def align_reference_to_recognized(
    ref_text: str, rec_text: str, rec_ts: list,
    seg_start: float, seg_end: float,
) -> list:
    """把参考文本字符映射到识别字符的时间戳。

    rec_ts: Paraformer timestamp [[start_ms,end_ms],...] 与 rec_text 字符一一对应
    (nosync 等标记须先清除并同步裁剪)。返回 [{text,start,end}](秒,段内绝对时间)。
    匹配块内:参考字符时间=识别字符时间;参考多出的字符按邻近距离内插。
    """
    rec_secs = rec_ts  # clean_recognition 已转秒
    sm = SequenceMatcher(None, rec_text, ref_text, autojunk=False)
    words = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                rs, re_ = rec_secs[i1 + k]
                words.append((ref_text[j1 + k], rs, re_))
        elif tag in ("insert", "replace"):
            # 参考多出的字符:在识别侧邻接边界内插
            left = rec_secs[i1 - 1][1] if i1 > 0 else 0.0
            right = rec_secs[i1][0] if i1 < len(rec_secs) else (seg_end - seg_start)
            span = max(right - left, 1e-3)
            for k, j in enumerate(range(j1, j2)):
                t0 = left + span * (k / max(1, j2 - j1))
                t1 = left + span * ((k + 1) / max(1, j2 - j1))
                words.append((ref_text[j], t0, t1))
        # delete: 识别多出的字符忽略
    # 夹到段范围并保证单调
    out = []
    prev = seg_start
    for text, t0, t1 in words:
        t0 = min(max(seg_start + t0, prev), seg_end)
        t1 = min(max(seg_start + t1, t0 + 1e-3), seg_end)
        prev = t1
        out.append({"text": text, "start": round(t0, 3), "end": round(t1, 3)})
    return out


# Paraformer 的 timestamp 只覆盖有效发音字符:标点/空白/特殊标记占 text 位
# 但没有对应条目。对齐前须剔除这些字符。
_NO_TS_CHARS = set("，。！？；：、,.!?;:…—~·\u3000 \t\n\"'\"'()（）[]【】<>《》「」『』")


def clean_recognition(result: dict) -> tuple[str, list]:
    """剔标点/特殊标记,返回 (有效字符, 对应秒制时间列表)。

    Paraformer 实测:标点无 timestamp;英文词多字符共享一条(如 "JI" 2 字符
    1 条)。因此不要求一一对应,按字符位置对 ts 序列线性插值取近似时间——
    误差在字符粒度内,逐字字幕足够;无 ts 或无有效字符返回空。"""
    text = str(result.get("text") or "")
    ts = [(s / 1000.0, e / 1000.0) for s, e in (result.get("timestamp") or [])]
    effective = [ch for ch in text if ch not in _NO_TS_CHARS and not ch.startswith("<|")]
    if not effective or not ts:
        return "", []
    n, m = len(effective), len(ts)
    times = []
    for i in range(n):
        pos = i * m / n
        j = min(int(pos), m - 1)
        if j + 1 < m:
            frac = pos - j
            t0 = ts[j][0] + (ts[j + 1][0] - ts[j][0]) * frac
            t1 = ts[j][1] + (ts[j + 1][1] - ts[j][1]) * frac
        else:
            t0, t1 = ts[j]
        times.append((t0, t1))
    return "".join(effective), times


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
        out_payload = json.loads(json.dumps(transcript))  # 深拷贝
        # out_payload 与 segments 同构遍历
        raw_out = out_payload.get("segments")
        if raw_out is None and "result" in out_payload:
            raw_out = out_payload["result"].get("utterances")
        out_iter = list(raw_out or [])

        for (idx, seg, st, en), target in zip(segments, out_iter):
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            chunk = td / f"seg{idx}.wav"
            write_wav_slice(samples, st - args.pad, en + args.pad, chunk)
            try:
                results = model.generate(input=str(chunk), batch_size_s=60)
            except Exception as exc:
                warnings.append(f"段{idx}: 识别失败 {type(exc).__name__}")
                continue
            rec_text, rec_ts = clean_recognition(results[0] if results else {})
            if not rec_text or not rec_ts:
                warnings.append(f"段{idx}: 识别无有效字符时间戳")
                continue
            sim = SequenceMatcher(None, rec_text, text, autojunk=False).ratio()
            if sim < args.min_similarity:
                warnings.append(
                    f"段{idx}: 参考与识别相似度 {sim:.2f} < {args.min_similarity},"
                    f"words 缺省(可信才用)")
                continue
            # chunk 内时间 → 段绝对时间(归一化轴)
            words = align_reference_to_recognized(
                text, rec_text, rec_ts,
                seg_start=st - args.pad, seg_end=en + args.pad)
            # 夹回声明段范围(去掉 pad 影响)
            words = [
                {"text": w["text"],
                 "start": round(min(max(w["start"], st), en), 3),
                 "end": round(min(max(w["end"], st), en), 3)}
                for w in words
            ]
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
        "total_segments": len(segments),
        "time_base": "normalized-audio",
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
