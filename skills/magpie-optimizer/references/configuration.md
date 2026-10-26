# 配置样例与私有副本

`config/` 只公开可复用的样例和 schema。个人取值写入 `*.local.*` 副本，由 `config/.gitignore` 排除。以下命令从 Skill 根目录运行。

| 样例 | 建议复制为 | 用途 | schema |
|---|---|---|---|
| `profile.example.json` | `profile.local.json` | 入口组、角色、硬边界与辅助调用 | `profile.schema.json` |
| `policy.example.json` | `policy.local.json` | 新建路由组的可执行计划输入 | `policy.schema.json` |
| `route-policy.example.json` | `route-policy.local.json` | 单入口嵌套角色组的设计草案 | `route-policy.schema.json` |
| `integration.example.json` | `integration.local.json` | 用户自选的接入记录模板；不是 Magpie 运行必需配置 | `integration.schema.json` |
| `inventory.example.json` | 一般无需复制 | 盘点脚本输出格式参考；真实快照写入 `state/` | `inventory.schema.json` |

## 推荐的起步顺序

从 Skill 根目录按需选择一个示例名，创建同名 `.local.json`。以下命令以 `profile` 为例，
使用排他创建和 0600 权限；目标已存在时拒绝覆盖。将参数换为 `route-policy`、`policy` 或
`integration` 可创建其本地副本。

```sh
python3 - profile <<'PYCONFIG'
import os
from pathlib import Path
import sys
name = sys.argv[1]
if name not in {'profile', 'route-policy', 'policy', 'integration'}:
    raise SystemExit('unknown example name')
source = Path('config') / (name + '.example.json')
target = Path('config') / (name + '.local.json')
content = source.read_bytes()
with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out:
    out.write(content)
PYCONFIG
```

先填写 `profile.local.json` 中的用户意图，再由 Agent 结合真实模型目录编写
`route-policy.local.json`，检查设计结构：

```sh
python3 scripts/magpie_route_design.py validate \
  --design config/route-policy.local.json --strict
```

`roles`、账号顺序和硬边界是 Agent 的设计输入。`inventory scan` 不会自动推荐模型，
`route_design validate` 不会生成或应用配置。嵌套组、intent 和 classifier 需按
[操作入口](operations.md)走原生 CLI 的具名变更计划；仅受限的平铺策略可转为
`policy.local.json` 并输入 `magpie_route.py plan`，不能为适配它而删掉嵌套设计。

`integration` 是可选接入记录模板；`inventory` 是脚本输出格式参考，真实快照写入
`state/`，通常无需复制。凭证仍交由 Magpie 保存，不复制到这些文件中。

## 规则

- 示例文件只使用 `example/...`、`other-example/...`、`account-*`、`<port>` 等明显占位。
- `*.local.*`、`state/`、日志、回执和密钥类文件不入库；不要把真实账号、密钥、代理地址或具体模型 ID 写进 example、schema、reference 或提交信息。
- 新增公开配置必须提供 `*.example.*` 和对应 schema；新增私有配置直接使用 `*.local.*`，不需要逐名补 ignore 规则。
- `route-policy.local.json` 是设计层输入，只用于结构检查和讨论；不能直接喂给 `magpie_route.py plan`。可执行 policy 是 `policy.local.json`。
