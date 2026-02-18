---
name: minimax-image-understand
description: 通过 MiniMax MCP 进行图像理解，适用于 OpenClaw 平台。如果你是 Claude Code 用户，请忽略此技能。
license: MIT
---

# MiniMax MCP 图像理解

> **重要提示**：本技能适用于 **OpenClaw** 平台。如果你使用的是 **Claude Code**，请忽略此技能。

通过 MiniMax MCP 进行图像理解。

## 触发条件

用户发送图片并要求分析、描述、识别时使用。

## 依赖

### 系统依赖

| 依赖         | 安装方式                                                                  |
| ------------ | ------------------------------------------------------------------------- |
| Python 3.10+ | macOS:`brew install python3<br>`Linux: `sudo apt-get install python3` |

### Python 包

| 包名    | 用途         | 安装命令            |
| ------- | ------------ | ------------------- |
| `mcp` | MCP 客户端库 | `pip install mcp` |

## 前置要求

1. 安装依赖：`pip install mcp`
2. 配置环境变量：复制 `.env.example` 为 `.env` 并填入 API Key

## 使用方法

```bash
cd ~/.openclaw/skills/minimax-image-understand/scripts
source .env
python3 image_understand.py <图片路径或URL> [提示词]
```

## 代码中调用

```python
import sys
import os
sys.path.insert(0, "~/.openclaw/skills/minimax-image-understand/scripts")
os.environ["MINIMAX_API_KEY"] = "your-key"  # 或从 .env 加载
from image_understand import understand_image
result = await understand_image("image.jpg", "描述这张图片")
```

## 图片路径

图片保存位置：`~/.openclaw/media/inbound/`，文件名格式：`{uuid}.jpg`

## 配置文件

`.env` 文件已放在 `scripts/` 目录下，格式：

```
MINIMAX_API_KEY=your-api-key
```
