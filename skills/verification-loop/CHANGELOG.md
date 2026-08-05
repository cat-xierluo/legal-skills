# Verification Loop Skill 变更记录

## [1.0.1] - 2026-08-05

### 改进
- **压缩 description**：321 → 201 字符，与 skill-lint 同量级。8 阶段细节移到正文（正文已有表格），description 保留「何时用 + 做什么 + 硬门禁要点 + 不要用于」，提升模型从候选池选 skill 时的触发命中率。
- **断言原则加 e2e 语境标注**：SKILL.md 工作原则第 3 条加「教用户写 e2e 时」前缀，明确「canvas 像素非空 / textLayerStatus ≠ unknown」是给用户的断言示例，非本 skill 产出视觉内容，消除读者与静态审查器（skill-lint ISG-002）对模态的误判。
- **初次 skill-lint 审查**：harness_failure_audit PASS（0 findings）；instruction_stability_gate NOT_VERIFIED（ISG-001/003/004 属初版流程指引型 skill 正常状态，未声称「稳定完成」；ISG-002 为静态关键词误判，已用语境标注缓解，不追修以免损害教学价值）。

## [1.0.0] - 2026-08-05

### 新增
- **初版发布**：代码改完后的验证门禁 skill，8 阶段验证（构建 / 类型 / lint / 单测 / **e2e 功能** / **真机** / 安全 / diff）。
- **e2e + 真机硬门禁**（阶段 5/6）：解决「编译过 ≠ 功能可用」——typecheck/build/lint/单测全过，实机仍可能崩，只有 e2e（功能验证）+ 真机能抓到。
- **项目类型分支**：Tauri 桌面 / Web / 服务 / Skill，各有验证命令。
- **断言深度规范**：断言功能结果（像素/文字/状态），非「存在元素」（防伪渲染）。
- **回归规范**：Bug 修复必须新增复现测试。
- **验证报告**：8 阶段 PASS/FAIL + Overall READY/NOT READY（e2e/真机是 READY 硬门禁）。
- **references/**（5 篇）：eight-phases-rationale（8 阶段理由）/ assertion-depth（断言深度）/ e2e-practice（e2e 实践）/ test-pyramid（测试金字塔）/ lessons-from-practice（实践教训反哺）。
- **LICENSE.txt**：MIT 许可证，与 skill-lint 模板一致。
