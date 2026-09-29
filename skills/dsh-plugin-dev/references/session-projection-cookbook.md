# 会话投影 Cookbook（0.1.7-rc.2 实测）

出处：dsh-session-projection/lib/index.js 源码核对 + dsh-plugins PR #11（含审查抓出的两个阻塞修复）与第五次装载实验。投影是替代轮询的会话状态消费正道（Pi 时代 desktop.invoke 轮询的全部替代面）。

## 服务接入

- `inject = ['sessionProjections']` → `SessionProjectionRegistry`（cordis Service，`super(ctx, "sessionProjections")`）。
- 方法面：`register(definition)` / `onChanged(listener)` / `stateOf(session, key)` / 快照一致性读取。

## register(definition) 契约（逐字段，两处是实测踩坑点）

| 字段 | 要求 | 踩坑 |
|---|---|---|
| `key` | string，全局唯一 | 同 key 二次注册走替代语义 |
| **`stateVersion`** | **必填非负整数**（`Number.isSafeInteger` 无条件校验，缺失/负数直接 throw） | **缺省 → 装载即抛 "stateVersion must be a non-negative integer, got undefined"，插件不激活**（PR #11 审查阻塞①） |
| `stateSchema` | 有 `.parse(v)` 的 Schema 形对象（restore/materialize 路径调用） | 零依赖插件可用恒等 `{ parse: v => v }` |
| `init(header, inheritedEventCount)` | 产初始 state | fork 继承语义的挂点 |
| `apply(state, event)` | fold 一条事件 | **返回同引用 = 无变化 = 不通知**（Object.is 比较）；要通知必须返回新对象 |
| `wire` | `{ viewSchema, view }`——**通知只走 wire 路径**（drive 实现里 `changed && wire !== void 0` 才 notify） | **不声明 wire 则 onChanged 永远收不到本单元的通知** |

## 通知机制

- `onChanged(listener)` → `listener(session, key, value, seq)`：session 是宿主 Session 实例（`.id` = `header.id`）、value 是 `wire.viewSchema.parse(wire.view(nextState))`、seq 是事件序号（observedSeq 水位）。
- 驱动顺序：按 `session/event` 日志顺序，带水位去重；同一 state 引用跳过。
- 订阅是 ctx.effect——随调用方 fiber 生命周期。

## 事件形状（易错点）

- **`turn/start` 的 `data.turn` 是数字**（dsh-agent-loop：`turn = phase.turn + 1`，从 1 起；invariant 种子 nextTurn:1）——**不是字符串**。守卫按 `typeof === 'string'` 写会让真实会话静默建不出任何东西（PR #11 审查阻塞②）。兼容写法：接受 number|string，runKey 里 `String()` 化。
- `turn/end` 带 `data.turn` 与 `data.reason`（dsh-session repair.js）——fold 不依赖也按实际形状记录。
- 已知事件类型集：`KNOWN_SESSION_EVENT_TYPES`（dsh-session/lib/index.js:79）——turn/start、turn/end、step/*、tool/call、tool/result、approval/*、assistant/* 等；无关事件 fold 返回原引用即可零成本。

## 官方已有投影键（避免重复造）

`todos`（dsh-tool-todo，整表替换单 owner）、`subagentCatalog`/`subagent`/`subagentTiming`（dsh-subagent，谱系/状态/耗时）、`sessionStats`（dsh-session-stats，全日志口径统计）。自定义单元先确认没有官方等价物；`todos` 无 revision/人工验收语义——业务契约需自有单元重建（Pilot P09 结论）。

## 验证模式（三层）

1. **单元**：definition 直接测——init/apply 的 fold 语义（同引用断言）、schema parse、wire view。
2. **集成**：mock registry（register/onChanged/手动 emit）+ 真实服务与消费者串接——用**数字 turn 样本**（贴宿主真实形态）+ 非法值防御用例。
3. **宿主**：装载后看 `real session projection wired` 类日志；真实 turn 驱动需 GUI 交互/凭据产生事件（无人值守环境是自然停点）。

## 反例记录（实测）

- mock 测试全绿但宿主必炸：mock registry 收任意 definition，掩盖 stateVersion 必填——**mock 必须复刻宿主校验**（或在宿主核过一次再信 mock）。
- 字符串 turnId 测试全绿但真实会话零 link：样本形态必须贴实物（数字）。
