# Case 01 Materials: 供应商服务合同审查

> v1 重对齐案例材料清单。本案例对应 v0 评测 `case-bundle-260705/case-01-contract-review/` 的重对齐版（参见 [v0 EVALUATION.md](../../../case-bundle-260705/EVALUATION.md) 作为基线）。

## 素材类型（v1 七类分类）

| 类型 | 数量 | 来源 | quality | 用途 |
|------|------|------|---------|------|
| sample（成品文书） | 2 | 历史审查意见书（仓储配送服务协议 + SaaS 服务协议） | silver | 提取结构骨架 / 风格特征 |
| sop（流程规则） | 1 | 律所内部供应商审查清单（8 步骤） | gold | 提取决策点 / 阈值 |
| qa | 0 | 无 | unrated（无 Q&A 素材） | — |
| rules（规则包） | 1 | SOP 中包含的阈值表 | gold | 阈值与判断标准 |
| revisions | 0 | 无 | unrated（无对话修订记录） | — |
| tools-data | 0 | 无 | unrated | — |
| authorities | 0 | 无（从样本中反向提取法条，见 Brief） | unrated（待与原文核对） | 法源验证 |

## v0 → v1 差异（与 case-bundle-260705/case-01 对照）

- **素材分类**：v0 仅 sample × 2 + sop × 1；v1 显式标为 sample / sop / rules / authorities 四类。
- **quality 字段**：v0 未填；v1 全填（silver / gold / unrated）。
- **authorities 单独列出**：v1 起法源作为独立素材类型管理，便于回溯验证状态。
- **三角色拆分**：v0 笼统写"终端用户角色：企业法务部 + 采购部门"；v1 拆为 `operator = buyer-counsel`、`represented_party = buyer`、`output_audience = buyer-internal-team`。
- **法源三列**：v0 法源条目无 jurisdiction / effective_date / verification_status；v1 全部补充。
- **阈值 source 列**：v0 阈值无来源；v1 全部带 source（SOP v3 / sample-002 反推）。
- **安全段**：v0 无；v1 必填，含敏感信息脱敏状态与外传策略。
- **待确认分类**：v0 用 `- [ ]` 列表；v1 按 `blocker` / `warning` 分类。
- **下游契约**：v0 移交语 "请调用 legal-skill-creator 编译"；v1 改为中立 "可交给通用 `skill-creator` 或 `legal-skill-creator`"。