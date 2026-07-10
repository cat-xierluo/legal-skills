# 更新日志

本文件记录 book-gate 技能的所有重要变更。

## [0.1.0] - 2026-07-11

### 新增（MVP：markdown 阶段 acceptance harness）
- **五支柱架构**（SKILL.md）：约束机器化（requirements.yaml）+ 分阶段检查正确产物 + 生产者验证者分离 + 证据绑定 candidate SHA + fail-closed 状态机（CONTRACTED→…→CLOSED，worker done=CANDIDATE / PR 合并=MERGED / hash 验证=VERIFIED）。
- **markdown 阶段验证器**（`scripts/checkers/markdown_checker.py`）：
  - MD-001 禁 mermaid 代码块（hard，转 Word 降级文本）
  - MD-002 禁 plantuml/dot/graphviz/flowchart 等非 SVG 图表 DSL（hard）
  - MD-004 中文夹 ASCII 撇号笔误（soft，md2word isalpha 回归·源稿建议用中文单引号）
- **主入口**（`scripts/book-gate.py`）：`verify` 跑所有 requirement → 输出证据包 JSON（绑 candidate SHA + 规范版本 + gate 版本 + 逐项 PASS/PARTIAL/FAIL/NEEDS_HUMAN_REVIEW），**blocking 项 FAIL/ERROR/缺证 → 退出码 1（fail-closed）**。无验证器的 requirement 强制 NEEDS_HUMAN_REVIEW（不默认通过）。
- **requirement schema**（`requirements.yaml`）：id/stage/scope/description/verifier/threshold/blocking/needs_human_review。

### 背景
法律 AI 书 acceptance harness 诊断（ultra-research 研究触发，PM 独立验证层层纠偏）确立核心范式：**不试图保证 Agent 不犯错，而保证错误无法穿过验收门、无法获得"完成"状态**。book-gate 是该范式的可复用出版组件（跨书复用）。诊断过程本身（`<style>` 规则四轮修订、md2word isalpha/footnote 两个真 bug、mermaid 审查盲区）反向印证了 acceptance harness 的必要性。

### 未做（v0.2+）
- SVG 阶段验证器（viewBox/padding/文字碰撞/箭头端点，复用 writing-reviewer figure-style 逻辑）
- PNG 渲染验证器（重叠/紧凑度/文字消失）
- DOCX 结构验证（图片数/脚注XML/字体，可选层）
- 独立 verifier 强制实现（干净只读环境重生成，与生产者分离）
- inject-regression 命令 + ch01 正反样本库（references/regression-samples/）
- 状态机持久化（candidate→SOURCE_VERIFIED→CLOSED 的文件锁定）
