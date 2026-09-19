# Case 02 Materials: 著作权侵权代理词

> v1 重对齐案例材料清单。本案例对应 v0 评测 `case-bundle-260705/case-02-copyright-litigation/` 的重对齐版。

## 素材类型（v1 七类分类）

| 类型 | 数量 | 来源 | quality | 用途 |
|------|------|------|---------|------|
| sample（成品文书） | 1 | 历史代理词 1 份 | bronze（单样本） | 提取结构骨架 / 风格特征 |
| sop | 0 | 无 | unrated（无 SOP） | — |
| qa | 0 | 无 | unrated | — |
| rules | 0 | 无独立规则包 | unrated | — |
| revisions | 0 | 无 | unrated | — |
| tools-data | 1 | 证据目录（含侵权比对表） | silver | 输入数据 / 关联证据 |
| authorities | 0 | 无（从样本中反向提取，见 Brief） | unrated | 法源验证 |

## v0 → v1 差异

- **素材分类**：v0 仅 sample × 1 + 证据目录 × 1；v1 显式标 sample / tools-data / authorities 三类。
- **quality 字段**：v0 未填；v1 全填（bronze / silver / unrated）——单样本场景诚实标 bronze。
- **三角色拆分**：v0 笼统写"终端用户角色：法院"；v1 拆为 `operator = plaintiff-counsel`、`represented_party = plaintiff-rights-holder`、`output_audience = judge`（**关键防错**：法官是 output_audience，不是 represented_party）。
- **法源三列**：v0 法源条目无版本信息；v1 补充——重点是《著作权法》多个司法解释的版本差异。
- **待确认分类**：v0 用 `- [ ]` 列表；v1 按 `blocker` / `warning` 分类，单样本场景诚实标 warning。
- **下游契约**：v0 → v1 同 case-01。