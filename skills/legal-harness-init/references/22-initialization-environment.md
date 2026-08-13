# 22 - 初始化环境元数据：为什么记、怎么记、记什么

## 一句话结论

`legal-harness-init` 每完成一次项目初始化或增量更新，都应在被初始化的项目里 append 一行"用了哪个 harness / 哪个 model / 哪个 init skill 版本 / 什么操作"——沉淀到 AGENTS.md 的受管区块 `init-environment`。将来出问题时可以快速判断"是 harness 层面的问题还是 model 层面的问题"。

## 为什么记

法律人用 AI 协作时，最难诊断的一类问题是"输出和预想不一致"。可能根因有：

1. **harness 升级**导致指令解释变化（CC 升级把 `@include` 改语义）
2. **model 切换**导致行为风格漂移（GLM-MiniMax-M3 切到 claude-fable-5 后回答详尽度变化）
3. **init skill 升级**改了受管区块结构（v0.3.0 加 init-environment 后老 agent 还在用旧版块名）
4. **隐私模式/操作类型**改了 AGENTS.md 的实际写入内容（quick vs team）

如果项目里**没有**一条"这次 init 用的什么环境"的留痕，事后翻 git 还要靠 commit message 猜——而 commit message 常常漏写。

`init-environment` 受管区块让"环境元数据"和"项目代码"在同一文件、同一时间线，方便审计。

## 记录什么

每行一个 init 事件，字段：

| 字段 | 含义 | 兜底 |
|---|---|---|
| 时间 | 何时执行 | `unknown-time`（`date` 命令不可用时） |
| Harness | 平台 key（claude-code / codex / openclaw / myagents / qoderwork / qwenwork / workbuddy / orca） | `unknown` |
| Harness Version | 该 harness 的版本 | 探测失败写 `unknown`；非 claude/codex 写 `n/a` |
| Model | 当前会话用的 model 名 | env 全空时**强制要求** `--model` 兜底，不臆造 |
| Init Skill | 固定 `legal-harness-init` | — |
| Init Skill Version | 本 skill 的 version（来自 SKILL.md frontmatter） | `unknown` |
| 操作 | `init` / `update` / `append` | 默认 `init` |

可选 `--note "..."` 字段会附在 `操作` 后（用 ` · ` 分隔），例如 `update · M6 项目级`。

## 怎么自动采集

`scripts/record-init-env.sh` 半自动采集，**3 个数据源 + 1 个兜底**：

1. **harness name**：优先 `--harness` 显式覆盖；否则 source `detect.sh`，取 `current_runtime` 字段（schema v3 已有）
2. **harness version**：探测 `claude --version` / `codex --version` 等命令，2s 超时，失败 `unknown`；非 claude/codex 直接 `n/a`
3. **model**：env 白名单探测（命中即用，未命中则**强制要求** `--model`）：
   - `ANTHROPIC_MODEL`（Claude 系）
   - `OPENAI_MODEL`（OpenAI 系）
   - `CLAUDE_MODEL`（部分 CC fork）
   - `GLM_MODEL`（智谱系）
   - `MY_MODEL`（用户自定义）
4. **init skill version**：从 `$(skill_root)/SKILL.md` frontmatter 读 `version: "X.Y.Z"`

> **关于 model env 信号的局限**：CC / Codex 等多数 harness 当前**不**把 model 名 export 到 env，必须靠用户在调用时显式传 `--model` 或自行 export 自己的 env 变量。脚本的兜底是拒绝 append、要求 `--model`——不臆造 model 名。

## 受管区块结构

`init-environment` 用与其他 M1—M8 相同的 marker 格式：

```
<!-- legal-harness-init:init-environment:start -->

| 时间 | Harness | Harness Version | Model | Init Skill | Init Skill Version | 操作 |
|---|---|---|---|---|---|---|
| 2026-08-13 14:30 | claude-code | 1.0.0 | MiniMax-M3 | legal-harness-init | 0.4.0 | init |

<!-- legal-harness-init:init-environment:end -->
```

行为：

- **create**：区块不存在时，整块创建（含表头）
- **append**：区块已存在时，在 end marker 前插入新行
- **残缺拒绝**：start/end 只出现一个时拒绝 append，提示人工修复
- **unchanged**：candidate 与 target 字节级一致时退出 0，不创建快照
- **dry-run**：`--dry-run` 显示 diff 不落盘
- **>50 行软提示**：超过 50 行提示归档（不阻断）

## 隐私边界

- harness / model / version 是**协作元数据**，**不**是案件事实
- 三档隐私模式 `strict` / `local` / `team` 均允许记录
- **不**进 `.legal-context.local.md`（那是个案事实载体，不放工具元数据）
- **不**被 `validate-content.sh` 拒绝（不与案号/手机/邮箱冲突）
- `--note` 字段由用户自负责，避免写入案件信息

## 回填策略

- **v0.4.0+ 起强制**：每次 init / update / append 都应自动调用 record-init-env.sh
- **v0.1.0~v0.3.0 不回填**：当天迭代环境都不可追溯，手动补意义不大；标 `unknown / NOT_VERIFIED` 即可
- **手动补记**：用户可手跑 `bash scripts/record-init-env.sh --model <name> --note "事后追溯"` 单独记一条

## append-only 增长与归档

表格随项目生命周期增长。**>50 行软提示**只是 stderr 警告，不阻断。归档建议：

1. 复制当前完整表格到 `docs/init-environment-history.md`（按年/月分段）
2. 留表头 + 最后 5 行作为衔接指针
3. 写一条 `docs/DECISIONS.md` 决策说明"为何归档"（这是 M5 回溯契约的标准动作）

注：record-init-env.sh 的 archive 自动化**不在 v0.4.0 范围**，避免一次引入太多新机制。

## 与现有模块的关系

| 模块 | 写在哪 | 写什么 | 何时写 |
|---|---|---|---|
| M5 回溯契约 | `docs/DECISIONS.md` / `CHANGELOG.md` / `TASKS.md` | 法律业务事件（案号/对方/关键时点/对外交付） | 用户告知变化时 |
| `init-environment` 受管区块 | AGENTS.md 末尾 | 协作工具事件（harness/model/init skill） | 每次 init / update / append |

两者**并存、互不替代**。M5 关注"业务上发生了什么"，init-environment 关注"工具环境是什么"。

## 失败关闭

`record-init-env.sh` 在以下情况拒绝 append：

- 缺 `--target` 或 `--target` 不存在
- `--action` 不是 `init` / `update` / `append` 之一
- env 白名单全空且未传 `--model`
- target 文件的 init-environment 区块残缺（只 start 或只 end）
- candidate marker 校验失败或整体结构异常
- atomic mv 失败

任何失败都退出码 1 + stderr 提示，不留半成品。

## 接下来读什么

- 受管区块模板 → [templates/modules/init-environment.md](../templates/modules/init-environment.md)
- 主流程第六步新增"记录初始化环境" → [SKILL.md](../SKILL.md)
- 决策记录 → [DECISIONS.md §DEC-015](../DECISIONS.md)
- 与 M5 的关系 → [references/11-module-audit-trail.md](11-module-audit-trail.md)
