# 15 - 与 `project-init` 的互补边界

## 一句话结论

`project-init` 做项目脚手架（skills、settings、docs 体系），本 skill 做法律人专属配置（用户级 + 项目级 AGENTS.md）。两者**互补不互替**，检测互不重复。

## 职责对照

| 职责 | `project-init` | 本 skill (`legal-harness-init`) |
|---|---|---|
| 用户级 `AGENTS.md`（`~/.claude/CLAUDE.md` 等） | ❌ 不做 | ✅ 做（法律人设 + 回溯契约 + 工作偏好） |
| 项目级 `AGENTS.md`（`<项目>/AGENTS.md`） | ✅ 做（生成项目协议 + docs 体系） | ✅ 做（叠加法律人设 + 回溯契约 + 法律工作流约束） |
| 项目脚手架（`.claude/.codex/settings/skills/.gitignore`） | ✅ 做 | ❌ 不做 |
| 检测项目类型 | ✅ | ❌（按用户告知/手动选） |
| 安装 skills | ✅ | ❌ |
| 生成 `docs/` 体系（ROADMAP/DECISIONS/CHANGELOG 等） | ✅ | ❌ |
| 生成 `settings.json` / `.gitignore` | ✅ | ❌ |
| 教学 harness 原理 | ❌ | ✅ |
| 法律人专属回溯契约 | ❌ | ✅ |

## 协作点

**已跑过 `project-init` 的项目**：

本 skill 的 detect.sh 检测到 `.claude/skills/` 和 `docs/` 目录存在 → 已跑过 `project-init`。

此时本 skill 只**追加**到项目级 `AGENTS.md`：

- 追加"法律人设 + 回溯契约 + 法律工作流约束"三块
- 不重写已有部分（项目协议、SOP 等）
- 用 `@include` 或 append 而非覆盖

**未跑过 `project-init` 的项目**：

本 skill 主动提示：

```
检测到当前项目未运行过 `project-init`。建议：

1. 先跑 `project-init`：初始化项目脚手架（skills、settings、docs 体系）
2. 再跑本 skill：补法律人专属三块

也可以只跑本 skill，但缺少 `project-init` 的脚手架，后续 `docs/`、`settings.json`、`.gitignore` 需要手动维护。
```

不强制——用户可选择"先跑本 skill 再补 `project-init`"或"两个都跑"。

## 用户级与项目级的协作

`project-init` 只做项目级，不做用户级。本 skill 同时做两层：

- **用户级**（一次性、跨项目稳定）：本 skill 独占
- **项目级**（每个项目不同）：本 skill 与 `project-init` 协作

用户级 M1-M5 完全独立，不依赖 `project-init`。
项目级 M6-M8 + M5 细化依赖 `project-init` 创建的目录结构（如果跑过）。

## 检测逻辑

`scripts/detect.sh` 检测项目级 `AGENTS.md` 和 `project-init` 痕迹：

```bash
# 检测 project-init 是否跑过
[ -d ".claude/skills/" ] && [ -d "docs/" ] && project_init_ran=true
```

返回结构化 JSON 后，agent 决定：

- 已跑过 → 只 append 法律人三块
- 未跑过 → 提示用户先跑 `project-init`

## 写入策略

**已跑过 `project-init`**：

```
项目级 AGENTS.md 现状（project-init 生成的）：
- 项目协议
- SOP
- ...

本 skill 追加（在文末）：
---

# 法律人设

（来自用户级 M1 摘要）

# 工作流约束

（M2/M4/M3 摘录）

# 回溯契约

（M5 用户级 + 项目级细化）
```

**未跑过 `project-init`**（用户选择直接用本 skill）：

```
项目级 AGENTS.md（本 skill 生成的完整版）：
- 法律人设（M1 摘要）
- 工作流约束（M2/M3/M4）
- 回溯契约（M5 用户级 + 项目级细化）
- 项目上下文（M6）
- 项目关键事实（M7）
- 文件结构（M8）
- 项目级回溯补充（M5 细化）
```

## 顺序建议

```
1. 第一次使用本 skill：先做用户级（M1-M5）
2. 新项目开工：
   a. 先跑 `project-init`（如果有项目脚手架需求）
   b. 再跑本 skill 项目级（M6-M8 + M5 细化）
```

不强制，但这个顺序最舒服：用户级一次性配好跨项目稳定部分；每个新项目用 `project-init` 起步 + 本 skill 补法律人专属。

## 与其他 skill 的关系

| Skill | 关系 |
|---|---|
| `project-init` | 互补不互替（详见上文） |
| `new-case` | 互补——`new-case` 做目录模板，本 skill M8 推荐使用 |
| `legal-ocr` | 独立——`legal-ocr` 做 OCR，本 skill 不涉及 |
| `legal-case-analysis` / `contract-copilot` 等业务 skill | 独立——这些是业务侧，本 skill 做配置 |

## 接下来读什么

- 完整参考范例（5 类律师的 AGENTS.md 写法）→ [references/17-examples/](17-examples/)
- FAQ（含错误处理、跨平台同步冲突）→ [references/16-faq.md](16-faq.md)