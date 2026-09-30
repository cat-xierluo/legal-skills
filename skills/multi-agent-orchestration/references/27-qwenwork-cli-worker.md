# 千问办公 CLI 支持

千问办公是按需兼容能力，平常不派发此 worker。不要把 Qwen Code (`qwen`) 或独立 Qoder CN 的账号、模型、权限与千问办公混同。

## 两个入口

2026-09-30 对本机 QwenWorkCN 安装的 `--help` 核对：

- `QwenWorkCN.app/Contents/Resources/bin/qwenwork` 是原生办公能力 CLI，提供 `tools`、`user` 等入口；实际办公能力受账号登录和服务端 discovery 控制。该入口不是接受任意编排任务的编码 REPL，不能直接替代 worker command。
- 同 bundle 的 `bin/qoderclicn` 提供 TUI、`-p`、`--config-dir`、`--permission-mode` 等编码 CLI 参数。本 Skill 以 `qwenwork-cn` 明确标识这一 bundled coding 入口，不声称它已能复用千问办公账号/积分。

## 按需接入

只做原生办公能力时，由用户提供已登录的千问办公环境，再读取 `qwenwork --help` / `qwenwork tools` 的真实能力合同；只调用具体任务需要的工具。帮助入口若触发服务端 discovery 且未认证，保留认证失败，不自动登录或复制其他产品 token。不得把 token 放入命令行、日志或 Git。

需要 bundled coding worker 时，准备独立且已确认登录归属的配置目录：

```bash
bash scripts/check-dependencies.sh --backend qwenwork-cn
bash scripts/render-runtime-profile.sh --backend qwenwork-cn \
  --config-dir /absolute/path/private-qwenwork-cli-config --output shell
```

生产入口默认绑定 QwenWorkCN bundle 的 qoderclicn；如传 `--bin`，命令身份仍须匹配此精确 bundle 路径（支持其软链实路径），不得用普通 qoderclicn 冒充。配置目录须存在且为绝对目录；renderer 把它传入 `--config-dir`，spawn/validator 复核。不要复用默认 Qoder 配置来猜测登录共享。模型显式指定或由这份配置的 native 会话决定，不复制历史 QoderWork 模型清单。

默认原生 auto，MCP 默认空配置；未验证的 dialog 不自动应答。编排 hook 尚未接入，spawn 必须显式 `--allow-prompt-only-install-guard '<授权来源>'`；安装与文件 scope 仅提示层约束，PM 必须检查真实产物。默认走 terminal-managed/tmux，STATUS/checkpoint + diff + 验证作为验收来源，不能要求未验证 supervised 通道回报。

## 证据边界

本机 help 与 bundled argv 可核对；原生 tools discovery 实测返回未认证。千问办公账号登录、可用工具、bundled coding 的账号/模型/积分归属，以及完整 worker 交付/Orca 生命周期均为 `NOT_VERIFIED`。这些字段需在用户明确选择此入口时逐项核验，不能从同名 binary 或同源 SDK 推导。
