---
name: 10-creditcard
title: 10-信用卡纠纷-民事起诉状 — 要素定稿（精调级）
case_type: 10-creditcard
template_tree: 10-信用卡纠纷-民事起诉状
version: "1.0"
status: stable
generated: 2026-08-17 由 10-creditcard-sample.json + fill_template 规则反推
---

# 10-信用卡纠纷-民事起诉状（精调级定稿）

> 模板树 `templates/10-信用卡纠纷-民事起诉状/`；规则 `build_rules_*`（叠加模式：案由特定在前 + 通用层在后）。
> 通用块（当事人 自然人N/法人N、编号标题填空、唯一标签、调解、具状、**通用勾选**）见 `../common-elements.md` 与骨架 `../skeletons/10-信用卡纠纷-民事起诉状.md`，此处只列案由特定增量。

## 一、案由特定字段（诉讼请求/事实）

| elements 路径 | 类型 | 渲染方式 |
|---|---|---|
| `本金` | {截至日期,金额} | 整段重写 |
| `利息` | {截至日期,合计,计算方式} | 整段重写 |
| `后续利息起算日` | date | 整段重写（自 X 之后…至实际清偿之日） |
| `明细` | str | 标签追加 |
| `实现债权费用` | {勾选,费用明细} | 两段式 |
| `事实与理由.透支金额/计算标准/违约责任` | str | 标签追加 |

## 二、通用勾选（本案由大勾选群走此机制）

elements 顶层 `勾选` 键：`{"锚文本": "选项原文"}`（多选用列表）。示例：

```json
"勾选": {"是否到期：": "是"}
```

锚=骨架"段落原文"列任一稳定子串；选项=骨架"选项/标签"列原文。

## 三、夹具与回归

- 样例：`tests/fixtures/10-creditcard-sample.json`；断言见 `tests/run_e2e.sh` CHECKS["tests/output/10-creditcard.docx"]
