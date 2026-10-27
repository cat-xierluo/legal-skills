# CLI 命令参考与额度读数合同

本文解决什么问题 / 何时读：需要某个 `magpie` 子命令的准确语法、或需要解读 `magpie quota --json` 的字段时读本文。它覆盖完整的命令面（供应商、订阅、插件、网关、模型与共享配置），并给出额度 JSON 的字段合同。设计决策、变更流程与治理语义不在这里，按[操作入口](operations.md)与[路由治理](routing-governance.md)执行。

命令形态以安装版 `magpie --version` 与对应 `--help` 为准；本文尖括号均为占位。涉及写入的命令遵守[CLI 与变更边界](cli-contract.md)：先只读回读、展示计划、按授权执行、逐项验证。

## 开始之前

```sh
magpie --version
magpie ls            # 本机 agents 与各自当前模型
magpie providers     # 供应商与密钥状态
magpie accounts      # 已登录订阅账号
magpie groups        # 路由组
magpie models        # 全部可选模型，provider/model 形态
```

命令不存在时先解决安装：应用内 Settings › About › Command line › Add to PATH，或直接运行应用内程序（macOS 形如 `/Applications/<app>.app/Contents/MacOS/<binary>`）。任何位置 `-h` / `--help` 只打印帮助，不改动配置。

## 供应商与密钥

```sh
magpie presets                                       # 已知供应商预设
magpie provider add <preset> <your-key>              # 预设供应商 + key（重复执行会另建 <preset>-2）
magpie provider add "<custom-name>" url=https://relay.example.com/v1 key=<your-key>       # 自定义 OpenAI 兼容入口
magpie provider add "<custom-name>" anthropic=https://gw.example.com key=<your-key>       # Anthropic 兼容入口
magpie provider add ollama url=http://127.0.0.1:11434/v1                                   # 本地模型服务
magpie provider test <provider>                      # 对各 endpoint 发最小请求
magpie provider models <provider>                    # 拉取模型列表
magpie provider models <provider> <model-a> <model-b>  # 上游无列表时手工指定
magpie provider fallback <provider> <provider/model>…  # 该供应商额度耗尽或不可用时的落点
magpie provider off|on <provider>                    # 停用（保留配置）或启用
```

`magpie provider --help` 列出自定义供应商支持的全部字段（headers、余额端点、上下文长度、user agent 等）。密钥处置遵守[供应商与账号接入](provider-integration.md)的安全边界：不回显、不写入项目文件、优先交互式输入。

## 订阅与插件账号

```sh
magpie accounts add <agent>          # claude、codex、gemini、antigravity、copilot 等
magpie accounts import <agent>       # 导入既有账号记录（会使原工具登出，需单独确认）
magpie plugin add <plugin-name>      # 社区插件的订阅接入
magpie plugin login <provider>       # 插件账号登录
```

登录窗口由真人完成。限制订阅账号：`magpie provider account-cap <provider> <account> <percent>`（每窗口用量上限百分比）、`magpie provider rpm <provider> <n>`。账号级并发与队列见[供应商与账号接入](provider-integration.md)。

## 指向 agent 与子 agent

```sh
magpie agents                        # 支持的 agent 清单
magpie models <agent>                # 该 agent 可选模型及原因
magpie <agent> <provider/model>      # 设置模型；也可指向 group/<id>
magpie <agent> effort high           # 其他字段按 magpie <agent> --help
magpie <agent> default               # 摘除 Magpie，恢复原状
```

子 agent 可独立指定模型：

```sh
magpie <agent> subagent_model <provider/model>   # 或 group/<id>
magpie <agent> subagent_model default            # 恢复跟随主请求
magpie <agent> subagent_effort low
magpie claude subagent <provider/model>          # claude 的子 agent
```

agent 在启动时读取模型；改完要重启对应客户端。客户端启动行为与坑位见[子Agent模型指定](subagent-models.md)。

## 路由组与规则

```sh
magpie group add "<name>" models=<provider/model>,<provider/model> routing=order
magpie group set <id> models+=<provider/model>     # 追加；models-= 删除
magpie group set <id> stays=session                # 会话粘住同一账号
magpie group add <id> models='<provider/*:free>' routing=order   # 通配模式，注意引号
magpie group template                              # 按本机已有模型生成现成组
magpie group template <kind>                       # 直接建某类模板组（先列 kinds 再问）
magpie <agent> group/<id>                          # agent 绑定组
```

routing 模式：`order` 按序尝试；`smart`（默认）偏好临近续期的订阅；`usage`、`pace`、`rotate`、`weight`、`manual` 见 `magpie group --help`。`group add` 同名即整体替换，先 `magpie groups` 确认；随附脚本拒绝对同名组写入，语义见[CLI 与变更边界](cli-contract.md)。

规则首条命中即生效，其余成员保持回退：

```sh
magpie group rule add <id> use=<member> time=09:00-18:00 days=mon-fri tz=<zone>
magpie group rule add <id> use=<member> time=09:00-18:00@<zone>       # 等价写法
magpie group rule add <id> pause=<member> time=22:00-08:00            # 夜间移出
magpie group rule add <id> use=<member> tokens=200k                   # 长请求
magpie group rule add <id> use=<member> images                        # 带图请求
magpie group rule add <id> use=<member> compact                       # 压缩摘要
magpie group rule add <id> use=<member> folders=~/<project>           # 指定项目
magpie group rule add <id> use=<member> agents=<agent>                # 指定客户端
magpie group rule add <id> use=<member> intent="<意图描述>" classifier=<small-model>
magpie group rule <id>          # 规则列表（带序号）
magpie group rule rm <id> <n>   # 删除后序号变化，批量按倒序
magpie group rule mv <id> <n> <to>
```

`use` 只是把目标提到前面，其余成员仍可回退；`pause` 是硬排除。不带 `tz=` 时按本机时钟。规则语义、坑位与实测差异见[路由治理](routing-governance.md)；嵌套入口组的设计与结构校验见[智能路由设计](adaptive-routing-design.md)。

## 网关、其他设备与预算

前提：应用内 Settings › Network and sharing › Share on local network 开启。

```sh
magpie gateway-key add <name>                 # 打印新 key
magpie gateway-key list
magpie gateway-key limit <id> month --cost 20 # 预算；周期：day、week、month、10d、5h
magpie gateway-key limit <id> add day --tokens 2m   # 叠加限制；全部满足才放行
magpie gateway-key models <id> '<provider/*>' group/<id>   # 限定可用模型
magpie gateway-key limit <id> off
```

订阅类账号仅供账号所有者使用；不为他人搭建可消耗订阅额度的网关 key，他人用 key 时以 API 计费供应商承载。key 回显与落盘遵守[安全边界](provider-integration.md#安全边界)。

## 模型呈现与共享配置

```sh
magpie model name <provider/model> "<display-name>"   # 全局显示名
magpie model disable '<pattern>'                      # 全路由拒绝；enable 恢复
magpie model price <provider/model> <in>,<out>,<cache-read>,<cache-write>   # USD / 1M tokens
magpie model context <provider/model> <length>
magpie visible <agent> <provider|family|group>,…      # 客户端只显示这些；all 恢复
```

```sh
magpie library                                        # 各 agent 共享配置
magpie library mcp add <name> <url-or-command> agents=<agent>,<agent>
magpie library instructions set <file>                # 所有 agent 读取的指令（- 为 stdin）
magpie library instructions agents <agent>,<agent>
magpie library skill agents <skill> <agent>,<agent>   # skill 由应用 Library › Market 添加
magpie search add <provider> [<key>]                  # 无 key 的免费源可直接加
```

## 运行与维护

```sh
magpie healthcheck          # exit 0 = 网关应答
magpie daemon install       # 网关常驻服务（仅明确要求时）
magpie web --lan            # 浏览器访问应用界面
magpie backup <file>        # 全量备份（口令密封）；magpie restore <file>
magpie usage 7d             # 按 agent、模型、账号的用量聚合
magpie quota                # 人读表格；--json 见下节
```

## 额度读数合同（magpie quota --json）

`magpie quota --json` 每个条目对应一个账号、套餐或 key 余额：

| 字段 | 含义 | 使用约束 |
|---|---|---|
| `provider` / `name` / `user` / `plan` | 供应商 ID、显示名、账号标识、套餐名 | `user` 是私有账号信息，脱敏输出 |
| `kind` | `subscription`（登录账号）、`plan`（key 购买的编码套餐）、`balance`（key 余额） | 三类窗口语义不同，不合并计算 |
| `windows[]` | 用量窗口：`name`（如 “5 hours”）、`used` / `remaining`（0-100）、`resetsAt`（RFC 3339）、`unlimited` | 多窗口并存且不可换算；`remaining` 为 0 即耗尽，直到 `resetsAt` |
| `display` / `amount` / `limit` / `unit` | 供应商原样计数（如 “1.2k / 3k”） | 只在能核供应商计数口径时引用 |
| `balance` | key 或账户余额，原币种或积分 | 不跨币种求和 |
| `error` | 读不到的原因 | 向使用者转述，不把该账号当作已耗尽 |
| `asOf` / `readAt` | 读数时间 | 过期读数注明时点 |
| `lastServedAt` / `last` | 最近一次经网关应答的时间与标记 | 用于确认当前落点 |

筛选与等待：

```sh
magpie quota <provider> --json          # 按 provider id、名称或 kind 过滤
magpie quota subscription --json        # 只看登录账号
magpie quota wait <provider|account> [--timeout 6h]   # 阻塞至额度恢复；exit 0 恢复、1 超时、2 名称未知、130 中断
magpie quota history <provider> --json --days 7       # 历史读数（保留约 45 天）
```

命令不可用时的等效只读入口：`curl -s http://127.0.0.1:<port>/v1/magpie/quotas`（端口以应用设置为准）。raw 响应含账号信息，仅在进程内使用，输出一律脱敏（见[隐私边界](privacy.md)）。

硬性禁区：不执行 `magpie quota reset`（消耗一次恢复机会且不可逆，仅使用者本人决定）；不改 `magpie quota credits`、`auto-reset`、`alert` 设置，除非使用者点名要求。不执行 `magpie library skill rm --all`、`magpie group auto off`、`magpie provider rm`、`magpie accounts import`、`magpie daemon install`，除非使用者明确点名。不签署或切换登录态，不使用 sudo 运行。

## 来源与许可

命令面与额度字段合同整理自 [magpie-community/plugins](https://github.com/magpie-community/plugins) 的 `skills/magpie-setup` 与 `skills/magpie-quota`（MIT License，Copyright (c) 2026 magpie-community contributors），按 MIT 兼容方式并入并重写；语义以安装版 CLI 实际行为为准，冲突时以实读帮助与本机回读为准。
