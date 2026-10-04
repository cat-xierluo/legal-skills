# zcode-browser-driver 配置门对抗性验收（config-adversarial）

> 资产：`scripts/test-zcode-browser-config-adversarial.cjs`（本文件为其使用与边界说明）
> 任务：TASK-2026-10-04-ZGUI-CONFIG-ADVERSARIAL ｜ 冻结 base：`4d3380b2`（`integration/mao-zcode-gui`）

## 1. 目的与定位

针对 `zcode-browser-driver.cjs` 的 **R4 精确配置核验门**（`--expected-provider/--expected-model/--expected-mode` 三参数 + 页面唯一 `v4-model-config` 机器 ID 严格等值）提供**独立对抗性故障验收**：

- 与原 42 契约测试（`test-zcode-browser-driver.cjs`，`node --test`）**完全独立**：互不导入、互不修改、不共享代码；本 harness 自带 Fake Page/fixture DB。
- 只读生产 driver；**不改 driver、不改原 42 测试、不加依赖**。
- 覆盖"恶意/异常页面 + 恶意/异常 state + 参数滥用 + 并发争用"四类对抗面。
- 内置**负控**：在私有 tmp 的冻结 driver 副本上注入安全相关弱化，证明本套测试对具体 fault 有杀伤力（变异体存活 = 灵敏度不足 = 退出码 4）。

## 2. 依赖

- Node ≥ 22（使用内置 `node:test` 无关；本 harness 用 `node:sqlite`、`child_process`、`crypto`，**无任何第三方依赖**）。
- 不启动真实浏览器/模型/服务；不读取真实凭证；CLI 子进程用例只命中 `fetchServerInfo`/`openPage`/Playwright 加载**之前**的 fail-closed 路径（唯一网络触点是 W3 变异负控下对 `127.0.0.1` 的连接尝试，必然被拒，不外联）。

## 3. 用法与退出码

```bash
# 默认：对抗矩阵 vs 生产 driver（15 项，含 5 项真实 CLI 子进程用例）
node scripts/test-zcode-browser-config-adversarial.cjs \
  --tmp-root <私有tmp> --report <report.json>

# 负控：3 个安全弱化变异体必须全部被击杀；生产 driver SHA 前后校验
node scripts/test-zcode-browser-config-adversarial.cjs --negative-control \
  --mutant-dir <私有tmp>/mutants --tmp-root <私有tmp> --report <report.json>

# 注册表
node scripts/test-zcode-browser-config-adversarial.cjs --list
```

| 退出码 | 含义 |
|---|---|
| 0 | 通过（默认模式全过 / 负控全击杀） |
| 1 | 存在失败或 harness 错误（含生产 driver SHA 被意外改动） |
| 2 | harness 参数错误 |
| 4 | 负控存在**存活变异体**（测试灵敏度不足，资产本身不可信） |

`--report` 输出 JSON 摘要：`taskId / driverSha256 / driverUnchanged / results[]（逐项 id/ok/ms/error） / mutants[] / exitCode`，供独立消费者（另一 SID/CI）复核，不依赖终端输出。（字段名以本行为准：测试项数组为 `results`。）

## 4. 对抗矩阵（与任务验收点一一对应）

| ID | 类型 | 验收点 |
|---|---|---|
| ADV-01 | 纯函数 | 显式 expected 三参数门：无值 flag/仅 1⁄3/2⁄3/空白值一律 `EXPECTED_CONFIG_INVALID`；齐备返回裁剪三元组；全不提供返回 `null`（不得伪称已核验） |
| ADV-02 | in-process | DOM 配置元素**重复**（两元素机器 ID 冲突：GOOD+EVIL）→ `EXPECTED_CONFIG_UNREADABLE(DUPLICATE)`，零发送 click、零 state 落盘、零残留 |
| ADV-03 | in-process | DOM 配置元素**缺失** → `UNREADABLE(MISSING)`，同上零副作用 |
| ADV-04 | in-process | 机器 ID 属性**空字符串/缺失(null)** → `UNREADABLE(EMPTY_ATTR)` |
| ADV-05 | in-process | **机器 ID 相似显示名冲突**：显示 label 与期望一致但 `data-model` 背离（label 陷阱）；大小写漂移（`glm-5.3`≠`GLM-5.3`）；mode 漂移 → `EXPECTED_CONFIG_MISMATCH`，证明匹配只认机器 ID、不认显示名/前缀/大小写 |
| ADV-06 | in-process | **草稿后发送前配置变化**（TOCTOU）：草稿录入前检查通过、marker 键入后机器 ID 漂移（Flash/其他 provider）→ 第二次核验（`submit-pre-click`）拒绝、清理自身草稿、零 click、**不写 intent**（不可盲重投） |
| ADV-07 | in-process | **state 配置继承/冲突**：成功 submit 持久化 `expectedConfig` 与两次核验证据（`submit-pre-draft`+`submit-pre-click`）；重复 submit 继承期望只对账（`reconciled`）；显式期望漂移 → `EXPECTED_CONFIG_CONFLICT`；既有任务无期望记录时**拒绝事后追认**（打开浏览器前裁决） |
| ADV-08 | in-process | **unknown/duplicate 零重投**：click 后 DB 无记录 → `unknown`/退出码 2/sent-unconfirmed；重复 submit 仍 `unknown` 零新 click 零新 openPage；DB 延迟补齐后仅对账 `reconciled`，全程恰好 1 次 click |
| ADV-09 | in-process | **多个状态进程争用**（真并发）：胜者持锁期间第二提交者 `LOCK_HELD` 且零副作用（不开页/不点击）；胜者唯一 click；锁随持有者以 nonce 校验释放 |
| ADV-10 | in-process | **零 click 拒绝（副作用前）**：部分期望参数在 openPage/锁/state 之前拒绝 |
| ADV-C1 | CLI 子进程 | 部分提供/无值期望参数 → **真实退出码 1** + `EXPECTED_CONFIG_INVALID` + 目录零残留（无 state/锁/tmp 文件） |
| ADV-C2 | CLI 子进程 | 外部持锁下**两个独立 OS 进程**争用 → 双双 `LOCK_HELD` 退出码 1；外部锁与 `owner.json` 原样保留（不抢占/不篡改） |
| ADV-C3 | CLI 子进程 | 损坏 state（非法 JSON）→ `STATE_CORRUPT` 退出码 1；**state 字节不变**（不猜测不覆写）；自建锁自清理 |
| ADV-C4 | CLI 子进程 | 既有 state 期望漂移 → `EXPECTED_CONFIG_CONFLICT` 退出码 1；**state 字节级不变** |
| ADV-C5 | CLI 子进程 | 既有任务无期望记录 + 全量显式期望 → 追认拒绝 `EXPECTED_CONFIG_CONFLICT` 退出码 1 |

证据口径：每个拒绝路径同时断言 **发送 click 计数（FakePage.sendClicks）、openPage 计数、state 文件存在性、锁/原子写 tmp 残留**；CLI 用例额外断言**真实退出码与 stdout JSON error.code**——不是纯函数断言的镜像。

## 5. 负控协议（--negative-control）

在私有 tmp 对冻结 driver **副本**注入单一弱化（`find` 串必须恰好出现 1 次，否则拒绝变异；副本过 `node --check`），然后运行"击杀目标"测试并**要求其失败**：

| 变异体 | 弱化内容 | 击杀目标 | 击杀证据（应失败的原因） |
|---|---|---|---|
| W1 | 移除草稿后/点击前第二次核验（`submit-pre-click` 直通） | ADV-06 | 漂移被放行，流程进入 click 之后的 DB 轮询（`DB_UNAVAILABLE` 仅 click 后可达）→ 测试断言落空 |
| W2 | 移除 `v4-model-config` 唯一性门（重复元素不再拒绝、静默取第一个） | ADV-02 | 重复+冲突元素被放行并点击 → 同上 |
| W3 | 移除三参数齐备门（部分提供静默降级为观察模式） | ADV-01、ADV-C1 | 纯函数不再抛；CLI 退出码仍 1 但 error.code 变为 `SERVICE_UNREACHABLE`（到达了本不该到达的网络阶段） |

- 任何变异体存活（目标测试仍通过）→ 退出码 4，资产不可信。
- 生产 driver 全程只读：运行前后 SHA256 必须一致（报告中 `driverUnchanged`），否则退出码 1。
- 变异文件只存在于 `--mutant-dir`（私有 tmp），路径与 SHA 记录在报告中备查。

## 6. 与原 42 测试的关系

- 原 42 测试（`node --test`）覆盖契约/单元面；本 harness 聚焦对抗面，二者**均须独立通过**。运行顺序建议错峰串行：先原 42（`node --test scripts/test-zcode-browser-driver.cjs`），再本 harness 默认模式，最后负控模式。
- 已知互补点：原 42 没有"经 `cmdSubmit` 断言 `LOCK_HELD`"的用例（只直接调 `withStateLock`），本 harness ADV-09/ADV-C2 补上该缺口；本 harness 不重复原 42 的 follow-up/对账细节矩阵。

## 7. NOT_VERIFIED（明确不声称）

1. **非真实模型/浏览器/服务 E2E**：页面为 Fake（协议级模拟 Playwright locator）；DB 为 fixture SQLite；CLI 用例只覆盖副作用前 fail-closed 路径。
2. **真实 Playwright locator 语义**（strict mode violation、可见性、超时行为）未验证。
3. **跨进程 exactly-once**：driver 自身只承诺同 state 内不自动重发；跨进程窗口（文件头已声明的"DOM 点击本身无法绝对保证"与第二次核验到 click 之间的残窗）超出本资产范围。
4. **sqlite3 CLI 回退路径**（无 `node:sqlite` 时）未覆盖。
5. **长期稳定性/真实 3.14.x DOM 变化**未验证；DOM 合同以 references/34、35 的实测记录为准。
6. 负控击杀证据中 W1/W2 的失败表现为"进入 click 后 DB 轮询失败"（`DB_UNAVAILABLE` 仅在 click 之后可达），据此判定弱化被测试捕获；如需更直接的"sendClicks 计数"式击杀证据，可在对应测试中补建 fixture DB（行为等价，非必须）。

## 8. 复核命令（PM/独审用）

```bash
cd <worktree>/skills/multi-agent-orchestration/scripts
shasum -a 256 zcode-browser-driver.cjs            # 前后应一致
node --test test-zcode-browser-driver.cjs          # 原 42（独立通过）
node test-zcode-browser-config-adversarial.cjs --list
node test-zcode-browser-config-adversarial.cjs --report /tmp/adv.json ; echo $?
node test-zcode-browser-config-adversarial.cjs --negative-control --mutant-dir /tmp/mut --report /tmp/adv-neg.json ; echo $?
```
