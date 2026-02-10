---
name: md2word
description: Markdown转Word文档技能。将Markdown文档转换为符合中文排版标准的专业格式Word文档，支持多种预设格式。适用于正式文档、论文、报告等需要规范排版的文档转换。
---

# Markdown转Word文档Skill

## 概述

将 Markdown 文档转换为符合中文排版标准的 Word 文档。支持完整的 Markdown 语法，自动应用专业格式设置。

## 依赖要求

### Python 依赖

```bash
pip install python-docx Pillow beautifulsoup4 PyYAML
```

### 可选依赖

```bash
npm install -g @mermaid-js/mermaid-cli
```

## 快速开始

主转换脚本：`scripts/md2word.py`

```bash
# 基本转换
python scripts/md2word.py input.md output.docx

# 使用预设格式
python scripts/md2word.py input.md --preset=academic

# 使用自定义配置
python scripts/md2word.py input.md --config=my-config.yaml
```

## 配置系统

### 内置预设

- **legal**: 正式文档格式（默认）
- **academic**: 学术论文格式
- **report**: 工作报告格式
- **simple**: 简单文档格式

> 完整配置见 `assets/presets/*.yaml`

### 自定义配置

复制配置模板并修改：
```bash
cp assets/config-template.yaml my-config.yaml
```

### Word 模板文件

将 `.docx` 模板放入 `assets/templates/` 目录，或使用 `--template` 指定。

**Word 模板 vs 配置文件**：
- **Word 模板**：控制视觉元素（页眉、页脚、Logo）
- **配置文件**：控制格式参数（字号、行距、页边距）

## 参考文档

**配置参考**: See [references/config-reference.md](references/config-reference.md)
**使用示例**: See [references/examples.md](references/examples.md)

## 错误处理

- **文件编码**：自动检测 UTF-8 和 GBK
- **模板找不到**：使用默认格式创建新文档
- **Mermaid 失败**：降级为文本描述
- **图片过大**：自动压缩和调整尺寸

## 目录结构

```
md2word/
├── SKILL.md               # 本文档
├── CHANGELOG.md           # 版本记录
├── references/            # 参考文档
│   ├── config-reference.md
│   └── examples.md
├── scripts/               # 转换脚本
│   ├── md2word.py         # 主脚本
│   ├── config.py          # 配置模块
│   ├── formatter.py       # 文本格式化模块
│   ├── table_handler.py   # 表格处理模块
│   ├── chart_handler.py   # 图表渲染模块
└── assets/                # 资源文件
    ├── presets/           # YAML 预设配置
    ├── templates/         # Word 模板文件
    └── config-template.yaml
```
