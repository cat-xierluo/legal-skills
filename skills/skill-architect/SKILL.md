---
name: skill-architect
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.3.0"
license: CC BY-NC-SA 4.0 - 详见 LICENSE.txt
description: 技能架构师向导与审查工具，整合官方 skill-creator 流程与内置合规检查。本技能应在用户需要创建新技能、编辑现有技能、打包技能、或审查现有技能的格式合规性时使用。不要用于：创建非 Claude Code 技能、代码生成、通用编程任务。
---

# Skill Architect

基于官方 skill-creator 的增强版技能架构师向导，内置合规检查规则，支持两种使用模式：

## 使用模式

### 模式一：创建模式

创建新技能时使用，遵循以下流程：

1. 理解技能需求（收集具体示例）
2. 规划可复用资源（scripts/, references/, assets/）
3. 初始化技能（创建目录结构）
4. 编辑技能（实现资源 + 编写 SKILL.md）
5. 合规性检查（内置检查规则）
6. 迭代（基于使用反馈改进）

### 模式二：审查模式

审查现有技能的合规性时使用：

1. 指定要审查的技能路径
2. 扫描目录结构和文件
3. 按检查清单逐项审查
4. 生成结构化审查报告

---

## 模式一：创建模式

### Step 1: 理解技能需求

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
description: 功能描述。本技能应在...时使用  # 第三人称 + 触发场景
license: CC BY-NC-SA 4.0 - 详见 LICENSE.txt
---
```

**description 写作要求**：
- 使用第三人称："本技能应在...时使用"
- 包含触发场景：明确说明何时使用
- 长度控制在 100 字以内
- 不要在 SKILL.md 正文中添加"何时使用"章节

**禁止字段**：
- `version` - 版本信息应在 CHANGELOG.md 中管理

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
| description 长度 ≤ 1024 字符 | ✅/❌ |
| 无 version 字段 | ✅/⚠️ |

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

## 模式二：审查模式

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
