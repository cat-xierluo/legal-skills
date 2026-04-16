#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
FunASR 转录服务 - HTTP API 服务器（FastAPI版）
启动本地 ASR 服务，提供音频/视频转录功能
支持自动启动和空闲自动关闭（10分钟）
"""

import os
import sys
import json
import shutil
import signal
import time
import copy
from datetime import datetime
from pathlib import Path
from typing import Optional
import argparse
import threading

import numpy as np

# 获取脚本所在目录和 skill 根目录
SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
MODELS_CONFIG = SKILL_DIR / "assets" / "models.json"
ARCHIVE_ROOT = SKILL_DIR / "archive"


def build_archive_subdir(source_file: str) -> Path:
    """构建归档子目录路径：archive/YYYYMMDD_HHMMSS_文件名（去扩展名）"""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    base_name = Path(source_file).stem
    # 截断过长的文件名
    if len(base_name) > 60:
        base_name = base_name[:60]
    return ARCHIVE_ROOT / f"{date_str}_{time_str}_{base_name}"


def archive_transcription(source_file: str, output_md: str, slides: list = None,
                          diarize: bool = False, slide_threshold: float = 27.0) -> dict:
    """归档转录结果到 archive 目录

    参照 mineru-ocr 的归档模式，每次转录后在 archive/ 下创建：
      - YYYYMMDD_HHMMSS_文件名/transcription_meta.json  — 元数据
      - YYYYMMDD_HHMMSS_文件名/文件名.md                 — 转录文件副本
      - YYYYMMDD_HHMMSS_文件名/slides/                   — 关键帧截图（如有）

    Args:
        source_file: 原始音视频文件路径
        output_md: 输出的 Markdown 文件路径
        slides: SlideFrame 列表（可选）
        diarize: 是否启用了说话人分离
        slide_threshold: 场景检测阈值

    Returns:
        dict: {archive_path, slide_count, ...}
    """
    try:
        archive_dir = build_archive_subdir(source_file)
        archive_dir.mkdir(parents=True, exist_ok=True)

        # 1. 复制 Markdown 文件
        md_name = Path(output_md).name
        archive_md = archive_dir / md_name
        shutil.copy2(output_md, archive_md)

        # 2. 复制 slides 图片（如果有）
        slide_manifest = []
        if slides:
            archive_slides_dir = archive_dir / "slides"
            archive_slides_dir.mkdir(exist_ok=True)
            for s in slides:
                src = s.image_path if hasattr(s, 'image_path') else str(s)
                if os.path.exists(src):
                    dest = archive_slides_dir / os.path.basename(src)
                    shutil.copy2(src, dest)
                    slide_manifest.append({
                        "image": os.path.basename(src),
                        "timestamp_ms": s.timestamp_ms if hasattr(s, 'timestamp_ms') else 0,
                        "time_label": s.time_label if hasattr(s, 'time_label') else "",
                    })

        # 3. 写入元数据
        meta = {
            "source_file": str(Path(source_file).absolute()),
            "output_markdown": str(Path(output_md).absolute()),
            "archive_path": str(archive_dir),
            "timestamp": datetime.now().isoformat(),
            "options": {
                "diarize": diarize,
                "extract_slides": slides is not None and len(slides) > 0,
                "slide_threshold": slide_threshold,
            },
            "slides": slide_manifest,
            "slide_count": len(slide_manifest),
        }
        meta_path = archive_dir / "transcription_meta.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"已归档到: {archive_dir}")
        return {
            "archive_path": str(archive_dir),
            "slide_count": len(slide_manifest),
        }
    except Exception as e:
        print(f"归档失败（不影响转录结果）: {e}")
        return {"archive_path": None, "slide_count": 0, "error": str(e)}

# 尝试导入 summary 模块（用于 AI 总结功能）
SUMMARY_MODULE = None
try:
    from . import summary as summary_module
    SUMMARY_MODULE = summary_module
except ImportError:
    try:
        import summary as summary_module
        SUMMARY_MODULE = summary_module
    except ImportError:
        pass

# 尝试导入 slide_extractor 模块（用于视频关键帧提取）
SLIDE_EXTRACTOR_AVAILABLE = False
try:
    from . import slide_extractor as slide_extractor_module
    SLIDE_EXTRACTOR_AVAILABLE = True
except ImportError:
    try:
        import slide_extractor as slide_extractor_module
        SLIDE_EXTRACTOR_AVAILABLE = True
    except ImportError:
        pass


# ============================================================================
# 环境检测函数
# ============================================================================

def get_summary_prompt_from_file(md_path: str) -> tuple[bool, str, str]:
    """
    从转录文件中提取文本并生成总结提示词
    
    Returns:
        tuple: (是否成功, 提示词, 提取的文本)
    """
    if not SUMMARY_MODULE:
        return False, "Summary module not available", ""
    
    try:
        path = Path(md_path)
        if not path.exists():
            return False, f"File not found: {md_path}", ""
        
        return SUMMARY_MODULE.summarize_file_for_claude(path)
    except Exception as e:
        return False, str(e), ""

# 全局服务状态
SERVICE_PID = os.getpid()
SERVICE_START_TIME = time.time()
LAST_ACTIVITY_TIME = time.time()
IDLE_TIMEOUT = 600  # 10分钟（600秒）
SERVICE_RUNNING = True
MONITOR_THREAD = None

# 默认模型配置
DEFAULT_MODEL = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
MODEL_CACHE = {}  # 模型实例缓存 {model_id: model_instance}


def check_dependencies():
    """检查依赖是否安装"""
    errors = []

    try:
        import fastapi
    except ImportError:
        errors.append("FastAPI")

    try:
        import funasr
    except ImportError:
        errors.append("FunASR")

    try:
        import torch
    except ImportError:
        errors.append("PyTorch")

    return errors


def get_model_cache_dir():
    """获取 ModelScope 模型缓存目录"""
    cache_dir = os.environ.get('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope/hub'))
    return Path(cache_dir) / "models"


def check_model_exists(model_id: str) -> bool:
    """检查模型是否已下载"""
    cache_dir = get_model_cache_dir()
    model_path = cache_dir / model_id.replace('/', os.sep)
    return model_path.exists() and any(model_path.iterdir())


def check_models():
    """检查模型是否已下载"""
    if not MODELS_CONFIG.exists():
        return ["模型配置文件不存在"]

    with open(MODELS_CONFIG, 'r', encoding='utf-8') as f:
        config = json.load(f)

    missing = []
    for model in config.get('models', []):
        if model.get('required', True):
            if not check_model_exists(model['id']):
                missing.append(model.get('name', model['id']))

    return missing


def startup_check():
    """启动前检查"""
    print("🔍 启动前检查...")

    # 检查依赖
    missing_deps = check_dependencies()
    if missing_deps:
        print(f"\n❌ 缺少依赖: {', '.join(missing_deps)}")
        print(f"\n请先运行安装脚本:")
        print(f"  python {SKILL_DIR / 'scripts' / 'setup.py'}")
        return False

    # 检查模型
    missing_models = check_models()
    if missing_models:
        print(f"\n❌ 缺少模型: {', '.join(missing_models)}")
        print(f"\n请先运行安装脚本下载模型:")
        print(f"  python {SKILL_DIR / 'scripts' / 'setup.py'}")
        return False

    print("✅ 检查通过\n")
    return True


def update_activity():
    """更新最后活动时间"""
    global LAST_ACTIVITY_TIME
    LAST_ACTIVITY_TIME = time.time()


def get_idle_time() -> int:
    """获取当前空闲时间（秒）"""
    return int(time.time() - LAST_ACTIVITY_TIME)


def should_shutdown() -> bool:
    """检查是否应该关闭服务"""
    idle_time = get_idle_time()
    return idle_time > IDLE_TIMEOUT


def shutdown_service():
    """关闭服务"""
    global SERVICE_RUNNING
    print(f"\n🕐 服务空闲超过 {IDLE_TIMEOUT // 60} 分钟，自动关闭")
    SERVICE_RUNNING = False
    os.kill(SERVICE_PID, signal.SIGTERM)


def monitor_idle():
    """监控服务空闲状态的后台线程"""
    global SERVICE_RUNNING

    while SERVICE_RUNNING:
        time.sleep(30)  # 每30秒检查一次

        # 检查是否有活动
        if get_idle_time() < 30:  # 30秒内有活动
            continue

        # 检查是否应该关闭
        if should_shutdown():
            print(f"⏰ 服务空闲检测: {get_idle_time()} 秒，自动关闭服务")
            shutdown_service()
            break


def signal_handler(signum, frame):
    """信号处理器"""
    global SERVICE_RUNNING
    print(f"\n收到信号 {signum}，正在关闭服务...")
    SERVICE_RUNNING = False
    sys.exit(0)


# 注册信号处理器
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# 检查通过后再导入
if not startup_check():
    sys.exit(1)

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from funasr import AutoModel

try:
    from funasr_onnx import Paraformer as ONNXParaformer
    from funasr_onnx import SenseVoiceSmall as ONNXSenseVoiceSmall
    from funasr_onnx import Fsmn_vad as ONNXFsmnVad
    ONNX_RUNTIME_AVAILABLE = True
except ImportError:
    ONNXParaformer = None
    ONNXSenseVoiceSmall = None
    ONNXFsmnVad = None
    ONNX_RUNTIME_AVAILABLE = False

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    librosa = None
    LIBROSA_AVAILABLE = False

try:
    from funasr.models.campplus.utils import sv_chunk, postprocess, distribute_spk
    from funasr.models.campplus.cluster_backend import ClusterBackend
    CAMPPLUS_AVAILABLE = True
except Exception:
    sv_chunk = None
    postprocess = None
    distribute_spk = None
    ClusterBackend = None
    CAMPPLUS_AVAILABLE = False

app = FastAPI(title="FunASR Transcribe API", version="1.0.0")

SUPPORTED_EXTENSIONS = {
    '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.webm',  # 视频
    '.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg', '.opus', '.wma', '.caf'  # 音频
}

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.webm'}

PARAFORMER_MODEL_ID = DEFAULT_MODEL
SENSEVOICE_MODEL_ID = os.environ.get("FUNASR_SENSEVOICE_MODEL_ID", "iic/SenseVoiceSmall")
VAD_MODEL_ID = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
SPK_MODEL_ID = "cam++"
DEFAULT_MODEL_ALIAS = os.environ.get("FUNASR_SERVER_DEFAULT_MODEL", "paraformer")
DEFAULT_ONNX_QUANTIZE = os.environ.get("FUNASR_SERVER_DEFAULT_QUANTIZE", "0").lower() in {
    "1", "true", "yes", "on"
}
DEFAULT_ONNX_THREADS = int(os.environ.get("FUNASR_SERVER_ONNX_THREADS", "4"))

MODEL_ALIASES = {
    "paraformer": {
        "runtime": "torch",
        "model_id": PARAFORMER_MODEL_ID,
        "supports_diarization": True,
        "onnx_class": None,
    },
    "paraformer-onnx": {
        "runtime": "onnx",
        "model_id": PARAFORMER_MODEL_ID,
        "supports_diarization": True,
        "onnx_class": "paraformer",
    },
    "sensevoice": {
        "runtime": "onnx",
        "model_id": SENSEVOICE_MODEL_ID,
        "supports_diarization": False,
        "onnx_class": "sensevoice",
    },
    "sensevoice-onnx": {
        "runtime": "onnx",
        "model_id": SENSEVOICE_MODEL_ID,
        "supports_diarization": False,
        "onnx_class": "sensevoice",
    },
}


def init_torch_model(with_speaker: bool = False, model_id: str = None):
    """初始化 FunASR 原生模型。"""
    global MODEL_CACHE

    use_model_id = model_id or DEFAULT_MODEL
    cache_key = f"torch::{use_model_id}::spk={with_speaker}"
    if cache_key in MODEL_CACHE:
        return MODEL_CACHE[cache_key]

    print(f"正在加载 FunASR 模型: {use_model_id}")

    if with_speaker:
        model_instance = AutoModel(
            model=use_model_id,
            vad_model=VAD_MODEL_ID,
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            spk_model=SPK_MODEL_ID,
            disable_update=True,
            disable_log=False,
        )
        print("模型加载完成（FunASR + 说话人分离）")
    else:
        model_instance = AutoModel(
            model=use_model_id,
            vad_model=VAD_MODEL_ID,
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            disable_update=True,
            disable_log=False,
        )
        print("模型加载完成（FunASR）")

    MODEL_CACHE[cache_key] = model_instance
    return model_instance


def ensure_onnx_runtime_available():
    """检查 ONNX 运行时依赖。"""
    if not ONNX_RUNTIME_AVAILABLE:
        raise RuntimeError(
            "缺少 funasr-onnx 依赖，请先运行 `python3 scripts/setup.py` 或 `pip install funasr-onnx`"
        )


def ensure_diarization_support_available():
    """检查 ONNX diarization 所需依赖。"""
    if not LIBROSA_AVAILABLE:
        raise RuntimeError("缺少 librosa 依赖，无法执行 ONNX 说话人分离流程")
    if not CAMPPLUS_AVAILABLE:
        raise RuntimeError("缺少 CAM++ 聚类依赖，无法执行 ONNX 说话人分离流程")


def get_onnx_model_class(model_alias: str):
    """根据逻辑模型名返回 ONNX 类。"""
    config = MODEL_ALIASES.get(model_alias, {})
    onnx_class = config.get("onnx_class")
    if onnx_class == "paraformer":
        return ONNXParaformer
    if onnx_class == "sensevoice":
        return ONNXSenseVoiceSmall
    raise RuntimeError(f"模型 {model_alias} 不支持 ONNX 运行时")


def init_onnx_model(model_alias: str, model_id: str = None, quantize: bool = False):
    """初始化 ONNX ASR 模型。"""
    ensure_onnx_runtime_available()

    use_model_id = model_id or MODEL_ALIASES[model_alias]["model_id"]
    cache_key = f"onnx::{model_alias}::{use_model_id}::quant={quantize}"
    if cache_key in MODEL_CACHE:
        return MODEL_CACHE[cache_key]

    model_class = get_onnx_model_class(model_alias)
    print(f"正在加载 ONNX 模型: {model_alias} ({use_model_id})")
    model_instance = model_class(
        use_model_id,
        batch_size=1,
        quantize=quantize,
        intra_op_num_threads=DEFAULT_ONNX_THREADS,
    )
    MODEL_CACHE[cache_key] = model_instance
    return model_instance


def init_onnx_vad_model(quantize: bool = False):
    """初始化 ONNX VAD 模型。"""
    ensure_onnx_runtime_available()
    cache_key = f"onnx::vad::{VAD_MODEL_ID}::quant={quantize}"
    if cache_key in MODEL_CACHE:
        return MODEL_CACHE[cache_key]

    print("正在加载 ONNX VAD 模型")
    model_instance = ONNXFsmnVad(
        VAD_MODEL_ID,
        quantize=quantize,
        intra_op_num_threads=DEFAULT_ONNX_THREADS,
    )
    MODEL_CACHE[cache_key] = model_instance
    return model_instance


def init_speaker_model():
    """初始化 CAM++ 说话人嵌入模型。"""
    cache_key = f"torch::{SPK_MODEL_ID}"
    if cache_key in MODEL_CACHE:
        return MODEL_CACHE[cache_key]

    print("正在加载 CAM++ 说话人模型")
    speaker_model = AutoModel(
        model=SPK_MODEL_ID,
        disable_update=True,
        disable_log=False,
    )
    MODEL_CACHE[cache_key] = speaker_model
    return speaker_model


def get_cluster_backend():
    """获取说话人聚类后端。"""
    cache_key = "cluster::cam++"
    if cache_key not in MODEL_CACHE:
        MODEL_CACHE[cache_key] = ClusterBackend()
    return MODEL_CACHE[cache_key]


def normalize_vad_segments(vad_result) -> list[list[int]]:
    """将 VAD 输出归一化为 [[start_ms, end_ms], ...]。"""
    if not isinstance(vad_result, list):
        return []

    if len(vad_result) == 2 and all(isinstance(x, (int, float)) for x in vad_result):
        return [[int(vad_result[0]), int(vad_result[1])]]

    normalized = []
    for item in vad_result:
        normalized.extend(normalize_vad_segments(item))
    return normalized


def offset_timestamps(timestamps: list, offset_ms: int) -> list:
    """为时间戳整体加偏移量。"""
    shifted = []
    for ts in timestamps or []:
        if isinstance(ts, list) and len(ts) >= 2:
            shifted.append([int(ts[0]) + offset_ms, int(ts[1]) + offset_ms])
    return shifted


def build_onnx_result(output, offset_ms: int = 0) -> dict:
    """将 ONNX 推理结果转换为与现有 server 兼容的结构。"""
    if isinstance(output, str):
        return {"text": output}

    if isinstance(output, dict):
        text = output.get("text") or output.get("preds") or ""
        result = {"text": text}
        timestamps = output.get("timestamp")
        if timestamps:
            result["timestamp"] = offset_timestamps(timestamps, offset_ms)
        return result

    return {"text": str(output)}


def transcribe_with_onnx_model(file_path: str, model_alias: str, model_id: str = None,
                               quantize: bool = False) -> dict:
    """使用 ONNX 模型执行非 diarization 转录。"""
    model_instance = init_onnx_model(model_alias, model_id=model_id, quantize=quantize)
    result = model_instance(file_path)
    if isinstance(result, list) and result:
        return build_onnx_result(result[0])
    return build_onnx_result(result)


def transcribe_paraformer_onnx_with_diarization(file_path: str, model_id: str = None,
                                                quantize: bool = False) -> dict:
    """ONNX Paraformer + ONNX VAD + CAM++ 聚类组合路径。"""
    ensure_onnx_runtime_available()
    ensure_diarization_support_available()

    vad_model = init_onnx_vad_model(quantize=quantize)
    asr_model = init_onnx_model("paraformer-onnx", model_id=model_id, quantize=quantize)
    speaker_model = init_speaker_model()
    cluster_backend = get_cluster_backend()

    waveform, sample_rate = librosa.load(file_path, sr=16000)
    if sample_rate != 16000:
        raise RuntimeError(f"ONNX diarization 需要 16k 音频，实际采样率为 {sample_rate}")

    vad_segments = normalize_vad_segments(vad_model(file_path))
    if not vad_segments:
        raw_result = asr_model(file_path)
        if isinstance(raw_result, list) and raw_result:
            raw_result = raw_result[0]
        result = build_onnx_result(raw_result)
        result["sentence_info"] = []
        return result

    sentence_info = []
    combined_texts = []
    combined_timestamps = []
    vad_segment_payloads = []

    for start_ms, end_ms in vad_segments:
        start_idx = max(0, int(start_ms / 1000 * 16000))
        end_idx = min(len(waveform), int(end_ms / 1000 * 16000))
        segment_audio = waveform[start_idx:end_idx]
        if segment_audio.size == 0:
            continue

        vad_segment_payloads.append([start_ms / 1000.0, end_ms / 1000.0, segment_audio])
        segment_result_raw = asr_model(segment_audio)
        if isinstance(segment_result_raw, list) and segment_result_raw:
            segment_result_raw = segment_result_raw[0]
        segment_result = build_onnx_result(segment_result_raw, offset_ms=start_ms)
        text = (segment_result.get("text") or "").strip()
        if not text:
            continue

        combined_texts.append(text)
        combined_timestamps.extend(segment_result.get("timestamp", []))
        sentence_info.append(
            {
                "start": int(start_ms),
                "end": int(end_ms),
                "sentence": text,
                "timestamp": segment_result.get("timestamp", []),
            }
        )

    if not sentence_info:
        return {"text": "", "timestamp": [], "sentence_info": []}

    speaker_chunks = sv_chunk(vad_segment_payloads)
    if speaker_chunks:
        speaker_results, _ = speaker_model.model.inference(
            [chunk[2] for chunk in speaker_chunks],
            key=[f"spk_{idx}" for idx in range(len(speaker_chunks))],
            **speaker_model.kwargs,
        )
        spk_embedding = speaker_results[0]["spk_embedding"]
        labels = cluster_backend(spk_embedding.cpu().numpy(), oracle_num=None)
        speaker_regions = postprocess(
            speaker_chunks,
            None,
            labels,
            spk_embedding.cpu().numpy(),
        )
        distribute_spk(sentence_info, speaker_regions)

    return {
        "text": " ".join(combined_texts),
        "timestamp": combined_timestamps,
        "sentence_info": sentence_info,
    }


def resolve_requested_model(model_name: Optional[str]) -> str:
    """解析逻辑模型名。"""
    if not model_name:
        return DEFAULT_MODEL_ALIAS if DEFAULT_MODEL_ALIAS in MODEL_ALIASES else "paraformer"
    if model_name not in MODEL_ALIASES:
        supported = ", ".join(MODEL_ALIASES.keys())
        raise RuntimeError(f"不支持的模型: {model_name}，支持的模型: {supported}")
    return model_name


def resolve_transcription_options(model_name: Optional[str], model_id: Optional[str],
                                  diarize: bool, fast: bool,
                                  quantize: Optional[bool]) -> dict:
    """解析请求参数，得到最终运行时配置。"""
    warnings = []
    resolved_model = resolve_requested_model(model_name)
    resolved_diarize = diarize
    resolved_quantize = DEFAULT_ONNX_QUANTIZE if quantize is None else quantize

    if fast:
        if model_name and model_name not in {"sensevoice", "sensevoice-onnx"}:
            warnings.append("已保留显式指定模型；fast 标记未自动覆盖模型选择。")
        else:
            resolved_model = "sensevoice"
            if resolved_diarize:
                warnings.append("fast 模式已自动关闭说话人分离，切换到 SenseVoice 单人快速路径。")
            resolved_diarize = False

    if resolved_model in {"sensevoice", "sensevoice-onnx"} and resolved_diarize:
        raise RuntimeError("SenseVoice-Small 不支持说话人分离，请改用 paraformer 或 paraformer-onnx。")

    model_config = MODEL_ALIASES[resolved_model]
    runtime = model_config["runtime"]
    resolved_model_id = model_id or model_config["model_id"]

    if runtime == "torch":
        resolved_quantize = False

    return {
        "model": resolved_model,
        "model_id": resolved_model_id,
        "runtime": runtime,
        "diarize": resolved_diarize,
        "quantize": resolved_quantize,
        "warnings": warnings,
    }


def run_transcription(file_path: str, resolved: dict) -> dict:
    """根据解析后的选项执行转录。"""
    if resolved["runtime"] == "torch":
        model_instance = init_torch_model(
            with_speaker=resolved["diarize"],
            model_id=resolved["model_id"],
        )
        result = model_instance.generate(input=file_path, cache={})
        if isinstance(result, list) and result:
            return result[0]
        return result

    if resolved["model"] == "paraformer-onnx" and resolved["diarize"]:
        return transcribe_paraformer_onnx_with_diarization(
            file_path,
            model_id=resolved["model_id"],
            quantize=resolved["quantize"],
        )

    return transcribe_with_onnx_model(
        file_path,
        model_alias=resolved["model"],
        model_id=resolved["model_id"],
        quantize=resolved["quantize"],
    )


def format_timestamp(ms: int) -> str:
    """将毫秒转换为时间戳格式

    规则：
    - 如果有小时，使用 HH:MM:SS 格式
    - 否则使用 MM:SS 格式（参考文件中的格式）
    """
    seconds = ms // 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        # 有小时时显示 HH:MM:SS
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        # 否则显示 MM:SS
        return f"{minutes:02d}:{secs:02d}"


def split_text_by_sentences(text: str) -> list:
    """按句子分割文本（保留分隔符）"""
    import re
    # 匹配句子结束符（。！？）以及可选的引号和空格
    # 格式：非结束符内容 + 结束符 + 可选引号 + 可选空格
    pattern = r'[^。！？\n]+[。！？][」』""\"]?\s*'
    sentences = re.findall(pattern, text)
    # 过滤空字符串并清理空白，同时处理没有结束符的最后一段
    result = [s.strip() for s in sentences if s.strip()]
    # 检查是否有剩余文本（没有结束符的段落）
    matched_len = sum(len(s) for s in sentences)
    if matched_len < len(text):
        remaining = text[matched_len:].strip()
        if remaining:
            result.append(remaining)
    return result


def result_to_markdown(result: dict, filename: str, diarize: bool = False, slides: list = None) -> str:
    """将转录结果转换为 Markdown 格式

    Args:
        result: FunASR 转录结果
        filename: 原始文件名
        diarize: 是否启用说话人分离
        slides: SlideFrame 列表（可选），用于在转录文本中插入关键帧截图
    """
    md_lines = []

    # 构建 slide 迭代器（按 timestamp_ms 排序）
    # slide_queue 用于按时间顺序在转录段落前插入截图
    slide_queue = list(slides) if slides else []
    slide_idx = 0  # 当前未插入的 slide 索引

    def _flush_slides_before(timestamp_ms: int):
        """输出所有 timestamp_ms <= 给定时间的未插入 slides"""
        nonlocal slide_idx, md_lines
        while slide_idx < len(slide_queue):
            s = slide_queue[slide_idx]
            if s.timestamp_ms <= timestamp_ms:
                # 使用相对于 Markdown 文件的路径
                rel = s.relative_path or os.path.basename(s.image_path)
                md_lines.append(f"\n![]({rel})\n")
                slide_idx += 1
            else:
                break

    # 标题（不带转录时间）
    md_lines.append(f"# 转录：{filename}\n")
    md_lines.append("## 转录内容\n")

    # 处理句子信息（说话人分离模式）
    if 'sentence_info' in result and result['sentence_info']:
        segments = result['sentence_info']

        # --- 合并连续相同说话人的段落 ---
        merged_segments = []
        current = None
        # 默认最大合并时长 30 秒
        max_merge_ms = 30000

        for seg in segments:
            start_ms = seg.get('start', 0)
            text = seg.get('sentence', seg.get('text', ''))
            spk = seg.get('spk') if diarize else None

            if current is None:
                current = {
                    'start': start_ms,
                    'spk': spk,
                    'texts': [text],
                }
            else:
                # 检查是否可以合并：相同说话人且时长不超过限制
                if spk == current.get('spk'):
                    if start_ms - current['start'] <= max_merge_ms:
                        # 合并到当前段落
                        current['texts'].append(text)
                    else:
                        # 超过时长限制，输出当前段落并开始新段落
                        merged_segments.append(current)
                        current = {
                            'start': start_ms,
                            'spk': spk,
                            'texts': [text],
                        }
                else:
                    # 说话人切换，输出当前段落并开始新段落
                    merged_segments.append(current)
                    current = {
                        'start': start_ms,
                        'spk': spk,
                        'texts': [text],
                    }

        # 输出最后一个段落
        if current is not None:
            merged_segments.append(current)

        # 规范化说话人 ID（从 1 开始连续编号）
        spk_map = {}
        next_label = 1
        for seg in merged_segments:
            spk = seg.get('spk')
            if spk is not None and spk not in spk_map:
                spk_map[spk] = next_label
                next_label += 1

        # 输出合并后的段落
        for seg in merged_segments:
            start_ts = format_timestamp(int(seg['start']))
            # 插入该时间段之前的截图
            _flush_slides_before(int(seg['start']))
            combined_text = ' '.join(seg['texts'])
            spk = seg.get('spk')

            if spk is not None:
                # 有说话人信息
                if isinstance(spk, str) and spk.startswith('speaker_'):
                    speaker_num = int(spk.split('_')[1]) + 1
                    speaker = f"发言人{speaker_num}"
                else:
                    # 使用映射后的编号（支持整数类型的 spk）
                    speaker = f"发言人{spk_map.get(spk, 1)}"
                md_lines.append(f"{speaker} {start_ts}\n")
            else:
                # 无说话人分离时，只显示时间戳
                md_lines.append(f"{start_ts}\n")

            md_lines.append(f"{combined_text}\n\n")

    # 处理 timestamp 字段（标准模式，无说话人分离）
    elif 'timestamp' in result and result['timestamp'] and 'text' in result:
        text = result['text']
        timestamps = result['timestamp']

        # 按句子分割文本
        sentences = split_text_by_sentences(text)

        if not sentences:
            # 无法分割时，输出整段
            md_lines.append(f"发言人1 00:00\n")
            md_lines.append(f"{text}\n\n")
        else:
            # 计算每个句子的字符范围
            char_idx = 0
            sentence_ranges = []
            for sent in sentences:
                # 计算句子在原文中的位置（考虑可能的空格差异）
                sent_clean = sent.replace(' ', '')
                text_from_idx = text.replace(' ', '')[char_idx:char_idx + len(sent_clean)]

                start_char = char_idx
                end_char = char_idx + len(sent_clean)
                sentence_ranges.append((sent, start_char, end_char))
                char_idx = end_char

            # 为每个句子分配时间戳
            # timestamp 列表中每个元素对应一个音频片段 [start_ms, end_ms]
            # 我们需要估算每个句子对应多少个 timestamp
            total_chars = len(text.replace(' ', ''))
            total_timestamps = len(timestamps)

            for sent, start_char, end_char in sentence_ranges:
                # 根据字符位置比例计算时间戳索引
                start_ts_idx = int(start_char / total_chars * total_timestamps)
                end_ts_idx = min(int(end_char / total_chars * total_timestamps), total_timestamps - 1)

                # 获取该句子的起始时间
                if start_ts_idx < len(timestamps):
                    start_ms = timestamps[start_ts_idx][0]
                else:
                    start_ms = timestamps[-1][0] if timestamps else 0

                start_ts = format_timestamp(int(start_ms))
                # 插入该时间段之前的截图
                _flush_slides_before(int(start_ms))
                md_lines.append(f"发言人1 {start_ts}\n")
                md_lines.append(f"{sent}\n\n")

    else:
        # 兜底：简单文本输出 - 添加默认说话人标签和时间戳
        text = result.get('text', '')
        # 即使不启用说话人分离，也显示"发言人1"以保持格式一致
        md_lines.append(f"发言人1 00:00\n")
        md_lines.append(f"{text}\n\n")

    # 输出剩余未插入的 slides（在最后一段文字之后）
    while slide_idx < len(slide_queue):
        s = slide_queue[slide_idx]
        rel = s.relative_path or os.path.basename(s.image_path)
        md_lines.append(f"\n![]({rel})\n")
        slide_idx += 1

    return '\n'.join(md_lines)


# 请求模型
class TranscribeRequest(BaseModel):
    file_path: str
    output_path: Optional[str] = None
    diarize: bool = True  # 默认启用说话人分离
    model: Optional[str] = None  # 逻辑模型名（paraformer / paraformer-onnx / sensevoice）
    model_id: Optional[str] = None  # 指定使用的模型 ID
    fast: bool = False  # 单人快速模式
    quantize: Optional[bool] = None  # ONNX INT8 量化
    extract_slides: bool = False  # 提取视频关键帧截图
    slide_threshold: float = 20.0  # 场景检测阈值


class BatchTranscribeRequest(BaseModel):
    directory: str
    output_dir: Optional[str] = None
    diarize: bool = True  # 默认启用说话人分离
    model: Optional[str] = None
    model_id: Optional[str] = None  # 指定使用的模型 ID
    fast: bool = False
    quantize: Optional[bool] = None


class TranscribeResponse(BaseModel):
    success: bool
    output_path: Optional[str] = None
    text: Optional[str] = None
    sentence_count: Optional[int] = None
    slide_count: Optional[int] = None  # 提取的关键帧数量
    archive_path: Optional[str] = None  # 归档目录路径
    summary_prompt: Optional[str] = None  # 自动附带的 AI 总结提示词
    text_preview: Optional[str] = None   # 转录文本预览（前500字）
    resolved_model: Optional[str] = None  # 最终使用的逻辑模型
    resolved_runtime: Optional[str] = None  # 最终运行时（torch / onnx）
    warnings: Optional[list[str]] = None  # 运行时提示
    error: Optional[str] = None


class BatchTranscribeResponse(BaseModel):
    success: bool
    total: Optional[int] = None
    results: Optional[list] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    uptime: int
    idle_time: int


# Summary 请求和响应模型
class SummaryRequest(BaseModel):
    md_path: str  # 转录生成的 Markdown 文件路径
    output_path: Optional[str] = None  # 输出路径（可选，默认原地更新）
    summary_content: Optional[str] = None  # 总结内容（用于 inject_summary 时传递）


class SummaryResponse(BaseModel):
    success: bool
    output_path: Optional[str] = None
    summary_prompt: Optional[str] = None  # 总结提示词（供 Agent 使用）
    text_preview: Optional[str] = None    # 转录文本预览（前500字）
    error: Optional[str] = None


class VerifySummaryRequest(BaseModel):
    md_path: str


@app.middleware("http")
async def update_activity_middleware(request: Request, call_next):
    """更新活动时间的中间件"""
    update_activity()
    response = await call_next(request)
    return response


@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    return HealthResponse(
        status="ok",
        service="FunASR Transcribe",
        uptime=int(time.time() - SERVICE_START_TIME),
        idle_time=get_idle_time()
    )


@app.post("/summary", response_model=SummaryResponse)
async def generate_summary(request: SummaryRequest):
    """
    生成 AI 总结
    
    此端点用于在 Agent 环境（OpenClaw / Claude Code）中自动生成总结。
    它会：
    1. 读取转录生成的 Markdown 文件
    2. 提取纯文本内容
    3. 生成总结提示词（供 Agent 调用 LLM 生成总结）
    4. 将总结写入文件（如果提供了总结内容）
    
    请求参数:
        - md_path: 转录生成的 Markdown 文件路径（必需）
        - output_path: 输出路径（可选，默认原地更新）
    
    返回:
        - success: 是否成功
        - output_path: 输出文件路径
        - summary_prompt: 总结提示词（供 Agent 使用）
        - text_preview: 转录文本预览
        - error: 错误信息（如果有）
    """
    try:
        update_activity()
        
        md_path = Path(request.md_path)
        if not md_path.exists():
            raise HTTPException(status_code=400, detail=f"文件不存在: {request.md_path}")
        
        # 提取文本和提示词
        success, prompt, text = get_summary_prompt_from_file(request.md_path)
        
        if not success:
            return SummaryResponse(
                success=False,
                error=prompt,
                md_path=request.md_path
            )
        
        # 读取文件获取文本预览
        content = md_path.read_text(encoding="utf-8")
        text_preview = content[:500] if len(content) > 500 else content
        
        # 输出路径
        output_path = request.output_path or request.md_path
        
        return SummaryResponse(
            success=True,
            output_path=output_path,
            summary_prompt=prompt,
            text_preview=text_preview
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        return SummaryResponse(success=False, error=str(e))


@app.post("/inject_summary")
async def inject_summary(request: SummaryRequest):
    """
    将 AI 总结注入到 Markdown 文件
    
    此端点用于在 Agent 环境（OpenClaw / Claude Code）中，
    在 LLM 生成总结后，将总结内容写入转录文件。
    
    请求参数:
        - md_path: 转录生成的 Markdown 文件路径（必需）
        - summary_content: 总结内容（必需）- 将写入文件
        - output_path: 输出路径（可选，默认原地更新）
    
    返回:
        - success: 是否成功
        - output_path: 输出文件路径
        - error: 错误信息（如果有）
    """
    try:
        update_activity()
        
        md_path = Path(request.md_path)
        if not md_path.exists():
            raise HTTPException(status_code=400, detail=f"文件不存在: {request.md_path}")
        
        # 获取总结内容
        summary_content = request.summary_content
        
        if not summary_content:
            raise HTTPException(status_code=400, detail="summary_content 不能为空")
        
        if not SUMMARY_MODULE:
            return {"success": False, "error": "Summary module not available"}
        
        # 写入总结到文件
        output_path = Path(request.output_path) if request.output_path else md_path
        SUMMARY_MODULE.inject_summary_to_file(md_path, summary_content)
        
        return {
            "success": True,
            "output_path": str(output_path)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/verify_summary")
async def verify_summary(request: VerifySummaryRequest):
    """
    验证 Markdown 文件中是否已注入 AI 摘要

    请求参数:
        - md_path: Markdown 文件路径（必需）

    返回:
        - has_summary: 是否存在摘要
        - summary_length: 摘要字符数
        - has_all_sections: 是否包含所有必需章节
        - missing_sections: 缺失的章节名称
    """
    try:
        update_activity()

        md_path = Path(request.md_path)
        if not md_path.exists():
            raise HTTPException(status_code=400, detail=f"文件不存在: {request.md_path}")

        if not SUMMARY_MODULE:
            return {"success": False, "error": "Summary module not available"}

        result = SUMMARY_MODULE.verify_summary_in_file(md_path)
        result["md_path"] = str(md_path)
        result["success"] = True
        return result

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """
    转录音频/视频文件

    请求参数:
        - file_path: 文件路径（必需）
        - output_path: 输出 Markdown 文件路径（可选）
        - diarize: 是否启用说话人分离（可选，默认 true）
        - model: 逻辑模型名（可选）
        - model_id: 指定使用的底层模型 ID（可选）
        - fast: 单人快速模式（可选）
        - quantize: ONNX INT8 量化（可选）

    返回:
        - success: 是否成功
        - output_path: 输出文件路径
        - text: 转录的纯文本
        - sentence_count: 句子数量
        - error: 错误信息（如果有）
    """
    try:
        # 更新活动时间
        update_activity()

        # 检查文件是否存在
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"文件不存在: {request.file_path}"
            )

        # 检查文件格式
        ext = Path(request.file_path).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {ext}，支持的格式: {', '.join(SUPPORTED_EXTENSIONS)}"
            )

        resolved = resolve_transcription_options(
            request.model,
            request.model_id,
            request.diarize,
            request.fast,
            request.quantize,
        )

        # 视频文件自动启用关键帧提取
        if not request.extract_slides and ext in VIDEO_EXTENSIONS:
            request.extract_slides = True
            print(f"[auto] 检测到视频文件，自动启用关键帧提取")

        # 默认输出路径
        output_path = request.output_path
        if not output_path:
            output_path = str(Path(request.file_path).with_suffix('.md'))

        print(f"正在转录: {request.file_path}")
        print(
            f"使用模型: {resolved['model']} "
            f"(runtime={resolved['runtime']}, diarize={resolved['diarize']}, quantize={resolved['quantize']})"
        )

        # 执行转录
        result = run_transcription(request.file_path, resolved)

        # 转换为 Markdown
        filename = Path(request.file_path).name

        # 视频关键帧提取（仅视频文件 + extract_slides=True）
        slides = None
        slide_count = 0
        if request.extract_slides and SLIDE_EXTRACTOR_AVAILABLE:
            if slide_extractor_module.SlideExtractor.is_video_file(request.file_path):
                slides_dir = str(Path(output_path).parent / "slides")
                extractor = slide_extractor_module.SlideExtractor(
                    threshold=request.slide_threshold,
                )
                slides = extractor.extract(request.file_path, slides_dir)
                # 设置相对路径
                for s in slides:
                    s.relative_path = f"slides/{os.path.basename(s.image_path)}"
                slide_count = len(slides)
                print(f"关键帧提取完成: {slide_count} 张")
            else:
                print("[slide_extractor] 非视频文件，跳过关键帧提取")
        elif request.extract_slides and not SLIDE_EXTRACTOR_AVAILABLE:
            print("[slide_extractor] 模块未安装，跳过关键帧提取（pip install scenedetect[opencv] imagehash）")

        markdown_content = result_to_markdown(result, filename, resolved["diarize"], slides=slides)

        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        print(f"转录完成，已保存到: {output_path}")

        # 归档
        archive_info = archive_transcription(
            source_file=request.file_path,
            output_md=output_path,
            slides=slides,
            diarize=resolved["diarize"],
            slide_threshold=request.slide_threshold,
        )

        # 自动生成总结提示词（供 Agent 直接使用，免去额外调用 /summary）
        summary_prompt = None
        text_preview = None
        if SUMMARY_MODULE:
            try:
                ok, prompt, extracted_text = SUMMARY_MODULE.summarize_file_for_claude(Path(output_path))
                if ok:
                    summary_prompt = prompt
                    text_preview = extracted_text[:500] if extracted_text else None
                else:
                    print(f"总结提示词生成跳过: {prompt}")
            except Exception as e:
                print(f"生成总结提示词失败（不影响转录结果）: {e}")

        return TranscribeResponse(
            success=True,
            output_path=output_path,
            text=result.get('text', ''),
            sentence_count=len(result.get('sentence_info', [])) if 'sentence_info' in result else 0,
            slide_count=slide_count,
            archive_path=archive_info.get("archive_path"),
            summary_prompt=summary_prompt,
            text_preview=text_preview,
            resolved_model=resolved["model"],
            resolved_runtime=resolved["runtime"],
            warnings=resolved["warnings"],
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch_transcribe", response_model=BatchTranscribeResponse)
async def batch_transcribe(request: BatchTranscribeRequest):
    """
    批量转录目录中的文件

    请求参数:
        - directory: 目录路径（必需）
        - output_dir: 输出目录（可选，默认同目录）
        - diarize: 是否启用说话人分离（可选，默认 true）
        - model_id: 指定使用的模型 ID（可选，默认使用 Paraformer）
    """
    try:
        # 更新活动时间
        update_activity()

        # 检查目录是否存在
        if not os.path.isdir(request.directory):
            raise HTTPException(
                status_code=400,
                detail=f"目录不存在: {request.directory}"
            )

        output_dir = request.output_dir or request.directory
        resolved = resolve_transcription_options(
            request.model,
            request.model_id,
            request.diarize,
            request.fast,
            request.quantize,
        )

        # 查找所有支持的文件
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(Path(request.directory).glob(f'*{ext}'))
            files.extend(Path(request.directory).glob(f'*{ext.upper()}'))

        if not files:
            raise HTTPException(
                status_code=400,
                detail="目录中没有找到支持的媒体文件"
            )

        results = []
        for file_path in files:
            try:
                print(f"正在转录: {file_path}")
                result = run_transcription(str(file_path), resolved)

                output_path = Path(output_dir) / f"{file_path.stem}.md"
                markdown_content = result_to_markdown(result, file_path.name, resolved["diarize"])

                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)

                results.append({
                    "file": str(file_path),
                    "output": str(output_path),
                    "success": True,
                    "resolved_model": resolved["model"],
                    "resolved_runtime": resolved["runtime"],
                })
            except Exception as e:
                results.append({
                    "file": str(file_path),
                    "success": False,
                    "error": str(e)
                })

        return BatchTranscribeResponse(
            success=True,
            total=len(files),
            results=results
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def start_idle_monitor():
    """启动空闲监控线程"""
    global MONITOR_THREAD
    MONITOR_THREAD = threading.Thread(target=monitor_idle, daemon=True)
    MONITOR_THREAD.start()
    print(f"🔍 空闲监控已启动（{IDLE_TIMEOUT // 60}分钟后自动关闭）")


def preload_default_model():
    """按环境变量预加载默认模型。"""
    try:
        resolved = resolve_transcription_options(
            DEFAULT_MODEL_ALIAS,
            None,
            diarize=False,
            fast=False,
            quantize=DEFAULT_ONNX_QUANTIZE,
        )
        if resolved["runtime"] == "torch":
            init_torch_model(with_speaker=False, model_id=resolved["model_id"])
        elif resolved["model"] == "paraformer-onnx":
            init_onnx_model("paraformer-onnx", model_id=resolved["model_id"], quantize=resolved["quantize"])
        elif resolved["model"] in {"sensevoice", "sensevoice-onnx"}:
            init_onnx_model(resolved["model"], model_id=resolved["model_id"], quantize=resolved["quantize"])
        print(
            f"✅ 默认模型已预加载: {resolved['model']} "
            f"(runtime={resolved['runtime']}, quantize={resolved['quantize']})"
        )
    except Exception as exc:
        print(f"⚠️  默认模型预加载失败，将按需加载: {exc}")


def main():
    parser = argparse.ArgumentParser(description='FunASR 转录服务 (FastAPI)')
    parser.add_argument('--port', type=int, default=8765, help='服务端口（默认 8765）')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='监听地址（默认 127.0.0.1）')
    parser.add_argument('--idle-timeout', type=int, default=600, help='空闲超时时间，单位秒（默认 600秒=10分钟）')
    parser.add_argument('--preload', action='store_true', help='预加载模型')
    args = parser.parse_args()

    # 设置空闲超时
    global IDLE_TIMEOUT
    IDLE_TIMEOUT = args.idle_timeout

    if args.preload:
        preload_default_model()

    # 启动空闲监控
    start_idle_monitor()

    print(f"🎙️ FunASR 转录服务启动中...")
    print(f"📍 地址: http://{args.host}:{args.port}")
    print(f"📚 API 文档: http://{args.host}:{args.port}/docs")
    print(f"🔍 空闲监控: {IDLE_TIMEOUT // 60}分钟自动关闭")
    print(
        f"⚙️ 默认模型: {DEFAULT_MODEL_ALIAS} "
        f"(onnx_quantize={DEFAULT_ONNX_QUANTIZE})"
    )
    print(f"📋 API 端点:")
    print(f"   POST /transcribe      - 转录单个文件")
    print(f"   POST /batch_transcribe - 批量转录")
    print(f"   POST /summary         - 生成 AI 总结提示词（供 Agent 使用）")
    print(f"   POST /inject_summary  - 将 AI 总结注入 Markdown 文件")
    print(f"   POST /verify_summary  - 验证摘要是否已注入")
    print(f"   GET  /health          - 健康检查\n")

    # 导入 uvicorn（延迟导入以加快启动速度）
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == '__main__':
    main()
