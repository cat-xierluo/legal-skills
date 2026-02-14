# Claude Code Skills 开发指南

本指南面向 Skills 开发者,提供 Skills 文档编写的完整规范和最佳实践。

## 1. 目录结构

基于官方 Claude Code skills(`skills/pdf`、`skills/skill-creator`)的标准格式:

```text
skill-name/
├── SKILL.md          # 必需 (官方规范)
├── LICENSE.txt       # 可选 (官方规范)
├── references/       # 可选:参考文档,按需加载 (官方规范)
├── scripts/          # 可选:可执行代码 (扩展)
└── assets/           # 可选:输出资源文件,不加载到上下文 (扩展)
```

**说明**:

- **官方规范**: `SKILL.md`、`LICENSE.txt`、`references/` 是 Claude Code 官方定义的标准目录
- **扩展内容**: `scripts/`、`assets/` 是本项目的扩展约定,用于更好地组织代码和资源

**注意**: `test/` 目录中的 `DECISIONS.md`、`TASKS.md`、`CHANGELOG.md` 是**开发协作文件**,不属于最终 skill 产品。

## 2. Frontmatter 元数据

SKILL.md 必须以 YAML frontmatter 开头:

```yaml
---
name: skill-name
description: 功能描述。This skill should be used when...
license: Complete terms in LICENSE.txt
---
```

**字段说明**:

- ✅ 有 `license` 字段
- ❌ 无 `version` 字段(版本信息在 `CHANGELOG.md` 中管理)

## 3. description 写作规范

### (1) 使用第三人称

- ❌ "Use when..." 或 "当...时使用"
- ✅ "This skill should be used when..."
- ✅ "本技能应在...时使用"

### (2) 示例

**英文**:

```yaml
description: Comprehensive PDF manipulation toolkit for extracting text and tables. This skill should be used when Claude needs to fill in a PDF form or programmatically process PDF documents at scale.
```

**中文**:

```yaml
description: 将法律文本转换为规范的 Markdown 格式。本技能应在用户需要处理法律条文(如民法典、刑法)、整理法律案例(如最高法典型案例)、或从粘贴文本中格式化法律文档时使用。
```

## 4. 依赖管理

### (1) 依赖说明位置

依赖说明应直接写在 `SKILL.md` 的"依赖"章节中。

### (2) SKILL.md 依赖章节格式

```markdown
## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| 软件名 | macOS: `brew install xxx`<br>Linux: `sudo apt-get install xxx` |

### Python 包

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| `package-name` | 用途说明 | `pip install package-name` |
```

### (3) 依赖包文件(可选,扩展)

如需管理大量 Python 依赖,可在 `assets/` 目录下使用 `requirements.txt`:

```bash
pip install -r assets/requirements.txt
```

## 5. Progressive Disclosure 设计

Skills 使用渐进式加载系统管理上下文:

### (1) Level 0: Frontmatter (始终加载)

- SKILL.md 的 YAML frontmatter
- 仅包含 name、description、license
- 用于技能发现和匹配,必须极度精简

### (2) Level 1: 核心文档 (按需加载)

- SKILL.md 的正文内容
- 当技能被触发时才加载到上下文
- 应包含核心操作流程和常用示例
- 避免大段代码,使用简洁示例
- 通过引用指向 scripts/ 和 references/

### (3) Level 2: 支持性文档 (不自动加载,官方规范)

- references/ 目录中的详细文档
- 仅在 SKILL.md 中明确引用时由 AI 主动读取
- 包含详细API文档、完整示例、边缘案例

### (4) Level 3: 可执行资源 (调用不加载,扩展)

- scripts/ 目录中的可执行脚本
- assets/ 目录中的资源文件
- 通过 Bash 工具直接调用,不占用上下文
- 代码应放在这里,而非文档中

## 6. 文档编写最佳实践

### (1) Frontmatter 优化

- description 必须精准,100字以内
- 明确触发场景,使用"本技能应在...时使用"格式
- 避免冗余关键词堆砌

### (2) SKILL.md 内容原则

1. **避免大段代码** - 代码应放在 scripts/ 中
2. **使用简洁示例** - 仅展示关键API调用
3. **引用而非粘贴** - 指向 scripts/ 和 references/
4. **聚焦工作流程** - 说明"做什么"和"怎么做"

### (3) 何时使用 scripts/ (扩展)

- 可复用的代码逻辑
- 完整的工具脚本
- 需要多次调用的函数
- 超过20行的代码

### (4) 何时使用 references/ (官方规范)

- 详细的API文档
- 完整的使用案例
- 边缘场景处理
- 历史版本说明

### (5) 何时使用 assets/ (扩展)

- 输出模板文件
- 配置文件示例
- 二进制资源
- requirements.txt

## 7. 配置文件规范

### (1) 文件命名规则

| 类型 | 格式 | 是否提交 | 说明 |
|------|------|----------|------|
| 模板文件 | `*.example.*` | ✅ 提交 | 包含示例值的模板，可直接复制使用 |
| 配置文件 | `*` | ❌ 忽略 | 实际使用的配置文件，应被 .gitignore 忽略 |

**示例**:

```text
.env.example            → 提交（模板）
.env                    → 忽略（实际配置）
config.json.example     → 提交（模板）
config.json             → 忽略（实际配置）
```

### (2) 自包含项目原则

每个 skill 是**自包含项目**，所有配置在项目目录内管理：

- ✅ 模板文件放在 `assets/` 目录
- ✅ 配置文件与模板文件在同一目录
- ✅ 用户复制 `.env.example` 为 `.env`（同目录）
- ✅ 代码从项目目录读取配置文件
- ❌ 不要要求用户复制到外部目录（如 `~/.xxx/`）

### (3) 代码读取配置

代码使用 `python-dotenv` 从当前目录加载配置：

```python
from dotenv import load_dotenv
load_dotenv()  # 自动加载项目目录下的 .env 文件

import os
api_key = os.getenv("API_KEY")  # 从 .env 读取
```

**注意**: `.gitignore` 在项目根目录配置，涵盖所有需要忽略的文件。

## 8. 技能间协作规范

### (1) 松耦合原则

技能应保持**松耦合**，避免直接引用其他技能的内部实现：

- ✅ 在 SKILL.md 中用自然语言描述协作场景
- ✅ 说明技能"做什么"和"如何配合"
- ❌ 不直接引用其他技能的内部脚本路径
- ❌ 不在代码中 import 其他技能的模块

### (2) 协作文档示例

**推荐写法**（自然语言描述）：

```markdown
## 与其他技能配合

下载的视频可以使用 FunASR 技能转录为带时间戳的 Markdown 文件。
两个技能独立运行，可根据需要灵活组合使用。
```

**避免写法**（直接引用实现）：

```markdown
## 与其他技能配合

转录时运行：
\`\`\`bash
python ../../skills/funasr-transcribe/scripts/transcribe.py
\`\`\`
```

### (3) AI 作为协调中介

技能协作由 **AI 负责理解和协调**，而非技能间直接调用：

- 用户描述需求 → AI 理解涉及哪些技能 → AI 依次调用相应技能
- 文档只需说明"可以配合使用"，AI 会自动处理协调细节
- 这种设计促进技能的可研究性、可维护性和可复用性

### (4) 复杂编排

对于涉及多个技能的复杂编排（如定时任务、条件分支、串行/并行执行），请参考 **[SKILL-ORCHESTRATION-GUIDE.md](SKILL-ORCHESTRATION-GUIDE.md)**。

**两份文档的关系**：

| 文档 | 职责 |
|:-----|:-----|
| **SKILL-DEV-GUIDE.md**（本文档） | 单个 Skill 的开发规范 |
| **SKILL-ORCHESTRATION-GUIDE.md** | 多个 Skill 的协作编排规范 |

SKILL-ORCHESTRATION-GUIDE.md 涵盖：
- 与传统 Workflow 工具（N8N/Dify）的区别
- 协作模式（串行/并行/条件/循环）
- 可编排 Skill 设计规范
- 编排描述格式（WORKFLOW.md 模板）
- 定时运行配置（launchd/cron）

## 9. SKILL-DEV-GUIDE.md 更新规范

**重要**: 本指南文件(SKILL-DEV-GUIDE.md)的每次修改都必须同步更新底部的"变更历史"章节。

### (1) 更新流程

1. **修改内容**: 在 SKILL-GUIDE.md 中进行任何修改(新增/修改规范、调整格式等)
2. **更新变更历史**: 在"变更历史"表格顶部添加新的版本记录
3. **版本号递增**: 根据修改性质递增版本号

### (2) 版本号规则

- **小修改**(格式调整、文字优化): 递增最后一位(如 v1.0.1 → v1.0.2)
- **新增规范**: 递增中间一位(如 v1.0.1 → v1.1.0)
- **重大变更**: 递增第一位(如 v1.0.1 → v2.0.0)

### (3) 变更历史记录格式

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0.0 | YYYY-MM-DD | 简要描述本次修改的内容 |

### (4) 自动更新要求

AI 代理在修改 SKILL-GUIDE.md 时,必须:

1. 检查是否对文件内容进行了实质性修改
2. 如果是,自动在"变更历史"表格顶部添加新记录
3. 递增版本号

## 变更历史

| 版本 | 日期 | 更新内容 |
| ---- | ---- | -------- |
| v1.3.0 | 2026-02-14 | 重命名为 SKILL-DEV-GUIDE.md；更新第8节引用为 SKILL-ORCHESTRATION-GUIDE.md |
| v1.2.0 | 2026-02-14 | 在第8节新增(4)"复杂工作流编排"，引用 WORKFLOW-GUIDE.md，明确两份文档的职责分工 |
| v1.1.0 | 2026-02-12 | 新增第8节"技能间协作规范"，明确技能应通过自然语言描述协作方式，避免直接引用其他技能的内部实现 |
| v1.0.2 | 2026-02-12 | 修正配置文件规范章节;移除每个skill创建.gitignore的指引;修正复制规则说明（配置文件与模板同目录）;修复章节编号重复问题 |
| v1.0.1 | 2026-01-30 | 为所有章节添加序号;明确标注 scripts/ 和 assets/ 为扩展内容,SKILL.md 和 references/ 为官方规范 |
| v1.0.0 | 2026-01-30 | 初始版本:从 AGENTS.md 中分离 Skill 文档规范,包含目录结构、Frontmatter 元数据、description 写作规范、依赖管理、Progressive Disclosure 设计、文档编写最佳实践 |
