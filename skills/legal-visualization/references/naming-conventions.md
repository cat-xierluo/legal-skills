# 节点命名规范

本文件规定 Legal Visualization 在 VizSpec YAML、drawio XML 标签、`annotations.text` 三处的统一命名。`scripts/normalize_naming.py` 按本文件做偏差检查。

## 总体规则

1. **程序身份严格用术语**：节点标签使用法定身份词，不替换为"对方/我方/客户"等口语化表达。
2. **案由用法律标准名**："民间借贷纠纷"而非"借款"、"买卖合同纠纷"而非"买卖"。
3. **诉讼请求用数字编号稳定引用**：诉讼请求 1、诉讼请求 2 …… 编号在 VizSpec、drawio 标签、附注中必须一致。
4. **证据编号格式 `证据 X-Y`**：X=证据组号，Y=组内序号，如"证据 2-3 表示第二组第 3 份"。
5. **争议/待证/推定不与"事实"混用**：节点标签只用"争议 X""待证 Y""推定 Z"，不写"事实（争议）"。

## 程序身份映射

| 中文标签 | VizSpec `entities[].role` | 备注 |
|---|---|---|
| 原告 | `plaintiff` | 一审起诉方 |
| 被告 | `defendant` | 一审被诉方 |
| 第三人 | `third_party` | 有独立请求权或无独立请求权 |
| 上诉人 | `appellant` | 二审提起方 |
| 被上诉人 | `appellee` | 二审被诉方 |
| 再审申请人 | `retrial_applicant` | 申请再审方 |
| 再审被申请人 | `retrial_respondent` | 再审对方 |
| 申请人 | `applicant` | 仲裁/特别程序申请方 |
| 被申请人 | `respondent` | 仲裁/特别程序被申请方 |
| 申请人（执行） | `execution_applicant` | 强制执行申请方 |
| 被执行人 | `execution_target` | 强制执行对象 |
| 案外人 | `outsider` | 执行异议案外人 |
| 公诉人 | `prosecutor` | 刑事公诉 |
| 被告人（刑事） | `criminal_defendant` | 刑事被告 |
| 自诉人 | `private_prosecutor` | 刑事自诉 |
| 法定代表人 | `legal_representative` | 法人代表 |
| 委托代理人 | `agent` | 律师/代理人 |

## 法律文书与材料

| 中文标签 | VizSpec 字段 | 备注 |
|---|---|---|
| 案由 | `case_type` | 用法律标准名，如"民间借贷纠纷" |
| 诉讼请求 1/2/3 | `annotations[].id` | 数字编号，全图稳定引用 |
| 抗辩 | `relations[].relation_type=claim` | 被告抗辩 |
| 反驳 | `relations[].relation_type=rebuttal` | 原告反驳 |
| 答辩意见 | `annotations[].text` | 放侧栏/底注 |
| 证据 X-Y | `evidence_ref` | X=组号, Y=组内序号 |
| 质证意见 | `annotations[].text` | 放侧栏/底注 |
| 法律依据 | `annotations[].text` | 引用"《民法典》第 123 条"格式 |
| 争议焦点 1/2/3 | `annotations[].id` | 编号稳定 |
| 事实理由 | `annotations[].text` | 放侧栏/底注，不入主图主体 |
| 证据目录 | `annotations[].text` | 与 `evidence_ref` 联动 |

## 关系状态标签前缀

`relations.status` 标签在 drawio 节点上按下表加前缀，便于肉眼识别：

| status | 标签前缀 | 示例 |
|---|---|---|
| `confirmed` | 无 | 借款本金 200 万元 |
| `disputed` | `争议：` | 争议：实际借款人身份 |
| `asserted` | `主张：` | 主张：对方违约 |
| `inferred` | `推定：` | 推定：共同意思表示 |
| `missing` | `待补充：` | 待补充：第三人收款账户 |

## 主体分组

`entities[].group` 用以下标准名：

- `原告方` / `被告方` / `第三人`
- `公司` / `股东` / `实际控制人` / `关联方`
- `银行` / `承兑行` / `贴现行`
- `发包人` / `承包人` / `分包人` / `实际施工人`
- `客户` / `客户决策层` / `客户业务部门` / `客户财务` / `客户法务`
- `团队` / `主办律师` / `协办律师` / `辅助人员`

## 一致性约束

- 同一主体在 VizSpec `entities` 与 drawio 节点标签中必须用同一字符串。
- 同一证据在 `events[].evidence_ref` 与 `annotations[].text` 中编号必须一致。
- 同一诉讼请求在 `relations[].label` 与 `annotations[].id` 中编号必须一致。

## 偏差检查

`scripts/normalize_naming.py` 读 VizSpec YAML + drawio XML，按本文件检查并输出三类偏差：

1. **程序身份偏差**：标签使用了"我方/对方/客户"等口语化表达。
2. **诉讼请求编号不一致**：同一编号在不同字段指代不同对象。
3. **证据编号格式不符**：未使用"证据 X-Y"格式。
