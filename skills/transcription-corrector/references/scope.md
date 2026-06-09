# Scope

> 本文件聚焦 skill 的**概述 / 适用边界**。
> 配置示例与配置解耦原则见 [config-decoupling.md](config-decoupling.md)。
> 工作流判断准则（误转写识别、口语词精简、并列停顿、必检清单、ASR 高频模式）见 [correction_patterns.md](correction_patterns.md)。
> 首次使用流程（复制 example.yaml、跑一次试跑）见 [first_use.md](first_use.md)。

## 概述

把 raw 转录稿里"听得对但写不对"的同音/形近/拼写错误按用户词典统一改对，并按需做轻度润色。**不做**：改写、总结、删减、改事实、生成课程章节。

| 模式 | 触发 | 输出 |
|---|---|---|
| **纠错模式（默认）** | 拿到 raw 转录稿，要先做"校对" | `archive/.../{原文件}_corrected.md` + 校对对照日志 |
| **纠错 + 轻度润色** | 还要顺手把发言人合并/标点整理 | 在纠错基础上再润色，输出到 `archive/.../{原文件}_polished.md` |

**与下游处理工作的边界**：
- 本 skill 不输出课程大纲、不重组章节、不改写为书面课程；只做"读起来对、不再丢脸"这一步。
- 用户词典 YAML 格式（`version` + `terms` 列表）已成为本 skill 公开的接口约定；其他下游处理工作可以按需读取同一份词典文件。

## 适用场景

- 拿到 ASR 输出的转录稿，需要先校对再发布/归档
- 跨多次整理同一批转录稿（用户词典复用）
- 客户沟通录音转写稿，需要修正人名/产品名/术语

## 不适用

- 重写为课程章节、报告、总结
- 完全空白的素材，需要"创作"
- 单条语句改写润色 → 手工

## references 目录分工

| 文件 | 职责 |
|------|------|
| [first_use.md](first_use.md) | 一次性配置引导（复制 example.yaml、跑试跑、多用户软链）|
| [correction_patterns.md](correction_patterns.md) | 工作流判断准则（误转写识别、口语词精简、并列停顿、必检清单、ASR 高频模式）|
| **本文件（scope.md）** | 概述 / 适用边界 |
| [config-decoupling.md](config-decoupling.md) | 配置示例 / 配置解耦原则（评价规范）|
