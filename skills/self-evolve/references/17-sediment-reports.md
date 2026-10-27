# 沉淀报告(panel「沉淀报告」tab)

## 定位

`review/inbox/` 下 self-evolve 写出的脱敏 md 报告(迭代周报 / deep-analysis 等),以**阅读视图**在 panel 第 4 个 tab「沉淀报告」统一展示。不再「手动翻 md」。

参照 info-evaluator 的运营模式(`assets/preferences/README.md`:「工作台和脚本都必须通过 `scripts/preference_ledger.py` 访问,不直接编辑文件」),self-evolve 的沉淀报告也走单一收集入口:`render_panel.collect_review_documents()`。

## 来源

| 产物 | 来源脚本 | 频率 |
|---|---|---|
| `iteration/YYMMDD*_weekly-iteration.md` | `scripts/iteration_report.py` | weekly |
| `deep-analysis/YYMMDD*_deep-analysis.md` | `scripts/deep_dream.py --execute` | weekly(可选,默认 `enabled: false`) |
| `YYMMDD*_skill_upgrade_*.md` | `scripts/proposal_store` 历史 | legacy 散落 |
| `YYMMDD*_article_*.md` | `scripts/proposal_store` 历史 | legacy 散落 |

新报告统一由各自写脚本经 `privacy_gate.write_review_artifact` 落盘,不在 panel 直接编辑。

## 安全

- 所有 md 由 `write_review_artifact` 写入,已经过 `privacy_gate.sanitize_text` + `validate_untrusted_source`(原始路径/邮箱/手机/身份证/银行卡/组织名/prompt 注入/secret 全替换/拒绝)。
- panel 前端再过 `render_panel.safe_text`(`validate_untrusted_source` + `validate_text`)第二层防护。
- 单文件 ≤ 20000 字(`safe_text` max_chars),`<details>` 展开 + 滚动,避免一次性渲染大文档。
- 不直接编辑 `review/inbox/` 下的 md——通过写脚本追加。

## 与其他审阅的关系

| Tab | 对象 | 决定语义 |
|---|---|---|
| Review Inbox | proposals(json) | 接受/拒绝/部分接受/观察 |
| 偏好审阅 | workmode 偏好(json) | 接受/观察/拒绝 |
| **沉淀报告** | md 报告 | **阅读视图**(MVP 不带决定) |
| Cron 任务 | scheduled_tasks | 读 |

沉淀报告是 digest,不是决定项(无 accept/reject 语义)。如需校准「提取是否精准」,是下一版(1.7.x)校准维度。

## 访问

- panel 启动后顶部第 4 个 tab「沉淀报告」。
- API:`GET /api/review-documents[?kind=iteration&sort=newest]` → `{documents:[...], total, metrics:{total, this_week, by_kind}}`(独立懒加载,不进 build_panel_data,避免大目录扫描拖累主面板)。
- 收集入口:`scripts/render_panel.collect_review_documents(kind=None, sort="newest", limit=50)`。
- 单一权威入口原则(参 info-evaluator README):其他脚本/前端不应直接 `rglob` review/inbox/,统一经 `collect_review_documents()`。

## Metrics

panel 顶部展示:
- **total**:全集计数(不被 kind/sort/limit 影响)
- **this_week**:近 7 天 mtime 的报告数
- **by_kind**:`{iteration: N, deep-analysis: M, skill_upgrade: K, article: ..., document: ...}`

## 未来(1.7.x)

- **校准维度**:每条归因 sample 可标记「准确 / 不准确 / 不确定」,反馈进 `runtime/sediment-calibration/calibration.jsonl`(append-only),panel 加校准交互。验证 self-evolve 提取质量有反馈闭环。
- 报告摘要结构化:iteration_report 产出 JSON 摘要 + md 双产物,panel 可跨报告聚合。
