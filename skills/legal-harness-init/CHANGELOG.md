# 变更日志

本文档记录 legal-harness-init skill 的重要变更。

> **如何阅读**：每个版本段含"变更 / 决策 / 验证 / 待办"四类。  
> **NOT_VERIFIED 标记**：未真实跑通端到端流程的部分会显式标 `NOT_VERIFIED`，不伪装成已完成。

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

## 待办

- 用户级 + 项目级完整流程跑通验证（需要真实律师测试）
- v0.2.0：根据反馈优化流程和模块

## 验证结果（v0.1.0）

### skill-lint 静态审查

- **Harness 失效审查**：`harness_failure_audit.py audit` → PASS（0 hard / 0 warning / 0 info）
- **安全扫描**：`security_scan.py audit` → 0 critical / 0 high / 1 medium / 8 low
  - medium：detect.sh 的 `$HOME` 读取被识别为"未在文档中披露"。已在 `references/03-harness-detection.md` §"检测脚本的隐私边界"补全说明：只检查目录存在性和文件行数，不读取文件内容
  - low：8 处 `$HOME` 路径读取（被误识别为 credential access，实际仅用于目录探测）

### 双场景 detect.sh 验证

- 干净环境（无 AGENTS.md，无 project-init 痕迹）：detect.sh 返回 `project_init_ran: false`
- 已跑过 project-init 的项目（含 AGENTS.md + .claude/skills/ + docs/）：detect.sh 返回 `project_init_ran: true` + `evidence: [.claude/skills/, docs/]`

### 未做（需要真实律师测试）

- 用户级 + 项目级完整流程的端到端跑通（NOT_VERIFIED）
- 真实 AGENTS.md 文件的写入测试（NOT_VERIFIED）
- 跨平台（OpenClaw / QoderWork）写入测试（NOT_VERIFIED，本机未安装）