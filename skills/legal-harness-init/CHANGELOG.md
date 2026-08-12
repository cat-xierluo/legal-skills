# 变更日志

本文档记录 legal-harness-init skill 的重要变更。

> **如何阅读**：每个版本段含"变更 / 决策 / 验证 / 待办"四类。  
> **NOT_VERIFIED 标记**：未真实跑通端到端流程的部分会显式标 `NOT_VERIFIED`，不伪装成已完成。

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

——它决定了所有后续会话的默认行为，比单次 prompt 更重要。多数人不会配，所以"用不好"。

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

完整 brainstorm 上下文见 `DECISIONS.md` 顶部"起源与动机"section 和 `drafts/2026-08-12-legal-harness-init-design.md` §0。

### 验证

- `scripts/detect.sh` 输出合法 JSON（已用 python3 -m json.tool 验证）
- Harness 失效审查 PASS（0 hard）
- 安全扫描：0 critical / 0 high / 1 medium（已补 disclosure）/ 8 low
- 双场景 detect.sh 验证：干净环境 ✅ + 已跑过 project-init ✅

<!-- v0.1.0 详细验证矩阵与双场景 detect.sh 测试已于 [0.1.2] 重新整理；历史明细见 git 历史 -->