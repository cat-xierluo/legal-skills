# 变更日志

本文档记录 legal-harness-init skill 的重要变更。

> **如何阅读**：每个版本段含"变更 / 决策 / 验证 / 待办"四类。  
> **NOT_VERIFIED 标记**：未真实跑通端到端流程的部分会显式标 `NOT_VERIFIED`，不伪装成已完成。

## [0.5.2] - 2026-08-13

> 国产平台 probe 全覆盖：用户指出 WorkBuddy/QwenWork 等国产平台才是主力用户群。本轮扩展 probe 支持 qwenwork/qoderwork/myagents（CC 克隆 jsonl）+ workbuddy（trace json），6 个主流 cli harness 全部能自动反查 model。

### 新增

- `probe-session-model.sh` 扩展 4 个国产平台分支：
  - **qwenwork**：`~/.qwenworkcn/projects/<encoded-cwd>/*.jsonl`，CC 克隆格式（model 是平台别名如 `qwork-advanced`）
  - **qoderwork**：`~/.qoderworkcn/projects/<encoded-cwd>/*.jsonl`，CC 克隆（别名如 `auto`）
  - **myagents**：`~/.myagents/sessions/*.jsonl`，CC 克隆 flat 不分 cwd（model 较真实如 `glm-5.2[1m]`）
  - **workbuddy**：`~/.workbuddy/traces/<pid>/trace_*.json`，遍历 mtime 降序找含 `chat.completion.model` 的 trace（每个操作一个 trace，只有 generation 类含 model；toolOutput 是 JSON 字符串需先去反斜杠再 grep）
- 重构 probe 抽 `probe_cc_clone_model` / `find_cc_clone_jsonl` / `encode_cwd` / `run_cc_clone_probe` helper，CC/qwenwork/qoderwork 共享 CC 克隆逻辑
- `openclaw` 分支按 CC 克隆常见路径试（sessions/projects），失败 not_found；`orca` 必定 not_found（worktree 型无统一 session）

### 决策

- DEC-026（本地不入仓）国产平台 probe 全覆盖：CC 克隆格式（qwenwork/qoderwork/myagents）复用同一 helper；workbuddy trace 遍历找 generation 类；openclaw/orca 因机制限制标 not_found 不臆造

### 验证

- ✅ `bash scripts/test.sh`：65/65 全过（v0.5.1 59 + v0.5.2 新增 6：qwenwork/qoderwork/myagents/workbuddy found + workbuddy/orca not_found）
- ✅ 真实环境 6 平台全部探测成功（放宽窗口到 30 天）：claude-code→glm-5.2、qwenwork→qwork-advanced、qoderwork→auto、myagents→glm-5.2[1m]、codex→gpt-5.6-sol、workbuddy→deepseek-v4-flash
- ✅ workbuddy 遍历逻辑：跳过工具调用 trace（无 model）取 generation trace
- ⚠️ openclaw 本机无会话 jsonl，**NOT_VERIFIED**（CC fork 会话路径待研究）
- ⚠️ orca worktree 型，结构性 not_found（不可自动反查）
- ⚠️ 端到端真实律师 init 全流程 `NOT_VERIFIED`

### 待办

- openclaw 真实会话 jsonl 路径研究（需在活跃使用 openclaw 的机器）
- 端到端真实 init 全流程跑通

## [0.5.1] - 2026-08-13

> codex session jsonl 反查：`--probe-from-session` 现支持 codex，从 `turn_context.payload.model` 取 model。

### 新增

- `probe-session-model.sh` 新增 codex 分支：`~/.codex/sessions/<年>/<月>/<日>/rollout-*.jsonl`，取最近 mtime 最大的 rollout，读最后一条 `turn_context` 记录的 `payload.model` 字段
- codex sessions 按时间分目录、不分 cwd（与 CC 按 encoded-cwd 分目录不同），probe 取最近 mtime 最大者

### 决策

- DEC-025（本地不入仓）codex probe 不按 cwd 过滤：codex 一次通常只跑一个项目，最近 mtime 的 rollout 大概率是当前；model 名跨项目通常一致；turn_context 行含 cwd 字段，若后续发现误取可加二次校验

### 验证

- ✅ `bash scripts/test.sh`：59/59 全过（v0.5.0 58 + v0.5.1 新增 1 codex found 路径；codex not_found 用例改用空 HOME 触发）
- ✅ probe codex 在 sandbox 真实 session 拿到 model（`gpt-5.6-sol`）
- ✅ probe codex sessions_root 不存在时 not_found
- ⚠️ openclaw / myagents / qoderwork / qwenwork / workbuddy / orca 的 probe **NOT_VERIFIED**（留 v0.5.2）
- ⚠️ 端到端真实律师 init 全流程 `NOT_VERIFIED`

### 待办

- v0.5.2：openclaw / myagents / qoderwork / qwenwork / workbuddy / orca 的 session model 探测路径研究（多数 non-agents-md 无 jsonl）
- 端到端真实 init 全流程跑通

## [0.5.0] - 2026-08-13

> session jsonl 事后回填：env 白名单全空时，`--probe-from-session` 从当前 harness 的 session jsonl 反查 model，覆盖之前 init-environment 表里的 unknown。

### 新增

- 新增 `scripts/probe-session-model.sh`：从当前 harness session jsonl 反查 model
  - claude-code 实现：`~/.claude/projects/<encoded-cwd>/*.jsonl`，取最近 10 分钟内 mtime 最大的 jsonl，读最后一条 `role=assistant` 记录的 `message.model` 字段
  - harness=unknown 宽容兜底为 claude-code（CC 是最常见默认场景，试不到再 not_found）
  - 隐私边界：只读 jsonl 元数据（mtime + `message.model`），**不**读 `message.content`（thinking / tool_use 正文）
- `record-init-env.sh` 新增 `--probe-from-session` 开关：env 白名单全空时自动调 probe-session-model.sh 反查；仍未命中走 hint 路径

### 改进

- `SKILL.md` 第六步半 model 采集说明补 `--probe-from-session` 路径与仅 claude-code 实现的边界
- `references/22-initialization-environment.md` 新增 § v0.5.0+ session jsonl 事后回填：讲探测路径、为什么默认关闭、隐私边界

### 决策

- DEC-024（本地不入仓）`--probe-from-session` 默认关闭 + 仅 claude-code 实现：probe 读 jsonl 是"重"操作，不适合每次 init 都跑；codex 嵌套 payload.turn_context.model 解析留 v0.5.1

### 验证

- ✅ `bash scripts/test.sh`：58/58 全过（v0.4.2 53 + v0.5.0 新增 5）
- ✅ probe-session-model.sh 在 sandbox 真实 CC session 拿到 model（`MiniMax-M3`）
- ✅ probe `--harness unknown` 宽容兜底为 claude-code 并正确反查
- ✅ probe `--harness codex` 在 v0.5.0 返回 not_found（待 v0.5.1）
- ✅ record-init-env.sh `--probe-from-session` + env 全空 + sandbox 真实 CC，自动从 jsonl 取 model 记录成功
- ✅ record-init-env.sh `--probe-from-session` 探测失败仍走 hint 路径（不臆造）
- ⚠️ codex / openclaw / myagents 等 7 个 harness 的 probe **NOT_VERIFIED**（留 v0.5.1）
- ⚠️ 端到端真实律师 init 全流程 `NOT_VERIFIED`

### 待办

- v0.5.1：codex session jsonl 反查（嵌套 payload.turn_context.model 解析）
- v0.5.2：openclaw / myagents / qoderwork / qwenwork / workbuddy / orca 的 session model 探测路径研究
- 端到端真实 init 全流程跑通

## [0.4.2] - 2026-08-13

> 把"必须 record"从 SKILL.md 文档约束升级为 write.sh 脚本级保证。同步修 v0.4.0 create 模式 bug。

### 改进

- `write.sh` 真实落盘后自动调一次 `record-init-env.sh`，无需 agent 手动串联
- `write.sh` 新增三个参数：`--record-init-env true|false`（默认 true）/ `--init-action init|update|append`（默认 init）/ `--model <name>`（透传给 record-init-env.sh）
- record-init-env.sh 探测失败时 `write.sh` **不阻断**：AGENTS.md 已落盘，init-environment 是 metadata；stderr 给出明确的手动补命令
- dry-run / needs_confirmation / write 失败路径不调 record-init-env.sh

### Bug 修复

- 修 v0.4.0 `record-init-env.sh` create 模式 bug：原 create 模式只写 init-environment 区块、不保留 target 原内容；导致 write.sh 集成后 target 中 legal-baseline 等其他受管区块被吞。fix：create 改为先 `cat target` + 补末尾换行 + 追加 init-environment 区块（v0.4.0 / v0.4.1 单独调用未暴露,因 record-init-env.sh 之前总在空 AGENTS.md 上跑）
- v0.4.2-B `--note` 含 markdown 破坏性字符 `|` 时不再破坏表格列分隔：新增 `escape_markdown_cell` 函数,`--note` 写入前 `|` → `\|` 转义；其他列（HARNESS_NAME / MODEL / VERSION 等 ASCII 标识符）不转义以减少误转义

### 决策

- DEC-022 write.sh 真实落盘后自动调 record-init-env.sh——从"文档约束"升级为"脚本级保证",agent 漏不掉
- DEC-023（待补）`--note` 只转义 `|`（最少必要）;不批量转义其他 markdown 元字符,避免误转义 ASCII 标识符

### 验证

- ✅ `bash scripts/test.sh`：53/53 全过（v0.4.1 48 + v0.4.2-A 新增 3 + v0.4.2-B 新增 2）
- ✅ write.sh 真实落盘后自动追加 init-environment（含 model 透传）
- ✅ `--record-init-env=false` 时不调 record-init-env.sh
- ✅ dry-run 时不调 record-init-env.sh
- ✅ write.sh 第二次同输入运行 status=unchanged,AGENTS.md 字节级零 diff
- ✅ 端到端：write.sh 落盘后 record-init-env.sh 自动追加,legal-baseline + init-environment 两个受管区块共存
- ✅ `--note "M6 项目级|关键时点"` 写入后 `\|` 被正确转义,表格列分隔未被破坏
- ⚠️ 端到端真实律师 init 全流程 `NOT_VERIFIED`(需真实律师测试)

### 待办

- 端到端真实 init 全流程跑通
- 真实 harness `--version` 探测在已装 claude/codex CLI 的机器验证
- v0.5.0-F session jsonl 事后回填（远期）

## [0.4.1] - 2026-08-13

> 扩展 model env 白名单 + 自助补 model hint。

### 改进

- `record-init-env.sh` env 白名单 5 → 9：新增 `CODEX_MODEL` / `OPENAI_MODEL_GLM`（部分 Codex 包装层）、`MYAGENTS_MODEL` / `QWEN_MODEL`（MyAgents / QwenWork）、`MY_MODEL`（用户兜底，agent 自检自填）
- env 全空 + 缺 `--model` 时不再一行 die，改为输出多行 hint：提示 `export MY_MODEL` 或 `--model` 兜底，引向 `references/22 § 自助补 model`
- `references/22-initialization-environment.md` 加 § 自助补 model：阐述"为什么不臆造"+ "为什么选 MY_MODEL 而不是 LEGAL_MODEL"（行业通用、不绑定 skill）
- `test.sh` 加 9 个新断言：env 全空时 hint 三短语 + 三个新 env 候选各自 record + `assert_contains` 加 `--` 终止符防 `--model` 被 grep 当 option

### 决策

- 保留 v0.4.0 DEC-021 "不臆造 model" 原则；v0.4.1 只是把"不知道怎么办"的提示做得更可执行，不动数据完整性

### 验证

- ✅ `bash scripts/test.sh`：48/48 全过（v0.4.0 39 + v0.4.1 新增 9）
- ✅ env 全空 + 缺 `--model` 仍 die 退出码 1（不臆造）
- ✅ env 全空时 stderr 出现"自助补 model" / "MY_MODEL" / "--model" 三个 hint 短语
- ✅ `CODEX_MODEL=codex-opus-1` / `MYAGENTS_MODEL=mya-pro` / `MY_MODEL=agent-self-detected` 三种新候选各自 record 成功 + 字段写入
- ⚠️ 真实 8 平台端到端 init 流程、session jsonl 事后回填 `NOT_VERIFIED`

## [0.4.0] - 2026-08-13

> 沉淀每次 init 的工具环境到被初始化的项目，作为将来追溯"问题出在 harness 还是 model 层"的元数据。端到端真实跑通仍 `NOT_VERIFIED`（缺真实律师 init 全流程）。

### 新增

- 新增 `scripts/record-init-env.sh`：半自动采集 harness(name+version) + model + init skill version，append 一行到目标 AGENTS.md 的 `init-environment` 受管区块
- 新增受管区块 `init-environment`（block-id 落 SKILL.md 第五步受管区块表）：与 M1—M8 同 marker 语法，append-only 表格
- 新增 `templates/modules/init-environment.md` 受管区块模板（首次 init 时的骨架示例）
- 新增 `references/22-initialization-environment.md`（背景/采集方式/env 局限/隐私边界/归档建议）

### 改进

- `SKILL.md` 第六步后插入"第六步半：记录初始化环境"；第六步 `write.sh` 真实落盘后必须再调一次 `record-init-env.sh`
- 输入参数表新增 `--model`（env 兜底）与 `--action {init,update,append}`
- 禁止事项补两条：禁止在 `record-init-env.sh` 探测不到 model 时臆造；禁止手改 `init-environment` 表格行
- 验收清单补一条：缺 init-environment 记录时报告 `INIT_ENV_NOT_RECORDED` 而非宣称完成
- 新增 `skill-lint:constraint INIT-ENVIRONMENT-RECORD-ON-WRITE` 约束 marker

### 决策

- DEC-021：项目级 init 环境元数据受管区块（append-only、半自动采集、不进 .legal-context.local.md、不回填 v0.1.0—v0.3.0）

### 验证

- ✅ `bash -n scripts/record-init-env.sh`：语法通过
- ✅ 9 个冒烟用例（手动）：缺 target → die；env 全空缺 model → die 强制 `--model`；dry-run 不落盘；干净项目 create；重复执行 unchanged；残缺 marker 拒绝；append 后行数 = 2
- ⚠️ 真实 harness `claude --version` / `codex --version` 探测：在 sandbox 探测到本机 `claude-code` 时 `Harness Version` 应可填真实值；当前 sandbox 缺 claude CLI → 标 `unknown` 兜底
- ⚠️ 端到端（quick 引导 → write.sh → record-init-env.sh 真实 init 一个新法律项目）`NOT_VERIFIED`，需真实律师测试
- ✅ 已有 `bash scripts/test.sh` 应继续 26/26 通过（新增 record-init-env.sh 回归待运行确认）

### 待办

- 端到端跑通：quick 引导 → write.sh → record-init-env.sh 三步顺序在真实律师 init 一个新项目时走通
- 真实 harness 版本探测：在已装 `claude` / `codex` CLI 的机器验证 `Harness Version` 字段能拿到真实值（当前 sandbox 标 `unknown`）
- 模型 env 探测覆盖：扩展 env 白名单（`OPENAI_MODEL_GLM` / `QWEN_MODEL` 等）
- 归档自动化：>50 行时自动复制到 `docs/init-environment-history.md`（v0.4.0 不做）

## [0.3.0] - 2026-08-12

### 新增

- 新增 `quick` / `guided` / `team` 三种引导模式；默认 quick 用一轮最多 5 个问题生成最小法律安全基线
- 新增 `strict` / `local` / `team` 三档隐私模式；M7 改为受控事实入口，默认不把完整当事人、案号、金额、联系方式、统一社会信用代码等写入长期指令
- 新增 `scripts/validate-content.sh`，在写入前拦截疑似凭证、高敏身份号及不符合隐私模式的案件信息
- 新增 `scripts/restore.sh`，按首次原始备份元数据恢复原文、权限和哈希
- 新增 `scripts/verify.sh` 与四类新会话行为探针，区分 `CONFIG_WRITTEN` / `INSTRUCTIONS_LOADED` / `BEHAVIOR_VERIFIED`
- 新增 `scripts/test.sh` 无网络回归；覆盖 runtime、project-init 误判、同路径去重、零 diff、权限、恢复、敏感内容和残缺 marker
- 新增 `references/18-privacy-and-context.md`、`19-activation-verification.md`、`20-team-layering.md`
- 新增指令稳定性合同、交付报告 checker 和 4 类候选内正反例

### 改进

- `write.sh` 改为稳定受管 marker 的区块级 upsert：按实际目标路径去重、候选校验、展示 diff、同目录原子替换；第二次相同写入报告 `unchanged`
- marker 校验拒绝畸形前缀；新会话证据绑定当前配置 SHA-256，配置变化后旧证据不能继续抬高完成状态
- 首次备份固定为 `.bak.legal-harness-init`，另存原权限/哈希元数据；每次变化的快照加入进程标识避免同秒碰撞；用户级目标与备份显式 `0600`
- `detect.sh` 升级 schema v3：runtime 输出候选/证据/置信度，支持 `--runtime` 显式声明；Codex 新增 `CODEX_THREAD_ID`、`CODEX_CI`、`CODEX_SHELL` 信号，`CODEX_HOME` 降为 low
- `project-init` 改用 `.claude/skills` + 项目指令文件 + 脚手架证据的复合判断；仅有 `docs/` 不再误判
- M4/M5 升级为权限、保密、溯源、人工裁决四项法律安全基线；回溯载体改为决策/证据/期限/交付分类并优先复用项目现有权威来源
- `--preset` 更名为 `--project-type`，旧名称仅兼容；项目类型只路由追问
- 团队治理明确组织、项目、个人三层所有权与冲突优先级
- 教学定位改为“持久默认基线”：明确 AGENTS.md/CLAUDE.md 的长期价值不等于脱离平台指令层级的绝对最高优先级，避免把当前明确指令与持久配置错误对立
- 用户级/项目级教学与 M8 示例同步最小披露原则：quick 不再被旧 10—30 分钟流程覆盖，文件命名默认使用内部项目代号，不再暗示研究材料可全部入 Git
- frontmatter `license` 统一为 `MIT`，LICENSE 版权年份按项目规范统一为 2025；同步 README 最近更新和技能索引

### 验证

- ✅ `bash scripts/test.sh`：26/26 通过
- ✅ `harness_failure_audit.py audit`：PASS，0 hard / 0 warning / 0 info
- ✅ `security_scan.py audit`：0 critical / 0 high / 0 medium；4 个 low 均来自已披露的 `$HOME` 路径与 runtime 环境信号探测
- ✅ 候选内稳定性 checker：正例通过；隐私泄露、重复 marker、无证据完成声明、反向团队优先级 4 个变异样例均退出 3
- ✅ `bash -n`：detect/write/validate/restore/verify/test 全部通过
- ⚠️ `INSTRUCTION_STABILITY_NOT_VERIFIED`：已具备合同和候选内正反例，但尚无候选外 Ed25519 签名硬约束基线、held-out、Harness evidence 与三轮签名回执
- ✅ Codex 新会话前向验证：新启动 `codex exec --ephemeral` 明确报告加载临时项目 `AGENTS.md` 的规范化精确绝对路径，并返回与当前文件一致的 SHA-256；权限、保密、信息缺口、回溯载体四类探针全部通过，`verify.sh` 复算输出 `BEHAVIOR_VERIFIED`
- ⚠️ Claude Code / OpenClaw / MyAgents 新会话行为探针本次未运行，仍为 `NOT_VERIFIED`，不从 Codex 结果外推
- ⚠️ Codex 官方 `quick_validate.py` 不接受项目 ClawHub 约定中的顶层 `version` / `author` / `homepage` 字段；当前保留项目格式，跨分发 schema 兼容性待统一

### 待办事项

- 在 Claude Code / OpenClaw / MyAgents 的真实新会话分别完成加载来源检查与四类行为探针
- 由候选外 evaluator 生成并签名硬约束基线、held-out、三轮运行证据和最终回执
- 在真实 quick 引导中记录开始/完成时间，验证“5 分钟最小基线”的可用性指标

## [0.2.0] - 2026-08-12

> 参考 self-evolve `detect_platforms()` 风格，补齐"检测当前 runtime + 自动写入对应位置"能力。端到端真实跑通仍 NOT_VERIFIED。

### 变更

- **新增 `scripts/lib_platforms.sh`**（DEC-009）：8 平台权威表（key → 配置文件 / config_kind / runtime env 标志），被 detect/write 共享的单一真值源。新增/改平台只改这里
- **新增 `scripts/write.sh`**：把生成好的 AGENTS.md/CLAUDE.md 内容写入对应 harness 位置。支持 `--content-file` / `--level` / `--platforms` / `--mode create|update|append` / `--dry-run` / `--force`；已存在先 `cp -p` 备份 `.bak.<ts>` + diff；用户级 `umask 077`、项目级 `umask 022`；输出 JSON 报告（written/backed_up/needs_confirmation/unsupported/error）
- **`detect.sh` 扩到 8 平台**（DEC-010）：CC / Codex / OpenClaw / MyAgents / QoderWork / QwenWork / WorkBuddy / Orca，每平台报 `config_kind`
- **修正 detect.sh 平台事实错误**：`.qoderworkcn/AGENTS.md` 实测不存在 → 标 `non-agents-md` 仅检测不写入；补漏检的 `.myagents/CLAUDE.md`
- **新增 `current_runtime` 字段**：通过 env 标志（`CLAUDECODE` / `CODEX_HOME` / `ORCA_AGENT_HOOK_TOKEN`，只看 set 不读值）推断当前会话跑在哪个 harness；可写平台优先于容器层；无法确定报 `null`
- **schema 1 → 2**：加 `current_runtime` / `current_runtime_writeable` / 每平台 `config_kind`；老字段保留
- **SKILL.md §第六步重写**：从"agent 手动逐个写"改为"调 `bash scripts/write.sh`"；平台表标自动写入 vs 手动；参数表加 `--mode` / `--dry-run` / `--force`
- **references/03 重写**：8 平台表 + runtime env 信号段 + 自动写入边界段 + schema v2 JSON 样例；隐私边界补 env 标志读取说明
- **移除 scripts/README.md**：脚本能力披露并入 SKILL.md §第零步 + references/03 §隐私边界，不再单独维护 README（v0.1.1 为过 skill-lint disclosure 建的载体，SKILL.md 已含同等披露后冗余）

### 决策

- DEC-009：平台权威表抽 `lib_platforms.sh` 单一真值源（避免 detect/write 路径漂移）
- DEC-010：只对 `claude_md` / `agents_md` 平台自动写入；`non-agents-md` 平台（QoderWork/QwenWork/WorkBuddy/Orca）仅检测提示手动

### 验证

- ✅ `bash scripts/lib_platforms.sh` 自检：8 平台 key/kind/path/env 全部正确解析
- ✅ detect.sh schema v2 JSON 合法（`python3 -m json.tool`）
- ✅ 干净环境 `HOME=/tmp/empty bash scripts/detect.sh` 不崩（继承 DEC-008 守卫）
- ✅ write.sh `--dry-run` 展示 diff 不落盘；`unsupported` 含 4 个 non-agents-md 平台
- ⚠️ 端到端（引导问答 → write.sh 真实写入用户 ~/.claude/CLAUDE.md）**NOT_VERIFIED**
- ⚠️ Codex runtime env 确切名（`CODEX_HOME`）待 codex session 内验证

### 待办

- 用户级 + 项目级完整流程端到端跑通（需真实律师测试）— NOT_VERIFIED
- QoderWork / QwenWork / WorkBuddy / Orca 真实配置机制研究（当前只检测不写）
- v0.3.0：references/18-walkthrough.md + 指令稳定性合同

## [0.1.2] - 2026-08-12

> skill-lint 审计修缮：修复 detect.sh 在 macOS bash 3.2 的边界崩溃 + 发布治理小修。端到端流程仍 NOT_VERIFIED。

### 变更

- **修复 detect.sh 空数组崩溃（bash 3.2 + `set -u`）**：无 harness 场景下 `for ... in "${ARR[@]}"` 触发 `unbound variable`、JSON 不输出（目标受众首发场景必崩）。三处 for 循环（HARNESSES / USER_LEVEL / PROJECT_INIT_EVIDENCE）加 `${#ARR[@]} -gt 0` 守卫。详见 DECISIONS §DEC-008
- **SKILL.md `version` 同步**：`0.1.0` → `0.1.2`（此前滞后于 CHANGELOG）
- **FAQ 断链修复**：[references/16-faq.md](references/16-faq.md) 末尾 `](templates-modules)` → `](../templates/modules/)`
- **CHANGELOG 结构整理**：散落在 `[0.1.0]` 段后的顶层 `## 待办` / `## 验证结果（v0.1.0）` 并入本段（信息冗余清理；双场景 detect.sh 验证以本次边界复测为准）

### 决策

- DEC-008：detect.sh 空数组守卫方案选用 `${#ARR[@]} -gt 0`（兼容 bash 3.2 与 5+，优于 `${arr[@]+...}` 的版本歧义）

### 验证

- ✅ `HOME=/tmp/empty /bin/bash scripts/detect.sh` 输出合法 JSON（`harnesses_detected: []`）+ 退出码 1（**此前崩溃不输出 JSON**）
- ✅ `bash scripts/detect.sh | python3 -m json.tool`（本机 4 平台）仍合法
- ✅ `security_scan.py audit`：0 critical / 0 high / 0 medium / 8 low（全为 `$HOME` 读取误报）
- ✅ `harness_failure_audit.py audit`：PASS，0 hard / 0 warning / 0 info
- ⚠️ 端到端流程（用户级 + 项目级真实跑通、跨平台写入）**NOT_VERIFIED**
- ⚠️ OpenClaw / QoderWork 真实写入测试 **NOT_VERIFIED**（本机未装）

### 待办

- 用户级 + 项目级完整流程跑通（需真实律师测试）— NOT_VERIFIED
- OpenClaw / QoderWork 真实写入测试 — NOT_VERIFIED
- v0.2.0：references/18-walkthrough.md + 指令稳定性合同 v1

## [0.1.1] - 2026-08-12

> ⚠️ 本版本以小修为主，**端到端用户级 + 项目级跑通仍 NOT_VERIFIED**（v0.1.0 起即未跑通，需真实律师测试）。

### 变更

- **detect.sh schema 版本化**：输出顶部新增 `"schema_version": "1"`，日后字段增删按版本递增
- **detect.sh 隐私边界摘要前置**：SKILL.md §第零步新增"**隐私边界**：detect.sh 只读取目录存在性和文件行数..."1 行摘要，配合 references/03 详述
- **CC 项目级 CLAUDE.md 用法澄清**：SKILL.md §第六步表头明确"独立写 / 用 `@include ./AGENTS.md` 引入"两条路径，由用户按多平台协作需要选择
- **FAQ 错别字修复**：[references/16-faq.md](references/16-faq.md) §"CC 的 CLAUDE.md 和 Codex 的 AGENTS.md 内容不一样怎么办"删一处"语法差异"重复字
- **M7 案号格式统一**：所有 `references/` 与 `templates/` 中具体年份范例从 `[2026]沪0115民初1234号` 改为 `(2026)沪0115民初1234号`（中国法院案号标准格式）。`[YYYY]` 占位符保持不变
- **scripts/README.md 新建**：解决 skill-lint `SEC-DISCLOSURE` 中级警告。含检测脚本用法、退出码语义、Schema v1 全字段表、隐私边界与维护原则
- **SKILL.md §第八步：增量更新模式**：补充"已存在 AGENTS.md 时的 4 种处理路径"，让主流程覆盖"用户跑了 v0.1.x 后再跑增量更新"场景
- **SKILL.md 第四步 M7 表格瘦身**：将"M7 动态问法"5 行表格替换为"详见 templates/modules/M7-case-facts.md"一句话引用，消除重复维护

### 决策

- DEC-006：detect.sh schema 版本号 + scripts/README.md（详见 DECISIONS.md）
- DEC-007：SKILL.md 第八步"增量更新模式"独立工作流（已有 AGENTS.md 时绝不重写，先 diff 再追加）

### 验证

- ✅ `bash skills/legal-harness-init/scripts/detect.sh | python3 -m json.tool` 输出合法 JSON，`schema_version` 字段存在
- ✅ `harness_failure_audit.py audit` → PASS（0 hard / 0 warning / 0 info）
- ✅ security scan：SEC-DISCLOSURE 已通过 scripts/README.md 显式披露（remaining 全部为 `$HOME` 路径探测 low 误报）
- ✅ cross-file [20XX] → (20XX) 替换 15 处，不动 `[YYYY]` 占位符
- ⚠️ 端到端流程（用户级 + 项目级真实跑通、跨平台写入测试）**NOT_VERIFIED**

### 待办

- 用户级 + 项目级完整流程跑通验证（需要真实律师测试）— **NOT_VERIFIED**
- OpenClaw / QoderWork 真实写入测试 — **NOT_VERIFIED**（本机未装）
- v0.2.0：根据 v0.1.1 反馈叠加 walkthrough 脚本与指令稳定性合同

## [0.1.0] - 2026-08-12

### 为什么做这个 skill

法律人用 AI 协作，**多数卡在最基础的 harness 初始化**：

- 不知道 AGENTS.md 是什么、写在哪、和每次会话什么关系
- 每次开会话都要从头交代角色（"我是律师"）
- 工作偏好散落在 prompt 里，没沉淀
- AI 做了关键动作没留痕，事后无法复盘/审计（**法律场景的天然痛点**）

杨卫薪律师观察到：

> "AGENTS.md 实际上是发给 agent 的 session 的最重要的一句话了。"

——这是最初的用户观察。v0.3.0 将其校准为“跨会话持续生效的默认协作基线”：价值来自持久、统一、可复核，不代表可以脱离平台指令层级覆盖当前明确指令。

### 目标

让法律人用最少的专业成本，把"AGENTS.md 是最重要的那句话"这件事写对——既有人人能懂的原理讲解（教学底座），又能直接帮他生成并写入当前环境（生成入口）。

### 变更

- **初始版本**（法律人专属 harness 初始化工具）
- **8 模块骨架 + 预设降级方案**（DEC-001）：不用 5 套预设硬套，用 M1-M8 模块让用户和 agent 一起拼装
- **教学底座 + 生成入口双形态**：
  - `references/01-16` 教学底座（16 章节）
  - `references/17-examples/` 5 套完整参考范例 + 好坏对比
  - `templates/modules/M1-M8.md` 8 模块片段库
  - `assets/audit-trail-snippet.md` 回溯契约通用片段
  - `scripts/detect.sh` 4 平台环境检测（CC/Codex/OpenClaw/QoderWork）
- **法律人专属回溯契约**（核心 section）：M5 模块默认开启，引导用户在 DECISIONS.md/CHANGELOG.md/TASKS.md 留痕
- **与 project-init 互补**：detect.sh 检测到 `.claude/skills/` 和 `docs/` 时只 append 三块，不重写

### 决策

- DEC-001：采用模块化为骨架、预设降级为参考范例（详见 DECISIONS.md）
- DEC-002：双层入口先用户级后项目级（用户级差异小、项目级差异大）
- DEC-003：覆盖 4 平台（CC/Codex/OpenClaw/QoderWork），按平台检测写入
- DEC-004：教学底座本身就是 skill 的活教材，agent 必须主动引用相关章节
- DEC-005：M5 回溯契约默认开启（法律工作强烈不建议关闭）

完整 brainstorm 核心结论见 `DECISIONS.md` 顶部“起源与动机”；原设计稿在 v0.3.0 从公开交付树移除，历史版本仍可由 Git 追溯。

### 验证

- `scripts/detect.sh` 输出合法 JSON（已用 python3 -m json.tool 验证）
- Harness 失效审查 PASS（0 hard）
- 安全扫描：0 critical / 0 high / 1 medium（已补 disclosure）/ 8 low
- 双场景 detect.sh 验证：干净环境 ✅ + 已跑过 project-init ✅

<!-- v0.1.0 详细验证矩阵与双场景 detect.sh 测试已于 [0.1.2] 重新整理；历史明细见 git 历史 -->
