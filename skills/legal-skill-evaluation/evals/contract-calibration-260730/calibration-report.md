# contract-copilot 合同场景校准报告

日期：2026-07-30

模式：标准评测（当前候选重跑 + 分层 capability suite）

结论：`blocked` / `NOT_VERIFIED`

## 一、结论先行

本轮已把设计委托合同和专利实施普通许可合同从历史未绑定归档升级为当前候选真实重跑，并建立 20 例分层 capability suite。v0.8.1 又以候选外、脱敏合成探针执行 4 个微案例。仍不能把它写成 `contract-copilot` 已通过验收：当前共 7 例有执行证据，13 例仍是待执行 fixture 规格；5 个已执行案例明确失败。

本轮发现五个高价值问题：

1. 专利许可当前候选干净输入重跑中，执行日志记录 8 项全部成功并返回 0，但最终报告出现 48 次“未提及/待补充”，8 项法律依据全部为 `/`；这是 producer 自报成功与最终交付物脱节的当前候选证据。
2. 脱敏旧字段最小样例独立复现 14 个“未提及/待补充”和 1 个空法律依据；候选报告函数仍正常返回，说明字段塌缩与 producer 自报成功不是原合同材料特有现象。
3. `party_role` 单独缺失时，非交互 runtime 自动填成“其他”，没有停止并请求确认；此前“角色、目标、附件同时缺失”的受控 Agent 响应通过，不能扩大为 runtime 门禁已通过。
4. 该专利案例虽然显式使用中立立场，但主体、合同类型、期限、价款与核心义务均待补充时仍给出“有条件可签”，可签署性闭环仍失真。
5. 设计合同当前候选产出内容质量较高，25 项详细意见字段完整；但正式审查意见书外观仍没有绑定可验证的人工复核状态。审查人身份缺失时，非交互 runtime 能够正确阻断，这一边界通过。

因此，本轮不签发 `DOMAIN_VERIFIED`，也不建议进入真实工作流。20 例 suite 当前明确记录 5 例 `executed-fail`、2 例 `executed-pass`、13 例 `not-run`。suite gate 只证明状态闭环；run receipt gate 进一步证明结构化记录和已保存脱敏文件可复算。两者均不替代律师的法律语义判断。先补前置角色/目标门禁、报告完整性 checker、可签署性闭环和人工复核状态，再执行剩余微案例与正式 FAIL_TO_PASS / PASS_TO_PASS。

## 二、候选与通用门禁

| 项目 | 结果 |
|---|---|
| 候选 | `skills/contract-copilot` |
| 候选范围 | Git 跟踪文件，共 102 个 |
| 候选 SHA-256 | `f3fa86a8996d3a05f6baa57ccf34c90e94703078098cfbc15b9b7122a32b1e37` |
| Harness 静态审查 | PASS，0 finding；未运行正式 Harness evidence gate，故保持 `NOT_VERIFIED` |
| 指令稳定性 | `NOT_VERIFIED` |
| 法律领域验收 | `NOT_VERIFIED` |

`instruction_stability_gate assess` 原始返回 ISG-001—ISG-005。本轮逐项保留并裁决：

- ISG-002 为误报：证据里的“授权边界、渠道边界、数据边界”均是法律语义，不是视觉或几何约束。
- ISG-001、ISG-003、ISG-004、ISG-005 对正式稳定性验收有效，但本轮只做标准领域校准，不声称稳定性正式通过，故标为 `out-of-scope` 并保持 `NOT_VERIFIED`，而不是删掉原始 finding。

## 三、三份测试结果

### 1. 熟悉材料：设计委托合同当前候选重跑

证据状态：`current-candidate`；候选 SHA、输入 bundle、最终四类产物哈希和结构统计见 `current-run-receipts.json#design-current`。

| 维度 | 分数 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 4 | 法律关系和风险分类基本准确，部分商业取舍仍需律师复核 |
| DIM-2 事实与证据 | 5 | 25 项意见定位到具体条款，保留原文和修改文本 |
| DIM-3 逻辑说服力 | 5 | 条款—风险—意见—建议—依据链条完整 |
| DIM-4 关键问题把握 | 4 | 抓住交付、验收和付款先后；摘要仍可进一步压缩优先级 |
| DIM-5 实务可用性 | 5 | 可直接进入红线修订和谈判 |
| DIM-6 格式完整度 | 5 | 摘要、明细、声明和出具信息完整 |

Taste：TASTE-6、TASTE-7 失败。正式意见书外观未证明已经人工复核，也没有明确要求律师核验法源适用性与时效性。技术链路通过：修订版和 Word 报告均可解包，日志为 14 项 applied、11 项 report-only、0 失败。

### 2. 同类但不熟悉：专利许可合同当前候选重跑

证据状态：`current-candidate`；由原始 `.doc` 在候选外临时转换为无批注、无修订 DOCX 后运行，避免复用历史审阅痕迹。证据见 `current-run-receipts.json#patent-current-clean`。

| 维度 | 分数 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 3 | 摘要识别了关键许可风险，但详细依据不可复核 |
| DIM-2 事实与证据 | 1 | 最终报告出现 48 次待补占位，8 项法律依据全部为 `/` |
| DIM-3 逻辑说服力 | 1 | 条款—风险—建议链条丢失 |
| DIM-4 关键问题把握 | 3 | 摘要抓住许可范围、分许可、无效与侵权处理 |
| DIM-5 实务可用性 | 1 | 除摘要外无法用于逐条修改 |
| DIM-6 格式完整度 | 1 | 字段外壳存在，内容为空；日志仍称 8 项全部成功并返回 0 |

Taste：TASTE-6、TASTE-7 失败。本轮已显式传入中立立场，所以不再复用历史案例的“立场待确认”失败；新的当前证据表明，即使立场明确，核心交易字段普遍缺失时仍会输出“有条件可签”，说明可签署性闭环是独立问题。

### 3. 故意缺失背景：当前候选受控边界响应

证据状态：`current-candidate`，但仅单轮 Agent 执行，不构成稳定性证明。

| 维度 | 分数 | 主要依据 |
|---|---:|---|
| DIM-1 法律准确性 | 4 | 不对可签署性和商业合理性作实质判断 |
| DIM-2 事实与证据 | 5 | 准确列出角色、目标、口径、身份确认和附件缺口 |
| DIM-3 逻辑说服力 | 5 | 缺口—限制—补充项—后续动作链条清楚 |
| DIM-4 关键问题把握 | 5 | 先处理决定审查方向的角色和目标 |
| DIM-5 实务可用性 | 5 | 用户可直接逐项补充信息 |
| DIM-6 格式完整度 | 4 | 作为例外响应完整，不冒充正式审查报告 |

八项 taste 全部通过。该结果只能证明本轮受控响应正确，不能证明候选在不同 Agent、不同轮次中稳定执行。

### 4. 候选外合成微案例

四个案例均通过 `contract_copilot_micro_probe.py` 在候选外执行，配置和记忆只写入临时目录；输入、输出和探针观察保存在 `micro-runs/`：

| 案例 | 状态 | 当前观察 |
|---|---|---|
| 审查立场为空 | executed-fail | 非交互 runtime 自动把空立场解析为“其他” |
| 审查人身份未确认 | executed-pass | 缺少 author/organization 时抛出 ValueError，未写身份配置 |
| 旧计划字段导致报告塌缩 | executed-fail | 14 个待补占位、1 个空法律依据，候选函数仍返回 |
| producer 自报成功与复核状态 | executed-fail | 关键字段不完整仍返回；正式外观没有复核状态 |

这些案例是脱敏、最小化的 runtime / renderer 探针，不等于完整合同审查 Agent 语义运行。剩余条款判断案例继续保持 `not-run`。

## 四、最小修复单元

| 优先级 | 类型 | 修复目标 | 回归 |
|---|---|---|---|
| P0 | template/schema | 兼容旧 `review-plan` 字段，禁止有效 finding 统一渲染成占位符 | REG-CONTRACT-001 |
| P0 | checker | 最终报告关键字段为空时非零退出，不采信 applied 数量自报成功 | REG-CONTRACT-002 |
| P0 | intake boundary | `party_role` 为空或待确认时禁止输出风险等级和可签结论 | REG-CONTRACT-003 |
| P1 | template/schema | 区分待复核草稿与已复核正式意见；正式署名外观绑定复核状态 | REG-CONTRACT-004 |

本轮未修改 `contract-copilot`。当前候选重跑与合成探针表明 REG-CONTRACT-001、002、003、004 均存在失败；设计合同内容完整性和审查人缺失阻断形成 PASS_TO_PASS 收据。受控 Agent 缺失背景案例仍通过，但与 runtime 的 role-only 失败共同说明前置边界尚不稳定。

## 五、对 legal-skill-evaluation 的回灌

当前候选重跑和 suite 扩展推动评测 Skill 完成以下升级：

1. 候选哈希新增 `git-tracked` 范围，避免真实合同归档和本地审查人配置污染候选快照。
2. schema 1.1 为每个 case 增加 `candidate_binding`；历史未绑定产出不能支撑 `DOMAIN_VERIFIED` 或 `enter-workflow`。
3. 通用门禁新增原始 finding 与人工裁决的闭环；误报和本轮范围外 finding 必须给理由及证据，不能静默删除。
4. 标准三份材料必须使用不同输入 bundle，防止同一运行重复充当多个 case。
5. 合同深度 rubric 增加“最终报告关键字段完整性”“前置立场门禁”“正式意见复核状态”三项校准规则。
6. 新增 `capability_suite_gate.py`：对 20—50 例案例数量、任务族、层级、来源、候选绑定、执行状态、断言证据和正式结论做 fail-closed 校验。
7. 20 例 suite 明确拆为完整端到端、动态微案例和静态能力合同；`not-run` 断言不得填写 pass/fail，`executed-fail` 必须有失败断言，未全量执行不得签发 `DOMAIN_VERIFIED`。
8. 新增 `capability_run_receipt_gate.py`：已执行案例使用结构化 run record，并复算 record、candidate、input、output、assertion 与本地 artifact 哈希；任意字符串收据和陈旧摘要 fail-closed。

## 六、证据索引

- 机器评测包：`evaluation-package.json`，文件 SHA-256 `5cbe015f052932d35b4fd23820afd4a8e29790c43a92f493aab8e8e6df251f57`
- Evaluation gate 规范化 artifact SHA-256：`b6bb1672923360c54c0d67837583f71a5beb505a5374c270ee7c40146a235f21`
- 当前候选结构化运行收据：`current-run-receipts.json`，文件 SHA-256 `4585dc368d950ba4f95379931c2777d5d4cb7bfa74e9f7c463ddbc9035a2935d`
- 20 例 capability suite：`capability-suite.json`，文件 SHA-256 `7d037f7abfee231512e860600b09841b7a6ed7366fb6efee7d37f27a476f684b`；Suite gate 规范化 artifact SHA-256 `55fa5f5b2230dd1a5ba55a624630cdc81dbdc193ea70ebbadfb7279b83d1b2b4`
- Run receipt gate 规范化 artifact SHA-256：`b208d743bf5674f455069ec3fa398536e06daf239cd7e46a01104c53f8fa5196`；7 条记录全部绑定，5 条 artifact-backed、2 条 digest-only，共复算 12 个本地证据文件
- capability / regression 索引：`capability-regression-seed.json`，文件 SHA-256 `695def33fb8f2b327df5163c8a9bfa2b4fb1a59523e112072c6c10c6aa20d9fe`
- 缺失背景输入清单：`missing-context-input.json`
- 缺失背景响应：`missing-context-output.md`

原始合同正文继续留在 `contract-copilot` 原归档；真实合同 DOCX、完整报告和隔离评测身份不复制进本 Skill，只保存 digest-only 摘要。`micro-runs/` 仅保存可公开复算的脱敏合成输入、候选真实输出和探针观察。
