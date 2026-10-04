# zcode-subagent-evidence：原生 Agent 子任务树只读证据采集

`scripts/zcode-subagent-evidence.py`（Python 3 标准库，无第三方依赖）从原生 SQLite 会话库中，以**只读、显式绑定**的方式采集一次原生 Agent 调用产生的子任务树证据，用于交付留痕与验收。

## 何时使用

- 需要证明"某次根输入（promoted input）所在会话派生了哪些原生 Agent 子会话"时；
- 需要子会话的白名单身份数据（状态/模型/provider/mode/运行时长/工具调用数）作为交付证据时;
- 禁止用它做任何写入、归并、猜测或自动验收。

## 用法

```bash
python3 skills/multi-agent-orchestration/scripts/zcode-subagent-evidence.py \
  --db <原生SQLite路径> \
  --root-session <根session id> \
  --root-input <session_input.promoted_message_id> \
  [--max-nodes 500] [--max-depth 32]
```

成功输出单行 JSON（退出码 0）；失败输出 `{"ok":false,"error":{"code":"...","exit":N}}`（退出码见下）。

## 绑定与枚举语义（安全核心）

1. **显式绑定**：`--root-session` + `--root-input` 必须命中同一行 `session_input`（`session_id` 匹配且 `promoted_message_id` 相等）。绑定成功后取该行 `promoted_sequence` 作为精确 turn（列缺失**或值不可解析**时回退 `admitted_sequence`，再不可得标 `UNKNOWN`）。不做绑定就无从谈"本次输入的后代"。
1a. **selected turn（R1 返修）**：`promoted_sequence`/`admitted_sequence` 只是 session_input 序数（ordinal），**不是 native turn 身份**。本次 root input 的真实选中 turn 必须且只能按 `turn_usage.session_id + turn_usage.user_message_id = promoted_message_id` 唯一命中，输出在 `root.selected_turn`（`turn_id/status/terminal/tool_call_count/duration_ms`）与 `root.turn_binding_status`：唯一命中 `bound_unique` 给真实值；`turn_usage` 缺表（`source_table_missing`）、缺 `user_message_id` 列（`binding_column_missing`）、0 行命中（`no_matching_turn`）、多行命中（`ambiguous_multiple_matching_turns`）一律全 `UNKNOWN`，**绝不借会话最新 turn**。节点级 `status/tool_call_count/duration_ms/turn_count` 是 session 维度聚合（root 节点含全部 input 的 turns、status 取会话最新 turn），与 `selected_turn` 分离（见输出顶层 `session_aggregation_note`）。
2. **只认 parent_id**：仅沿 `session.parent_id` 做 BFS 枚举真实后代（含根节点自身，depth=0）。**禁止**按标题、时间邻近或其他启发式猜子任务。
3. **有界与环安全**：`visited` 集合防环（重复边计入 `cycle_edges`，不展开）；`--max-nodes/--max-depth` 触发时 `truncated=true` 并给出 `truncation_reasons`（SQLite 资源边界）。
4. **歧义必须保留**：根会话存在多个 promoted input 时，`root_input_attribution=ambiguous_multiple_promoted_inputs`——`parent_id` 只证明 session 级归属，**不证明**后代属于本次 `--root-input`；唯一 promoted input 时标 `unique_promoted_input_in_root_session`（仍属 session 级证明）。
5. **UNKNOWN 优先**：无法证明的字段一律输出 `"UNKNOWN"`，绝不默认"完成"。

## 只读保证

- 打开方式 `file:...?mode=ro` + `PRAGMA query_only=ON` + 单一 `BEGIN DEFERRED` 读事务快照；
- 数据库文件不存在时**不创建**（`db_file_missing`）；任何失败路径都不写库、不建 `-wal`/`-journal`；
- 每个节点只按列名 SELECT 白名单列，绝不 SELECT 非白名单列；
- `parent_id` 语义：NULL（无父，典型为根会话）输出 `null`；非空但不符合白名单 token 形态输出 `"UNKNOWN"`（不回显原值）；
- 边界：WAL 模式库只读打开依赖已存在的 `-shm`/`-wal`，否则保守失败（`db_open_failed`），不会尝试创建。

## 白名单输出（全部允许字段）

- 身份：`session_id`、`parent_id`、`root_input_promoted_message_id`；
- 结构：`depth`、`parent_exists`、`node_count`、`edge_count`、`max_depth_observed`、`cycle_edges`、`truncated`、`limits`；
- 状态：`status`/`terminal`（来自 `turn_usage` 最后一个 turn 的 `status`；无行则 `UNKNOWN`；`running` 等非终态原样输出且 `terminal=false`）；
- 明确存在的模型/provider/mode：`models`/`providers`（`model_usage.model_id/provider_id` 去重）、`modes`（`model_usage.mode`）、`permission_mode`（`session.permission`）；无行则 `UNKNOWN`；
- 运行时间：`duration_ms` + `duration_source`（优先 `turn_usage` 跨度，回退 `session.time_updated-time_created`）；
- 工具数量：`tool_call_count`（优先 `COUNT(tool_usage)`，回退 `SUM(turn_usage.tool_call_count)`）；
- 绑定：`turn`/`turn_source`（session_input 序数 ordinal，非 turn 身份）、`turn_binding_status`、`selected_turn`（user_message_id 精确绑定的真实选中 turn，无法唯一证明则全 UNKNOWN）、`promoted_input_count`/`root_input_attribution`/`attribution_note`/`session_aggregation_note`。

**禁止输出**：payload、reasoning、工具参数/结果、标题（`title`）、目录（`directory`/`path`）、账号、凭据；所有值先过紧凑 token 白名单正则（`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`），不匹配即 `UNKNOWN`。JSON 编码字段只提取同名键的标量，坏 JSON 一律 `UNKNOWN`。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功（允许包含 UNKNOWN/截断，详见 JSON） |
| 2 | 用法错误（缺参数/非法 id/非法上限） |

错误只输出固定错误码，**不回显任何原生异常文本或路径**。例外说明：argparse 层的缺参/非法参数错误以退出码 2 退出，stderr 为 argparse 固定 usage 文本（不含路径与敏感值），stdout 无 JSON——机器消费方以退出码为准。
| 3 | 数据库错误：`db_file_missing`/`db_open_failed`/`db_not_sqlite`/`db_schema_missing_table`/`db_schema_missing_column`/`db_query_failed` |
| 4 | root 绑定失败：`root_session_not_found`/`root_input_not_bound` |
| 5 | `internal_error` |

错误只输出固定错误码，**不回显任何原生异常文本或路径**。

## 原生 schema 映射（`~/.zcode/cli/db/db.sqlite`）

| 证据 | 来源 |
|------|------|
| 精确 turn | `session_input.promoted_sequence`（回退 `admitted_sequence`） |
| 父子树 | `session.parent_id` |
| mode | `session.permission`、`model_usage.mode` |
| 状态/时长 | `turn_usage.status/started_at/completed_at` |
| 工具数 | `tool_usage`（回退 `turn_usage.tool_call_count`） |
| 模型/provider | `model_usage.model_id/provider_id` |

必需表：`session(id,parent_id)`、`session_input(session_id,promoted_message_id)`；`turn_usage/tool_usage/model_usage` 为可选增强（**整表缺失**→对应字段 `UNKNOWN`，`sources` 字段如实标注；表存在但缺实现所需列，如 `turn_usage.turn_id`（排序 tiebreak 依赖），按 schema 错误处理退出 3，不降级猜测）。

## 测试

```bash
python3 skills/multi-agent-orchestration/scripts/test-zcode-subagent-evidence.py
```

覆盖：坏 schema、坏 JSON、跨 session、孤儿、循环、深树/大量节点、非终态、多轮归属歧义、缺字段、秘密金丝雀零输出、真实小消费者（subprocess+JSON 契约）、只读不可写证明（0444 文件/目录校验和不变、缺库不创建）。fixture 全部在临时目录生成，**绝不触碰真实用户数据库**；真实库证据与 fixture 产物分开存放，不得混淆。
