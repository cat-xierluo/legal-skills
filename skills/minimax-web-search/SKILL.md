---
name: minimax-web-search
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.1.1"
description: "通过 MiniMax MCP 搜索实时网络信息，检索最新动态、查找文章和回答需要在线数据的问题，返回结构化搜索结果。适用于 OpenClaw 平台。本技能应在用户需要搜索网络、查找最新信息、在线查询实时数据时使用。Claude Code 用户请忽略此技能。"
license: MIT
---

# MiniMax 网络搜索

> **平台限制**：本技能仅适用于 **OpenClaw** 平台，Claude Code 用户请忽略。

通过 MiniMax MCP 搜索实时网络信息并返回结构化结果。

## 前置要求

1. 安装依赖：`pip install mcp`
2. 配置环境变量：复制 `scripts/.env.example` 为 `scripts/.env` 并填入 API Key
3. 确保 `uvx minimax-coding-plan-mcp` 可用（参见 [MiniMax MCP 文档](https://github.com/anthropics/anthropic-cookbook/tree/main/misc/mcp)）

## 使用方法

```bash
cd ~/.openclaw/skills/minimax-web-search/scripts
source .env
python3 web_search.py "搜索关键词"
```

示例：

```bash
python3 web_search.py "法律AI最新动态"
python3 web_search.py "2026年知识产权法修订"
```

## 代码中调用

```python
import os
import sys
import asyncio

sys.path.insert(0, os.path.expanduser("~/.openclaw/skills/minimax-web-search/scripts"))
os.environ["MINIMAX_API_KEY"] = "your-key"  # 或从 .env 加载
from web_search import web_search

result = asyncio.run(web_search("法律AI最新动态"))
print(result)
```

## 配置文件

`scripts/.env` 格式：

```
MINIMAX_API_KEY=your-api-key
```
