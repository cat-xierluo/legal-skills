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
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import argparse
import threading
from pathlib import Path

# 获取脚本所在目录和 skill 根目录
SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
MODELS_CONFIG = SKILL_DIR / "assets" / "models.json"

# 全局服务状态
SERVICE_PID = os.getpid()
SERVICE_START_TIME = time.time()
LAST_ACTIVITY_TIME = time.time()
IDLE_TIMEOUT = 600  # 10分钟（600秒）
SERVICE_RUNNING = True
MONITOR_THREAD = None


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
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from funasr import AutoModel

app = FastAPI(title="FunASR Transcribe API", version="1.0.0")

# 全局模型实例
model = None
model_with_spk = None

SUPPORTED_EXTENSIONS = {
    '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.webm',  # 视频
    '.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg', '.opus', '.wma', '.caf'  # 音频
}


def init_model(with_speaker: bool = False):
    """初始化 ASR 模型"""
    global model, model_with_spk

    if with_speaker and model_with_spk is None:
        print("正在加载 ASR 模型（含说话人分离）...")
        # 使用标准 ASR 模型 + CAM++ 说话人分离模型
        model_with_spk = AutoModel(
            model="iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            spk_model="damo/speech_campplus_speaker-diarization_common",
            spk_model_revision="master",
            disable_update=True,
            disable_log=False,
        )
        print("模型加载完成（含说话人分离）")
        return model_with_spk

    if model is None:
        print("正在加载 ASR 模型...")
        model = AutoModel(
            model="iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            disable_update=True,
            disable_log=False,
        )
        print("模型加载完成")

    return model_with_spk if with_speaker else model


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


def result_to_markdown(result: dict, filename: str, diarize: bool = False) -> str:
    """将转录结果转换为 Markdown 格式"""
    md_lines = []

    # 标题（不带转录时间）
    md_lines.append(f"# 转录：{filename}\n")
    md_lines.append("## 转录内容\n")

    # 处理句子信息
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
            spk = seg.get('speaker') if diarize else None

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
            combined_text = ' '.join(seg['texts'])
            spk = seg.get('spk')

            if spk is not None:
                # 有说话人信息
                if spk.startswith('speaker_'):
                    speaker_num = int(spk.split('_')[1]) + 1
                    speaker = f"发言人{speaker_num}"
                else:
                    # 使用映射后的编号
                    speaker = f"发言人{spk_map.get(spk, 1)}"
                md_lines.append(f"{speaker} {start_ts}\n")
            else:
                # 无说话人分离时，只显示时间戳
                md_lines.append(f"{start_ts}\n")

            md_lines.append(f"{combined_text}\n\n")
    else:
        # 简单文本输出 - 添加默认说话人标签和时间戳
        text = result.get('text', '')
        # 即使不启用说话人分离，也显示"发言人1"以保持格式一致
        md_lines.append(f"发言人1 00:00\n")
        md_lines.append(f"{text}\n\n")

    return '\n'.join(md_lines)


# 请求模型
class TranscribeRequest(BaseModel):
    file_path: str
    output_path: Optional[str] = None
    diarize: bool = False


class BatchTranscribeRequest(BaseModel):
    directory: str
    output_dir: Optional[str] = None
    diarize: bool = False


class TranscribeResponse(BaseModel):
    success: bool
    output_path: Optional[str] = None
    text: Optional[str] = None
    sentence_count: Optional[int] = None
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


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """
    转录音频/视频文件

    请求参数:
        - file_path: 文件路径（必需）
        - output_path: 输出 Markdown 文件路径（可选）
        - diarize: 是否启用说话人分离（可选，默认 false）

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

        # 默认输出路径
        output_path = request.output_path
        if not output_path:
            output_path = str(Path(request.file_path).with_suffix('.md'))

        # 获取模型
        current_model = init_model(with_speaker=request.diarize)

        print(f"正在转录: {request.file_path}")

        # 执行转录
        result = current_model.generate(input=request.file_path, cache={})

        # 处理结果
        if isinstance(result, list) and len(result) > 0:
            result = result[0]

        # 转换为 Markdown
        filename = Path(request.file_path).name
        markdown_content = result_to_markdown(result, filename, request.diarize)

        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        print(f"转录完成，已保存到: {output_path}")

        return TranscribeResponse(
            success=True,
            output_path=output_path,
            text=result.get('text', ''),
            sentence_count=len(result.get('sentence_info', [])) if 'sentence_info' in result else 0
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
        - diarize: 是否启用说话人分离（可选，默认 false）
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
        current_model = init_model(with_speaker=request.diarize)

        for file_path in files:
            try:
                print(f"正在转录: {file_path}")
                result = current_model.generate(input=str(file_path), cache={})

                if isinstance(result, list) and len(result) > 0:
                    result = result[0]

                output_path = Path(output_dir) / f"{file_path.stem}.md"
                markdown_content = result_to_markdown(result, file_path.name, request.diarize)

                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)

                results.append({
                    "file": str(file_path),
                    "output": str(output_path),
                    "success": True
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
        init_model()

    # 启动空闲监控
    start_idle_monitor()

    print(f"🎙️ FunASR 转录服务启动中...")
    print(f"📍 地址: http://{args.host}:{args.port}")
    print(f"📚 API 文档: http://{args.host}:{args.port}/docs")
    print(f"🔍 空闲监控: {IDLE_TIMEOUT // 60}分钟自动关闭")
    print(f"📋 API 端点:")
    print(f"   POST /transcribe      - 转录单个文件")
    print(f"   POST /batch_transcribe - 批量转录")
    print(f"   GET  /health          - 健康检查\n")

    # 导入 uvicorn（延迟导入以加快启动速度）
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == '__main__':
    main()
