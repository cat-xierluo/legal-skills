# 操作入口

所有个人策略、计划、观察、回执放在 Skill 目录内的 `config/*.local.json` 与 `state/`；文件名不能复用已有结果。先核安装版与当前配置，脚本路径相对本 Skill。

私有层不入库的口径只认 Skill 内两个 ignore 文件：`config/.gitignore` 用 `*.local.*` 通配排除全部本地配置（早期版本曾逐个列出 `profile.local.json`、`inventory.local.json`、`route-policy.local.json`、`integration.local.json`，现已被通配取代，新私有文件名不需要再逐名补规则）；`state/.gitignore` 排除该目录下全部运行证据，只保留 `.gitignore` 自身。仓库根 `.gitignore` 不含本 Skill 的专用条目，是否另有覆盖以实际仓库为准，不能拿它替代 Skill 内规则。

**以下命令在 Skill 目录内执行，`scripts/`、`config/`、`state/` 均相对该目录。**

## 原有能力

- `python3 scripts/magpie_route.py inspect --live --output state/inventory.json`：配置与远端额度；不加 live 为离线。
- `python3 scripts/magpie_route.py plan --policy config/policy.local.json --output state/plan.json`。
- `python3 scripts/magpie_route.py apply --plan state/plan.json --plan-sha256 SHA --execute --receipt state/receipt.json`。

## 新建组：可执行 policy

可执行模板见 [`../config/policy.example.json`](../config/policy.example.json)，schema `magpie-route-policy.v1`，是 `plan` 的合法输入。使用时复制为本地副本并替换占位，命令一律指向这份副本：

```sh
# 按 references/configuration.md 创建拒绝覆盖、权限 0600 的 policy.local.json
python3 scripts/magpie_route.py plan --policy config/policy.local.json --output state/plan.json
```

[`../config/route-policy.example.json`](../config/route-policy.example.json) 是更高层的设计示例，schema `magpie-route-design.v1`，列出分组角色、意图、分类器与账号顺序等字段，**只用于规划讨论，不能直接喂给 `plan`**：`plan` 只接受 `magpie-route-policy.v1` 且字段封闭。

先用只读检查器核设计草案，再进入人工转换与原生实施：

```sh
python3 scripts/magpie_route_design.py validate --design config/route-policy.local.json --strict
```

检查范围：JSON schema、入口/嵌套组引用、自引用与循环、嵌套深度、规则目标在成员内、意图规则有分类器、compact 规则置首、意图描述含排除语，以及角色组是否有至少两个 provider 前缀。最后一条只是容量线索，不证明账号池独立；真实容量仍须按盘点与回读核对。

### plan 的执行边界（据 `scripts/magpie_route.py` 的校验）

- **只新建**：组 ID 必须匹配 `mpr-` 加小写字母数字与连字符，且不与既有组的 ID 或名称冲突（冲突时报 `existing_group_collision`）。既有组不会被 plan 改动，既有组变更走下面的 `magpie_change.py`。
- **字段封闭**：policy 顶层只接受 `schema` 与 `groups`；每个组只接受 `id`、`members`、`routing`、`stays`、`rules`。多写一个键即被拒绝。
- **规模上限**：组数 1–8，每组成员 1–12 且不重复，规则不超过 20 条。
- **取值受限**：`routing` 只接受 `order`、`smart`、`usage`、`pace`；`stays` 只接受 `auto`、`session`、`turn`。
- **成员必须是已启用模型**：成员只能是「未停用、未隐藏的 provider 下已列出的具体模型 ID」。pattern 成员、停用供应商、未暴露模型都不接受。
- **规则受限**：只接受 `use`、`pause`、`time`、`effort`、`tokens`、`images`、`compact`；`use` 与 `pause` 二选一且目标必须在组内；`pause` 只能与 `time` 同时出现；`time` 写成 `HH:MM-HH:MM`；`effort` 取 `on`、`low`、`medium`、`high`、`xhigh`、`max`；`tokens` 为正整数；`images`、`compact` 只接受 `true`；不接受无条件规则。

### 超出边界的设计怎么办

意图（intent）分流、分类器（classifier）、嵌套组、账号顺序、权重等字段**不在** plan 支持范围内：写进去会被拒绝，本 Skill 也**不提供**把设计层文件转换成可执行 policy 的转换器。这类设计按已核的原生 CLI 或 GUI 单独实施并逐项回读：

- 组级字段（`effort`、`levels`、`weight`、`fast` 等）与意图规则前置条件见[路由治理](routing-governance.md)；
- 账号顺序的入口、持久化位置与回读口径见[供应商与账号接入](provider-integration.md)；
- 改动既有组的具名命令见[CLI 与变更边界](cli-contract.md)。

不要为了套进 plan 而删掉这些设计，也不要把设计层示例当作 plan 输入。

## 已有分组变更

```json
{
  "schema": "magpie-group-change.v1",
  "group": "existing-group",
  "set": {"routing": "order", "stays": "auto"},
  "append_rules": [{"pause": "example/efficient", "time": "14:00-18:00"}]
}
```

将 group 和模型替换成当前目标。`set` 只支持 routing、stays、members；members 是整个成员列表，若移除仍被既有规则或 off 状态引用的成员则拒绝。模型必须是已启用供应商已选择的显式ID。其他原有字段保留；复杂既有规则不自动重写，追加规则支持 use/pause、time、effort、tokens、images、compact，语义沿 `magpie group rule --help`。追加在末尾，既有规则可能先匹配，实施前须核顺序。

```sh
python3 scripts/magpie_change.py plan --spec state/change.json --output state/change-plan.json
python3 scripts/magpie_change.py apply --plan state/change-plan.json --plan-sha256 SHA --execute --receipt state/change-receipt.json
python3 scripts/magpie_change.py recovery-plan --source-plan state/change-plan.json --output state/recovery-plan.json
python3 scripts/magpie_change.py apply --plan state/recovery-plan.json --plan-sha256 SHA --execute --receipt state/recovery-receipt.json
```

SHA 使用计划命令输出的哈希，阅读全部步骤后实施。恢复只移除本次追加规则并恢复本次涉及字段，计划保存完整目标前态。部分成功时，仅在目标精确匹配已保存计划的某个中间后态时生成恢复；若目标组有其他人修改或状态不明，拒绝自动恢复。原生 JSON 把 `stays` 存为 `affinity`，校验按相同语义比较；默认字段省略不视为行为差异。其余未知字段变化仍拒绝。

该能力不启用已关闭供应商、不删除分组、不切客户端默认值、不操作密钥或账号。供应商并发/队列按 `cli-contract.md` 的具名原生命令维护；不把组内设置当账号级总限流。
