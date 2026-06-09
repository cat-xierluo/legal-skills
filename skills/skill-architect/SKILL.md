---
name: skill-architect
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.6.1"
license: MIT
description: 技能架构师与格式审查一体化工具，整合官方 skill-creator 流程、原 skill-lint 合规检查和发布规范同步。本技能应在用户需要创建新技能、编辑现有技能、打包技能、审查 skill 格式合规性、检查 Frontmatter/版本/文档一致性、生成技能审计报告时使用。不要用于：创建非 Claude Code 技能、代码审查、功能测试、通用编程任务。
---

# Skill Architect

基于官方 skill-creator 的增强版技能架构师向导，统一承接原 `skill-lint` 审查能力，内置合规检查规则，支持两种使用模式。

兼容旧称：用户提到 `skill-lint` 时，按本技能的审查模式处理。

## 使用模式

### 模式一：创建模式

创建新技能时使用，遵循以下流程：

1. 理解技能需求（收集具体示例）
2. 规划可复用资源（scripts/, references/, assets/）
3. 初始化技能（创建目录结构）
4. 编辑技能（实现资源 + 编写 SKILL.md）
5. 合规性检查（内置检查规则）
6. 迭代（基于使用反馈改进）

### 模式二：审查模式（原 skill-lint）

审查现有技能的合规性时使用：

1. 指定要审查的技能路径
2. 扫描目录结构和文件
3. 按检查清单逐项审查
4. 生成结构化审查报告

---

## 模式一：创建模式

## Step 1: 理解技能需求

跳过此步骤的条件：技能的使用模式已经非常清晰。

收集具体的使用示例：

- "这个技能应该支持什么功能？"
- "能给一些具体的使用场景吗？"
- "用户会说什么话来触发这个技能？"

**完成标准**：清楚知道技能的功能边界和触发场景。

---

## Step 2: 规划可复用资源

分析每个使用场景，确定需要的资源：

### 资源类型

| 类型 | 目录 | 用途 | 何时需要 |
|------|------|------|----------|
| 脚本 | `scripts/` | 可执行代码 | 同一代码反复重写时 |
| 参考 | `references/` | 详细文档 | 需要 schema/API 文档时 |
| 资产 | `assets/` | 输出模板 | 需要模板/图标/字体时 |

### 依赖规划

如果技能包含脚本，在此步骤中梳理依赖关系：

1. **列出所有外部依赖**：区分硬依赖（缺了就跑不了）和可选依赖（增强功能）
2. **规划降级策略**：
   - 硬依赖：try/except + 安装提示 + 退出
   - 可选依赖：try/except + 功能标志 + 静默降级
3. **准备 requirements.txt**：只包含硬依赖
4. **规划 SKILL.md 说明位置**：在需要依赖的功能章节内就近放置安装说明

### 目录结构规范

创建时遵循以下结构：

```
skill-name/
├── SKILL.md          # 必需 - 主文档
├── LICENSE.txt       # 推荐 - 许可证
├── references/       # 可选 - 参考文档
├── scripts/          # 可选 - 可执行脚本
└── assets/           # 可选 - 输出资源
```

**禁止创建**：
- `README.md` - 与 SKILL.md 重复
- `docs/` - 应使用 `references/`
- `test/` - 开发文件不应在发布版中
- `__pycache__/` - Python 缓存不应提交
- `.env` - 敏感配置不应提交

---

## Step 3: 初始化技能

创建技能目录和基础文件：

1. 创建技能目录 `<skill-name>/`
2. 创建 `SKILL.md` 并添加 frontmatter
3. 创建 `LICENSE.txt`（推荐）
4. 创建需要的子目录（`scripts/`, `references/`, `assets/`）

---

## Step 4: 编辑技能

### 4.1 Frontmatter 规范

```yaml
---
name: skill-name                    # 小写字母 + 连字符
description: 本技能应在用户需要...时使用。不要用于：...  # 第三人称 + 触发边界
version: "1.0.0"                   # 与 CHANGELOG 最新版本一致
license: MIT                       # 或 CC-BY-NC
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---
```

**description 写作要求**：
- 使用第三人称："本技能应在...时使用"
- 包含触发场景：明确说明何时使用
- 包含负向触发条件："不要用于..."说明边界
- 长度控制在 1024 字符以内
- 不要在 SKILL.md 正文中添加"何时使用"章节

**发布字段要求**：
- `version` 是公开发布推荐字段；如存在，必须与 `CHANGELOG.md` 最新版本一致
- `CHANGELOG.md` 仍是完整版本历史来源
- `homepage` 推荐保留；已有 `homepage` 时不强制 `source`

### 4.2 SKILL.md 内容规范

**保持简洁**：
- 避免大段代码（>20 行应移至 `scripts/`）
- 使用简洁示例，仅展示关键 API 调用
- 聚焦工作流程，说明"做什么"和"怎么做"

**Progressive Disclosure**：
- 核心流程在 SKILL.md 正文中
- 详细文档放在 `references/` 中
- 在 SKILL.md 中引用 references 文件

### 4.3 配置文件规范

**命名规则**：

| 类型 | 格式 | 是否提交 |
|------|------|----------|
| 模板文件 | `*.example.*` | 提交 |
| 实际配置 | `*` | 被 .gitignore 忽略 |

示例：
- `config.example.yaml` → 提交
- `config.yaml` → 忽略
- `.env.example` → 提交
- `.env` → 忽略

### 4.4 输出模式规范

对于需要一致性输出的技能，提供输出格式指导。

**严格模式**（API 响应、数据格式）：

```markdown
ALWAYS use this exact template structure:

# [Analysis Title]

## Executive summary
[One-paragraph overview]

## Key findings
- Finding 1 with supporting data
- Finding 2 with supporting data
```

**灵活模式**（分析报告、创意内容）：

```markdown
Here is a sensible default format, but use your best judgment:

# [Analysis Title]

## Executive summary
[Overview]

Adjust sections as needed for the specific context.
```

### 4.5 工作流模式规范

**顺序工作流**：

```markdown
Filling a PDF form involves these steps:

1. Analyze the form (run analyze_form.py)
2. Create field mapping (edit fields.json)
3. Validate mapping (run validate_fields.py)
4. Fill the form (run fill_form.py)
```

**条件工作流**：

```markdown
1. Determine the modification type:
   **Creating new content?** → Follow "Creation workflow" below
   **Editing existing content?** → Follow "Editing workflow" below

2. Creation workflow:
   - Step 1: ...
   - Step 2: ...
```

### 4.6 技能协作规范

**松耦合原则**：
- 用自然语言描述协作场景
- 说明技能"做什么"和"如何配合"
- 不直接引用其他技能的内部脚本路径
- 不在代码中 import 其他技能的模块

**推荐写法**：

```markdown
## 与其他技能配合

下载的视频可以使用 FunASR 技能转录为带时间戳的 Markdown 文件。
两个技能独立运行，可根据需要灵活组合使用。
```

**避免写法**：

```markdown
## 与其他技能配合

转录时运行：
python ../../skills/funasr-transcribe/scripts/transcribe.py
```

### 4.7 可编排性设计

对于可能参与复杂工作流编排的技能：

**输入/输出声明**：

```markdown
## 输入/输出

### 输入
- 必需：`--input` 参数说明
- 可选：`--flag` 参数说明

### 输出
- 输出文件：`output/path.md` 说明
- 副作用：如创建目录、修改文件等
```

**单一职责**：
- 技能只做一件事
- 避免多任务混合

**幂等性**：
- 多次执行结果相同
- 无累积效应

---

## Step 5: 合规性检查

打包前，按以下检查清单逐项检查：

### 5.1 目录结构

| 检查项 | 状态 |
|--------|------|
| SKILL.md 存在 | ✅/❌ |
| 无 README.md | ✅/⚠️ |
| 无 docs/ 目录 | ✅/⚠️ |
| 无 test/ 目录 | ✅/⚠️ |
| 无 __pycache__/ | ✅/❌ |
| 无 .env 文件 | ✅/❌ |

### 5.2 Frontmatter

| 检查项 | 状态 |
|--------|------|
| name 字段存在且格式正确 | ✅/❌ |
| description 字段存在 | ✅/❌ |
| description 使用第三人称 | ✅/❌ |
| description 包含负向触发条件 | ✅/⚠️ |
| description 长度 ≤ 1024 字符（硬约束） | ✅/❌ |
| description 最佳 ≤ 250 字符（信息密度建议） | ✅/⚠️ |
| version 与 CHANGELOG 最新版本一致 | ✅/⚠️ |
| homepage/author/license 推荐字段完整 | ✅/⚠️ |
| **references/ 子文件无 frontmatter** | ✅/❌ |

### 5.3 SKILL.md 行数

| 检查项 | 状态 |
|--------|------|
| SKILL.md 行数 ≤ 500 行 | ✅/⚠️ |

### 5.4 目录层级

| 检查项 | 状态 |
|--------|------|
| references/ 扁平结构（一级） | ✅/⚠️ |
| scripts/ 扁平结构（一级） | ✅/⚠️ |
| assets/ 扁平结构（一级） | ✅/⚠️ |

### 5.5 文档一致性

| 检查项 | 状态 |
|--------|------|
| 引用的脚本文件存在 | ✅/❌ |
| 引用的参考文档存在 | ✅/❌ |
| 引用的资源文件存在 | ✅/❌ |

### 5.6 配置文件

| 检查项 | 状态 |
|--------|------|
| 模板使用 *.example.* 命名 | ✅/⚠️ |
| example 字段与代码匹配 | ✅/❌ |

### 5.7 技能协作

| 检查项 | 状态 |
|--------|------|
| 不直接引用其他技能路径 | ✅/⚠️ |
| 使用自然语言描述协作 | ✅/⚠️ |

### 5.8 模块化设计

| 检查项 | 状态 |
|--------|------|
| 独立功能解耦到单独脚本 | ✅/⚠️ |
| 跨 skill 不直接调用内部脚本 | ✅/⚠️ |

### 5.9 安全审计

| 检查项 | 状态 |
|--------|------|
| 无硬编码 API keys | ✅/❌ |
| 无危险删除命令（rm -rf ~ 等） | ✅/❌ |
| 删除命令使用安全方式 | ✅/⚠️ |

### 5.10 依赖声明与防护

| 检查项 | 状态 |
|--------|------|
| SKILL.md 声明了依赖（区分开箱即用 vs 需安装功能） | ✅/⚠️ |
| 脚本硬依赖有 try/except + 安装提示 | ✅/❌ |
| 脚本可选依赖有 try/except + 降级标志 | ✅/⚠️ |
| requirements.txt 只包含硬依赖 | ✅/⚠️ |
| 依赖安装说明就近放置（对应功能章节内） | ✅/⚠️ |

### 5.11 references/ 子文件 frontmatter 限制

| 检查项 | 状态 |
|--------|------|
| `references/*.md` 不携带 frontmatter | ✅/❌ |
| 元数据唯一来源 = SKILL.md frontmatter | ✅/❌ |

**为什么**：references/ 是 SKILL.md 引用展开的细节文档，不应重复元数据；重复 frontmatter 会出现"两份描述 / 两份 name"漂移风险。前置扫描命令：

```bash
for f in references/*.md; do
  head -1 "$f" | grep -q "^---$" && echo "FRONTMATTER: $f"
done
```

### 5.12 references/ 命名与 SKILL.md 的概念边界

| 检查项 | 状态 |
|--------|------|
| 文件名反映"具体职责"（`first_use` / `correction_patterns` / `boundaries`） | ✅/⚠️ |
| 避免通用词（`overview` / `guide` / `intro`） | ✅/⚠️ |
| 避免与 `SKILL.md` 概念重叠的命名（`skill_overview` / `skill_intro`） | ✅/⚠️ |

**为什么**：通用词和与 SKILL.md 重叠的命名会让读者误以为"这是另一个主文档"。命名应一眼看出"这一份是干什么的"。

### 5.13 公开内容清洁度

| 检查项 | 状态 |
|--------|------|
| SKILL.md / references/ / CHANGELOG.md / config/*.example.* / DECISIONS.md / TASKS.md 不含其他 skill 名 | ✅/❌ |
| 不含私有工作流项目名 / 自家平台名 | ✅/❌ |
| 涉及上下游协作时使用通用描述 | ✅/❌ |

**反例**：

- "与 course-generator 共用词典格式" → "与其他下游处理工作可按需读取同一份词典文件"
- "funasr 输出的转录稿" → "本地转录引擎 / 云端 ASR 的输出"

**为什么**：公开仓库应只承载"工作流本身"；私有工作流的依赖（其他 skill / 自家平台）一旦入仓就形成"公开耦合"，reviewer 无法判断是真实依赖还是历史遗留。

**判定命令**：

```bash
# 找出所有可能的项目 / skill 名
grep -nE "course[- ]?generator|funasr|tingwu|听悟|xx-skill|其他 skill" SKILL.md references/*.md
```

### 5.14 Git 跟踪状态

| 检查项 | 状态 |
|--------|------|
| SKILL.md / CHANGELOG.md / LICENSE.txt 已 git 跟踪 | ✅/❌ |
| config/*.example.* 已 git 跟踪 | ✅/❌ |
| references/*.md 已 git 跟踪 | ✅/❌ |
| 真实配置（config/*.yaml）已被 .gitignore 覆盖 | ✅/❌ |
| 私有档案（archive/、DECISIONS.md、TASKS.md）已被 .gitignore 覆盖 | ✅/❌ |
| 整个 skill 目录不是 `git status` 中的 `??` 状态 | ✅/❌ |

**为什么**：当 skill 已注册到 `.claude-plugin/marketplace.json` 和 README 但 `git ls-files` 返回空，外部用户 clone 仓库时将看不到任何文件——这是"看起来已发布但实际不存在"的状态。

**判定命令**：

```bash
# 必跑：验证已跟踪文件
git ls-files skills/<skill-name>/ | head -20
# 必跑：验证 .gitignore 覆盖
git check-ignore -v skills/<skill-name>/config/<real-config>.yaml
# 严重警告：整个 skill 目录未跟踪
git status --porcelain skills/<skill-name>/ | grep '^??'
```

### 5.15 CHANGELOG 历史一致性

| 检查项 | 状态 |
|--------|------|
| v1.0.0 段落仅描述"v1.0.0 当下"的能力 | ✅/⚠️ |
| 后续版本能力增量在对应版本段落补写 | ✅/⚠️ |
| 各版本段落不包含"尚未实现"的能力 | ✅/⚠️ |

**反例**：v1.0.0 段落就描述了"源文件目录镜像 / STABLE.md 标记 / 必检清单"等 v1.0.6 才完整的能力——读者从 v1.0.0 段落无法判断"我装的 v1.0.0 是否真有这些能力"。

**为什么**：CHANGELOG 是版本考古文档，应当在每个版本段落忠实反映"该版本发布时的能力"，后续增量在新版本段落补写。

### 5.16 archive/ 内部一致性

| 检查项 | 状态 |
|--------|------|
| archive/ 子目录数 ≥ 5 时 STABLE.md / DECISIONS.md 记录保留策略 | ✅/⚠️ |
| STABLE.md 中的 `[DEC-XXX]` 编号与 DECISIONS.md 实际条目一致 | ✅/⚠️ |
| STABLE.md 内的累计数据（描述行 + 表格行）自洽 | ✅/⚠️ |

**为什么**：archive/ 虽然已被 .gitignore 隔离，但作为技能内部"校对质量的承载体"，其内部一致性影响后续 agent / 下游 skill 读取时的信任度。

### 5.17 description 内容边界（只写三件事）

| 检查项 | 状态 |
|--------|------|
| description 仅含"功能 / 触发 / 不触发"三件事 | ✅/❌ |
| 不含归档 / 输出位置 / 写入策略 | ✅/❌ |
| 不含内部步骤 / 开关状态 / 默认行为 | ✅/❌ |
| 不含产物结构 / 副作用 / 双写策略 | ✅/❌ |

**三件事的内容定义**：

| 段落 | 应回答的问题 | 示例 |
|---|---|---|
| **功能** | 这个 skill 是什么 / 做什么 | "转录稿纠错与轻度优化" |
| **触发** | 什么场景下使用 / 用户说什么会触发 | "本技能应在用户需要...时使用" |
| **不触发** | 什么场景不能用 / 避免误触 | "不要用于：重写、总结、删减、改事实" |

**反例**（不该出现在 description 里）：

| 反例内容 | 为什么不该出现 |
|---|---|
| "结果归档 archive/ 并在源目录同步副本" | 输出策略属于运作细节，挪到 SKILL.md §5 输出阶段 |
| "原始文件保持不动" | 内部行为约束，挪到 SKILL.md 工作流原则 |
| "（默认开启）/ （默认关闭）" | 开关状态属于配置说明，挪到 SKILL.md Phase 说明 |
| "含基础空白清理与口语词精简" | 内部步骤列表，挪到 SKILL.md 概述表 |
| "可选合并同发言人发言" | 可选功能列表，挪到 SKILL.md 概述表 |

**为什么**：description 是触发器的"匹配指纹"——Claude 模型在路由决策时先看 description；触发器越聚焦（含"做什么 / 何时用 / 何时不用"），路由越准。归档策略、默认行为、内部步骤属于"被触发之后怎么工作"，与触发判断无关。

**判定命令**：

```bash
# 找出可能越界的"运作细节"关键词
grep -nE "归档|原始文件|默认开启|默认关闭|默认无损|同步|双写|在.*目录|在.*目录.*副本|输出到" SKILL.md | head -5
```

人工对照 description 文本，确认这些关键词不出现在 frontmatter description 字段里。

**反例案例**：

- transcription-corrector v1.0.7 description（已修正前）："转录稿纠错与轻度优化：按用户词典纠正 ASR 同音字 / 英文专有名称漂移（人名、产品、术语），附基础空白清理与口语词精简（默认开启），可选合并同发言人发言 / 标点规范；原始文件不动，结果归档 archive/ 并在源目录同步副本。" → 含归档策略 / 默认行为 / 内部步骤，已在 v1.0.7 修正版清理。

**问题严重程度**：

| 级别 | 说明 | 处理 |
|------|------|------|
| ❌ 严重 | 阻塞技能正常使用 | 必须修复 |
| ⚠️ 警告 | 影响可维护性 | 建议修复 |

---

## Step 6: 迭代

基于实际使用反馈改进技能：

1. 使用技能处理真实任务
2. 发现困难或效率问题
3. 更新 SKILL.md 或相关资源

---

## 模式二：审查模式（原 skill-lint）

审查现有技能的合规性，生成结构化审查报告。

### 审查流程

1. **指定目标** - 提供要审查的技能路径
2. **扫描文件** - 列出技能目录所有文件
3. **逐项检查** - 按检查清单审查（使用 Step 5 相同规则）
4. **生成报告** - 输出结构化审查结果

### 审查报告格式

```markdown
# [skill-name] 格式审查报告

**审查时间**: YYYY-MM-DD HH:MM
**技能路径**: /path/to/skill

## 审查摘要

| 检查项 | 状态 | 问题数 |
|--------|------|--------|
| 目录结构 | ✅/⚠️/❌ | N |
| Frontmatter | ✅/⚠️/❌ | N |
| SKILL.md 行数 | ✅/⚠️ | N |
| 目录层级 | ✅/⚠️ | N |
| 文档一致性 | ✅/⚠️/❌ | N |
| 配置文件 | ✅/⚠️/❌ | N |
| 技能协作 | ✅/⚠️/❌ | N |
| 模块化设计 | ✅/⚠️ | N |
| 安全审计 | ✅/❌ | N |

## 详细问题

### ❌ 严重问题（必须修复）

1. **[问题标题]**
   - 位置: `文件路径:行号`
   - 规范: 违反的规范条款
   - 建议: 修复建议

### ⚠️ 建议优化

1. **[问题标题]**
   - 位置: `文件路径`
   - 建议: 优化建议

## 审查完成

- 总问题数: N
- 严重问题: N
- 建议优化: N
```

### 审查执行方式

1. 使用 Glob 列出技能目录所有文件
2. 使用 Read 读取 SKILL.md 和关键文件
3. 按 Step 5 检查清单逐项审查
4. 生成结构化审查报告

---

## 规范参考

详细规范标准见 [references/skill-standards.md](references/skill-standards.md)
