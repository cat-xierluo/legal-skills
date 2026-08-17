---
name: 23-trademark
title: 23-侵害商标权纠纷-民事起诉状 — 要素定稿（精调级）
case_type: 23-trademark
template_tree: 23-侵害商标权纠纷-民事起诉状
version: "1.0"
status: stable
generated: 2026-08-17 由 23-trademark-sample.json + fill_template 规则反推
---

# 23-侵害商标权纠纷-民事起诉状（精调级定稿）

> 模板树 `templates/23-侵害商标权纠纷-民事起诉状/`；规则 `build_rules_*`（叠加模式：案由特定在前 + 通用层在后）。
> 通用块（当事人 自然人N/法人N、编号标题填空、唯一标签、调解、具状、**通用勾选**）见 `../common-elements.md` 与骨架 `../skeletons/23-侵害商标权纠纷-民事起诉状.md`，此处只列案由特定增量。

## 一、案由特定字段（诉讼请求/事实）

| elements 路径 | 类型 | 渲染方式 |
|---|---|---|
| `同 22 著作权结构` | — | 经济损失金额句/费用行/标签；商标专用权与侵权情形勾选走通用勾选 |

## 二、通用勾选（本案由大勾选群走此机制）

elements 顶层 `勾选` 键：`{"锚文本": "选项原文"}`（多选用列表）。示例：

```json
"勾选": {"法定赔偿": "法定赔偿"}
```

锚=骨架"段落原文"列任一稳定子串；选项=骨架"选项/标签"列原文。

## 三、夹具与回归

- 样例：`tests/fixtures/23-trademark-sample.json`；断言见 `tests/run_e2e.sh` CHECKS["tests/output/23-trademark.docx"]
