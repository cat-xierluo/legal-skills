# 技术文档主题样式配置

专为技术文档设计的主题，适合 API 文档、开发指南等。

## 主题概述

- **名称**: 技术文档主题
- **适用场景**: API 文档、技术规范、开发指南
- **风格**: 现代、清晰、易读
- **模板文件**: `tech-doc.docx`

---

## 样式特点

### 标题

- 字体: Source Sans Pro 或 微软雅黑
- 颜色: 技术蓝 (#2196F3)
- H1: 18pt / H2: 16pt / H3: 14pt

### 正文

- 字体: Source Sans Pro / 宋体
- 字号: 10.5pt
- 行距: 1.3

### 代码块

- 字体: Fira Code 或 Source Code Pro
- 背景: 深色 (#282C34) 或浅色 (#F5F5F5)
- 语法高亮支持

### 行内代码

- 字体: 等宽
- 背景: 浅灰 (#E8E8E8)
- 圆角边框

---

## 使用方法

```bash
python scripts/extract_template_config.py \
  --template assets/templates/tech-doc.docx \
  --output assets/presets/tech-doc.yaml \
  --profile tech-doc
```

---

## 推荐字体安装

### macOS

```bash
brew install --cask font-source-sans-pro
brew install --cask font-source-code-pro
brew install --cask font-fira-code
```

### Windows

从以下网站下载安装：
- https://fonts.google.com/ (Source Sans Pro, Source Code Pro)
- https://github.com/tonsky/FiraCode

---

## 待修改配置

当前为默认模板副本，需手动调整：

1. 打开 `tech-doc.docx`
2. 修改标题颜色为 #2196F3
3. 调整代码块背景色
4. 设置代码字体为 Fira Code
