# 03 - 怎么检测当前环境有哪些 harness

## 一句话结论

"harness" 指的是承载 AI agent 工作的客户端平台（如 Claude Code、Codex、OpenClaw、QoderWork）。每个 harness 读取 AGENTS.md 的路径和语法略有差异。本 skill 的策略是**检测到哪个平台就写入哪个平台**——不主动写你没用过的平台。

## 四个常见 harness

| 平台 | 用户级文件 | 项目级文件 | 检测线索 |
|---|---|---|---|
| **Claude Code** | `~/.claude/CLAUDE.md` | `<项目>/CLAUDE.md`（含 `@include ./AGENTS.md`） | `~/.claude/` 目录存在 |
| **Codex** | `~/.codex/AGENTS.md` | `<项目>/AGENTS.md` | `~/.codex/` 目录存在 |
| **OpenClaw** | `~/.openclaw/AGENTS.md`（或等价） | `<项目>/AGENTS.md` | `~/.openclaw/` 目录存在 |
| **QoderWork** | `~/.qoderworkcn/AGENTS.md`（或等价） | `<项目>/AGENTS.md` | `~/.qoderworkcn/` 目录存在 |

## 本 skill 怎么检测

`scripts/detect.sh` 一次性扫描：

```bash
bash scripts/detect.sh
```

返回结构化 JSON：

```json
{
  "harnesses_detected": ["claude-code", "codex"],
  "user_level_files": {
    "claude-code": {"exists": true, "path": "~/.claude/CLAUDE.md", "lines": 42},
    "codex": {"exists": false, "path": "~/.codex/AGENTS.md", "lines": 0}
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

- 检查 `~/.claude/`、`~/.codex/`、`~/.openclaw/`、`~/.qoderworkcn/` 目录是否存在（`[ -d ]`）
- 检查用户级配置文件是否存在并统计行数（`wc -l`）
- 检查当前 cwd 的 `AGENTS.md` / `CLAUDE.md` 是否存在并统计行数
- 检查 `.claude/skills/` 和 `docs/` 目录是否存在（用于探测 `project-init` 痕迹）

**不读取任何文件内容**——只读取文件元数据（行数）和目录存在性。不会触及 CLAUDE.md / AGENTS.md 里的实际配置。

输出结构化 JSON 到 stdout，由 agent 解析后决定下一步动作。

## 检测到没有 harness 时

如果 `detect.sh` 返回 `harnesses_detected: []`：

- 提示用户"当前环境似乎没安装 Claude Code / Codex 等 AI 客户端"
- 询问"是否要先安装？或你计划用什么平台？"
- 不强行写入（没平台写入毫无意义）

## 接下来读什么

- 8 模块全览 → [references/04-modules.md](04-modules.md)
- 与 `project-init` 的协作细节 → [references/15-sync-with-project-init.md](15-sync-with-project-init.md)