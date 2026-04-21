---
name: minimax-image-understand
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.1.0"
description: "通过 MiniMax MCP 对图片进行内容描述、文字识别（OCR）和视觉问答，返回结构化文本分析结果。适用于 OpenClaw 平台。本技能应在用户发送图片并要求分析、描述、识别内容、提取文字、或回答关于图片内容的问题时使用。Claude Code 用户请忽略此技能。"
license: MIT
---

# MiniMax MCP 图像理解

> **平台限制**：本技能仅适用于 **OpenClaw** 平台，Claude Code 用户请忽略。

通过 MiniMax MCP 对图片进行内容描述、文字提取和视觉问答。

## 前置要求

1. 安装依赖：`pip install mcp`
2. 配置环境变量：复制 `scripts/.env.example` 为 `scripts/.env` 并填入 API Key

## 使用方法

```bash
cd ~/.openclaw/skills/minimax-image-understand/scripts
source .env
python3 image_understand.py <图片路径或URL> [提示词]
```

示例：

```bash
python3 image_understand.py photo.jpg "描述这张图片的内容"
python3 image_understand.py screenshot.png "提取图中的文字"
```

## 代码中调用

```python
import os
import sys
import asyncio

sys.path.insert(0, os.path.expanduser("~/.openclaw/skills/minimax-image-understand/scripts"))
os.environ["MINIMAX_API_KEY"] = "your-key"  # 或从 .env 加载
from image_understand import understand_image

result = asyncio.run(understand_image("image.jpg", "描述这张图片"))
print(result)
```

## 图片路径

OpenClaw 平台接收的图片保存位置：`~/.openclaw/media/inbound/`，文件名格式：`{uuid}.jpg`

## 配置文件

`scripts/.env` 格式：

```
MINIMAX_API_KEY=your-api-key
```
