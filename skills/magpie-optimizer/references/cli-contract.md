# CLI 与变更边界

基于本机 Magpie 0.1.1237 核对。配置默认 `~/.config/magpie/providers.json`，尊重 `XDG_CONFIG_HOME`。网关本机地址从实际 settings 或 `magpie models` 查明，不硬编码端口。文件中有密钥，读取仅在进程内做比较与 allowlist 投影，不打印原件。

## 只读调查

- `magpie --version`、`magpie group --help`、`magpie group rule --help`。
- `magpie groups`、`magpie models`、`magpie group <id>`。
- `magpie quota --json`：可访问平台刷新用量；raw 中包含账号，不直接输出。
- `magpie usage today`、`magpie usage 7d`：只摘聚合，用量来源可能重叠。
- `magpie provider account-concurrency <provider>`、`magpie provider queue <provider>`、`magpie provider rpm <provider>`：省略修改值为查询。前者可能输出私有账号，只保留限制值。
- 已装插件初始化可能下载其运行时。希望零联网时使用离线 inspect；不自动执行 sync、update、plugin install 或 quota reset。

注意：该版本 `magpie provider <子命令> --help` 可能只返回总帮助，exit 0 不能证明能力；必要时在临时 HOME＋XDG_CONFIG_HOME＋XDG_CACHE_HOME、`MAGPIE_NO_ACCOUNTS=1` 下验证参数并检查实际文件。环境隔离要通过子进程 env 实现，不更改当前 shell 的 HOME。不要复制真实认证到测试目录。

## 原生写入

下列是已核对语法，尖括号由实际对象替换，不直接执行模板：

```text
magpie group set <id> models=<完整列表> routing=order stays=auto
magpie group rule add <id> pause=<组内模型> time=14:00-18:00
magpie group rule add <id> use=<组内模型> time=18:00-23:00
magpie group rule rm <id> <规则序号>
magpie group rule mv <id> <原序号> <目标序号>
magpie provider account-concurrency <provider> <account-or-key-id> 1
magpie provider queue <provider> 2 15
magpie provider rpm <provider> <已确认的每分钟上限>
```

修改已有对象先保留目标的完整 JSON 与 CLI 只读状态到私有 0600 文件（不导出 provider key），锁定变更字段。`models=` 替换整个列表，`models+=`/`models-=` 是增删。组成员 off 与 provider off 是独立状态，不能只看组 members。规则 rm 的序号每删一条都会变化，批量删除按倒序，并逐步回读。

账号并发是跨模型/分组共享的上限。`off` 或 0 表示不限，不能当“停用”。已设置的账号 override 可能覆盖供应商默认。实际可承受并发由限流表现确认，不能用多建组绕过。

普通 use 规则仅把目标提到前面，其他成员仍能 fallback；manual 路由不自动失败回退。pause 是硬排除，优先保护避峰成本但可能中断缓存。不要把 free 与付费项放在同一自动回退组后称“只用免费”。意图分类器本身也消耗额度，第一版建议显式按任务选组。

`group add` 同名替换：随附脚本拒绝此情况，只创建 mpr-*。修改旧组通过上面的人工审核流程执行，脚本不自动接管。

## 凭证、失败与恢复

不把 providers.json 完整内容放进报告、测试或 Git，不调用 provider key 写入示例凭证。一次变更不得顺带打开关闭的供应商、重置卡、切换登录或改所有 Agent 默认模型。

随附脚本预览时记录全配置 SHA-256，应用时严格核对；不是 Magpie 内部事务锁。GUI 及其他写入者应暂停配置编辑，后台正常推理无需停止。检测到漂移或 CLI timeout 时，不自动补偿、重放或整文件回滚，先确认实际落盘。

恢复新组：确认没有 Agent、其他组或规则引用，检查它仍是本次创建后的内容，再明确执行 `magpie group rm <id>`，回读剩余组和 Agent 配置。新组已被使用或有人追加修改时先保留；不能盲删。恢复旧组：仅用原生 CLI 恢复本次变更字段和规则，保留他人新配置。

应用成功后，先回读配置，再在授权内做代表性真实请求，检查 usage 的实际 served provider/model。新增组可供下次会话选择，但不自动切换当前任务；各客户端是否需要新会话按其实际行为验证。
