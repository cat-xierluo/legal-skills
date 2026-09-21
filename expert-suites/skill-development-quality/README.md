# Skill 开发与质量保障专家套件

> [下载完整专家套件](https://github.com/cat-xierluo/legal-skills/releases/latest/download/suite-skill-development-quality-0.1.0.zip)

用于初始化法律类 Skill 项目、约束 Agent 协作、开展质量审查、执行分层验证，并通过安全的 Git 和多 Agent 流程完成工程收口。

## 适用场景

- 新建或重大改造一个 Skill；
- 为法律项目补齐 Agent 指令、验证合同和协作边界；
- 在多 Agent 或跨平台协作中管理任务交接、Git 分支和完成证据。

## 不适用场景

- 不替代具体法律业务 Skill；
- 不自动批准高风险 Git、发布或外部发送动作；
- 不把静态检查等同于真实行为验证。

## 包含的 Skills

| Skill | 在本套件中的作用 | 单独下载 |
| :--- | :--- | :--- |
| [project-init](../../skills/project-init/) | 初始化项目上下文和最小协作指令 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/project-init-1.2.4.zip) |
| [legal-harness-init](../../skills/legal-harness-init/) | 为法律工作区治理 AGENTS.md、CLAUDE.md 等 Harness | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/legal-harness-init-0.5.2.zip) |
| [skill-lint](../../skills/skill-lint/) | 审查 Skill 结构、指令稳定性、安全和发布质量 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/skill-lint-2.9.0.zip) |
| [verification-gate](../../skills/verification-gate/) | 运行分层验证并记录可复查证据 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/verification-gate-1.3.0.zip) |
| [git-workflow](../../skills/git-workflow/) | 管理分支、Worktree、PR、合并和安全回退 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/git-workflow-1.8.7.zip) |
| [multi-agent-orchestration](../../skills/multi-agent-orchestration/) | 编排两个以上边界独立的本地 Worker | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/multi-agent-orchestration-2.27.4.zip) |
| [cross-agent-coordination](../../skills/cross-agent-coordination/) | 协调不同 Agent 平台的归属、路由和交接 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/cross-agent-coordination-1.0.0.zip) |
| [agent-email](../../skills/agent-email/) | 为 Agent 提供统一邮件收发和任务分发通道 | [下载](https://github.com/cat-xierluo/legal-skills/releases/latest/download/agent-email-0.4.1.zip) |

## 建议使用方式

1. 用 `project-init` 或 `legal-harness-init` 建立项目级约束；
2. 创建或修改 Skill 后，先用 `skill-lint` 做结构与安全审查；
3. 涉及脚本行为时用 `verification-gate` 运行真实分层验证；
4. Git 分支、Worktree 和 PR 交给 `git-workflow`；
5. 只有任务确实可独立拆分时，才引入多 Agent、跨平台协调或 Agent 邮箱。

## 安装方法

下载并解压完整套件 ZIP，把其中 `skills/*` 复制到 Agent 的 Skills 根目录。各 Agent 平台支持的协作方式不同，使用前应阅读对应 Skill 的依赖、权限与安全边界。

## 人工复核与使用边界

任何测试、审查或 Worker 自报都只是证据的一部分。PR 合并、外部发送、凭证配置、分支删除和发布仍应遵循项目权限与人工门禁；无法验证的结果必须标记 `NOT_VERIFIED`。

## 版本与许可证

当前套件版本为 `0.1.0`。套件外层文件按 [LICENSE.txt](LICENSE.txt) 的 MIT License 授权；各成员 Skill 按其目录内 `LICENSE.txt` 分别授权。下载或使用套件不改变成员原有许可条件。
