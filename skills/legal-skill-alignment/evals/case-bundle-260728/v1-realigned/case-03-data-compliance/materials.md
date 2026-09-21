# Case 03 Materials: App 数据合规扫描

> v1 重对齐案例材料清单。本案例对应 v0 评测 `case-bundle-260705/case-03-data-compliance/` 的重对齐版。

## 素材类型（v1 七类分类）

| 类型 | 数量 | 来源 | quality | 用途 |
|------|------|------|---------|------|
| sample（成品文书） | 1 | 历史合规扫描报告 1 份 | bronze（单样本） | 表格化输出格式 / 风险矩阵 |
| sop | 1 | 合规扫描流程清单（含字段说明） | silver | 扫描维度 / 检查项 |
| qa | 0 | 无 | unrated | — |
| rules | 1 | SOP 中包含的合规判断规则 | silver | 判断标准 |
| revisions | 0 | 无 | unrated | — |
| tools-data | 0 | 无 | unrated | — |
| authorities | 0 | 无（合规法规从样本 / SOP 反推） | unrated（待核对） | 法源验证 |

## v0 → v1 差异

- **素材分类**：v0 描述"样本 × 1 + SOP × 1"；v1 显式标 sample / sop / rules / authorities 四类（rules 与 sop 拆分）。
- **quality 字段**：v0 未填；v1 全填（bronze / silver / unrated）。
- **三角色拆分**：v0 笼统写"终端用户角色：法务总监"；v1 拆为 `operator = compliance-officer`、`represented_party = app-company`（App 运营方）、`output_audience = company-management`（管理层决策）。
- **stage 修正**：v0 因 stage 枚举不完整只能用 `non_litigation`；v1 stage 枚举扩展后用 `post_launch`（运营中合规体检），更精确。
- **法源三列**：v0 法源无版本；v1 补齐——《个人信息保护法》《数据安全法》《网络安全法》《App 违法违规收集使用个人信息行为认定方法》等关键法规全部带 effective_date。
- **表格化输出**：v0 B5 断点已识别"输出格式多样性"，v1 起在 Outputs 段明确 `产出形态 = mixed`，并在 prompt-output.md 末尾附"输出格式多样化指引"。
- **待确认分类**：v0 用 `- [ ]` 列表；v1 按 `blocker` / `warning` 分类。