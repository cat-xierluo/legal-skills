# ZCode GUI driver 精确模型/Provider/权限核验合同

本页定义 `scripts/zcode-browser-driver.cjs` 的精确配置核验能力（v0.2.0）：在发送前对页面唯一 `v4-model-config` 节点的 `data-provider` / `data-model` / `data-mode` 三个机器 ID 做**严格等值断言**。驱动入口、状态锁、单 Buffer prompt 指纹、unknown 不重投等基础合同不变；本页只新增精确核验语义。

## 1. 合法命令

三参数必须**齐备且为非空字符串**，部分提供、无值（`--expected-provider` 不带值）或空值在任何副作用（打开浏览器/键入草稿）之前以 `EXPECTED_CONFIG_INVALID` 拒绝：

```bash
node scripts/zcode-browser-driver.cjs inspect --url http://127.0.0.1:18490 \
  --expected-provider account:bigmodel-individual-coding-plan \
  --expected-model GLM-5.3 --expected-mode yolo

node scripts/zcode-browser-driver.cjs submit --url http://127.0.0.1:18490 \
  --workspace /absolute/workspace --task-id TASK_ID --prompt-file /tmp/task.txt \
  --state /tmp/task-state.json \
  --expected-provider account:bigmodel-individual-coding-plan \
  --expected-model GLM-5.3 --expected-mode yolo

node scripts/zcode-browser-driver.cjs follow-up --state /tmp/task-state.json \
  --input-id REVIEW_R1 --prompt-file /tmp/review.txt   # 默认继承 state 期望
```

三个参数全部不提供时保持原**兼容观察模式**：照旧回读 model/mode 标签但不做机器 ID 断言，输出不得声称"已精确核验/最高权限"。`observe`/`collect` 只读继承 state 证据，从不发送模型输入。

## 2. 机器 ID 与比较语义

- 唯一 `[data-testid="v4-model-config"]` 元素的三个 data 属性是可靠机器 ID（2026-10-03 官方 3.14.4 DOM 实见：`account:bigmodel-individual-coding-plan` / `GLM-5.3` / `yolo`）。
- 逐字段**严格等值**（`===`）：大小写敏感、不做前缀匹配（`GLM-5.3-Flash` 不等于 `GLM-5.3`）、不拿显示 label 或套餐文案推断。
- 元素缺失、出现多个、任一属性缺失/空/非字符串 → `EXPECTED_CONFIG_UNREADABLE`，fail-closed 零发送。
- 任何字段与期望不一致 → `EXPECTED_CONFIG_MISMATCH`，fail-closed 零发送。
- 断言是只读的：driver 不点击模型菜单、不修改全局/会话默认配置；配置漂移由 PM 在可见 GUI 修正后重试。本 scope 只做精确核验，不实现自动选择。

## 3. submit 核验顺序与零 click 保证

1. 参数解析后、打开浏览器前：三参数齐备校验 + 与既有 state 期望的一致性裁决（见 §5）。
2. workspace 选定、composer 配置就绪后（`submit-pre-draft`）：第一次严格核验，失败零键入零 click。
3. 键入草稿并回读一致后、**intent 持久化与唯一 click 之前**（`submit-pre-click`）：第二次紧邻核验。第一次正确而第二次漂移（变 Flash、换 provider、非期望 mode、不可读）时只清理本 driver 自己键入的草稿，state 不写 intent，**零 click**；该 state 保留 fresh，可修正页面后重试。
4. click 之后的任何未知沿用既有 `sent-unconfirmed` 合同：只能 DB 对账，不自动再 send。

期望与两次核验的实际值持久化在 `state.expectedConfig` / `state.page.expectedChecks`（仅三字段名值、stage 与时间，不含授权 URL 或凭证）。

## 4. inspect 语义

`inspect` 附带三参数时输出 `modelConfig`（actual IDs 及可读性）、`expectedConfig` 与 `expectedMatch`：页面可读时为严格等值布尔结果，不可读时为 `unknown`；不附带三参数时 `expectedMatch` 为 `null`（兼容观察）。inspect 始终零发送，可作为发送前的无副作用预检。

## 5. state 继承与不降级

- `submit` 首次调用把期望写入 state；同一 state 重复调用不带三参数时**继承原期望**（严格性不降级），带三参数时必须逐字段一致，否则 `EXPECTED_CONFIG_CONFLICT` 拒绝且不打开浏览器。
- 既有 state 已过 fresh 阶段（已发送/intent）而此前无期望记录时，追加显式期望会被拒绝：旧兼容任务不能被事后追认为"已精确核验"；需要精确核验链路应开新任务/新 state。
- `follow-up` 默认继承 state 期望；显式传值必须与 state 既有期望一致；state 无期望时拒绝显式传值（同一理由：不能只核验链路的后半段）。
- state schema 不变（v1），旧 state 可读、不迁移、不删除；每轮 follow-up 的核验证据记录在 `followUps[inputId].expectedChecks`。
- 期望冲突、锁占用、指纹冲突等所有拒绝路径都不重投：state intent 一经写入只能对账。

## 6. 退出语义（新增错误码）

| 错误码 | 含义 |
|---|---|
| `EXPECTED_CONFIG_INVALID` | 三参数部分提供/无值/空值（副作用前拒绝） |
| `EXPECTED_CONFIG_UNREADABLE` | `v4-model-config` 缺失/重复或属性缺失/空（fail-closed 零发送） |
| `EXPECTED_CONFIG_MISMATCH` | 机器 ID 与期望不一致（严格等值，零发送） |
| `EXPECTED_CONFIG_CONFLICT` | 显式期望与 state 既有期望不一致，或对无期望记录的已发送 state/无期望 state 的 follow-up 追加期望（打开浏览器前拒绝） |

既有退出语义（0 调用/对账成功、1 拒绝/错误、2 unknown、3 不支持恢复）不变。

## 7. NOT_VERIFIED（如实保留）

- 自动选择模型/provider/mode 未实现：本合同只做只读断言，页面配置仍由 PM/真人在可见 GUI 设置。
- 真实浏览器下的新模型派发→完成→跨进程续聊全流程、长时全自动稳定性沿用既有 NOT_VERIFIED；本页测试为源码级 FakePage/SQLite fixture 回归（含发送次数断言），不签成 E2E。
- `v4-model-config` 的 data 属性合同基于 2026-10-03 官方 3.14.4 DOM 实见，后续版本变化时以 `inspect` 实测为准再更新映射。
