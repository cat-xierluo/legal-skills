# 16 - FAQ（含错误处理）

## 用户级相关

**Q：我已经有 `~/.claude/CLAUDE.md` 了，会被覆盖吗？**

A：不会。本 skill 检测到文件已存在时，会展示完整 diff 让用户决定覆盖/合并/追加。默认不覆盖。

**Q：用户级和项目级 AGENTS.md 内容有重叠怎么办？**

A：用户级写跨项目稳定的内容，项目级写本项目特定的内容。如果有重叠（如角色身份），项目级可以引用用户级（`@include` 或注释说明）。

**Q：可以只做用户级不做项目级吗？**

A：可以。用户级是独立的（一劳永逸），项目级是按需（新项目开工时再做）。

**Q：可以只做项目级不做用户级吗？**

A：可以，但不推荐。没有用户级，每次项目级都从零开始，工作流偏好每次重复。

## 项目级相关

**Q：项目级 AGENTS.md 应该写在哪里？**

A：项目根目录的 `AGENTS.md`（或 `CLAUDE.md` 配合 `@include`）。

**Q：项目已经跑过 `project-init`，AGENTS.md 已存在怎么办？**

A：本 skill 检测到后只追加法律人三块，不重写已有内容。展示 diff 让用户确认。

**Q：项目级 AGENTS.md 没有"回溯契约"段落怎么办？**

A：这是常见情况——很多项目跑过 `project-init` 但没加法律人专属。本 skill 检测后会建议追加。

**Q：项目中途修改了关键事实（如对方当事人变更），AGENTS.md 怎么处理？**

A：手动更新 AGENTS.md 的 M7 段，并在 `docs/DECISIONS.md` 写变更记录（这正是回溯契约要求的动作）。

## Harness 与平台相关

**Q：我同时用 Claude Code 和 Codex，怎么处理？**

A：本 skill 检测到两个平台就同时写：

- 用户级：`~/.claude/CLAUDE.md` 和 `~/.codex/AGENTS.md` 分别写
- 项目级：项目内一份 `AGENTS.md` 作为真值源；CC 的 `CLAUDE.md` 通常 `@include ./AGENTS.md`

**Q：我装了一个新平台（如 OpenClaw），要重新跑本 skill 吗？**

A：不用。可以单独针对新平台再跑一次，本 skill 会补写新平台的文件，不影响已有平台。

**Q：CC 的 `CLAUDE.md` 和 Codex 的 `AGENTS.md` 内容不一样怎么办？**

A：本 skill 给每个平台生成等价但适配格式的内容（每个平台语法差异）。展示差异让用户确认。

**Q：`detect.sh` 返回检测不到任何平台怎么办？**

A：本 skill 会提示用户先安装 Claude Code / Codex 等之一，然后退出。不会强行写入（无意义）。

## 回溯契约相关

**Q：回溯契约开启后，每个动作都要写吗？**

A：不是。只写"关键动作"——会影响后续决策、会承担法律责任、需要向第三方披露的。日常工具调用、agent 自己的推理不需要写。

**Q：写入 DECISIONS/CHANGELOG/TASKS 的格式是什么？**

A：参考 [references/06-audit-trail-contract.md](06-audit-trail-contract.md) §"三个留痕目的地"段。每个文件有不同的字段要求。

**Q：M5 关闭了会怎样？**

A：AI 做了关键动作不会自动留痕。**法律工作强烈不建议关闭**。

**Q：写入 DECISIONS 之前，文件不存在怎么办？**

A：agent 会提示用户先创建（或 agent 创建空模板，按项目约定）。

## 错误处理

| 错误情况 | 处理 |
|---|---|
| 检测不到任何 harness | 提示安装，退出 |
| 用户级文件已存在且非空 | 展示 diff 让用户决定覆盖/合并/追加，默认不覆盖 |
| 项目级 AGENTS.md 已存在但不含回溯契约 | 提示"建议只追加法律人三块"，默认 append |
| 项目级 AGENTS.md 已存在且含法律人设 | 提示"是否更新模块配置/回溯契约"，进入更新模式 |
| 用户中途放弃 | 不写任何文件，保留已完成问答供下次接续 |
| 跨平台同步冲突 | 用户级各平台独立写，写入前展示差异，由用户确认 |
| 项目目录无写权限 | 提示用户检查权限，退出 |
| `detect.sh` 执行失败 | 提示错误信息，建议手动检查 harness 安装 |

## 重新生成 vs 增量更新

**首次生成**：用户从未配过 AGENTS.md，按 M1-M5 / M6-M8 顺序引导生成完整内容。

**增量更新**（已有 AGENTS.md）：检测到 AGENTS.md 已存在：

- 比对已有内容与本 skill 引导内容
- 提示"已检测到 X 模块，建议更新/补充哪些"
- 用户选择性更新需要的模块
- 不重写未变化的模块

## 与 `project-init` 的协作

**Q：我先跑了 `project-init`，还能用本 skill 吗？**

A：可以，本 skill 检测到后会只补法律人三块。

**Q：我先跑了本 skill，再跑 `project-init`，会不会冲突？**

A：`project-init` 会生成项目协议和 docs 体系，但通常不会覆盖已有的 AGENTS.md 的法律人三块。建议顺序：`project-init` → 本 skill。

**Q：两个都跑了，发现 AGENTS.md 有重复内容怎么办？**

A：手动整合，或重跑本 skill 让它合并。

## 维护与更新

**Q：多久更新一次 AGENTS.md？**

A：参考 [references/05-write-an-agents-md.md](05-write-an-agents-md.md) §"维护原则"段。

- 每会话：看是否有新禁区要加
- 每月：检查 M5 触发场景
- 每季度：检查 M4 工具链
- 每年：全量复盘用户级 AGENTS.md

**Q：用户身份变了（如换城市/换业务方向）怎么办？**

A：手动更新 M1，重新跑本 skill 检测。

**Q：项目归档（结案）后，AGENTS.md 怎么处理？**

A：项目归档后项目级 AGENTS.md 通常不再修改，保留作为复盘资料。如果项目结案且不再需要 agent 协作，可以删除项目级 AGENTS.md（或归档目录）。

## 接下来读什么

- 完整参考范例（5 类律师）→ [references/17-examples/](17-examples/)
- 模块片段库（用户卡壳时的参考片段）→ [templates/modules/](templates-modules)