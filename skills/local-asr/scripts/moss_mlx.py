"""Apple Silicon 上的可选 MOSS 转写后端。

只在实际进入 moss-mlx 路由时导入 mlx-audio；长音频分段后用 CAM++
把每段内的匿名说话人标签链接成文件内一致的标签。
"""

from __future__ import annotations

import platform
import importlib.util
import os
import re
import subprocess
import tempfile
import time
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    from . import speaker_store
except ImportError:
    import speaker_store


DEFAULT_MODEL_ID = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
SAMPLE_RATE = 16000
try:
    CHUNK_SECONDS = max(60, min(600, int(os.environ.get("FUNASR_MOSS_CHUNK_SECONDS", "600"))))
except ValueError as exc:
    raise RuntimeError("FUNASR_MOSS_CHUNK_SECONDS 必须是 60–600 的整数秒数") from exc
MAX_OUTPUT_TOKENS = 16000
SPEAKER_MATCH_THRESHOLD = 0.55
# diarize 时总是提取说话人声纹（含单段短录音），供认领注册与识别复用；
# 确定不需要时设 FUNASR_MOSS_SPEAKER_EMBEDDINGS=0 可跳过单段提取以省资源。
SPEAKER_EMBEDDINGS_ENABLED = os.environ.get("FUNASR_MOSS_SPEAKER_EMBEDDINGS", "1") != "0"
try:
    # 识别阈值与跨段链接一致：六段真实录音验收中，同人跨录音最低 0.56、
    # 非同人最高 0.14，分离边际充足；0.60 会漏识弱信道（如微信 8kHz）录音。
    SPEAKER_IDENTIFY_THRESHOLD = max(0.0, min(1.0, float(os.environ.get("FUNASR_SPEAKER_IDENTIFY_THRESHOLD", "0.55"))))
except ValueError as exc:
    raise RuntimeError("FUNASR_SPEAKER_IDENTIFY_THRESHOLD 必须是 0–1 之间的数值") from exc
SEGMENT_RE = re.compile(
    r"\[(?P<start>\d+(?:\.\d+)?)\]\[(?P<speaker>S\d+)\]"
    r"(?P<text>.*?)\[(?P<end>\d+(?:\.\d+)?)\]",
    re.DOTALL,
)
TRANSCRIPTION_PROMPT = (
    "请将音频转写为文本，每一段需以起始时间戳和说话人编号（[S01]、[S02]、[S03]…）开头，"
    "正文为对应的语音内容，并在段末标注结束时间戳，以清晰标明该段语音范围。"
)


def load_model(model_id: str = DEFAULT_MODEL_ID):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("moss-mlx 仅支持 Apple Silicon macOS；其他设备请使用 FunASR。")
    if importlib.util.find_spec("mlx_audio") is None:
        raise RuntimeError(
            "缺少默认 MOSS-MLX 依赖。请在服务使用的 Python 环境运行 "
            "`python3 -m pip install 'mlx-audio[stt]>=0.4.5,<0.5'`。"
        )
    try:
        from mlx_audio.stt.utils import load
    except ImportError as exc:
        raise RuntimeError(f"MOSS-MLX 依赖已安装但无法导入：{exc}") from exc
    if model_id == DEFAULT_MODEL_ID:
        cache_root = Path(os.environ.get("MODELSCOPE_CACHE", os.path.expanduser("~/.cache/modelscope/hub")))
        cached_model = cache_root / "models" / "OpenMOSS" / "MOSS-Transcribe-Diarize"
        if (cached_model / "config.json").is_file():
            try:
                return load(str(cached_model))
            except Exception as cache_exc:
                print(f"ModelScope 本地 MOSS 缓存加载失败，继续尝试远端来源：{cache_exc}")
    try:
        return load(model_id)
    except Exception as exc:
        if model_id == DEFAULT_MODEL_ID:
            try:
                from modelscope.hub.snapshot_download import snapshot_download
            except ImportError as dependency_exc:
                raise RuntimeError(
                    "Hugging Face 模型加载失败，且缺少 ModelScope 回退依赖；"
                    "请安装基础 requirements 或使用 --model-id 指向本地模型目录。"
                ) from dependency_exc
            try:
                print("Hugging Face 模型加载失败，尝试从 ModelScope 获取 MOSS 权重")
                local_path = snapshot_download("OpenMOSS/MOSS-Transcribe-Diarize")
                return load(local_path)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"MOSS-MLX 在 Hugging Face 和 ModelScope 均加载失败：{fallback_exc}。"
                    "可用 --model-id 指向已下载的本地模型目录。"
                ) from fallback_exc
        raise RuntimeError(
            f"MOSS-MLX 模型加载失败：{exc}。若 Hugging Face 连接失败，可先从 ModelScope "
            "下载 OpenMOSS/MOSS-Transcribe-Diarize，再通过 model_id/--model-id 指向本地目录。"
        ) from exc


def _wav_info(path: Path) -> tuple[int, int]:
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, SAMPLE_RATE):
            raise RuntimeError("MOSS 音频归一化结果不是 16kHz 单声道 PCM16")
        return stream.getnframes(), stream.getframerate()


def _read_samples(path: Path, start_frame: int, end_frame: int) -> np.ndarray:
    with wave.open(str(path), "rb") as stream:
        stream.setpos(start_frame)
        return np.frombuffer(stream.readframes(end_frame - start_frame), dtype="<i2").astype(np.float32) / 32768.0


def _split_points(path: Path, total_frames: int) -> list[int]:
    """在 10 分钟目标点附近寻找较安静的切点；绝不丢弃音频帧。"""
    points = [0]
    step = CHUNK_SECONDS * SAMPLE_RATE
    while total_frames - points[-1] > step:
        target = points[-1] + step
        start = max(points[-1] + SAMPLE_RATE, target - 15 * SAMPLE_RATE)
        end = min(total_frames - SAMPLE_RATE, target + 15 * SAMPLE_RATE)
        window = _read_samples(path, start, end)
        block = SAMPLE_RATE // 4
        usable = len(window) // block * block
        if usable:
            rms = np.sqrt(np.mean(window[:usable].reshape(-1, block) ** 2, axis=1))
            quiet = np.flatnonzero(rms < 0.004)
            runs = []
            if quiet.size:
                run_start = previous = int(quiet[0])
                for item in quiet[1:]:
                    item = int(item)
                    if item != previous + 1:
                        if previous - run_start + 1 >= 4:  # 至少 1 秒静音
                            runs.append((run_start, previous))
                        run_start = item
                    previous = item
                if previous - run_start + 1 >= 4:
                    runs.append((run_start, previous))
            if runs:
                midpoints = [start + ((a + b + 1) * block) // 2 for a, b in runs]
                cut = min(midpoints, key=lambda point: abs(point - target))
            else:
                cut = start + (int(np.argmin(rms)) * block) + block // 2
        else:
            cut = target
        if cut <= points[-1] or cut >= total_frames:
            cut = target
        points.append(cut)
    points.append(total_frames)
    return points


def _write_chunk(source: Path, target: Path, start_frame: int, end_frame: int) -> None:
    with wave.open(str(source), "rb") as reader, wave.open(str(target), "wb") as writer:
        reader.setpos(start_frame)
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(reader.readframes(end_frame - start_frame))


def _is_near_silent(path: Path) -> bool:
    """仅跳过整段几乎为零的波形，避免长录音中的纯静音块触发幻觉。"""
    with wave.open(str(path), "rb") as stream:
        while frames := stream.readframes(SAMPLE_RATE):
            samples = np.frombuffer(frames, dtype="<i2")
            if samples.size and int(np.max(np.abs(samples.astype(np.int32)))) > 3:
                return False
    return True


def _parse_output(output, duration_s: float) -> list[dict]:
    raw = str(getattr(output, "text", "") or "").strip()
    token_count = getattr(output, "generation_tokens", None)
    if token_count is not None and token_count >= MAX_OUTPUT_TOKENS:
        raise RuntimeError("MOSS 输出达到 token 上限，可能截断；可调低 FUNASR_MOSS_CHUNK_SECONDS 后重启服务重试。")
    matches = list(SEGMENT_RE.finditer(raw))
    if (
        not matches
        or raw[:matches[0].start()].strip()
        or raw[matches[-1].end():].strip()
        or any(raw[left.end():right.start()].strip() for left, right in zip(matches, matches[1:]))
    ):
        raise RuntimeError("MOSS 输出缺少完整的时间戳/说话人段，拒绝写入不完整转录稿。")
    segments = []
    previous_start = -1.0
    for match in matches:
        start = float(match.group("start"))
        end = float(match.group("end"))
        sentence = match.group("text").strip()
        if (
            not sentence or start < previous_start or end <= start
            or start >= duration_s + 0.01 or end > duration_s + 0.5
        ):
            raise RuntimeError("MOSS 输出段的文字或时间戳无效，拒绝写入转录稿。")
        segments.append({
            "start": start,
            "end": end,
            "speaker": match.group("speaker"),
            "text": sentence,
        })
        previous_start = start
    return segments


def _discard_near_silent(path: Path, segments: list[dict]) -> tuple[list[dict], int]:
    """仅剔除几乎没有任何波形能量的生成段；正常低音量人声保留。"""
    kept = []
    removed = 0
    for segment in segments:
        start = max(0, int(segment["start"] * SAMPLE_RATE))
        end = max(start + 1, int(segment["end"] * SAMPLE_RATE))
        samples = _read_samples(path, start, end)
        if samples.size and float(np.max(np.abs(samples))) <= 0.0001:
            removed += 1
        else:
            kept.append(segment)
    return kept, removed


def _speaker_embeddings(path: Path, segments: list[dict], speaker_model) -> dict[str, np.ndarray]:
    """每个段内说话人最多取 30 秒音频；短发言不强行跨段认人。"""
    regions = defaultdict(list)
    for segment in segments:
        regions[segment["speaker"]].append(segment)
    samples, labels = [], []
    for label, turns in regions.items():
        pieces = []
        remaining = 30 * SAMPLE_RATE
        for turn in sorted(turns, key=lambda item: item["end"] - item["start"], reverse=True):
            start = max(0, int(turn["start"] * SAMPLE_RATE))
            end = min(int(turn["end"] * SAMPLE_RATE), start + remaining)
            if end > start:
                pieces.append(_read_samples(path, start, end))
                remaining -= end - start
            if remaining <= 0:
                break
        if pieces and sum(len(piece) for piece in pieces) >= 3 * SAMPLE_RATE:
            samples.append(np.concatenate(pieces))
            labels.append(label)
    if not samples:
        return {}
    raw, _ = speaker_model.model.inference(
        samples, key=[f"moss_spk_{index}" for index in range(len(samples))], **speaker_model.kwargs
    )
    vectors = raw[0]["spk_embedding"]
    if hasattr(vectors, "detach"):
        vectors = vectors.detach().cpu().numpy()
    else:
        vectors = np.asarray(vectors)
    return {label: np.asarray(vector, dtype=np.float32).reshape(-1) for label, vector in zip(labels, vectors)}


def _link_speakers(chunks: list[tuple[Path, list[dict]]], speaker_model) -> tuple[list[dict], dict[str, np.ndarray]]:
    """贪心链接跨段声纹；同一段内不同标签不能并入同一个全局说话人。

    同时返回全局标签到单位声纹向量的映射，供声纹识别/认领复用。
    """
    profiles: list[np.ndarray | None] = []
    linked = []
    for chunk_index, (path, segments) in enumerate(chunks):
        embeddings = _speaker_embeddings(path, segments, speaker_model)
        local_to_global = {}
        used = set()
        for local in dict.fromkeys(seg["speaker"] for seg in segments):
            vector = embeddings.get(local)
            if vector is not None:
                vector = vector / max(float(np.linalg.norm(vector)), 1e-8)
            candidates = [
                (float(np.dot(vector, profile)), index)
                for index, profile in enumerate(profiles)
                if vector is not None and profile is not None and index not in used
            ]
            best_score, best_index = max(candidates, default=(-1.0, -1))
            if best_score >= SPEAKER_MATCH_THRESHOLD:
                global_index = best_index
                blended = profiles[best_index] + vector
                profiles[best_index] = blended / max(float(np.linalg.norm(blended)), 1e-8)
            else:
                global_index = len(profiles)
                profiles.append(vector)
            local_to_global[local] = global_index
            used.add(global_index)
        for segment in segments:
            linked.append({**segment, "speaker": f"S{local_to_global[segment['speaker']] + 1:02d}", "chunk": chunk_index})
    global_embeddings = {
        f"S{index + 1:02d}": profile for index, profile in enumerate(profiles) if profile is not None
    }
    return linked, global_embeddings


def _identify_speakers(embeddings: dict[str, np.ndarray], speaker_profiles: list[dict]
                       ) -> tuple[dict[str, dict | None], list[str]]:
    """把文件内说话人标签与本地声纹库比对；分数需达阈值，同一注册名只命中一个标签。

    声纹库历史条目与比对计算都做逐条防御：坏条目/计算异常只隔离该条或该标签，
    进入 issues 告警，绝不让识别附加步骤抛错阻断转录。
    返回 (identification: 标签 → {"name","score"} 或 null, issues: 隔离原因)。
    """
    identification: dict[str, dict | None] = {label: None for label in embeddings}
    issues: list[str] = []
    registry = []
    for profile in speaker_profiles or []:
        try:
            if not isinstance(profile, dict):
                raise ValueError("条目不是对象")
            name = str(profile.get("name", "")).strip()
            if not name:
                raise ValueError("条目缺少有效 name")
            raw = np.asarray(profile.get("embedding") or [], dtype=np.float32).reshape(-1)
            if raw.size != speaker_store.EXPECTED_EMBEDDING_DIM:
                raise ValueError(
                    f"条目向量维度 {raw.size} 与当前模型 {speaker_store.EXPECTED_EMBEDDING_DIM} 不符"
                )
            norm = float(np.linalg.norm(raw.astype(np.float64)))
            if raw.size == 0 or not np.all(np.isfinite(raw)) or not np.isfinite(norm) or norm <= 1e-8:
                raise ValueError("条目向量无效（数值/范数）")
            registry.append((name, raw / norm))
        except (ValueError, TypeError) as exc:
            label_hint = str(profile.get("name", "<未命名>"))[:50] if isinstance(profile, dict) else "<非对象条目>"
            issues.append(f"声纹库条目已隔离（{label_hint}）: {exc}")
    candidates = []
    for label, vector in embeddings.items():
        try:
            norm = float(np.linalg.norm(vector.astype(np.float64)))
            if norm <= 1e-8 or not np.isfinite(norm) or not np.all(np.isfinite(vector)):
                issues.append(f"说话人 {label} 声纹向量无效，本次保持匿名")
                continue
            if not registry:
                break
            unit = vector / norm
            name, score = max(
                ((name, float(np.dot(unit, ref))) for name, ref in registry),
                key=lambda item: item[1],
            )
            if not np.isfinite(score):
                issues.append(f"说话人 {label} 声纹比对出现非有限分数，本次保持匿名")
                continue
            candidates.append((score, label, name))
        except (ValueError, TypeError) as exc:
            issues.append(f"说话人 {label} 声纹比对失败，本次保持匿名: {exc}")
    used_names = set()
    for score, label, name in sorted(candidates, reverse=True):
        if score >= SPEAKER_IDENTIFY_THRESHOLD and name not in used_names:
            identification[label] = {"name": name, "score": round(score, 4)}
            used_names.add(name)
    return identification, issues


def _build_speaker_states(all_labels: list[str], identification: dict,
                          unit_embeddings: dict[str, np.ndarray],
                          extraction_failed: bool = False,
                          identify_failed: bool = False,
                          disabled_reason: str | None = None) -> dict[str, dict]:
    """按稳定 speaker ID 构建完整识别状态（Task-019 契约）。

    状态语义：
    - matched            命中注册声纹（name 为注册名）
    - unknown            有合格声纹向量但未达阈值（可认领注册）
    - insufficient_audio 总发言不足 3 秒，未提取声纹（仅可为本稿命名，不能持久注册）
    - extraction_failed  声纹提取/识别步骤失败（本次无法识别/认领）
    - disabled           说话人声纹识别未启用（fast / 显式关闭提取 / CAM++ 模型不可用）
    """
    states: dict[str, dict] = {}
    for label in all_labels:
        hit = identification.get(label)
        if hit:
            states[label] = {"status": "matched", "name": hit["name"]}
        elif disabled_reason:
            states[label] = {"status": "disabled", "name": None, "detail": disabled_reason}
        elif identify_failed:
            states[label] = {"status": "extraction_failed", "name": None,
                             "detail": "声纹识别步骤失败，本次保持匿名"}
        elif label in unit_embeddings:
            states[label] = {"status": "unknown", "name": None,
                             "detail": "有声纹向量但未达阈值，可经用户确认后认领注册"}
        elif extraction_failed:
            states[label] = {"status": "extraction_failed", "name": None,
                             "detail": "声纹提取失败，本次无法识别或认领"}
        else:
            states[label] = {"status": "insufficient_audio", "name": None,
                             "detail": "总发言不足 3 秒，未提取声纹；只能为本稿命名，不能持久注册"}
    return states


def transcribe(file_path: str, model, speaker_model_factory=None, hotwords: list[str] | None = None,
               diarize: bool = True, speaker_profiles: list[dict] | None = None) -> dict:
    """返回兼容 FunASR 的 text / sentence_info 结构。

    diarize 时额外返回 speaker_embeddings（文件内标签→单位声纹向量，供认领注册）、
    speaker_identification（与本地声纹库逐人比对结果；空库时全部为 null，识别故障时
    保持匿名并告警）和 speaker_states（每位说话人的完整识别状态，含 insufficient_audio /
    extraction_failed / disabled 等显式原因）。
    """
    timings = {}
    warnings = []
    speaker_extraction_failed = False
    speaker_disabled_reason: str | None = None
    if diarize and not SPEAKER_EMBEDDINGS_ENABLED:
        speaker_disabled_reason = "声纹提取已显式关闭（FUNASR_MOSS_SPEAKER_EMBEDDINGS=0）"
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="moss_mlx_") as temp_dir:
        workspace = Path(temp_dir)
        normalized = workspace / "audio.wav"
        phase = time.perf_counter()
        try:
            process = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", file_path,
                 "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-acodec", "pcm_s16le", str(normalized)],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("缺少 ffmpeg；请在 macOS 运行 `brew install ffmpeg` 后重试") from exc
        if process.returncode != 0:
            raise RuntimeError(f"音频归一化失败：{process.stderr.strip()[:300]}")
        total_frames, _ = _wav_info(normalized)
        if total_frames == 0:
            raise RuntimeError("音频为空，无法转录")
        points = _split_points(normalized, total_frames)
        timings["audio_prepare_s"] = round(time.perf_counter() - phase, 3)
        chunks = []
        phase = time.perf_counter()
        for index, (start, end) in enumerate(zip(points, points[1:])):
            chunk_path = workspace / f"chunk_{index:04d}.wav"
            _write_chunk(normalized, chunk_path, start, end)
            if _is_near_silent(chunk_path):
                chunks.append((chunk_path, []))
                warnings.append(f"第 {index + 1} 段音频近乎静音，已跳过模型推理")
                continue
            try:
                prompt = TRANSCRIPTION_PROMPT
                if hotwords:
                    prompt += "热词提示：" + ", ".join(hotwords[:30])
                output = model.generate(
                    str(chunk_path), max_tokens=MAX_OUTPUT_TOKENS,
                    prompt=prompt, temperature=0.0,
                )
            except Exception as exc:
                raise RuntimeError(f"MOSS 第 {index + 1} 段推理失败：{exc}") from exc
            duration = (end - start) / SAMPLE_RATE
            segments = _parse_output(output, duration)
            segments, silent_count = _discard_near_silent(chunk_path, segments)
            if silent_count:
                warnings.append(f"第 {index + 1} 段剔除 {silent_count} 条近乎静音的模型输出")
            chunks.append((chunk_path, segments))
        if not any(segments for _, segments in chunks):
            raise RuntimeError("MOSS 未输出可验证的语音段，未生成转录稿。")
        timings["asr_s"] = round(time.perf_counter() - phase, 3)
        phase = time.perf_counter()
        speaker_embeddings: dict[str, np.ndarray] = {}
        if len(chunks) > 1 and diarize:
            if speaker_model_factory is None:
                raise RuntimeError("长录音需要 CAM++ 跨段链接说话人，但说话人模型不可用")
            speaker_model = speaker_model_factory()
            linked, speaker_embeddings = _link_speakers(chunks, speaker_model)
        else:
            linked = [
                {**segment, "chunk": index}
                for index, (_, segments) in enumerate(chunks)
                for segment in segments
            ]
            if diarize and SPEAKER_EMBEDDINGS_ENABLED and speaker_model_factory is not None and len(chunks) == 1:
                # 单段录音：无跨段链接需求，但为声纹识别/认领提取嵌入
                try:
                    speaker_model = speaker_model_factory()
                    speaker_embeddings = _speaker_embeddings(chunks[0][0], chunks[0][1], speaker_model)
                except Exception as exc:
                    speaker_extraction_failed = True
                    warnings.append(f"声纹提取失败，本次不做说话人识别: {exc}")
            elif diarize and SPEAKER_EMBEDDINGS_ENABLED and speaker_model_factory is None and len(chunks) == 1:
                speaker_disabled_reason = "CAM++ 说话人模型不可用，未提取声纹"
        timings["speaker_link_s"] = round(time.perf_counter() - phase, 3)
        sentence_info = []
        for segment in linked:
            offset = points[segment["chunk"]] / SAMPLE_RATE
            sentence_info.append({
                "start": round((offset + segment["start"]) * 1000),
                "end": round((offset + segment["end"]) * 1000),
                "sentence": segment["text"],
                "spk": segment["speaker"],
            })
        if diarize:
            speaker_durations = defaultdict(float)
            for segment in sentence_info:
                speaker_durations[segment["spk"]] += (segment["end"] - segment["start"]) / 1000
            if len(speaker_durations) >= 2:
                for label, duration in speaker_durations.items():
                    if duration < 3:
                        warnings.append(f"说话人 {label} 总发言约 {duration:.1f} 秒，匿名标签可能不稳定，请人工核对")
    timings["moss_total_s"] = round(time.perf_counter() - started, 3)
    result = {
        "text": "".join(segment["sentence"] for segment in sentence_info),
        "sentence_info": sentence_info,
        "speaker_scope": "global" if diarize else "none",
        "_timings": timings,
        "_warnings": warnings,
    }
    if diarize:
        # Task-019：以全部转录段的稳定 speaker ID 为全集建立识别状态，
        # 空库/短发言/提取失败/主动关闭都有明确结果，不再依赖字段缺失推断。
        all_labels = list(dict.fromkeys(segment["spk"] for segment in sentence_info))
        unit_embeddings: dict[str, np.ndarray] = {}
        for label, vector in speaker_embeddings.items():
            norm = float(np.linalg.norm(np.asarray(vector, dtype=np.float64)))
            if np.isfinite(norm) and norm > 1e-8:
                unit_embeddings[label] = np.asarray(vector, dtype=np.float64) / norm
        identification: dict[str, dict | None] = {label: None for label in all_labels}
        identify_issues: list[str] = []
        identify_failed = False
        if unit_embeddings and speaker_profiles is not None:
            try:
                identification, identify_issues = _identify_speakers(unit_embeddings, speaker_profiles)
                identification = {**{label: None for label in all_labels}, **identification}
            except Exception as exc:  # 识别附加步骤失败：降级为全匿名，不影响文字稿交付
                identify_failed = True
                identify_issues.append(f"声纹识别步骤失败，本次全部保持匿名: {exc}")
        if identify_issues:
            warnings.extend(identify_issues)
        if speaker_embeddings:
            result["speaker_embeddings"] = {
                label: [round(float(x), 6) for x in vector]
                for label, vector in unit_embeddings.items()
            }
        result["speaker_identification"] = identification
        result["speaker_states"] = _build_speaker_states(
            all_labels, identification, unit_embeddings,
            extraction_failed=speaker_extraction_failed,
            identify_failed=identify_failed,
            disabled_reason=speaker_disabled_reason,
        )
        if speaker_profiles is not None and unit_embeddings:
            hits = [
                f"{label}={info['name']}({info['score']:.2f})"
                for label, info in identification.items() if info
            ]
            misses = [label for label, info in identification.items() if not info]
            parts = []
            if hits:
                parts.append("已识别 " + "、".join(hits))
            if misses:
                parts.append("未识别 " + "、".join(misses) + "（可经用户确认后认领注册）")
            if parts:
                warnings.append("说话人声纹识别：" + "；".join(parts))
    else:
        # fast / 显式关闭分离：明确表达识别未启用，不谎报为"未识别"。
        result["speaker_states"] = {
            segment["spk"]: {"status": "disabled", "name": None,
                             "detail": "说话人声纹识别未启用（fast/diarize=false）"}
            for segment in sentence_info if segment.get("spk")
        }
    return result
