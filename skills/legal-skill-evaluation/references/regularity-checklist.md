# 通用质量快速核查桥

本文件只用于在缺少完整 skill-lint 收据时做人工分流，不是通用 Skill 规范的权威副本。目录、frontmatter、安全、Harness、指令稳定性和发布治理的现行判则，以运行时可用的 skill-lint 版本为准。

## 使用边界

- 发布验收或正式结论：运行 skill-lint，保存候选哈希、版本、命令和原始收据。
- 标准评测：优先消费与当前候选哈希一致的 skill-lint 结果；结果缺失或过期时补跑。
- 快速评测：可用本页做非权威初筛，但证据状态保持 NOT_VERIFIED。
- 不把本页的检查结果写成 HARNESS_REVIEW_VERIFIED、INSTRUCTION_STABILITY_VERIFIED 或 DOMAIN_VERIFIED。

## 快速分流清单

| 类别 | 快速问题 | 发现问题后的去向 |
|------|----------|------------------|
| 触发与边界 | 功能、使用时机、不使用时机是否能被识别？ | skill-lint 触发描述检查 |
| 结构与引用 | 核心文件是否存在，引用是否可达，支持文件是否渐进披露？ | skill-lint 结构与引用检查 |
| 业务流 | Trigger / Intake / Reasoning / Output / Safety 是否形成可执行闭环？ | skill-lint 业务流检查 |
| 安全 | 是否存在凭证、危险执行、隐私泄露、提示注入或未披露外联？ | skill-lint 安全检查；命中则阻断 |
| 可评估性 | 是否有范围、红线、案例、验收标准与动态评测入口？ | skill-lint 可评估性检查 |
| Harness | 关键约束是否有主动检查器、正负案例、可观测量和失败注入？ | skill-lint Harness 审查 |
| 指令稳定性 | 约束、检查器、案例、测量和外部评估证据是否形成闭环？ | skill-lint 指令稳定性门禁 |
| 发布治理 | 版本、许可证、变更记录与目录状态是否一致？ | skill-lint 发布治理检查 |

## 结果映射

将 skill-lint 输出映射到本技能评测包的 generic_gate：

| 本技能字段 | 来源 |
|------------|------|
| skill_lint_version | 实际运行版本 |
| candidate_sha256 | 被测 Skill 候选快照哈希 |
| candidate_hash_scope | 候选快照读取范围（git-tracked / full-directory） |
| raw_hard_findings | 通用门禁原始阻断发现，不静默删除 |
| hard_findings | 阻断级或 Hard Fail 发现 |
| finding_adjudications | 误报、不适用或本轮范围外 finding 的理由与证据 |
| harness_status | HARNESS_REVIEW_VERIFIED 或 NOT_VERIFIED |
| instruction_stability_status | INSTRUCTION_STABILITY_VERIFIED 或 NOT_VERIFIED |
| domain_status | DOMAIN_VERIFIED 或 NOT_VERIFIED |
| evidence_receipts | 原始报告、命令输出、基线与留出集收据的路径或摘要 |

## 候选绑定

只有当 `generic_gate.candidate_sha256` 与 `candidate.sha256` 完全一致，且两者 hash scope 相同时，才消费已有结论。候选文件或读取范围发生变化后，旧结论只能作为历史背景，不能继续支撑当前版本。

## 法律领域继续评什么

通用质量门通过后，本技能继续评估 skill-lint 不替代判断的部分：三份真实测试材料上的法律准确性、事实忠实、论证、重点把握、实务可用性、交付格式、律师 taste，以及修复后是否通过 FAIL_TO_PASS / PASS_TO_PASS 双门槛。
