---
name: legal-harness-init
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.2.0"
license: MIT License - 详见 LICENSE.txt
description: |
  法律人专属的 harness 初始化工具：帮法律人理解"AGENTS.md/CLAUDE.md 是发给 agent session 的最重要的一句话"这件事，并直接帮他生成、写入对应的 AGENTS.md 文件（用户级 + 项目级）。本技能应在用户说"配置 AGENTS.md / 配置 CLAUDE.md / 帮我初始化 agent / 怎么配 harness / 我不会用 AI 怎么开始 / 帮我写 AGENTS.md / 给我讲讲怎么跟 AI 协作"时使用。不要用于：业务侧工作（合同审查、案件分析、文书起草）、project-init 的项目脚手架、skill 内容开发。
---

# Legal Harness Init

法律人专属的 AGENTS.md 配置工具：**教学底座 + 生成入口**。

- **教学底座**：`references/` 16 个章节 + 5 套参考范例，讲清为什么 AGENTS.md 重要、用户级 vs 项目级怎么分、8 模块是什么、法律人专属的"回溯契约"怎么写、按法律工作流怎么落地。
- **生成入口**：检测**当前 runtime**（你这次会话正跑在哪个 harness）+ **所有已装平台**，按"先用户级、后项目级"顺序引导你产出 AGENTS.md 内容，再用 `scripts/write.sh` **自动写入**对应平台位置（带 `.bak` 备份 + diff 确认）。自动写入覆盖 CC / Codex / OpenClaw / MyAgents；QoderWork / QwenWork / WorkBuddy / Orca 检测到但因非 AGENTS.md 模式仅提示手动。

**核心理念**：不给你 5 套"标准答案"让你套，而是教你怎么"想清楚自己的维度"，让你和 agent 一起拼装出真正贴合你的 AGENTS.md。法律工作的多样性远超模板能覆盖的范围。

**与 `project-init` 的关系**：互补不互替。`project-init` 做项目脚手架（skills、settings、docs 体系），本 skill 做法律人专属配置（用户级 AGENTS.md + 项目级 AGENTS.md 中的法律人设/回溯契约/工作流约束）。两者检测互不重复，已跑过 `project-init` 的项目本 skill 只补法律人专属三块。

## 适用场景

1. 第一次用 AI 协作的法律人——不知道 AGENTS.md 是什么、写在哪、为什么重要。
2. 有 AI 使用经验但配置混乱的律师——工作偏好散落在每次 prompt 里，没沉淀。
3. 新接案件/项目——需要把当前案件/项目的特定上下文（案号/委托人/阶段）沉淀到项目级 AGENTS.md。
4. 律所技术对接人/团队 lead——想给团队成员配置统一基线。

不适用场景：

- 业务侧工作（合同审查、案件分析、文书起草、检索）——用对应业务 skill。
- 项目脚手架、.claude/.codex/settings/skills/docs 体系初始化——用 `project-init`。
- skill 内容开发、代码生成——用其他 skill。

## 触发方式

### 自然语言触发

- "帮我配置 AGENTS.md"
- "配置 CLAUDE.md"
- "帮我初始化 agent"
- "怎么配 harness"
- "我不会用 AI，怎么开始"
- "帮我写 AGENTS.md"
- "给我讲讲怎么跟 AI 协作"
- "我的项目怎么配 agent"

### 参数化触发

| 参数 | 必需 | 说明 | 示例 |
|------|------|------|------|
| `--level` | 否 | 用户级 (`user`) 还是项目级 (`project`) | `user` / `project` |
| `--platforms` | 否 | 限定写入的 harness 平台（默认 = 当前 runtime + 所有可写已装平台） | `claude-code,codex` |
| `--preset` | 否 | 项目类型预设（项目级时） | `litigation` / `transactional` / `ip` / `in-house` / `research` |
| `--mode` | 否 | 写入模式，透传 `scripts/write.sh`（`create` 已存在则等确认 / `update` 备份后覆盖 / `append` 备份后追加） | `create` / `update` / `append` |
| `--dry-run` | 否 | 只展示 diff 不落盘（透传 write.sh） | — |
| `--force` | 否 | 已存在时不等确认，直接备份+覆盖（透传 write.sh） | — |

## 工作流程

### 第零步：环境检测

调 `bash scripts/detect.sh` 一次性扫描：

- **当前 runtime**：这次会话正跑在哪个 harness（通过 env 标志变量推断，如 `CLAUDECODE`）
- **所有已装 harness**（8 平台）：CC / Codex / OpenClaw / MyAgents / QoderWork / QwenWork / WorkBuddy / Orca，每平台报 `config_kind`（`claude_md` / `agents_md` / `non-agents-md`）和配置文件是否存在、行数
- 当前 cwd 是否有 `AGENTS.md` / `CLAUDE.md`
- 当前 cwd 是否已经跑过 `project-init`（探测 `.claude/skills/`、`docs/` 是否存在）

**隐私边界**：detect.sh 读取目录存在性 + 文件行数（`[ -d ]` + `wc -l`），以及**已知 harness 的 runtime 标志变量是否存在**（`CLAUDECODE` / `CODEX_HOME` / `ORCA_AGENT_HOOK_TOKEN` 等，只看"是否 set"，**不读变量值**）。**不读** `.env` / 凭证 / token / 用户名 / 密钥的值，不读取配置文件内容。详见 [references/03-harness-detection.md](references/03-harness-detection.md) §"检测脚本的隐私边界"。

返回结构化 JSON（schema v2），让 agent 决定后续怎么走。

### 第一步：问候与定位

告诉用户：

1. 本 skill 是做什么的（教学底座 + 生成入口）
2. AGENTS.md 为什么重要（引用 [references/01-why-agents-md-matters.md](references/01-why-agents-md-matters.md)）
3. 检测到了哪些 harness，会写入哪些位置
4. 默认走"先用户级、后项目级"流程；用户可单独选用户级或项目级

### 第二步：选层级

问用户：

- **用户级**（一次性、跨项目稳定）：包含 5 个模块（M1-M5）—— 角色身份 / 工作流与产出 / 协作偏好 / 工具链与禁区 / **回溯契约**。预计 5-10 个问答。
- **项目级**（每个案件/项目不同）：包含 4 个模块（M6/M7/M8 + M5 细化）。预计 8-15 个问答，问题按所选项目类型动态调整。
- **两个都做**（推荐）：先用户级，完成后再项目级。

### 第三步：用户级流程（按 M1→M5 顺序）

按 [references/04-modules.md](references/04-modules.md) 走 5 个模块，每个模块 1-3 个引导问答：

| 模块 | 答什么 | 引用 |
|---|---|---|
| M1 角色身份 | 你的角色？主要业务方向？执业地域？ | [references/07-module-role.md](references/07-module-role.md) |
| M2 工作流与产出 | 你最常做的几类工作？产出什么文档？ | [references/08-module-workflow.md](references/08-module-workflow.md) |
| M3 协作偏好 | 详尽 vs 简洁？批注 vs 修订？中英文？ | [references/09-module-collab-style.md](references/09-module-collab-style.md) |
| M4 工具链与禁区 | 允许/禁止的工具？必须人工复核的动作？红线？ | [references/10-module-toolchain-redlines.md](references/10-module-toolchain-redlines.md) |
| **M5 回溯契约** ⭐ | 是否开启（默认开）→ 勾选通用触发场景 | [references/06-audit-trail-contract.md](references/06-audit-trail-contract.md) + [references/11-module-audit-trail.md](references/11-module-audit-trail.md) |

**引导策略**：每个模块问完后，agent 必须用 1-2 句话讲清这个模块是什么、为什么需要（教学底座作用）。用户在某模块卡壳时，agent 主动调出 [references/17-examples/](references/17-examples/) 对应类型范例作参考，**不直接套用**。

### 第四步：项目级流程（按 M6→M7→M8→M5 细化）

| 模块 | 答什么 | 引用 |
|---|---|---|
| M6 项目上下文 | 什么类型（诉讼/非诉/知产/法务/研究）？编号？委托人？当前阶段？ | [references/12-module-project-context.md](references/12-module-project-context.md) |
| M7 案件/项目关键事实 | 按所选项目类型动态问 | [references/13-module-case-facts.md](references/13-module-case-facts.md) + [templates/modules/M7-case-facts.md](templates/modules/M7-case-facts.md) |
| M8 文件结构约定 | 用什么目录模板？命名约定？哪些文件不进版本？ | [references/14-module-file-structure.md](references/14-module-file-structure.md) |
| M5 项目级细化 | 本项目有没有特殊的回溯要求（叠加用户级总开关）？ | [references/11-module-audit-trail.md](references/11-module-audit-trail.md) |

**M7 动态问法**：按 [templates/modules/M7-case-facts.md](templates/modules/M7-case-facts.md) 动态展开；该文件含 5 种项目类型（诉讼 / 非诉合同 / 知产 / 企业法务 / 法律研究）的完整问法 + 答案片段 + 脱敏范例，是 agent 的真值源。SKILL.md 不重复。

**与 `project-init` 协作**（关键）：

- 已跑过 `project-init`（detect.sh 检测到 `.claude/skills/` 和 `docs/`）→ 只补"法律人设 + 回溯契约 + 法律工作流约束"三块到现有 `AGENTS.md`，不重写其他部分。
- 未跑过 → 提示用户"建议先跑 `project-init` 初始化项目脚手架"，但仍可先生成"法律人设 + 回溯契约"的核心三块（项目级其余部分后续由 `project-init` 补齐）。

### 第五步：拼装与预览

按 [references/05-write-an-agents-md.md](references/05-write-an-agents-md.md) 的固定模板拼装：

```
# {M1 角色摘要}

## 工作流与产出
{M2 内容}

## 协作偏好
{M3 内容}

## 工具链与禁区
{M4 内容}

## 回溯契约
{M5 内容}

---

# 项目：{M6 项目类型 + 编号}

## 上下文
{M6 内容}

## 关键事实
{M7 内容}

## 文件结构
{M8 内容}

## 项目级回溯补充
{M5 项目级细化内容}
```

**先展示完整预览**给用户确认，再写入文件。

### 第六步：写入与覆盖处理

把第五步拼装好的内容存成临时文件，调 `bash scripts/write.sh` 自动写入检测到的可写平台：

```bash
bash scripts/write.sh \
  --content-file <第五步生成的内容文件> \
  --level <user|project> \
  --mode <create|update|append>      # 默认 create
  # 可选：--platforms <key,key>  --dry-run  --force  --project-dir <path>
```

**写入目标**（权威表见 [scripts/lib_platforms.sh](scripts/lib_platforms.sh)）：

| 平台 | config_kind | 用户级写入 | 项目级写入 | 自动写入? |
|---|---|---|---|---|
| Claude Code | claude_md | `~/.claude/CLAUDE.md` | `<cwd>/CLAUDE.md` | ✅ |
| Codex | agents_md | `~/.codex/AGENTS.md` | `<cwd>/AGENTS.md`（项目真值源） | ✅ |
| OpenClaw | agents_md | `~/.openclaw/AGENTS.md` | `<cwd>/AGENTS.md` | ✅ |
| MyAgents | claude_md | `~/.myagents/CLAUDE.md` | `<cwd>/CLAUDE.md` | ✅ |
| QoderWork / QwenWork / WorkBuddy / Orca | non-agents-md | — | — | ❌ 检测到但提示手动 |

**多平台项目级策略**：项目内 `AGENTS.md`（Codex 真值源）+ `CLAUDE.md`（CC/OpenClaw/MyAgents 读）。CC 的 `CLAUDE.md` 可独立写或用 `@include ./AGENTS.md` 共享——多平台时建议后者，单一维护。

**幂等与冲突**（write.sh 自动处理，语义见 [references/16-faq.md](references/16-faq.md)）：

- **检测不到任何可写 harness** → write.sh 退出码 1，提示安装 CC / Codex 等之一。
- **目标已存在 + `--mode create` + 非 `--force`** → 备份 + 展示 diff，记 `needs_confirmation`；用户决定后用 `--force` 覆盖或 `--mode append` 追加。
- **`--mode update` 或 `--force`** → 备份 `.bak.<ts>` 后覆盖（`cp -p` 保留时间戳）。
- **`--mode append`** → 备份后追加（含 `---` 分隔）。
- **目标不存在** → 直接写（用户级 `umask 077` 保护隐私；项目级 `umask 022`）。
- **非 AGENTS.md 模式平台** → 记 `unsupported`，提示用户手动配置。
- **用户中途放弃** → 不调 write.sh，内容保留在临时文件供下次接续。

### 第七步：报告与下一步

输出：

- 已写入的文件清单（按平台）
- 已生成但未写入的内容备份位置（如有）
- 下一步建议（用户级完成后可做项目级 / 已跑过 `project-init` 提示补项目级法律块 / 等）

### 第八步：增量更新模式（已存在 AGENTS.md 时）

detect.sh 检测到 AGENTS.md / CLAUDE.md **已存在**，自动进入增量更新模式（**不重写已有内容**）：

| 场景 | 默认动作 | 升级路径 |
|---|---|---|
| 用户级文件已存在 | 仅展示**新增的 M1-M5 内容**与现有 diff，让用户决定追加/覆盖/合并 | 用户选"完整重写"才走原六步流程 |
| 项目级 AGENTS.md 已存在、不含"回溯契约" | 提示"建议只追加法律人三块（M5+M6+M7+M8）"，默认 append | 用户可手动选"合并到指定 section" |
| 项目级 AGENTS.md 已存在且含回溯契约 / 法律人设 | 进入"差异分析"模式：逐模块比对已有与本 skill 引导内容，标红"建议更新 / 可保留 / 冲突" | 用户选择性更新需要的模块 |
| 检测到 `project-init` 痕迹（`.claude/skills/`、`docs/`） | 同上一行——只 append 三块，不动项目脚手架 | 由 `project-init` 处理通用脚手架 |

**关键原则**：本 skill 绝不主动覆盖用户已有内容。所有"首次生成"路径都必须经过"已存在"分支判断。

## 依赖

无外部依赖。仅使用 shell 标准工具（`bash`、`grep`、`stat`、`wc`）。

## 参考文档

教学底座在 `references/` 目录，按需读取：

| 章节 | 内容 |
|------|------|
| [references/01-why-agents-md-matters.md](references/01-why-agents-md-matters.md) | 为什么 AGENTS.md 是最重要的一句话 |
| [references/02-user-vs-project-level.md](references/02-user-vs-project-level.md) | 用户级 vs 项目级：为什么分两层 |
| [references/03-harness-detection.md](references/03-harness-detection.md) | 怎么检测当前环境有哪些 harness |
| [references/04-modules.md](references/04-modules.md) | 8 模块全览：每个模块答什么、为什么需要 |
| [references/05-write-an-agents-md.md](references/05-write-an-agents-md.md) | 一份好 AGENTS.md 的结构与原则（顺序、详略、风格） |
| [references/06-audit-trail-contract.md](references/06-audit-trail-contract.md) | ⭐ 回溯契约机制（核心 section） |
| [references/07-module-role.md](references/07-module-role.md) | M1 角色身份深度讲解 |
| [references/08-module-workflow.md](references/08-module-workflow.md) | M2 工作流与产出深度讲解 |
| [references/09-module-collab-style.md](references/09-module-collab-style.md) | M3 协作偏好深度讲解 |
| [references/10-module-toolchain-redlines.md](references/10-module-toolchain-redlines.md) | M4 工具链与禁区深度讲解 |
| [references/11-module-audit-trail.md](references/11-module-audit-trail.md) | M5 回溯契约深度讲解（与 §06 联动） |
| [references/12-module-project-context.md](references/12-module-project-context.md) | M6 项目上下文深度讲解 |
| [references/13-module-case-facts.md](references/13-module-case-facts.md) | M7 案件/项目关键事实深度讲解（含 5 种问法） |
| [references/14-module-file-structure.md](references/14-module-file-structure.md) | M8 文件结构约定深度讲解 |
| [references/15-sync-with-project-init.md](references/15-sync-with-project-init.md) | 与 `project-init` 的互补边界 |
| [references/16-faq.md](references/16-faq.md) | 常见问题（含错误处理） |
| [references/17-examples/](references/17-examples/) | 5 套完整参考范例（教学用，不直接套用） |

## 模块片段库

`templates/modules/` 提供每个模块的"常见答案片段"，agent 在用户卡壳时主动调出参考：

| 文件 | 内容 |
|------|------|
| [templates/modules/M1-role.md](templates/modules/M1-role.md) | 角色身份片段（含多种角色答案） |
| [templates/modules/M2-workflow.md](templates/modules/M2-workflow.md) | 工作流与产出片段 |
| [templates/modules/M3-collab-style.md](templates/modules/M3-collab-style.md) | 协作偏好片段 |
| [templates/modules/M4-toolchain-redlines.md](templates/modules/M4-toolchain-redlines.md) | 工具链与禁区片段 |
| [templates/modules/M5-audit-trail.md](templates/modules/M5-audit-trail.md) | ⭐ 回溯契约片段（核心） |
| [templates/modules/M6-project-context.md](templates/modules/M6-project-context.md) | 项目上下文片段 |
| [templates/modules/M7-case-facts.md](templates/modules/M7-case-facts.md) | 案件/项目关键事实片段（含 5 种类型问法） |
| [templates/modules/M8-file-structure.md](templates/modules/M8-file-structure.md) | 文件结构约定片段 |

## 输出验证

完成引导后，确认：

- [ ] 用户级 5 个模块（M1-M5）全部有内容，无空模块
- [ ] M5 回溯契约已开启（除非用户明确关闭）
- [ ] 项目级 4 个模块（M6/M7/M8 + M5 细化）按需填写
- [ ] 写入前已展示完整预览给用户确认
- [ ] 已写入的文件按检测到的平台逐个覆盖/合并/追加
- [ ] 写入后报告已写入文件清单 + 下一步建议

## 禁止事项

- 禁止跳过教学引导直接生成（失去"教学底座"价值）
- 禁止替用户回答（用户必须自己说出偏好和限制）
- 禁止直接套用 `references/17-examples/` 范例（只作参考）
- 禁止替用户做实质性法律判断、案件分析、文书起草（用对应业务 skill）
- 禁止主动覆盖用户已有的 `AGENTS.md` / `CLAUDE.md`（必须展示 diff 让用户决定）
- 禁止在 M5 默认开启回溯契约时替用户决定具体触发场景（必须让用户勾选）
- 禁止第八步自动覆盖用户已有内容；用户明确选"完整重写"才走原首次生成流程