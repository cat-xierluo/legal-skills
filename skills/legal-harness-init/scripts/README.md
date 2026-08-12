# scripts/

本目录是 legal-harness-init skill 的**唯一可执行代码产出**。

## detect.sh

一次性环境检测，输出结构化 JSON 到 stdout。

### 用法

```bash
bash scripts/detect.sh
```

或从 SKILL.md 工作流第零步调用，agent 拿到 stdout 后决定后续动作。

### 退出码

- `0`：检测到至少一个 harness 平台（CC / Codex / OpenClaw / QoderWork）
- `1`：未检测到任何 harness 平台（agent 会提示用户先安装）

### 输出 Schema（v1）

```json
{
  "schema_version": "1",
  "harnesses_detected": ["claude-code", "codex", "openclaw", "qoderwork"],
  "user_level_files": {
    "claude-code": {"exists": true, "path": "/Users/.../.claude/CLAUDE.md", "lines": 42},
    "codex": {"exists": false, "path": "/Users/.../.codex/AGENTS.md", "lines": 0}
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

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 当前固定为 `"1"`；日后字段增删会递增 |
| `harnesses_detected` | string[] | 按检测顺序，4 平台中已安装的子集 |
| `user_level_files` | object | key = 平台名（`claude-code`/`codex`/`openclaw`/`qoderwork`） |
| `user_level_files.<plat>.exists` | bool | 该平台用户级配置文件是否存在 |
| `user_level_files.<plat>.path` | string | 绝对路径（`$HOME` 展开） |
| `user_level_files.<plat>.lines` | number | 文件行数；不存在为 `0` |
| `project_level.cwd` | string | 当前工作目录绝对路径 |
| `project_level.agents_md_exists` / `claude_md_exists` | bool | 项目根目录对应文件是否存在 |
| `project_level.agents_md_lines` / `claude_md_lines` | number | 对应行数 |
| `project_level.project_init_ran` | bool | 是否检测到 `project-init` 痕迹（`SKILL.md` 由 project-init 在 `~/.codex`/`~/.claude` 中残留结构推断） |
| `project_level.evidence` | string[] | 触发 `project_init_ran=true` 的目录列表（`.claude/skills/`、`docs/` 等） |

### 隐私边界

detect.sh **只做以下检查**，不会读取 `CLAUDE.md` / `AGENTS.md` 的实际内容，也**不访问 `.env`、环境变量、凭证、用户名、密钥等敏感信息**：

- 检查 4 个 harness 配置目录是否存在（`[ -d ]`）
- 检查用户级配置文件是否存在并统计行数（`wc -l`）
- 检查当前 cwd 的 `AGENTS.md` / `CLAUDE.md` 是否存在并统计行数
- 检查 `.claude/skills/` 和 `docs/` 目录是否存在

**不会**：

- 访问 `~/.ssh/`、`~/.aws/`、网络、日志文件或其他敏感目录
- 读取 `.env`、环境变量、Token、凭证、用户名、密码、密钥
- 写入任何文件

### 依赖

仅使用 shell 标准工具：`bash`、`grep`、`stat`（间接）、`wc`、`pwd`、标准 I/O 与数组。可在 macOS 默认 bash 3.2 与 Linux bash 5+ 上运行。

## 维护原则

- 新增字段：`schema_version` 必须递增；老字段可保留
- 隐私边界：**永远不**读取 harness 配置文件内容，只读取元数据
- 退出码：`0` = 有 harness；`1` = 没 harness；其他 = 工具错误（建议加 stderr 行）
- 测试：在跑通 `bash scripts/detect.sh | python3 -m json.tool` 不报错的最小项目上至少测一次
