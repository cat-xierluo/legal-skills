# 常用 CLI 参数与读取路由

目录：[入口](#1-先按任务选入口) · [公共参数](#2-renderer-公共参数) · [Claude](#3-claude-code) · [Codex](#4-codex) · [生成后检查](#5-生成后检查与推荐)

在已选定 backend、准备渲染启动命令时读取本页。派发流程从 [SKILL.md](../SKILL.md) 开始；backend 的机械许可由 [harness policy](../config/harness-backend-policy.json) 决定，具体模式由 [dispatch profile](32-dispatch-profiles.md) 决定。

`render-runtime-profile.sh` 只生成命令和上下文，不创建工作树、运行 Agent 或投递任务。生成命令不代表准入通过；交给正式 spawn 入口，继续使用同一任务的范围、验证、预算和身份。

## 1. 先按任务选入口

| 已选入口 | 操作资料 | 选择边界 |
|---|---|---|
| Claude Code | 本页 §3 | 日常 worker；provider/OAuth 明确区分 |
| Codex | 本页 §4 | 日常可选；仍消费个人配置与本轮授权 |
| CodeBuddy | [08 操作指南](08-codebuddy-cli-worker.md) | 用户明确指定时使用 |
| 独立 ZCode CLI | [28 模型与套餐](28-zcode-cli-bigmodel-coding-plan.md)、[30 原生 Orca](30-zcode-native-orca.md) | 用户明确指定；长程使用原生交互 CLI |
| MiniMax Code | [26 按需 backend](26-optional-cli-backends.md) | 用户明确指定；默认 Orca，保留显式直连 |
| 独立 Qoder CN / 千问办公 | [26](26-optional-cli-backends.md)、[27](27-qwenwork-cli-worker.md) | 两个配置与身份边界不同的入口 |
| legacy ZCode driver | [09 兼容入口](09-zcode-cli-worker.md)、[24 安全合同](24-zcode-driver-safety.md) | 不代表独立原生 CLI；先核配置隔离能力 |
| ZCode GUI | [34 GUI 操作](34-zcode-desktop-remote.md)、[35 驱动](35-zcode-browser-automation.md) | 浏览器路线，不能套 CLI backend 身份 |

QoderWork 已移除。OpenCode/custom 的历史 renderer 能输出命令，但正式 spawn 不据此允许该 backend；Kimi/Gemini/Rudder 的历史研究同样不是派发许可。Hermes 的 PM host 权限按 policy 判定，不等于存在 Hermes worker backend。

不要把这张表维护为本机软件资产表或模型推荐榜。当前模型/额度读取已选配置与真实可用入口；任务匹配读取 [01](01-model-selection-matrix.md)，日常与显式选择边界读取 SKILL。

## 2. renderer 公共参数

从项目工作区使用 Skill 脚本的确定路径。以下命令均仅生成文本，示例模型和路径需由本轮已核输入替换。

| 参数 | 含义与限制 |
|---|---|
| `--backend` | 必选；renderer 支持列表不等于 spawn 白名单 |
| `--mode interactive\|batch` | 默认 interactive；按任务选择，不因批处理可渲染就替换长程交互任务 |
| `--model` | 指定已选择的模型；独立 ZCode CLI 拒绝此启动参数，须原生会话选择 |
| `--runtime-profile` | 写入生成上下文的 profile 标签，不单独授予权限 |
| `--api-provider` / `--provider-slot` | provider 与并发槽位标签；实际额度/lease 仍由正式入口校验 |
| `--prompt-file` | batch 必需，指向本轮确定的任务文件 |
| `--output command` | 只输出启动命令字符串，适合供 spawn 的 `--command` 消费 |
| `--output shell` | 默认；输出命令及上下文变量，先核来源和字段再消费 |
| `--output prompt-context` | 输出描述上下文；不是实际启动回执 |

保持完整 command 的参数和引用，不手工拆引号，不将任务正文当 shell 代码拼接。正式启动和完成链分别读取 [13](13-orca-cli-worker.md)、[14](14-pm-orchestrate.md)；短路径示例见 [00](00-fast-dispatch-runbook.md)。

## 3. Claude Code

### provider 与 OAuth

第三方 provider 使用 `--settings` 或 `--provider-registry`，同时给精确 `--model`。registry 还需 `--api-provider`；有 models 映射时，renderer 校验别名并生成真实模型名。

```bash
bash scripts/render-runtime-profile.sh \
  --backend claude-code --mode interactive \
  --settings /absolute/private/provider.settings.json \
  --model provider-model --output command
```

renderer 默认包装 `claude-provider-env.sh`，隔离继承的 provider 路由变量，按所选配置设置认证及模型，并使用 `--setting-sources project,local`。不要绕过 wrapper 裸启动，再依赖主终端的配置探针推断 worker provider。

registry 的 `auth_type` 由 registry 决定；settings 路径可通过 `--auth-type` 显式选择脚本支持的方式。真实配置留在私有文件，不能写入任务正文、公共日志或 Git。

已有订阅/OAuth 路线使用 `--backend claude-oauth`；生成命令清理 Anthropic API 路由环境变量。它是既有 Claude 路线，不新增 PM host 或 worker 身份。

### 权限与配置

| renderer 参数 | 当前生成行为 |
|---|---|
| `--permission-mode` | 未指定时 interactive 为 `auto`，batch 为 `acceptEdits`；显式值原样生成 |
| `--no-mcp` | 注入只使用空 MCP 配置的参数；Claude 路线需显式选择 |
| `--setting-sources` | provider wrapper 默认 `project,local`；保留本地 hook 所需配置层 |
| `--claude-bare` | 仅 provider 隔离路线显式选择；会标注 degraded/unhooked，不能据此绕过 spawn 安装门 |
| `--no-provider-env-isolation` | 显式关闭 wrapper 的高级选项；registry 路线拒绝此组合 |

`auto` 的普通 Bash 判断与编排 hook 是不同层。安装、受保护 Git 操作、范围和完成协议仍按 [依赖与授权合同](02-runtime-dependencies.md) 及 SKILL 执行。`--bare`、safe/simple 模式或排除 local 配置可能使 hook 无法证明；缺证时消费正式门的拒绝/显式降级结果。

### 模式与恢复

interactive 保留会话以供观察和纠偏。batch 由 renderer 生成 `-p --verbose --output-format stream-json`，从确定的 prompt 文件输入。不要把短请求成功当作持续任务闭环证明。

恢复既有 worker 时沿原 Session/Task/Dispatch 读取正式恢复动作。CLI 原生 continue/resume 只是工具能力，不能代替编排身份或成为重发完整任务的理由。

## 4. Codex

### 生成命令

```bash
bash scripts/render-runtime-profile.sh \
  --backend codex --mode interactive \
  --model selected-model --codex-profile selected-profile \
  --sandbox danger-full-access --approval never --output command
```

模型/profile 必须是本轮实际选定值；未使用 profile 时省略该参数。不要复制旧软件版本或个人 Spark 配置作为通用默认。

| renderer 参数 | 当前生成行为 |
|---|---|
| `--model` | 生成 Codex `-m` |
| `--codex-profile` | 生成 `-p`；配置文件语法以该实际 CLI 版本为准 |
| `--sandbox` | 默认 `danger-full-access`，显式更窄模式保留 |
| `--approval` | 默认 `never`，仍受宿主实际权限合同约束 |
| `--mode batch --prompt-file` | 生成 `codex exec`，以 stdin 输入本轮文件 |

当 renderer 从可读 launcher 脚本中证明 sandbox/approval 与请求完全一致时，会省略重复 flag；否则显式保留。重复参数报错是启动失败，不代表 Agent 已收到任务。先核 argv、退出码和终端实际进程，不能把业务文本继续发送给已退回的 shell。

配置中的 sandbox 字段、命令行覆盖与实际宿主权限应分别核对。不要凭 profile 名字猜测权限或认证来源，也不要把本机一种 profile 文件布局推广到所有 Codex 版本。

## 5. 生成后检查与推荐

1. 确认选择来源：用户指定的 backend/model，或已配置的日常路由；有额度不等于可自动改用显式限定 backend。
2. 确认 command 中实际 backend、模型、权限、输入方式与任务类型一致；ZCode 原生模型另由会话回读核实。
3. 把 command 交给原任务的 spawn/profile 合同，保留 scope、预算、provider、验证和完成通道；不在本页直接执行裸 CLI 绕过准备阶段。
4. 读取正式回执并核真实运行与输入消费。若未启动或身份不明，按 [排障索引](10-parallel-lessons.md) 回到原任务处理。
5. 任务返回后由 PM 验收产物并结算。输入 accepted、退出码 0 和模型自述都不能单独证明任务交付。

历史 CLI 全表、型号价格、个人默认值和旧实验保存在原维护任务及归档中；本页只维护本 Skill 实际使用的参数合同。参数生成可在无模型请求下验证，真实 backend 功能须另有原生任务证据。
