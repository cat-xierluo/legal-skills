# 01 - 为什么 AGENTS.md 是最重要的一句话

## 一句话结论

AGENTS.md / CLAUDE.md 是每次 agent session 启动时读的第一段文本。**它发给 agent 的，比你这一轮输入的 prompt 更重要**——因为它决定了所有后续会话的默认行为。

## 为什么很多人用不好 AI

大多数法律人用 AI 卡在同一点：**每次开会话都要从头交代**。

- "我是律师"
- "我做合同审查"
- "不要替我下结论"
- "按这个格式输出"

这些信息每次重复，又每次漏掉一些。然后你得出结论："AI 不懂我"、"AI 不靠谱"。

**问题不在 AI，在配置**。你从来没把它持久化过。

## 持久化的两个层次

法律人最常做的两类工作：

| 层次 | 文件 | 何时生效 | 谁负责 |
|---|---|---|---|
| 用户级 | `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` | 你本机所有项目、所有 session 都生效 | 你自己 |
| 项目级 | `<项目>/AGENTS.md` / `<项目>/CLAUDE.md` | 仅在该项目目录下生效 | 项目负责人 |

**用户级**写"我是谁、我做什么、怎么协作"——一次性配好，跨项目稳定。
**项目级**写"这个项目是什么、关键事实、特殊约束"——每个新案件/项目单独配。

## 不写 AGENTS.md 会怎样

不写不致命，但会有持续成本：

- 每次 prompt 开头都要重复角色交代（30 秒 × 100 次会话 = 50 分钟）
- agent 不知道你的偏好，会按通用模型默认输出（你要反复纠偏）
- agent 不知道你的禁区，可能替你做你不希望的事（即使你事后纠正，也已经发生）
- 关键工作没留痕，事后追责、复盘都缺依据（**这一点对法律人尤其致命**——见 [references/06-audit-trail-contract.md](06-audit-trail-contract.md)）

## 写了 AGENTS.md 之后

写对一份 AGENTS.md 后，变化是明显的：

- agent 知道你是谁——不再需要每次交代角色
- agent 知道你的工作流——直接产出符合你习惯的格式
- agent 知道你的禁区——不会替你做你不希望的事
- agent 知道留痕规则——关键工作自动落到 `CHANGELOG.md` / `DECISIONS.md` / `TASKS.md`
- 团队成员共用同一份 AGENTS.md——协作基线一致

## 写一份好 AGENTS.md 的成本

- **用户级**：5-10 个问答，10-15 分钟一次，**一劳永逸**
- **项目级**：8-15 个问答，15-30 分钟一次，每个新案件/项目配一次

**对比**：不写的成本是每个会话 30-60 秒 × 100+ 次会话，且效果持续劣化。

## 接下来读什么

- 不清楚用户级 vs 项目级 → [references/02-user-vs-project-level.md](02-user-vs-project-level.md)
- 不知道怎么检测自己装了哪些 harness → [references/03-harness-detection.md](03-harness-detection.md)
- 想直接开始配 → [references/04-modules.md](04-modules.md)（8 模块全览）
- 想知道法律人专属的"回溯契约"是什么 → [references/06-audit-trail-contract.md](06-audit-trail-contract.md)