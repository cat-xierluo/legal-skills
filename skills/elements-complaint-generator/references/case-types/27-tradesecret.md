---
name: 27-tradesecret
title: 27-侵害商业秘密纠纷-民事起诉状 — 要素定稿（精调级）
case_type: 27-tradesecret
template_tree: 27-侵害商业秘密纠纷-民事起诉状
version: "1.0"
status: stable
generated: 2026-08-17 由 27-tradesecret-sample.json + fill_template 规则反推
---

# 27-侵害商业秘密纠纷-民事起诉状（精调级定稿）

> 模板树 `templates/27-侵害商业秘密纠纷-民事起诉状/`；规则 `build_rules_*`（叠加模式：案由特定在前 + 通用层在后）。
> 通用块（当事人 自然人N/法人N、编号标题填空、唯一标签、调解、具状、**通用勾选**）见 `../common-elements.md` 与骨架 `../skeletons/27-侵害商业秘密纠纷-民事起诉状.md`，此处只列案由特定增量。

## 一、案由特定字段（诉讼请求/事实）

| elements 路径 | 类型 | 渲染方式 |
|---|---|---|
| `费用名为公证费` | {金额,凭证} | fee=律师费/公证费/差旅费（与 22/23 差异） |
| `秘密点/保密措施等事实段` | — | 标题填空走通用 |

## 二、通用勾选（本案由大勾选群走此机制）

elements 顶层 `勾选` 键：`{"锚文本": "选项原文"}`（多选用列表）。示例：

```json
"勾选": {"被告获利": "被告获利"}
```

锚=骨架"段落原文"列任一稳定子串；选项=骨架"选项/标签"列原文。

## 三、夹具与回归

- 样例：`tests/fixtures/27-tradesecret-sample.json`；断言见 `tests/run_e2e.sh` CHECKS["tests/output/27-tradesecret.docx"]
