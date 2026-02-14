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
    from .summary import summarize_file_for_claude, inject_summary_to_file
except ImportError:
    # 如果是直接运行
    try:
        from summary import summarize_file_for_claude, inject_summary_to_file
    except ImportError:
        summarize_file_for_claude = None
        inject_summary_to_file = None


DEFAULT_SERVER = "http://127.0.0.1:8765"

# 可用模型列表
# 注意: Nano 模型暂不支持当前 FunASR 版本 (1.3.1)，需要等待官方修复
AVAILABLE_MODELS = {
    "paraformer": "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    # "nano": "FunAudioLLM/fun-asr-nano-2512",  # 暂不可用
    # "nano-mlt": "FunAudioLLM/fun-asr-mlt-nano-2512",  # 暂不可用
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
                    model_id: str = None) -> dict:
    """
    转录单个文件

    Args:
        file_path: 音频/视频文件路径
        server_url: 转录服务地址
        output_path: 输出 Markdown 文件路径
        diarize: 是否启用说话人分离
        model_id: 指定使用的模型 ID（可选）

    Returns:
        转录结果字典
    """
    # 转换为绝对路径
    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        return {"success": False, "error": f"文件不存在: {file_path}"}

    payload = {
        "file_path": file_path,
        "diarize": diarize
    }
    if output_path:
        payload["output_path"] = os.path.abspath(output_path)
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
                     model_id: str = None) -> dict:
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
        "diarize": diarize
    }
    if output_dir:
        payload["output_dir"] = os.path.abspath(output_dir)
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
        epilog=f"""
可用模型:
  paraformer  - Paraformer 大模型（默认，传统流水线）
  nano        - Fun-ASR-Nano-2512（端到端，800M参数，支持方言）
  nano-mlt    - Fun-ASR-MLT-Nano-2512（多语言版本）

示例:
  # 转录单个文件
  python transcribe.py /path/to/audio.mp3

  # 转录并指定输出路径
  python transcribe.py /path/to/video.mp4 -o transcript.md

  # 启用说话人分离
  python transcribe.py /path/to/meeting.m4a --diarize

  # 使用新模型 Fun-ASR-Nano
  python transcribe.py /path/to/audio.mp3 --model nano

  # 批量转录目录
  python transcribe.py /path/to/media_folder/ --batch

  # 智能目录映射（配合抖音下载技能使用）
  python transcribe.py /path/to/用户ID/视频/ --batch
  # 自动输出到: /path/to/用户ID/视频（已转录）/

  # 指定服务地址
  python transcribe.py /path/to/audio.mp3 --server http://localhost:8765

  # 转录但不生成 AI 总结
  python transcribe.py /path/to/audio.mp3 --no-summary
"""
    )
    parser.add_argument('path', help='音频/视频文件或目录路径')
    parser.add_argument('-o', '--output', help='输出文件路径（单文件模式）或目录（批量模式）')
    parser.add_argument('--diarize', action='store_true', help='启用说话人分离')
    parser.add_argument('--batch', action='store_true', help='批量转录目录')
    parser.add_argument('--server', default=DEFAULT_SERVER, help=f'转录服务地址（默认 {DEFAULT_SERVER}）')
    parser.add_argument('--json', action='store_true', help='以 JSON 格式输出结果')
    parser.add_argument('--no-summary', action='store_true', help='禁用 AI 总结功能（默认启用）')
    parser.add_argument('--claude-code', action='store_true', help='Claude Code 模式：自动请求 AI 生成并注入总结')
    parser.add_argument('--model', choices=['paraformer'],
                       help='选择使用的 ASR 模型（默认: paraformer）')

    args = parser.parse_args()

    # 解析模型 ID
    model_id = None
    if args.model:
        model_id = AVAILABLE_MODELS.get(args.model)
        if model_id:
            print(f"🔧 使用模型: {args.model} ({model_id})")

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
            model_id=model_id
        )
    else:
        result = transcribe_file(
            args.path,
            server_url=args.server,
            output_path=args.output,
            diarize=args.diarize,
            model_id=model_id
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
                if result.get('sentence_count'):
                    print(f"📝 句子数: {result['sentence_count']}")

                # 生成 AI 总结（默认启用，使用 --no-summary 可禁用）
                if not args.json and not args.no_summary and summarize_file_for_claude and inject_summary_to_file:
                    md_path = Path(result['output_path'])

                    # Claude Code 模式：打印转录文本供 AI 直接处理
                    if args.claude_code:
                        success, prompt, text = summarize_file_for_claude(md_path)
                        if success:
                            print("\n" + "="*60)
                            print("📋 Claude Code 请根据以下转录内容生成 AI 总结：")
                            print("="*60)
                            print(f"\n文件: {md_path}")
                            print(f"\n转录文本:\n{text}")
                            print("="*60)
                            print("\n✅ 转录完成！请生成 AI 总结并注入到文件中。")
                    else:
                        # 标准模式：显示提示词供用户复制
                        print("🤖 正在准备 AI 总结...")
                        success, prompt, text = summarize_file_for_claude(md_path)

                        if not success:
                            print(f"❌ {prompt}")  # prompt contains error message
                        else:
                            print("\n" + "="*60)
                            print("📋 请将以下提示词发送给 Claude AI 以生成总结：")
                            print("="*60)
                            print(prompt)
                            print("="*60)
        else:
            print(f"❌ 转录失败: {result.get('error', '未知错误')}")
            sys.exit(1)


if __name__ == '__main__':
    main()
