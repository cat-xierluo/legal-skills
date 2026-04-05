#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
FunASR 自动转录 + 总结脚本

此脚本用于 OpenClaw / Claude Code 等 Agent 环境中，自动完成：
1. 转录音频/视频文件
2. 生成 AI 总结提示词
3. 输出总结内容（供 Agent 调用 LLM 生成总结）
4. 将总结注入 Markdown 文件

用法:
    python auto_transcribe.py <音频文件路径> [选项]

选项:
    --output PATH       输出 Markdown 文件路径（默认与音频同目录）
    --diarize           启用说话人分离
    --no-summary       跳过总结步骤
    --prompt-only      只返回总结提示词，不生成总结
    --api URL          API 地址（默认 http://127.0.0.1:8765）

示例:
    python auto_transcribe.py /path/to/audio.aac
    python auto_transcribe.py /path/to/audio.mp4 --diarize
    python auto_transcribe.py /path/to/audio.m4a --prompt-only
"""

import argparse
import json
import os
import sys
import requests
from pathlib import Path


def check_server(api_url: str) -> bool:
    """检查服务是否运行"""
    try:
        resp = requests.get(f"{api_url}/health", timeout=5)
        if resp.status_code == 200:
            return True
    except Exception:
        pass
    return False


def start_server():
    """尝试启动服务"""
    print("FunASR 服务未运行，尝试启动...")
    import subprocess
    script_dir = Path(__file__).parent.absolute()
    subprocess.Popen(
        [sys.executable, str(script_dir / "server.py")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    # 等待服务启动
    import time
    for _ in range(30):
        time.sleep(1)
        if check_server():
            print("✅ FunASR 服务已启动")
            return True
    print("❌ 无法启动 FunASR 服务")
    return False


def transcribe(file_path: str, output_path: str = None, diarize: bool = False, api_url: str = "http://127.0.0.1:8765", extract_slides: bool = False, slide_threshold: float = 27.0) -> dict:
    """转录音频文件"""
    print(f"📝 转录中: {file_path}")

    payload = {
        "file_path": file_path,
        "diarize": diarize,
        "extract_slides": extract_slides,
        "slide_threshold": slide_threshold
    }
    if output_path:
        payload["output_path"] = output_path
    
    resp = requests.post(f"{api_url}/transcribe", json=payload, timeout=600)
    resp.raise_for_status()
    result = resp.json()
    
    if result.get("success"):
        print(f"✅ 转录完成: {result.get('output_path')}")
    else:
        print(f"❌ 转录失败: {result.get('error')}")
        sys.exit(1)
    
    return result


def get_summary_prompt(md_path: str, api_url: str = "http://127.0.0.1:8765") -> dict:
    """获取总结提示词"""
    print(f"📋 生成总结提示词...")
    
    resp = requests.post(
        f"{api_url}/summary",
        json={"md_path": md_path},
        timeout=30
    )
    resp.raise_for_status()
    result = resp.json()
    
    if result.get("success"):
        print(f"✅ 提示词已生成")
    else:
        print(f"❌ 获取提示词失败: {result.get('error')}")
        sys.exit(1)
    
    return result


def inject_summary(md_path: str, summary_content: str, api_url: str = "http://127.0.0.1:8765") -> dict:
    """注入总结到 Markdown 文件"""
    print(f"📝 注入总结到文件...")
    
    resp = requests.post(
        f"{api_url}/inject_summary",
        json={
            "md_path": md_path,
            "summary_content": summary_content
        },
        timeout=30
    )
    resp.raise_for_status()
    result = resp.json()
    
    if result.get("success"):
        print(f"✅ 总结已注入: {result.get('output_path')}")
    else:
        print(f"❌ 注入失败: {result.get('error')}")
        sys.exit(1)
    
    return result


def main():
    parser = argparse.ArgumentParser(description="FunASR 自动转录 + 总结")
    parser.add_argument("file", help="音频/视频文件路径")
    parser.add_argument("--output", "-o", help="输出 Markdown 文件路径")
    parser.add_argument("--diarize", action="store_true", help="启用说话人分离")
    parser.add_argument("--no-summary", action="store_true", help="跳过总结步骤")
    parser.add_argument("--prompt-only", action="store_true", help="只返回总结提示词，不生成总结")
    parser.add_argument("--api", default="http://127.0.0.1:8765", help="API 地址")
    parser.add_argument("--slides", action="store_true", help="提取视频关键帧截图（PPT幻灯片）")
    parser.add_argument("--slide-threshold", type=float, default=27.0, help="场景检测阈值（默认27.0，值越低越灵敏）")
    
    args = parser.parse_args()
    
    api_url = args.api
    
    # 检查服务
    if not check_server(api_url):
        if not start_server():
            print("错误: FunASR 服务未运行且无法启动")
            sys.exit(1)
    
    # 确定输出路径
    file_path = Path(args.file).absolute()
    if args.output:
        output_path = str(Path(args.output).absolute())
    else:
        output_path = str(file_path.with_suffix(".md"))
    
    # 步骤 1: 转录
    transcribe_result = transcribe(
        str(file_path),
        output_path=output_path,
        diarize=args.diarize,
        api_url=api_url,
        extract_slides=args.slides,
        slide_threshold=args.slide_threshold,
    )
    
    md_path = transcribe_result.get("output_path", output_path)
    
    # 步骤 2: 获取总结提示词
    if not args.no_summary:
        summary_result = get_summary_prompt(md_path, api_url)
        
        if args.prompt_only:
            # 只输出提示词（供 Agent 使用）
            print("\n" + "="*60)
            print("总结提示词（供 Agent 调用 LLM 生成总结）:")
            print("="*60)
            print(summary_result.get("summary_prompt", ""))
            print("="*60)
            print(f"\n📄 Markdown 文件: {md_path}")
            print("\n下一步: 使用上面的提示词调用 LLM 生成总结，")
            print("然后使用 inject_summary 端点将总结注入文件。")
        else:
            # 输出完整信息
            print("\n" + "="*60)
            print("📋 总结提示词:")
            print("="*60)
            print(summary_result.get("summary_prompt", ""))
            print("="*60)
            print(f"\n📄 Markdown 文件: {md_path}")
            print("\n💡 提示: 使用上述提示词调用 LLM 生成总结，")
            print("   然后调用 /inject_summary 将总结注入文件。")
            print("   或使用本脚本的完整流程自动完成。")
    else:
        print(f"\n✅ 转录完成: {md_path}")
        print("   (已跳过总结步骤)")


if __name__ == "__main__":
    main()
