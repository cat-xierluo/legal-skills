# 按需 CLI backend

## 选择合同

重点支持独立 ZCode CLI 和独立 MiniMax Code CLI。保留 CodeBuddy，新增独立 Qoder CN CLI 与千问办公入口。所有这些 backend 只在用户明确指定时选用，不进入日常 Claude Code/Codex worker 池，也不因余额/额度不足自动回退。支持集合以 `config/harness-backend-policy.json` 的 hosts 为机械权限权威，dispatch_selection 说明选择规则。

| 产品 | backend | CLI | 配置与权限 | 验证状态 |
|---|---|---|---|---|
| 独立 ZCode CLI | `zcode-cli` | `zcode` TUI / `--prompt` | 原生会话配置；默认 `build`，`edit/yolo` 须显式选择 | help/argv、原生 TUI 模型切换与 BigModel 短请求已核对；Orca 生命周期 `NOT_VERIFIED` |
| 独立 MiniMax Code | `minimax-code`（`mcode` 别名） | `mcode` TUI / `mcode exec` | 原生 Session/Run 模型；exec 默认 `smart` | help/exec help/argv 已核对；provider/Orca 生命周期 `NOT_VERIFIED` |
| CodeBuddy | `codebuddy` | `codebuddy` | 沿用既有 settings/hook 集成 | 本次保留；未重测 live 生命周期 |
| 独立 Qoder CN | `qoder-cn`（`qoderclicn` 别名） | 独立安装的 `qoderclicn` | 原生 auto；不继承旧 QoderWork 模型表或 hook 保证 | 官方参数/隔离 argv 已核对；本机独立入口未安装、live `NOT_VERIFIED` |
| 千问办公 | `qwenwork-cn` | 指定 bundle 的 `qoderclicn`；原生工具是 `qwenwork` | 需显式独立 config-dir；见 ref 27 | help 已核对；账号/provider `NOT_VERIFIED` |
| 旧 ZCode driver | `zcode` | Skill app-server driver | 仍要求私有 `--settings`，且目标 runtime 必须接受隔离参数 | 沿用 ref 24，不作为独立 CLI 默认入口 |

## 启动配方

先检查本地已安装 CLI，不自动安装、登录、复制凭证或改全局默认模型：

```bash
bash scripts/check-dependencies.sh --backend zcode-cli --backend minimax-code
zcode --help
mcode --help
mcode exec --help
```

渲染交互式命令（便于持续巡检和纠偏）：

```bash
bash scripts/render-runtime-profile.sh --backend zcode-cli --output shell
bash scripts/render-runtime-profile.sh --backend minimax-code --output shell
bash scripts/render-runtime-profile.sh --backend qoder-cn --bin /absolute/path/qoderclicn --output shell
```

自包含短任务可渲染 batch（原任务仍须通过完整价值/验证合同）：

```bash
bash scripts/render-runtime-profile.sh --backend zcode-cli --mode batch \
  --permission-mode edit --prompt-file /absolute/path/task.md --output shell
bash scripts/render-runtime-profile.sh --backend minimax-code --mode batch \
  --model '<provider/model>' --prompt-file /absolute/path/task.md --output shell
```

MiniMax batch 使用 `exec --permission smart --output-format stream-json --input -`；stdin 原样读取 prompt。交互模式仅 `-m` 覆盖当前 Session，不能传 headless 的 `--permission`。ZCode 启动帮助未提供 `--model`，renderer 在传模型时拒绝，不能静默忽略或改共享配置；按原生 `/model list` 与 `/model <provider/model>` 明确选择；BigModel 套餐认证、reasoning 必填与静默回落风险读取 [独立 CLI 的 BigModel 实测](28-zcode-cli-bigmodel-coding-plan.md)。ZCode renderer 显式默认 `--mode build`，避免 CLI `--prompt` 的原生 yolo 默认隐式扩大权限。

用渲染后的 WORKER_COMMAND 交给 `spawn-worker.sh --worker-backend ... --command ...`；ZCode CLI、MiniMax Code、Qoder CN 尚无本 Skill 已配置的 PreToolUse 集成，必须显式传 `--allow-prompt-only-install-guard '<授权来源>'`。本次增加支持不授权实际派发、安装、push/PR 或 bypass 模式；按真实任务授权运行。不要自动应答未验证 CLI 的 trust/permission dialog。

## 身份与失败边界

- 移除 QoderWork：旧 backend/别名拒绝；命令实路径含 QoderWork 的软链也拒绝。只改 backend 标签不能把旧产品伪装成新产品。
- 同名 qoderclicn：千问 bundle 只认 `qwenwork-cn`；独立 Qoder CN 只认 `qoder-cn`。千问 bundle 的配置目录必须显式提供且存在，不能从产品同源推断账号/额度共享。
- 默认路由：route_suggest 自动 provider 补选仍只处理 Claude Code，新可选 backend 不加入 tier_policy。
- 新 backend 优先 terminal-managed/tmux。仅帮助和隔离 stub argv 通过不证明真实模型写文件、持续交互、hook 或 supervised 成功；真实 `worker_done → Delivery → settlement → ack` 缺失则 `NOT_VERIFIED`。

## 依赖与来源

现有依赖之外，只需用户自行安装对应 CLI；Qoder CN 独立安装文档为 [官方安装与升级](https://docs.qoder.cn/cli/installation)，常规 npm 入口是 `@qodercn-ai/qoderclicn`，安装先遵循本机依赖纪律。本 Skill 不执行安装。MiniMax Code 的运行时依赖和安装方式以 [官方仓库](https://github.com/MiniMax-AI/minimax-code) 为准。Qoder 参数以 [官方 CLI 参考](https://docs.qoder.cn/cli/cli-reference) 与运行中 help 为准。

2026-09-30 本机观测：独立 ZCode help 显示 TUI、prompt、mode；MiniMax Code help 与 exec help 显示 Session 模型、stdin 与 permission；旧 QoderWork 的 PATH 软链目标不存在。只记录入口行为，不打印用户配置、凭证或 session 数据。
