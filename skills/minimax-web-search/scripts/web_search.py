#!/usr/bin/env python3
"""
MiniMax MCP 网络搜索工具
"""

import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

API_KEY = os.environ.get("MINIMAX_API_KEY", "")
OUTPUT_DIR = "/tmp/minimax-mcp"
DEFAULT_MAX_RESULTS = 5

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


async def web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS):
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("web_search", {"query": query})
            result_text = result.content[0].text if hasattr(result.content[0], 'text') else str(result)
            try:
                data = json.loads(result_text)
                organic_results = data.get("organic", [])[:max_results]
                return {
                    "query": query,
                    "results": [{"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", ""), "date": r.get("date", "")} for r in organic_results],
                    "related_searches": [r.get("query", "") for r in data.get("related_searches", [])]
                }
            except json.JSONDecodeError:
                return {"raw_result": result_text}


def main():
    if len(sys.argv) < 2:
        print("用法: python3 web_search.py <搜索查询> [最大结果数]")
        sys.exit(1)

    query = sys.argv[1]
    max_results = DEFAULT_MAX_RESULTS
    if len(sys.argv) >= 3:
        try:
            max_results = max(1, int(sys.argv[2]))
        except ValueError:
            print("错误: 最大结果数必须是正整数")
            sys.exit(1)
    print(f"🔍 搜索: {query}")
    print("-" * 60)

    try:
        result = asyncio.run(web_search(query, max_results=max_results))
        for i, r in enumerate(result.get("results", []), 1):
            print(f"\n{i}. {r['title']}")
            print(f"   📎 {r['link']}")
            print(f"   📝 {r['snippet'][:150]}...")
    except Exception as e:
        print(f"❌ 搜索失败: {e}")


if __name__ == "__main__":
    main()
