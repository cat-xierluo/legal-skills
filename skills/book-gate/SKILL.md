---
name: book-gate
description: 书籍/长文出版物的 acceptance harness（验收内核）。针对作者最终看到的成品（Markdown 源 + 内联 SVG + PNG 渲染 + 可选 DOCX）独立验证并控制完成状态。生产者（worker/作者）的 done 只等于 CANDIDATE，PR 合并只等于 MERGED，独立 verifier 验证通过才是 VERIFIED，缺证不准归档。让 Agent 漏项无法穿过验收门、无法获得"完成"状态。触发词：book-gate verify / 出版前验收 / 验收门禁 / 防漏项 / 回归验证 / fail-closed / 成品验证。
version: 0.1.0
---

# book-gate：出版 acceptance harness

## 为什么存在（核心范式）

Agent harness（让 worker 读规则/分工/运行/汇报/合并）**无法消灭漏项**——规则在长上下文不被稳定调用、worker 自评偏乐观、规则/版本/多份表示持续漂移。book-gate 不试图保证 Agent 不犯错，而是 **保证错误无法穿过验收门、无法获得"完成"状态**（fail-closed）。

区分两种 harness：
- **agent harness**：worker 读规则、改文件、commit、PR、汇报——**产出 candidate**。
- **acceptance harness**（本 skill）：针对**成品**独立验证，控制完成状态——candidate 能否升级为 VERIFIED / CLOSED。

## 五支柱

1. **约束机器化**：每条要求 → 结构化 requirement 记录（`requirement_id` / 适用范围 / 被验证产物阶段 / 验证器 / 阈值 / 证据路径 / 是否阻断 / `needs_human_review`）。**无自动验证器的规则强制进 `needs_human_review`，不能默认通过。**
2. **分阶段检查正确产物**：不查源码代理指标，查作者最终看到的成品：
   - **Markdown 源**：mermaid 残留 / 图表顺序 / 引用 / 术语 / 长段 / 脚注源格式
   - **内联 SVG**：viewBox / 可见 bbox / padding / 文字碰撞 / 箭头端点与目标框距离
   - **PNG 渲染**：重叠 / 紧凑度 / 箭头方向 / 文字消失
   - **可选 DOCX**：图片数 / 脚注 XML / 字体 / 页边距
   - （Word/PDF 仅最终展示，**不进强制 gate**——作者通读兜底；本 skill 验证 Markdown + SVG + PNG，DOCX 可选）
3. **生产者与验证者分离**：生产 worker 只能提交 `CANDIDATE`，**无权批准自己**。独立 verifier 干净只读环境，自己重生成产物，不先读生产者"已通过"结论；确定性检查优先；视觉项用 fresh-context 或不同模型；主观项用作者标定的正反例校准。
4. **证据绑定成品哈希**：每项结果记录 `candidate SHA + 规范版本 + 验证器版本 + 产物 hash + requirement_id + 逐项 PASS/PARTIAL/FAIL + 页面/图号/bbox + 截图/日志路径`。正文/SVG/转换器/字体/模板任一变化，旧证据自动失效。
5. **fail-closed 状态**：`CONTRACTED → IN_PROGRESS → CANDIDATE → SOURCE_VERIFIED → RENDERED → INDEPENDENT_VERIFIED → MERGED → RELEASE_VERIFIED → CLOSED`。worker `done`=CANDIDATE；PR 合并=MERGED；最终成品对应 hash 验证通过=`*_VERIFIED`；文档同步后 CLOSED。**任一 blocking 项缺证/失败，禁止归档。all-of gate——不能用"平均分"抵消一处缺图/箭头重叠/图注错位。**

## 调用

```bash
# 验证一个 candidate（manuscript 目录）
book-gate verify <manuscript-dir> [--requirements requirements.yaml] [--stage markdown|all] [--out evidence-dir]
#   blocking FAIL → 退出码 1（fail-closed），candidate 不能升级 SOURCE_VERIFIED

# 查看证据包
book-gate status <evidence-dir>
```

## 回归机制（最重要）

作者发现的每个真实错误 → 转回归样例：反向/悬空箭头、viewBox 多 80px、文字与序号重叠、两图直接相邻、图注归属错误、mermaid 残留、ASCII 单引号、脚注星号、页边距/字体。
**先故意注入这些错误到测试样本，验证 gate 能否稳定报错**（mutation testing 思路）——一个连已知错误都抓不住的 auditor，不具备放行资格。回归样本存 `references/regression-samples/`。

## 指标
- 硬约束可执行覆盖率：100%
- 本次改动视觉项成品验证率：100%
- 已知回归复发：0
- P0 成品逃逸：0
- verifier 被作者推翻率：逐步降至 5% 以下（区分假阳性 vs 真漏）

## 目录结构
```
book-gate/
├── SKILL.md                       # 本文件（架构 + 调用）
├── requirements.yaml              # 约束机器化：requirement 清单（id/stage/verifier/blocking/needs_human_review）
├── CHANGELOG.md
├── scripts/
│   ├── book-gate.py               # 主入口：verify（跑 requirement + 输出证据包 + fail-closed 退出码）
│   └── checkers/
│       └── markdown_checker.py    # markdown 阶段验证器（mermaid/图表DSL/中文撇号）
└── references/
    └── regression-samples/        # ch01 正反样本（故意注入已知错误）
```

## 范围与边界
- **验证对象**：Markdown 源 + 内联 SVG 源 + PNG 渲染（核心）；DOCX 结构（可选层）；Word/PDF 不进强制 gate（作者通读兜底）。
- **不替代 agent harness**：worker 仍读规则/分工/commit；book-gate 只在"完成状态"关口独立验证。
- **通用跨项目**：requirement 清单项目自维护（每本书的 `requirements.yaml` 不同）；本 skill 提供验证器框架 + fail-closed 状态机，跨书复用。

## v0.1 已实现 / v0.2+ 待办
- ✅ v0.1：markdown 阶段验证器（MD-001/002/004）+ requirement schema + 证据包（candidate SHA 绑定）+ fail-closed 退出码。
- ⏳ v0.2+：SVG 验证器（复用 writing-reviewer figure-style）/ PNG 渲染验证器 / DOCX 结构验证 / 独立 verifier 强制实现（干净只读环境重生成）/ inject-regression 命令 + ch01 正反样本库 / 状态机持久化（candidate→CLOSED 文件锁定）。
