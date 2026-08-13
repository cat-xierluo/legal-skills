# init-environment 初始化环境受管区块片段库

本片段是 `legal-harness-init` 在被初始化的项目里**自动追加**的元数据表格，目的是将来出问题时能追溯"问题出在 harness 层面还是 model 层面"。**agent 不应手写这个区块**——它的内容由 `scripts/record-init-env.sh` 自动采集并 append。

## 受管区块标识

- block-id：`init-environment`
- start marker：`<!-- legal-harness-init:init-environment:start -->`
- end marker：`<!-- legal-harness-init:init-environment:end -->`
- 位置：建议放在 AGENTS.md 末尾（M8 之后）；不与 M1—M8 顺序冲突

## 字段约定

| 字段 | 来源 | 兜底 |
|---|---|---|
| 时间 | `date '+%Y-%m-%d %H:%M'` | 探测失败时写 `unknown-time` |
| Harness | `detect.sh` 的 `current_runtime`（或 `--harness` 显式覆盖） | 无命中时写 `unknown` |
| Harness Version | 探测 harness 自带 `--version` 命令（2s 超时） | 探测失败时写 `unknown`；非 claude/codex 写 `n/a` |
| Model | env 白名单 `ANTHROPIC_MODEL` / `OPENAI_MODEL` / `CLAUDE_MODEL` / `GLM_MODEL` / `MY_MODEL`（或 `--model` 显式覆盖） | env 全空时 **拒绝 append**（强制 `--model`） |
| Init Skill | 固定为 `legal-harness-init` | — |
| Init Skill Version | 本 skill 根 `SKILL.md` frontmatter `version` 字段 | 探测失败时写 `unknown` |
| 操作 | `--action` 参数：`init` / `update` / `append` | 默认 `init` |

## 由 record-init-env.sh 自动生成的骨架（首次 init 时）

```markdown
<!-- legal-harness-init:init-environment:start -->

| 时间 | Harness | Harness Version | Model | Init Skill | Init Skill Version | 操作 |
|---|---|---|---|---|---|---|
| 2026-08-13 14:30 | claude-code | 1.0.0 | MiniMax-M3 | legal-harness-init | 0.4.0 | init |

<!-- legal-harness-init:init-environment:end -->
```

## 追加行的样例

```markdown
| 2026-08-15 10:00 | claude-code | 1.0.0 | claude-fable-5 | legal-harness-init | 0.4.0 | update · M6 项目级 |
```

## 行为边界

- 区块 append-only；agent 不应在受管区块里手改或删除行。
- 表格超过 50 行时脚本会软提示归档；推荐做法：
  1. 复制当前表格到 `docs/init-environment-history.md`（按年/月归档）
  2. 留下表头 + 末行作为衔接指针
  3. 在区块里保留 N 行作为"近期上下文"
- 用户手动追加（如换 model 没跑 init 想自己记一行）：在 `init · 手动追加` 格式下追加，但建议改用 `bash scripts/record-init-env.sh --model <新 model>` 走标准路径。

## 与现有 M5 回溯契约的关系

- M5 回溯记录**法律业务**事件（案号变更、对方变更、关键时点、对外交付）
- init-environment 记录**协作工具**事件（harness 切换、model 切换、init skill 升级）
- 两者并存、互不替代；M5 写在 `docs/DECISIONS.md` 或 `CHANGELOG.md`，init-environment 写在 AGENTS.md 受管区块

## 隐私边界

- harness / model / version 是**协作元数据**，**不**是案件事实
- `strict` / `local` / `team` 三档隐私模式均允许记录
- 不进 `.legal-context.local.md`
- 不在 validate-content.sh 的"案号/手机/邮箱/统一社会信用代码"白名单里
- 但 `note` 字段可手填，用户自负责不写案件信息
