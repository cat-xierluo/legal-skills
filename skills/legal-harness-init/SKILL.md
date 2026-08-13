---
name: legal-harness-init
description: 面向法律工作者初始化或增量治理 AGENTS.md/CLAUDE.md：识别当前 AI harness，区分用户级、项目级和团队级指令，生成最小法律安全基线，安全合并受管区块，并在新会话中验证权限、保密、信息缺口和回溯行为。用户明确提到法律工作且要配置 harness、AGENTS.md、CLAUDE.md、agent 协作规则或 AI 使用基线时使用。不要用于合同审查、案件分析、文书起草、项目脚手架或 Skill 开发。
version: "0.4.0"
license: MIT
author: 杨卫薪律师（微信ywxlaw）
homepage: https://github.com/cat-xierluo/legal-skills
---

# Legal Harness Init

把法律人的稳定协作要求写成可加载、可增量更新、可验证的 harness 指令。完成不等于“文件已写入”；必须区分：

1. `CONFIG_WRITTEN`：文件与受管区块存在。
2. `INSTRUCTIONS_LOADED`：新会话报告了精确加载来源。
3. `BEHAVIOR_VERIFIED`：新会话通过四类行为探针。

<!-- skill-lint:constraint COMPLETION-STATUS-NO-OVERCLAIM -->
如果无法启动新会话，必须报告 `CONFIG_WRITTEN` + `NOT_VERIFIED`，不得声称配置已经生效。

## 适用边界

在以下条件同时满足时使用：

- 用户是律师、法务、合规、知识产权或其他法律工作者；
- 用户要建立或更新 AI 协作规则、AGENTS.md、CLAUDE.md 或 harness 基线。

不要用于：

- 合同审查、案件研判、检索、文书起草等法律业务；
- `.claude/`、`.codex/`、skills、docs 等项目脚手架初始化（改用 `project-init`）；
- Skill 或代码开发。

## 输入参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--guide-mode` | `quick` | `quick` / `guided` / `team` |
| `--level` | 自动判断 | `user` / `project`；team 模式按组织→项目→个人处理 |
| `--platforms` | 当前 runtime + 可写已安装平台 | 平台 key，逗号分隔 |
| `--runtime` | 自动检测 | 调用方明确知道当前平台时传给 `detect.sh` |
| `--project-type` | 询问 | `litigation` / `transactional` / `ip` / `in-house` / `research`；只路由问题，不提供标准答案 |
| `--privacy-mode` | `strict` | `strict` / `local` / `team` |
| `--mode` | `create` | `create` / `update` / `append`；三者均只 upsert 受管区块 |
| `--block-id` | 按模块指定 | 稳定 marker id，见“受管区块” |
| `--dry-run` | 否 | 只展示候选 diff，不写入 |
| `--model` | env 白名单探测 | init-environment 受管区块需要时兜底；`ANTHROPIC_MODEL` / `OPENAI_MODEL` / `CLAUDE_MODEL` / `GLM_MODEL` / `MY_MODEL` 命中即用 |
| `--action` | `init` | record-init-env.sh 的操作类型：`init` / `update` / `append` |

将旧参数 `--preset` 解释为 `--project-type`，并提示新名称；项目类型只决定追问路线，不能替用户填答案。

## 第一步：检测环境

运行：

```bash
bash scripts/detect.sh
# 调用方明确知道当前平台时：
bash scripts/detect.sh --runtime codex
```

读取 schema v3 的：

- `runtime_candidates`：候选平台、信号、置信度、是否可写；
- `current_runtime`：只在显式声明或最高置信度唯一命中时设置；
- `harnesses_detected`：已安装平台；
- `project_level`：AGENTS.md / CLAUDE.md 与 `project-init` 复合证据。

检测脚本只读取已知目录、文件存在性、行数及 runtime 环境变量是否存在，不读取环境变量值、配置正文、Token 或凭证。详见 [references/03-harness-detection.md](references/03-harness-detection.md)。

## 第二步：选择引导模式与隐私模式

### quick：5 分钟最小安全基线

默认使用。用一轮最多 5 个问题确认：

1. 角色和主要工作类型是什么？
2. 常见交付物及期望格式是什么？
3. AI 可做、必须先确认、绝对禁止的动作分别是什么？
4. 采用 `strict`、`local` 还是 `team` 隐私模式？
5. 哪些决策、证据变化、期限和交付版本需要留痕，项目已有哪个权威载体？

每组答案只解释一句“为何需要”。不要跳过必要安全问题，也不要强迫用户完成全部教学章节。生成 M1、M2、M3、法律安全基线和 M5；项目级再生成最小 M6—M8。

### guided：逐模块共同设计

按 M1→M8 逐项引导，参考 [references/04-modules.md](references/04-modules.md) 与 `templates/modules/`。用户卡住时给候选维度，不替用户决定，不直接套用范例。

### team：三层治理

先读取 [references/20-team-layering.md](references/20-team-layering.md)，分别确认：

- 组织层：稳定且不可被项目弱化的安全、保密、审批与工具政策；
- 项目层：事项范围、阶段、事实入口、时限与项目工作流；
- 个人层：表达、格式与非强制偏好。

<!-- skill-lint:constraint TEAM-LAYER-PRECEDENCE -->
在平台允许配置的同一治理范围内，冲突时必须遵循法律安全边界/组织强制政策 > 项目具体规则 > 个人偏好；同层冲突请求负责人确认并留痕。AGENTS.md/CLAUDE.md 是持久默认基线，不得把这条团队层规则解释成对平台指令层级或用户当前明确授权的通用改写。

### 三档隐私模式

按 [references/18-privacy-and-context.md](references/18-privacy-and-context.md) 执行：

- `strict`：AGENTS.md 只写项目代号、类型、阶段、关键时点和规则，不写真实当事人、案号、金额、联系方式或身份号码。
- `local`：真实事实写入权限为 `0600` 且被 `.gitignore` 排除的 `.legal-context.local.md`；AGENTS.md 只保留入口和按需读取规则。
- `team`：真实事实只进入组织批准的受控团队载体；AGENTS.md 记录载体路径、访问条件和脱敏/对外规则，不记录凭证或高敏个人身份号。

## 第三步：生成法律安全基线

<!-- skill-lint:constraint PRIVACY-MINIMUM-CONTEXT -->
M4/M5 必须覆盖四项契约，且项目配置不得直接包含凭证、高敏身份号或与协作无关的可识别案件信息：

- 权限契约：读、写、外发、提交、删除、支付分别需要什么授权；外部或不可逆动作必须逐项确认。
- 保密契约：默认最小必要上下文；禁止把客户材料、身份号码、凭证或未脱敏事实写入公开配置、日志、提交或外部服务。
- 溯源契约：区分材料事实、推断与建议；法律结论保留来源、时间和适用范围；信息不足时明确缺口。
- 人工裁决契约：AI 不作最终法律判断；期限、金额、主体、法条引用和对外交付必须由指定人员复核。

回溯载体按事实性质选择，并优先复用项目已有权威来源：

- 决策/取舍 → 已有 `DECISIONS.md` 或项目指定决策载体；
- 证据材料新增、来源或证明目的变化 → 证据目录/证据索引/项目指定证据日志；
- 期限与责任人 → 已有 `TASKS.md`、期限台账或经授权的日历；
- 交付物版本和用户可见变化 → `CHANGELOG.md` 或项目指定交付记录。

项目未启用某类文件时先询问或标记待补充，不为形式完整创建空文档。详见 [references/06-audit-trail-contract.md](references/06-audit-trail-contract.md)。

## 第四步：生成最小项目上下文

M6—M8 默认只生成：

```markdown
# 项目：{项目代号}

- 类型：{项目类型}
- 阶段：{当前阶段}
- 关键时点：{日期 + 事项；未知则写待补充}
- 受控事实入口：{不需要则写“无”}
- 文件结构与权威载体：{沿用项目现有约定}
```

不要默认询问或写入完整当事人、真实案号、金额、统一社会信用代码。确需使用真实事实时，根据隐私模式写入受控载体。项目类型只用于决定下一条必要问题，参见 [references/12-module-project-context.md](references/12-module-project-context.md) 和 [references/13-module-case-facts.md](references/13-module-case-facts.md)。

若检测到 `project-init` 复合证据，只补法律安全、回溯和受控上下文入口，不改项目脚手架。

## 第五步：用稳定受管区块预览

每个模块使用固定 `block-id`，一次只更新一个逻辑区块：

| 内容 | block-id |
|---|---|
| 角色 | `m1-role` |
| 工作流 | `m2-workflow` |
| 协作偏好 | `m3-collab-style` |
| 法律安全基线（含 M4） | `legal-safety-baseline` |
| 回溯契约 | `m5-traceability` |
| 项目上下文 | `m6-project-context` |
| 受控事实入口 | `m7-fact-entry` |
| 文件结构 | `m8-file-structure` |
| 初始化环境（受 `legal-harness-init` 自动 append） | `init-environment` |

<!-- skill-lint:constraint MANAGED-BLOCK-SAFE-UPSERT -->
`write.sh` 必须自动添加形如 `<!-- legal-harness-init:m1-role:start -->` 的唯一成对 marker，并按实际目标路径去重；内容临时文件不得自行添加外层 marker。先运行内容校验，再用 `--dry-run` 展示合并候选 diff。

## 第六步：校验并安全写入

```bash
bash scripts/validate-content.sh \
  --file <模块内容文件> \
  --privacy-mode <strict|local|team>

bash scripts/write.sh \
  --content-file <模块内容文件> \
  --level <user|project> \
  --platforms <key,key> \
  --mode <create|update|append> \
  --block-id <稳定-id> \
  --privacy-mode <strict|local|team> \
  --project-dir <项目路径> \
  --dry-run
```

确认 diff 后去掉 `--dry-run`。脚本必须：

- 按实际目标路径去重；Codex + OpenClaw 同指向项目 `AGENTS.md` 时只写一次；
- 校验 marker 与敏感信息后，在目标同目录构造候选并原子替换；
- 保存首次写入前的 `.bak.legal-harness-init` 及权限/哈希元数据，并为每次变化保存唯一快照；
- 将用户级配置、原始备份、快照和元数据收紧为 `0600`；
- 第二次写入相同内容时报告 `unchanged`，不产生新快照。

需要回退时：

```bash
bash scripts/restore.sh --target <AGENTS.md-or-CLAUDE.md>
```

平台路径与非 AGENTS.md 模式限制见 [scripts/README.md](scripts/README.md)。

## 第六步半：记录初始化环境

`write.sh` 完成后，在被初始化的项目里 append 一条"用了哪个 harness / 哪个 model / 哪个 init skill 版本 / 什么操作"到 AGENTS.md 的 `init-environment` 受管区块，作为将来追溯"问题出在 harness 还是 model 层"的依据。详见 [references/22-initialization-environment.md](references/22-initialization-environment.md) 与 [templates/modules/init-environment.md](templates/modules/init-environment.md)。

```bash
bash scripts/record-init-env.sh \
  --target <项目/AGENTS.md|CLAUDE.md> \
  --action <init|update|append> \
  [--model <model-name>] \
  [--harness <key>] \
  [--harness-version <v>] \
  [--skill-version <v>] \
  [--note "<额外说明>"] \
  [--dry-run]
```

脚本半自动采集，env 全部命中即可直接调用：

- harness(name)：默认 source `detect.sh` 取 `current_runtime`（schema v3）；可用 `--harness` 显式覆盖
- harness version：探测 `claude --version` / `codex --version`（2s 超时，失败 `unknown`）；非 claude/codex 写 `n/a`
- model：env 白名单 `ANTHROPIC_MODEL` / `OPENAI_MODEL` / `CLAUDE_MODEL` / `GLM_MODEL` / `MY_MODEL` 探测，**全部未命中时拒绝 append 并要求 `--model` 兜底**（不臆造）
- init skill version：从本 skill 根 `SKILL.md` frontmatter `version` 字段读

脚本必须：

- 用受管 marker 包裹，append-only 表格行（不覆盖历史）
- 区块残缺（只 start 或只 end）拒绝 append，提示人工修复
- 失败关闭：参数非法、target 不存在、candidate marker 不完整或整体结构异常均拒绝
- 表格行数 >50 时 stderr 软提示归档（不阻断）

<!-- skill-lint:constraint INIT-ENVIRONMENT-RECORD-ON-WRITE -->
每次 `write.sh` 真实落盘（不是 dry-run、不是 needs_confirmation）后都必须再调一次 `record-init-env.sh`；缺这条记录等同于"配置改了但没记工具环境"。无法获得 model 时不臆造，必须显式传 `--model` 或回退到 NOT_VERIFIED。

## 第七步：在新会话验证生效

按 [references/19-activation-verification.md](references/19-activation-verification.md) 新启动目标 harness 会话，确认加载来源，并执行四类探针：权限、保密、信息缺口、回溯载体选择。

将证据保存为本地临时 `key=value` 文件后运行：

```bash
bash scripts/verify.sh \
  --target <配置文件> \
  --block-id <稳定-id> \
  --session-evidence <证据文件>
```

证据必须包含 `new_session=true`、`loaded=true`、精确 `source_path`、与当前配置一致的 `config_sha256`，以及四项 `probe_*=pass` 才可报告 `BEHAVIOR_VERIFIED`。配置变化后旧证据失效；当前写入会话的自报不算加载证据。

## 验收

运行：

```bash
bash scripts/test.sh
```

交付前确认：

- 默认产物没有真实可识别案件信息或凭证；
- 已有文件的非受管内容完整保留；
- 多平台同路径只写一次，重复执行零 diff；
- 原始内容、权限和哈希可恢复；
- 最终状态没有把 `CONFIG_WRITTEN` 扩大成已加载或行为已验证；
- 无法新启会话时明确报告 `NOT_VERIFIED`；
- 每次 `write.sh` 真实落盘后都已 `record-init-env.sh` 追加一条 init-environment 行；缺记录时报告 `INIT_ENV_NOT_RECORDED` 而非宣称完成。

## 依赖

日常初始化开箱即用，无第三方包。需要 Bash 3.2+ 及常见系统工具：`awk`、`grep`、`sed`、`stat`、`diff`、`mktemp`、`shasum` 或 `sha256sum`。正式指令稳定性 checker 另需系统自带或已安装的 Python 3，不需要额外 Python 包。

## 禁止事项

- 禁止替用户决定权限、保密边界或最终法律结论。
- 禁止把真实案件详情、客户材料或凭证直接写入用户级配置或公开项目配置。
- 禁止覆盖、删除或重排受管 marker 之外的用户内容。
- 禁止在 marker 残缺、内容校验失败或目标不明确时写入。
- 禁止将旧会话、当前写入进程或静态检查当作新会话加载证据。
- 禁止为了“留痕完整”擅自创建不适用的 DECISIONS、TASKS 或 CHANGELOG。
- 禁止在 `record-init-env.sh` 探测不到 model 时臆造 model 名；必须 `--model` 兜底或留 `unknown` 并标 `INIT_ENV_NOT_VERIFIED`。
- 禁止手改 `init-environment` 受管区块里的表格行；append-only 由脚本负责。
