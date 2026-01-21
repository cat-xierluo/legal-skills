# Legal Skills

> 面向法律从业者的 Claude Skills 集合，将 Claude 从通用 AI 助手转变为专业的法律工作协作者。

[![GitHub](https://img.shields.io/badge/GitHub-cat--xierluo-blue)](https://github.com/cat-xierluo/legal-skills)

## 📋 项目概述

本项目旨在沉淀并分发面向法律实务的 Claude Skills，支持诉讼与非诉场景的 AI 协作。

### 核心特点

- 🎯 **场景导向**：聚焦法律实务场景（证据整理、文档转换、案件分析等）
- 📦 **独立自包含**：每个技能都是完整的模块，可单独使用或组合使用
- 📝 **文档完善**：每个技能配备决策记录、任务跟踪、变更日志

## 🛠️ 技能列表

### 官方技能

来自 Claude Code 官方的通用技能：

| 技能                                   | 说明                                         |
| :------------------------------------- | :------------------------------------------- |
| **[skill-creator](skills/skill-creator/)** | 技能创建指南和工具集                         |
| **[pdf](skills/pdf/)**                     | PDF 处理工具包：文本提取、表单填写、合并拆分 |

### 自研技能

面向法律场景定制开发的技能：

| 技能 | 说明 | 状态 |
| :--- | :--- | :--- |
| **[skill-manager](skills/skill-manager/)** | 管理 Claude Skills 的安装、同步、卸载和列表查看 | ✅ v1.0.0 |
| **[funasr-transcribe](skills/funasr-transcribe/)** | 本地语音转文字，支持会议记录、视频字幕、播客转录 | ✅ v1.1.1 |
| **[mineru-ocr](skills/mineru-ocr/)** | PDF/图片转 Markdown，支持 OCR、表格和公式识别 | ✅ v1.0.1 |
| **[piclist-upload](skills/piclist-upload/)** | 将 Markdown 中的本地图片上传到图床，自动替换为云端链接 | ✅ v1.1.0 |
| **[wechat-article-fetch](skills/wechat-article-fetch/)** | 抓取微信公众号文章内容，支持自动重试和错误处理 | 🧪 v0.1.1 |

### 其他创作者技能

来自社区贡献的技能：

> 暂无，欢迎贡献！

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
