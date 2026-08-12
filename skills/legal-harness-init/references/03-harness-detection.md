# 03 - 怎么检测当前环境有哪些 harness

## 一句话结论

"harness" 指的是承载 AI agent 工作的客户端平台（如 Claude Code、Codex、OpenClaw、QoderWork）。每个 harness 读取 AGENTS.md 的路径和语法略有差异。本 skill 的策略是**检测到哪个平台就写入哪个平台**——不主动写你没用过的平台。

## 八个 harness 平台

权威表在 [scripts/lib_platforms.sh](../scripts/lib_platforms.sh)（detect/write 共享单一真值源）。

| 平台 | key | config_kind | 用户级文件 | 项目级文件 | 自动写入? |
|---|---|---|---|---|---|
| **Claude Code** | `claude-code` | claude_md | `~/.claude/CLAUDE.md` | `<项目>/CLAUDE.md`（可 `@include ./AGENTS.md`） | ✅ |
| **Codex** | `codex` | agents_md | `~/.codex/AGENTS.md` | `<项目>/AGENTS.md` | ✅ |
| **OpenClaw** | `openclaw` | agents_md | `~/.openclaw/AGENTS.md` | `<项目>/AGENTS.md` | ✅ |
| **MyAgents** | `myagents` | claude_md | `~/.myagents/CLAUDE.md` | `<项目>/CLAUDE.md` | ✅ |
| **QoderWork** | `qoderwork` | non-agents-md | —（`~/.qoderworkcn/` 非 AGENTS.md 模式） | — | ❌ 仅检测 |
| **QwenWork** | `qwenwork` | non-agents-md | —（`~/.qwenworkcn/`） | — | ❌ 仅检测 |
| **WorkBuddy** | `workbuddy` | non-agents-md | —（GUI 任务型） | — | ❌ 仅检测 |
| **Orca** | `orca` | non-agents-md | —（worktree 型） | — | ❌ 仅检测 |

**自动写入边界**：只对 `claude_md` / `agents_md` 平台自动写入（CC / Codex / OpenClaw / MyAgents）。其余 4 个平台不是 AGENTS.md/CLAUDE.md 配置模式（GUI 任务型或 worktree 编排型），写入会无效或破坏——detect 报告里标 `non-agents-md`，write.sh 记 `unsupported` 并提示用户手动配置。

## 当前 runtime 检测（env 标志）

除了"装了哪些"，detect.sh 还报 `current_runtime`——**这次会话正跑在哪个 harness**，通过已知 env 标志变量推断（只看变量是否 set，**不读值**）：

| key | env 标志变量 |
|---|---|
| `claude-code` | `CLAUDECODE` |
| `codex` | `CODEX_HOME` |
| `orca` | `ORCA_AGENT_HOOK_TOKEN` |

优先级：可写平台（claude_md/agents_md）> 容器层（orca 等）。多个命中或都不命中时报 `null`（诚实不强猜）。例如 CC 跑在 Orca 里时，`CLAUDECODE` 与 `ORCA_AGENT_HOOK_TOKEN` 都 set，但 `current_runtime` 报 `claude-code`（agent 层优先于编排层），因为要写入的是 agent 配置（`~/.claude/CLAUDE.md`），不是 Orca。

## 本 skill 怎么检测

`scripts/detect.sh` 一次性扫描：

```bash
bash scripts/detect.sh
```

返回结构化 JSON（schema v2）：

```json
{
  "schema_version": "2",
  "current_runtime": "claude-code",
  "current_runtime_writeable": true,
  "harnesses_detected": ["claude-code", "codex", "openclaw", "myagents"],
  "user_level_files": {
    "claude-code": {"exists": true, "path": "~/.claude/CLAUDE.md", "lines": 42, "config_kind": "claude_md"},
    "codex": {"exists": false, "path": "~/.codex/AGENTS.md", "lines": 0, "config_kind": "agents_md"}
  },
  "project_level": {
    "cwd": "/path/to/project",
    "agents_md_exists": true,
    "agents_md_lines": 30,
    "claude_md_exists": true,
    "claude_md_lines": 5,
    "project_init_ran": true,
    "evidence": [".claude/skills/", "docs/"]
  }
}
```

字段说明：

- `schema_version`：`"2"`（v1 不含 `current_runtime` / `config_kind`；老调用方忽略新字段不影响）
- `current_runtime`：这次会话正跑在哪个 harness（env 标志推断）；`null` = 无法确定
- `current_runtime_writeable`：当前 runtime 是否支持自动写入
- `harnesses_detected`：本机已装平台 key 列表（通过目录 + 文件痕迹验证）
- `user_level_files.<key>.config_kind`：`claude_md` / `agents_md` / `non-agents-md`——决定 write.sh 是否自动写入

agent 拿到这个 JSON 后决定：

- 写入哪些用户级文件（只写检测到的平台）
- 项目级是否要 append/覆盖/合并
- 是否提示"建议先跑 `project-init`"

## 检测不到的常见情况

| 情况 | 现象 | 处理 |
|---|---|---|
| 平台未安装 | `~/.claude/` 不存在 | 跳过该平台，仅写已安装的 |
| 平台刚装但无配置文件 | `~/.claude/` 存在但 `CLAUDE.md` 不存在 | 提示"首次使用，将创建 CLAUDE.md" |
| 项目是新目录 | 当前 cwd 无 `AGENTS.md` / `CLAUDE.md` | 提示"将创建新文件" |
| 项目已跑过 `project-init` | 检测到 `.claude/skills/` 和 `docs/` | 只补法律人三块，不重写 |

## 多平台的写入策略

**用户级**：每个平台**独立维护**自己的文件，不要用 `@include`（不在同一目录）。本 skill 给每个平台各自生成一份等价但适配格式的内容。

**项目级**：项目内一份 `AGENTS.md` 作为真值源。

- Claude Code 的 `CLAUDE.md` 通常内容是 `@include ./AGENTS.md`（CC 支持 `@include`）
- 其他平台直接用 `AGENTS.md`

**单一维护原则**：项目内只维护一份 `AGENTS.md`，所有平台的入口都指向它，避免多份内容漂移。

## 检测脚本的隐私边界

`scripts/detect.sh` 只做以下检查：

- 检查 8 个 harness 目录是否存在（`~/.claude/` / `~/.codex/` / `~/.openclaw/` / `~/.myagents/` / `~/.qoderworkcn/` / `~/.qwenworkcn/` / `~/.workbuddy/` / `~/.orca/`，用 `[ -d ]`）
- 个别平台加文件痕迹验证（如 `~/.openclaw/cron/jobs.json`、`~/.workbuddy/workbuddy.db`），避免目录存在但平台未真正安装的误报
- 检查用户级配置文件是否存在并统计行数（`wc -l`）
- 检查已知 harness 的 **runtime 标志环境变量是否存在**（`CLAUDECODE` / `CODEX_HOME` / `ORCA_AGENT_HOOK_TOKEN`）——**只看变量是否 set，不读其值**（值可能含 token）
- 检查当前 cwd 的 `AGENTS.md` / `CLAUDE.md` 是否存在并统计行数
- 检查 `.claude/skills/` 和 `docs/` 目录是否存在（用于探测 `project-init` 痕迹）

**不读取任何文件内容**——只读文件元数据（行数）、目录存在性、env 标志存在性。不会触及 CLAUDE.md / AGENTS.md 里的实际配置，**不读** `.env` / 凭证 / token / 用户名 / 密钥的值。

输出结构化 JSON 到 stdout，由 agent 解析后决定下一步动作。

## 检测到没有 harness 时

如果 `detect.sh` 返回 `harnesses_detected: []`：

- 提示用户"当前环境似乎没安装 Claude Code / Codex 等 AI 客户端"
- 询问"是否要先安装？或你计划用什么平台？"
- 不强行写入（没平台写入毫无意义）

## 接下来读什么

- 8 模块全览 → [references/04-modules.md](04-modules.md)
- 与 `project-init` 的协作细节 → [references/15-sync-with-project-init.md](15-sync-with-project-init.md)