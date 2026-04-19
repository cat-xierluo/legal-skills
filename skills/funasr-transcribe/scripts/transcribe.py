#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
FunASR 转录客户端 - 调用本地 ASR 服务进行转录
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path

# 导入总结功能
try:
    from .summary import summarize_file_for_claude, generate_summary_via_api
except ImportError:
    # 如果是直接运行
    try:
        from summary import summarize_file_for_claude, generate_summary_via_api
    except ImportError:
        summarize_file_for_claude = None
        generate_summary_via_api = None


DEFAULT_SERVER = "http://127.0.0.1:8765"

AVAILABLE_MODELS = {
    "paraformer": "FunASR 原生 Paraformer（默认，支持 diarization）",
    "paraformer-onnx": "ONNX Paraformer（更快，支持 diarization）",
    "sensevoice": "SenseVoice-Small ONNX（实验性单人路径，不支持 diarization）",
    "sensevoice-onnx": "SenseVoice-Small ONNX（sensevoice 别名）",
}


def check_server(server_url: str) -> bool:
    """检查服务是否运行"""
    try:
        req = urllib.request.Request(f"{server_url}/health")
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except:
        return False


def transcribe_file(file_path: str, server_url: str = DEFAULT_SERVER,
                    output_path: str = None, diarize: bool = False,
                    model: str = None,
                    model_id: str = None,
                    fast: bool = False,
                    extract_slides: bool = False, slide_threshold: float = 27.0) -> dict:
    """
    转录单个文件

    Args:
        file_path: 音频/视频文件路径
        server_url: 转录服务地址
        output_path: 输出 Markdown 文件路径
        diarize: 是否启用说话人分离
        model_id: 指定使用的模型 ID（可选）
        extract_slides: 是否提取视频关键帧截图
        slide_threshold: 场景检测阈值

    Returns:
        转录结果字典
    """
    # 转换为绝对路径
    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}"}

    payload = {
        "file_path": file_path,
        "diarize": diarize,
        "fast": fast,
        "extract_slides": extract_slides,
        "slide_threshold": slide_threshold,
    }
    if output_path:
        payload["output_path"] = os.path.abspath(output_path)
    if model:
        payload["model"] = model
    if model_id:
        payload["model_id"] = model_id

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{server_url}/transcribe",
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            return json.loads(error_body)
        except:
            return {"success": False, "error": error_body}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"无法连接到服务: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def batch_transcribe(directory: str, server_url: str = DEFAULT_SERVER,
                     output_dir: str = None, diarize: bool = False,
                     model: str = None, model_id: str = None,
                     fast: bool = False) -> dict:
    """
    批量转录目录中的文件

    Args:
        directory: 目录路径
        server_url: 转录服务地址
        output_dir: 输出目录
        diarize: 是否启用说话人分离
        model_id: 指定使用的模型 ID（可选）

    Returns:
        批量转录结果
    """
    directory = os.path.abspath(directory)

    if not os.path.isdir(directory):
        return {"success": False, "error": f"目录不存在: {directory}"}

    # 智能输出目录：如果输入目录的父文件夹名是纯数字，自动创建 "视频（已转录）/"
    if output_dir is None:
        dir_name = os.path.basename(directory)
        parent_dir = os.path.dirname(directory)
        parent_name = os.path.basename(parent_dir)

        # 检测父文件夹名是否为纯数字（配合抖音下载技能）
        if parent_name and parent_name.isdigit():
            output_dir = os.path.join(parent_dir, "视频（已转录）")
            os.makedirs(output_dir, exist_ok=True)
            print(f"📁 自动创建输出目录: {output_dir}")

    payload = {
        "directory": directory,
        "diarize": diarize,
        "fast": fast,
    }
    if output_dir:
        payload["output_dir"] = os.path.abspath(output_dir)
    if model:
        payload["model"] = model
    if model_id:
        payload["model_id"] = model_id

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{server_url}/batch_transcribe",
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=3600) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            return json.loads(error_body)
        except:
            return {"success": False, "error": error_body}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"无法连接到服务: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description='FunASR 转录客户端 - 将音频/视频转换为 Markdown',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 转录单个文件
  python transcribe.py /path/to/audio.mp3

  # 转录并指定输出路径
  python transcribe.py /path/to/video.mp4 -o transcript.md

  # 禁用说话人分离
  python transcribe.py /path/to/audio.mp3 --no-diarize

  # 单人快速模式（关闭说话人分离，保留默认 Paraformer）
  python transcribe.py /path/to/course.m4a --fast

  # 指定 Paraformer ONNX
  python transcribe.py /path/to/meeting.m4a --model paraformer-onnx

  # 批量转录目录
  python transcribe.py /path/to/media_folder/ --batch

  # 指定服务地址
  python transcribe.py /path/to/audio.mp3 --server http://localhost:8765

  # 转录但不生成 AI 总结
  python transcribe.py /path/to/audio.mp3 --no-summary
"""
    )
    parser.add_argument('path', help='音频/视频文件或目录路径')
    parser.add_argument('-o', '--output', help='输出文件路径（单文件模式）或目录（批量模式）')
    parser.add_argument('--diarize', action='store_true', default=True, help='启用说话人分离（默认启用）')
    parser.add_argument('--no-diarize', action='store_false', dest='diarize', help='禁用说话人分离')
    parser.add_argument('--batch', action='store_true', help='批量转录目录')
    parser.add_argument('--server', default=DEFAULT_SERVER, help=f'转录服务地址（默认 {DEFAULT_SERVER}）')
    parser.add_argument('--json', action='store_true', help='以 JSON 格式输出结果')
    parser.add_argument('--no-summary', action='store_true', help='禁用 AI 总结功能（默认启用）')
    parser.add_argument('--auto-summary', action='store_true', help='自动调用 LLM 生成并注入总结（需要 API Key）')
    parser.add_argument('--model', choices=list(AVAILABLE_MODELS.keys()),
                       help='选择使用的 ASR 模型')
    parser.add_argument('--fast', action='store_true', help='单人快速模式：关闭 diarization，保留当前模型路径')
    parser.add_argument('--slides', action='store_true', help='提取视频关键帧截图（PPT幻灯片）')
    parser.add_argument('--slide-threshold', type=float, default=27.0, help='场景检测阈值（默认27.0，值越低越灵敏）')

    args = parser.parse_args()

    if args.fast and args.diarize:
        args.diarize = False
        print("⚡ fast 模式已自动关闭说话人分离")

    if args.model:
        print(f"🔧 使用模型: {args.model} ({AVAILABLE_MODELS[args.model]})")
    elif args.fast:
        print("⚡ 使用单人快速模式（关闭说话人分离，保留默认 Paraformer）")

    # 检查服务是否运行
    if not check_server(args.server):
        print(f"❌ 无法连接到转录服务: {args.server}")
        print(f"\n请先启动服务:")
        print(f"  python ~/.claude/skills/transcribe/server.py")
        sys.exit(1)

    # 执行转录
    if args.batch or os.path.isdir(args.path):
        result = batch_transcribe(
            args.path,
            server_url=args.server,
            output_dir=args.output,
            diarize=args.diarize,
            model=args.model,
            model_id=None,
            fast=args.fast,
        )
    else:
        result = transcribe_file(
            args.path,
            server_url=args.server,
            output_path=args.output,
            diarize=args.diarize,
            model=args.model,
            model_id=None,
            fast=args.fast,
            extract_slides=args.slides,
            slide_threshold=args.slide_threshold,
        )

    # 输出结果
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get('success'):
            if 'results' in result:
                # 批量结果
                print(f"✅ 批量转录完成，共 {result['total']} 个文件")
                for r in result['results']:
                    status = "✓" if r['success'] else "✗"
                    print(f"  {status} {r['file']}")
                    if r['success']:
                        print(f"    → {r['output']}")
                    else:
                        print(f"    错误: {r.get('error', '未知')}")
            else:
                # 单文件结果
                print(f"✅ 转录完成")
                print(f"📄 输出: {result['output_path']}")
                if result.get('resolved_model'):
                    print(f"🧠 模型: {result['resolved_model']} ({result.get('resolved_runtime', 'unknown')})")
                if result.get('warnings'):
                    for warning in result['warnings']:
                        print(f"⚠️  {warning}")
                if result.get('sentence_count'):
                    print(f"📝 句子数: {result['sentence_count']}")

                # 生成 AI 总结（默认启用，使用 --no-summary 可禁用）
                if not args.json and not args.no_summary and summarize_file_for_claude:
                    md_path = Path(result['output_path'])

                    # 自动模式：生成总结请求，Claude Code 会自动处理
                    if args.auto_summary and generate_summary_via_api:
                        print("🤖 正在自动生成 AI 总结...")
                        success, msg = generate_summary_via_api(md_path)
                        if success:
                            print(f"✅ {msg}")
                        else:
                            print(f"❌ 自动总结失败: {msg}")
                        # 自动模式不需要再输出提示词
                        return

                    # 标准模式：输出提示词供 LLM 调用
                    print("🤖 正在准备 AI 总结...")
                    success, prompt, text = summarize_file_for_claude(md_path)

                    if not success:
                        print(f"❌ {prompt}")
                    else:
                        print("\n" + "="*60)
                        print("📋 请将以下提示词发送给 AI 以生成总结：")
                        print("="*60)
                        print(prompt)
                        print("="*60)
        else:
            print(f"❌ 转录失败: {result.get('error', '未知错误')}")
            sys.exit(1)


if __name__ == '__main__':
    main()
