本项目旨在沉淀并分发面向律师办案的 Claude Skills，支持诉讼与非诉场景的 AI 协作。请所有 AI 代理遵循以下约定，确保技能可复用、可追溯、可扩展。

## 核心原则

- **中文优先**：**所有回复必须使用中文**，无论用户使用何种语言提问。这是强制要求，不是可选项。
- **技能导向**：每个技能独立成树（例：`med-extract/`），根目录直接包含 `SKILL.md`、`references/` 等资源和配套文档（`DECISIONS.md`、`TASKS.md`、`CHANGELOG.md`）。
- **文档即上下文**：关键决策、路线、任务、变更、日志必须记录在各技能目录下的对应文档文件中。
- **透明变更**：任何对用户或协作者有影响的修改都要写入对应技能目录下的 `CHANGELOG.md`，重要决策写入 `DECISIONS.md`。
- **技能级文档**：本项目的 `CHANGELOG.md`、`DECISIONS.md`、`TASKS.md` 等文档均为**技能级别**（位于各技能目录下），**不创建项目级别的文档**。当用户要求"更新文档"时，默认指当前操作涉及的特定技能的文档。
- **保留证据**：输出引用需可回溯到来源文件；缺失信息明确标注"未提及/待补充"，避免臆测。

## 目录约定（每个技能项目）

- 根目录：`SKILL.md`（必填，含 frontmatter），`config/`、`references/`、`scripts/`、`assets/`（按需），文档文件（`DECISIONS.md`、`TASKS.md`、`CHANGELOG.md`），原始材料。

## 依赖管理规范

依赖说明应直接写在 `SKILL.md` 的"依赖"章节中。

### SKILL.md 依赖章节格式

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

### 依赖包文件（可选）

如需管理大量 Python 依赖，可在 `assets/` 目录下使用 `requirements.txt`：

```bash
pip install -r assets/requirements.txt
```

## 许可证管理规范

### 技能许可证分类

1. **法律专业应用技能**：使用 CC BY-NC-SA 4.0（署名-非商业性使用-相同方式共享）
   - 涉及法律业务分析、文书生成、专业咨询的技能
   - 示例：`litigation-analysis`、`legal-proposal-generator`、`legal-text-format`、`legal-qa-extractor`

2. **通用工具类技能**：使用 MIT 许可证
   - 内容获取、格式转换、开发工具等通用功能
   - 示例：`mineru-ocr`、`funasr-transcribe`、`skill-manager`、`piclist-upload`、`course-generator` 等

3. **官方技能**：保持原有许可证不变
   - `skill-creator`、`pdf`

### SKILL.md Frontmatter 许可证字段

- **法律专业应用**：`license: CC-BY-NC-SA-4.0`
- **通用工具**：`license: MIT`
- **官方技能**：`license: Complete terms in LICENSE.txt`

### LICENSE.txt 文件

每个技能目录应包含对应的 LICENSE.txt 文件，使用完整许可证文本：

- CC BY-NC-SA 4.0 许可证模板位于 `templates/LICENSE-NC-APACHE.txt`
- MIT 许可证使用标准 MIT 许可证文本

### 版权信息规范

所有自研技能的 LICENSE.txt 文件必须使用统一的版权信息格式：

```text
Copyright (c) 2025 杨卫薪律师（微信ywxlaw）
```

**例外情况**：

- **官方技能**（skill-creator、pdf）：保持原作者版权信息
- **协作技能**：如 mineru-ocr、funasr-transcribe 等基于外部项目的技能，可保留项目特定的版权信息（如 "MinerU Skill Contributors"）

### README.md 许可证列

在 README.md 技能列表表格中应包含"许可证"列，明确标注各技能的许可证类型。

## 文件夹存放规范（主项目）

- 正式发布的技能放在 `skills/` 目录下（如 `skills/pdf/`），调试中的技能放在 `test/` 目录下。
- 技能目录名与技能 name 保持一致。
- 示例/原始材料与技能同级放置，命名清晰，避免混入其他技能资料。

## 标准作业流程（每个技能）

1) **选择目标**：阅读 `TASKS.md`，选择首个未完成目标作为当前任务。若无目标，补充并认领。
2) **分析与计划**：理解目标输出与验收标准；必要时内部规划步骤。
3) **执行与决策记录**：

   - 代码/文档修改同步在对应技能目录下完成。
   - 涉及重要取舍或涌现任务，写入 `DECISIONS.md`（说明背景、方案、理由）。
4) **更新文档**：

   - 变更：`CHANGELOG.md` 按类别记录。
   - 任务：完成项在 `TASKS.md` 勾选，新增子任务时及时登记。

## 写作与输出要求

- SKILL.md 使用祈使/不定式语气，明确何时触发、如何操作。
- 引用具体文件请使用相对路径（示例：`med-extract/SKILL.md`），避免粘贴大段内容。
- 发现矛盾或缺失要显式提示（如"缺少出院时间，需补充"）。

### CHANGELOG.md 格式规范

- **版本号规则**：

  - 测试版本（`test/` 目录）：使用 `0.x.x` 版本号
  - 正式版本（根目录）：使用 `1.x.x` 版本号
  - 禁止使用 `Unreleased` 作为版本号
- **版本记录格式**：

  ```markdown
  ## [版本号] - YYYY-MM-DD

  ### 新增
  - 新功能描述

  ### 改进
  - 优化内容描述

  ### 技术优化
  - 技术改进描述

  ### 待办事项
  - 后续计划描述
  ```
- **分类标签**：使用 `新增`、`改进`、`修复`、`技术优化`、`文档完善` 等分类
- **内容要求**：明确说明变更的性质、影响和原因，避免模糊描述
- **文件格式**：确保文件以单个换行符结尾

### 迁移类 Skill 的版本历史保留规范

当 Skill 从现有 Command 或提示词迁移而来时，应保留原有版本历史以支持完整追溯：

- **保留场景**：Skill 从 `/illustrate`、`/extract-course` 等 Command 转换，或从其他已维护的提示词迁移而来
- **保留要求**：

  - 在 CHANGELOG 底部添加「原始版本记录（Command 时期）」或类似章节
  - 保留完整的版本迭代历史，从 v1.0 到迁移前的最后一个版本
  - 每个版本记录日期和变更摘要，确保历史可追溯
- **格式示例**：

  ```markdown
  ## 原始版本记录（Command 时期）

  ### v3.0.3 (2025-12-28)
  - 强化逻辑性动态效果优先：明确箭头绘制动画和虚线框流动动画为最高优先级

  ### v3.0 (2025-12-28)
  - 重大升级：引入动态 SVG 效果，支持角色浮动动画、虚线框流动、指向性线条动画等

  ### v1.0 (2025-10-27)
  - 初版命令框架，确立基本设计原则和流程
  ```
- **版本号延续**：Skill 的正式版本从 v1.0.0 开始，不延续原始 Command 的版本号
- **价值说明**：保留原始版本历史有助于理解功能演进脉络、设计决策依据和潜在问题追溯

## Skill 开发指南

关于 Skill 的目录结构、Frontmatter 元数据、Progressive Disclosure 设计、文档编写最佳实践等详细规范,请参阅 [SKILL-GUIDE.md](./SKILL-GUIDE.md)。

## 多技能协作

- 新增技能：使用 Skill Creator 初始化后，按上述目录约定补齐文档文件。
- 避免跨技能污染：只修改当前技能树内文件，除非明确需要共享资源。

## 安全与合规

- 避免编造事实；无法确认的信息标记"未提及/待补充"。
- 如处理未脱敏材料，提醒用户审查隐私与合规。
- 不执行破坏性命令（如 `git reset --hard`），保持用户未提交的更改。

## Plugin Marketplace 配置规范

### 目录结构

```text
legal-skills/
├── .claude-plugin/
│   └── marketplace.json          # 插件市场主清单
├── mineru-ocr/                   # 技能目录
├── funasr-transcribe/            # 技能目录
└── ...
```

### marketplace.json 格式

位于根目录 `.claude-plugin/marketplace.json`，定义插件集合的元数据和技能列表：

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "legal-skills",
  "version": "1.0.0",
  "description": "面向法律从业者的 Claude Skills 集合",
  "owner": {
    "name": "杨卫薪律师（微信ywxlaw）",
    "email": "ywxlaw"
  },
  "homepage": "https://github.com/cat-xierluo/legal-skills",
  "repository": {
    "type": "git",
    "url": "https://github.com/cat-xierluo/legal-skills.git"
  },
  "bugs": {
    "url": "https://github.com/cat-xierluo/legal-skills/issues"
  },
  "plugins": [
    {
      "name": "skill-name",
      "description": "技能描述",
      "version": "1.0.0",
      "author": {
        "name": "杨卫薪律师（微信ywxlaw）"
      },
      "source": ".claude/skills/skill-name",
      "category": "productivity",
      "tags": ["tag1", "tag2"]
    }
  ]
}
```

### 添加新技能到 Marketplace

1. **更新主清单**：在根目录 `.claude-plugin/marketplace.json` 的 `plugins` 数组中添加技能条目
2. **版本同步**：确保 `plugins` 数组中的 `version` 与技能 `CHANGELOG.md` 中的版本号一致
3. **更新 README**：在根目录 `README.md` 的技能列表中添加新技能

### 版本管理

- **marketplace.json 版本**：反映插件集合的整体版本，重大变更时递增
- **plugins 数组中的版本**：必须与对应技能的 `CHANGELOG.md` 版本号一致
- **版本号规则**：遵循 CHANGELOG.md 规范（测试版 `0.x.x`，正式版 `1.x.x`）

遵循以上约定，确保法律技能在不同 IDE/CLI（含 Claude Code）中可被可靠触发与复用。***

## AGENTS.md 更新规范

**重要**：本规范文件（AGENTS.md）的每次修改都必须同步更新底部的"变更历史"章节。

### 更新流程

1. **修改内容**：在 AGENTS.md 中进行任何修改（新增/修改规范、调整格式等）
2. **更新变更历史**：在"变更历史"表格顶部添加新的版本记录
3. **版本号递增**：根据修改性质递增版本号

### 版本号规则

遵循相同的 CHANGELOG.md 规范：
- **小修改**（格式调整、文字优化）：递增最后一位（如 v1.1.5 → v1.1.6）
- **新增规范**：递增中间一位（如 v1.1.5 → v1.2.0）
- **重大变更**：递增第一位（如 v1.1.5 → v2.0.0）

### 变更历史记录格式

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.1.6 | YYYY-MM-DD | 简要描述本次修改的内容 |

**示例**：

```markdown
| 版本   | 日期       | 更新内容                                                 |
| :----- | :--------- | :------------------------------------------------------- |
| v1.1.6 | 2026-01-23 | 新增 AGENTS.md 更新规范：要求每次修改 AGENTS.md 时同步更新变更历史 |
```

### 自动更新要求

AI 代理在修改 AGENTS.md 时，必须：
1. 检查是否对文件内容进行了实质性修改
2. 如果是，自动在"变更历史"表格顶部添加新记录
3. 递增版本号

## 变更历史

| 版本   | 日期       | 更新内容                                                                                                                              |
| :----- | :--------- | :------------------------------------------------------------------------------------------------------------------------------------ |
| v1.3.5 | 2026-02-13 | 新增"技能级文档"原则：明确 CHANGELOG.md 等文档为技能级别（位于各技能目录下），不创建项目级别文档；用户要求"更新文档"时默认指当前技能的文档 |
| v1.3.4 | 2026-02-08 | 新增版权信息规范：统一所有自研技能 LICENSE.txt 的版权信息为"杨卫薪律师（微信ywxlaw）"，并更新 4 个技能的 LICENSE.txt 文件 |
| v1.3.3 | 2026-02-08 | 更新许可证管理规范：将法律专业应用技能的许可证从 Apache-2.0-NC 更改为 CC BY-NC-SA 4.0（署名-非商业性使用-相同方式共享），更新相关文档和模板 |
| v1.3.2 | 2026-02-08 | 新增许可证管理规范：定义技能许可证分类（法律专业应用使用 Apache-2.0-NC、通用工具使用 MIT）、SKILL.md frontmatter 许可证字段、LICENSE.txt 文件要求和 README.md 许可证列 |
| v1.3.1 | 2026-02-07 | 新增迁移类 Skill 版本历史保留规范：要求从 Command 或提示词迁移的 Skill 在 CHANGELOG 中保留原始版本历史，确保功能演进可追溯 |
| v1.3.0 | 2026-01-30 | 重构文档结构:将 Skill 开发相关内容分离到独立的 SKILL-GUIDE.md 文件,AGENTS.md 聚焦项目协作规范;通过引用链接两个文档 |
| v1.2.0 | 2026-01-30 | 重新设计 Progressive Disclosure 层级:基于官方加载机制,将三级系统扩展为四级(Level 0: Frontmatter, Level 1: 核心文档, Level 2: 支持性文档, Level 3: 可执行资源);新增"文档编写最佳实践"章节;修正技能目录位置说明(`skills/` 目录);优化依赖管理说明,删除反向约束 |
| v1.1.6 | 2026-01-23 | 新增 AGENTS.md 更新规范：要求每次修改 AGENTS.md 时必须同步更新底部的"变更历史"章节；定义版本号递增规则和自动更新要求                   |
| v1.1.5 | 2026-01-23 | 新增 Skill 文档规范：基于官方 Claude Code skills 格式，定义 SKILL.md frontmatter 元数据、description 写作规范、依赖说明格式和 Progressive Disclosure 设计原则 |
| v1.1.4 | 2026-01-22 | 简化依赖管理规范：依赖说明直接写在 SKILL.md 中 |
| v1.1.3 | 2026-01-21 | 强化中文回复要求：将"中文优先"提升为核心原则首位，明确为强制要求而非可选项                                               |
| v1.1.2 | 2026-01-07 | 新增 `CHANGELOG.md` 格式规范：定义版本号规则（测试版 0.x.x、正式版 1.x.x）、版本记录格式、分类标签和内容要求           |
| v1.1.1 | 2026-01-07 | 将 `config/` 纳入按需目录，支持需要配置文件的技能（如 API Token）；配置 archive/ 目录的 git 策略（忽略内容但保留目录） |
| v1.1.0 | 2026-01-07 | 精简文档结构：删除冗余的 `ROADMAP.md` 和 `JOURNAL.md`，保留核心文档 `DECISIONS.md`、`TASKS.md`、`CHANGELOG.md` |
| v1.0.0 | 2026-01-07 | 初始版本，定义法律技能项目的核心协作规范：技能导向、文档即上下文、透明变更、目录约定、标准作业流程及安全合规要求         |
