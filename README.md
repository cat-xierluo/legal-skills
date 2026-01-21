# Legal Skills

> 面向创作者与法律从业者的 Claude Skills 集合，提供从内容获取、处理到归档的全流程 AI 协作能力。

[![GitHub](https://img.shields.io/badge/GitHub-cat--xierluo-blue)](https://github.com/cat-xierluo/legal-skills)

## 📋 项目概述

本项目旨在沉淀并分发实用的 Claude Skills，围绕创作者与法律工作者的核心需求，构建一套完整的技能生态系统。

### 技能体系

我们的技能覆盖三大核心场景：

1. **内容获取** - 从多种来源抓取和转换内容
   - 微信公众号文章抓取、OCR 识别、语音转文字

2. **内容处理** - 格式转换、媒体处理、图片托管
   - PDF/图片转 Markdown、图片上传到图床

3. **专业应用** - 法律业务场景的专业技能
   - （筹备中，欢迎贡献）

### 核心特点

- 🎯 **全流程覆盖**：从内容获取到处理归档的完整工作流
- 📦 **独立自包含**：每个技能都是完整的模块，可单独使用或组合使用
- 📝 **文档完善**：每个技能配备决策记录、任务跟踪、变更日志
- 🌐 **跨平台支持**：全面支持 Windows、macOS 和 Linux

## 🛠️ 技能列表

### 官方技能

来自 Claude Code 官方的通用技能：

| 技能 | 说明 |
| :--- | :--- |
| **[skill-creator](skills/skill-creator/)** | 技能创建指南和工具集 |
| **[pdf](skills/pdf/)** | PDF 处理工具包：文本提取、表单填写、合并拆分 |

### 自研技能

面向创作者与法律工作者的实用技能：

#### 📥 内容获取

从各种来源抓取和转换内容：

| 技能 | 说明 | 状态 |
| :--- | :--- | :--- |
| **[wechat-article-fetch](skills/wechat-article-fetch/)** | 抓取微信公众号文章内容，自动保存为 Markdown，支持 Windows 平台和智能回退 | ✅ v1.0.0 |
| **[mineru-ocr](skills/mineru-ocr/)** | PDF/图片转 Markdown，支持 OCR、表格和公式识别 | ✅ v1.0.1 |
| **[funasr-transcribe](skills/funasr-transcribe/)** | 本地语音转文字，支持会议记录、视频字幕、播客转录 | ✅ v1.1.1 |

#### 📤 内容处理

格式转换、媒体处理、图片托管：

| 技能 | 说明 | 状态 |
| :--- | :--- | :--- |
| **[piclist-upload](skills/piclist-upload/)** | 将 Markdown 中的本地图片上传到图床，自动替换为云端链接 | ✅ v1.1.0 |

#### 🔧 开发工具

技能开发、插件管理等开发工具：

| 技能 | 说明 | 状态 |
| :--- | :--- | :--- |
| **[skill-manager](skills/skill-manager/)** | 管理 Claude Skills 的安装、同步、卸载和列表查看 | ✅ v1.0.0 |

> 💡 **技能定位说明**：本项目名为 "Legal Skills"，但技能库不仅限于法律场景。我们围绕创作者工作流构建通用工具集，同时欢迎法律专业场景的技能贡献。

## 📖 协作规范

本项目遵循 [AGENTS.md](AGENTS.md) 定义的协作规范（v1.1.2）：

- **技能导向**：每个技能独立成树，根目录包含 SKILL.md 和配套文档
- **文档即上下文**：关键决策、任务、变更记录在文档中
- **透明变更**：所有修改写入 CHANGELOG.md，遵循版本号规范
- **保留证据**：输出引用可回溯，缺失信息明确标注

## 🚀 安装方法

### 方式一：通过 Claude Code Plugin Marketplace（推荐）

在 Claude Code 中使用以下命令安装：

```bash
# 添加插件市场源
/plugin marketplace add cat-xierluo/legal-skills

# 安装技能集合
/plugin install legal-skills
```

### 方式二：下载压缩包

下载本项目压缩包，解压后将技能目录复制到 Claude Code 技能目录：

```bash
# macOS / Linux
cp -r legal-skills/skills/* ~/.claude/skills/

# Windows
xcopy legal-skills\skills\* %USERPROFILE%\.claude\skills\ /E /I
```
