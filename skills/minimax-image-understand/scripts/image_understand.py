#!/usr/bin/env python3
"""
MiniMax MCP 图像理解工具
"""

import asyncio
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

API_KEY = os.environ.get("MINIMAX_API_KEY", "")
OUTPUT_DIR = "/tmp/minimax-mcp"

if not API_KEY:
    print("错误: 请设置环境变量 MINIMAX_API_KEY")
    sys.exit(1)

server_params = StdioServerParameters(
    command="env",
    args=[
        f"MINIMAX_API_KEY={API_KEY}",
        f"MINIMAX_MCP_BASE_PATH={OUTPUT_DIR}",
        "MINIMAX_API_HOST=https://api.minimaxi.com",
        "MINIMAX_API_RESOURCE_MODE=url",
        "uvx", "minimax-coding-plan-mcp"
    ],
)


async def understand_image(image_source: str, prompt: str = "描述这张图片的内容"):
    if image_source.startswith('@'):
        image_source = image_source[1:]
    
    if not image_source.startswith('http://') and not image_source.startswith('https://'):
        if not os.path.exists(image_source):
            return f"错误：文件不存在: {image_source}"
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("understand_image", {"image_source": image_source, "prompt": prompt})
            if hasattr(result, 'content') and result.content:
                return result.content[0].text if hasattr(result.content[0], 'text') else str(result)
            return str(result)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 image_understand.py <图片路径或URL> [提示词]")
        sys.exit(1)
    
    image_source = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) >= 3 else "描述这张图片的内容"
    
    print(f"🖼️ 理解图片: {image_source}")
    print(f"📝 提示词: {prompt}")
    print("-" * 60)
    
    try:
        result = asyncio.run(understand_image(image_source, prompt))
        print(result)
    except Exception as e:
        print(f"❌ 理解图片失败: {e}")


if __name__ == "__main__":
    main()
