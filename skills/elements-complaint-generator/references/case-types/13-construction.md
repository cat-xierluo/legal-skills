---
name: 13-construction
title: 13-建设工程施工合同纠纷-民事起诉状 — 要素定稿（精调级）
case_type: 13-construction
template_tree: 13-建设工程施工合同纠纷-民事起诉状
version: "1.0"
status: stable
generated: 2026-08-17 由 13-construction-sample.json + fill_template 规则反推
---

# 13-建设工程施工合同纠纷-民事起诉状（精调级定稿）

> 模板树 `templates/13-建设工程施工合同纠纷-民事起诉状/`；规则 `build_rules_*`（叠加模式：案由特定在前 + 通用层在后）。
> 通用块（当事人 自然人N/法人N、编号标题填空、唯一标签、调解、具状、**通用勾选**）见 `../common-elements.md` 与骨架 `../skeletons/13-建设工程施工合同纠纷-民事起诉状.md`，此处只列案由特定增量。

## 一、案由特定字段（诉讼请求/事实）

| elements 路径 | 类型 | 渲染方式 |
|---|---|---|
| `工程款利息违约金` | {截至日期,利息,违约金} | 日期利息句（与 09 同款句式） |
| `请求至实际清偿之日/超付利息至清偿` | bool | occurrence 0/1 两处同锚 |
| `担保权利/连带责任` | {勾选,内容} | 两段式 |
| `停工损失/赔偿金` | str | 『是☑ X X 元』形态句 |
| `超付利息` | {截至日期,利息} | 整段重写 |

## 二、通用勾选（本案由大勾选群走此机制）

elements 顶层 `勾选` 键：`{"锚文本": "选项原文"}`（多选用列表）。示例：

```json
"勾选": {"是□ 内容": "是"}
```

锚=骨架"段落原文"列任一稳定子串；选项=骨架"选项/标签"列原文。

## 三、夹具与回归

- 样例：`tests/fixtures/13-construction-sample.json`；断言见 `tests/run_e2e.sh` CHECKS["tests/output/13-construction.docx"]
