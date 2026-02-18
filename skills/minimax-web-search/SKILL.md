---
name: minimax-web-search
description: 通过 MiniMax MCP 进行网络搜索，适用于 OpenClaw 平台。如果你是 Claude Code 用户，请忽略此技能。
license: MIT
---

# MiniMax 网络搜索

> **重要提示**：本技能适用于 **OpenClaw** 平台。如果你使用的是 **Claude Code**，请忽略此技能。

通过 MiniMax MCP 进行网络搜索。

## 触发条件

需要搜索实时信息、网络最新动态时使用。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| Python 3.10+ | macOS: `brew install python3`<br>Linux: `sudo apt-get install python3` |

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `mcp` | MCP 客户端库 | `pip install mcp` |

## 前置要求

1. 安装依赖：`pip install mcp`
2. 配置环境变量：复制 `.env.example` 为 `.env` 并填入 API Key

## 使用方法

```bash
cd ~/.openclaw/skills/minimax-mcp-web-search/scripts
source .env
python3 web_search.py "搜索关键词"
```

## 代码中调用

```python
import sys
import os
sys.path.insert(0, "~/.openclaw/skills/minimax-mcp-web-search/scripts")
os.environ["MINIMAX_API_KEY"] = "your-key"  # 或从 .env 加载
from web_search import web_search
result = await web_search("法律AI最新动态")
```

## 配置文件

`.env` 文件已放在 `scripts/` 目录下，格式：
```
MINIMAX_API_KEY=your-api-key
```
