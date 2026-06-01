# 模型选择与执行模式矩阵

> 本文档为 SKILL.md 的 Level 2 参考文档，提供模型路由和执行模式选择的完整细节。
> 读取时机：规划并行任务、为 Agent 分配模型、选择 Subagent / Agent Teams / tmux 时。

---

## 1. 模型分级（L0 / L1 / L2）

### 1.1 能力定义

| 级别 | 定位 | 典型模型 | 适合任务 |
|------|------|---------|---------|
| **L0 轻量** | 快速、低成本 | Haiku / Flash | 单文件改动、i18n、翻译、配置调整 |
| **L1 标准** | 平衡性价比 | Sonnet | 多文件但边界清晰的功能、bug 修复 |
| **L2 重型** | 深度理解 | Opus | 架构重构、跨模块集成、首次探索陌生代码库 |

### 1.2 任务-模型路由

| 任务特征 | 推荐级别 | 判断关键词 |
|---------|---------|-----------|
| 单文件改动、逻辑简单 | L0 | "添加"、"补充"、"翻译"、"复制" |
| 多文件但边界清晰 | L1 | 默认 |
| 需理解现有架构 | L1→L2 | "修改"、"重构" |
| 跨模块集成 | L2 | "理解"、"分析"、"设计" |
| 架构级重构 | L2 | "拆分"、"重写" |
| 首次探索陌生代码库 | L2 | "探索"、"调研" |

**经验法则**：任务描述包含"理解/分析/重构/设计"→ L2；包含"添加/补充/翻译/复制"→ L0；其余默认 L1。

### 1.3 各执行模式下指定模型

**Agent Teams 模式**：创建 Teammate 时直接指定 model 参数（`haiku` / `sonnet` / `opus`）。

**tmux 降级模式**：

```bash
# 启动 Claude Code 后切换模型
tmux send-keys -t session-name "/model" Enter
sleep 1
# 用 Up/Down 导航到目标模型（次数取决于菜单排序）
for i in 1 2 3; do tmux send-keys -t session-name Down; sleep 0.05; done
tmux send-keys -t session-name Enter
```

或在 prompt 文件开头声明模型偏好：

```
[模型建议: 这是 i18n 任务，适合轻量模型。请先 /model 切换。]
```

### 1.4 运行时升降级

**升级（→ L2）**：Agent 反复失败 >2 次、任务复杂度超预期

**降级（→ L0）**：架构设计完成进入实现、剩余为重复性工作

Agent Teams 模式下模型在创建时指定，升降级需重新创建 Teammate。

tmux 降级模式下：

```bash
# 中断 Agent 并切换模型
tmux send-keys -t session-name C-c
sleep 0.5
tmux send-keys -t session-name "/model" Enter
# 导航到目标模型后继续
tmux send-keys -t session-name -l -- "模型已升级，继续刚才的任务。"
tmux send-keys -t session-name Enter
```

### 1.5 批量调度模板

```bash
# tasks.conf 格式: name  worktree路径  模型级别  prompt文件
worker-1  .claude/worktrees/i18n-fixes    L0  /tmp/task-i18n.txt
worker-2  .claude/worktrees/file-ops      L1  /tmp/task-fileops.txt
worker-3  .claude/worktrees/refactor-core L2  /tmp/task-refactor.txt
```

---

## 2. 执行模式选择

### 2.1 三元对比：Subagent / Agent Teams / tmux Session

| 维度 | Subagent（Agent tool） | Agent Teams（Teammate） | tmux Session |
|------|----------------------|----------------------|-------------|
| **上下文** | 共享父会话（受窗口大小影响） | 独立完整上下文 | 独立完整上下文 |
| **可见性** | 后台运行 | 独立终端窗格（split-panes） | 独立终端 pane |
| **通信** | 单向汇报 | 双向邮箱 + 共享任务列表 | send-keys + capture-pane |
| **生命周期** | 随父会话结束 | 随团队结束 | 独立存活 |
| **模型** | 继承父会话 | 创建时独立指定 | 运行时切换 |
| **文件隔离** | 在当前目录操作 | worktree + 分支 | worktree + 分支 |
| **任务管理** | 无 | 共享任务列表（pending/in-progress/completed） | 外部脚本 |
| **Agent 间协作** | 不支持 | 支持邮箱通信 | 不支持 |
| **启动开销** | 几乎为零 | 低 | 中等 |
| **适合时长** | ≤15 分钟 | 小时级 | 小时级 |
| **并发上限** | 受上下文/API 限制 | 团队规模 | tmux session 数量 |
| **可靠性** | 高（内置） | 高（官方内置） | 中（send-keys 脆弱） |
| **环境要求** | 通用 | Claude Code + feature flag | tmux + 终端 |

### 2.2 路由矩阵

| 任务特征 | 推荐模式 | 理由 |
|---------|---------|------|
| Code review 一个 PR | Subagent | 明确、短、无需隔离 |
| 研究技术问题 | Subagent | 纯信息收集 |
| 快速修复 bug（单分支） | Subagent | 改动小 |
| 新增完整功能模块 | **Agent Teams**（或 tmux） | 需独立上下文、长时间 |
| 并行 2+ 个独立功能 | **Agent Teams**（或 tmux） | 需文件隔离 |
| 大规模重构 | **Agent Teams**（或 tmux） | 需完整上下文理解 |
| 批量重复操作（i18n） | Subagent × N | 并发效率高 |
| 需要 Agent 间协作 | **Agent Teams** | 唯一支持双向通信 |

**路由决策树**：

```
任务时长 ≤15 分钟？
├─ 是 → Subagent
└─ 否 → 需独立 git 分支？
    ├─ 否 → Subagent
    └─ 是 → 在 Claude Code 中？
        ├─ 是 → Agent Teams 已启用？
        │   ├─ 是 → Agent Teams（split-panes）
        │   └─ 否 → tmux 降级
        └─ 否 → tmux 降级
```

### 2.3 混合模式

```
PM（Team Lead）
├── Subagent A: review PR #1              ← 分钟级，共享上下文
├── Subagent B: 研究 X 接入方案            ← 分钟级，共享上下文
├── Teammate 1: feat/i18n                 ← 小时级，L0，独立上下文
└── Teammate 2: feat/refactor             ← 小时级，L2，独立上下文
```

PM 在等待 Teammate 期间用 Subagent 处理短任务，不空闲。

tmux 降级模式下，将 Teammate 替换为 tmux session 即可。
