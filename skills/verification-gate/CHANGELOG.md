# Verification Gate Skill 变更记录

## [1.0.2] - 2026-08-05

### 改进
- **重命名 verification-loop → verification-gate**：规避 ClawHub 等同名/近似同名 skill，检索更友好；语义更贴合「验证门禁」定位。目录、SKILL.md name、README、marketplace.json 同步更新。
- **新增「本地 vs CI 门禁」小节**：明确「CI 不是另一种验证，是同一套验证的自动化载体」；本地即可跑完整 8 阶段验证，CI 是可选强化（阻断 PR 合并）；平台不限 GitHub Actions（GitLab CI / Gitea / Jenkins / act / husky·lefthook pre-push 均可）。
- **8 阶段表加「CI」列**：标注哪些阶段进 CI（1-5 + 7-8 为 PR 阻断项）、哪些通常本地/真机跑（阶段 6）。
- **验证报告加「CI 门禁」行**：CI job 红 = 验证报告 NOT READY。
- **e2e-practice.md CI 模板扩写**：从单段 GitHub Actions YAML 扩为「通用结构 + 无 GitHub Actions 也能做」对照表，强调 build 产物上跑 e2e、真机单独跑。
- **新增「本地开发：哪些验证必要」小节**：按场景给出最低必要清单（日常循环 = 1-2-4-5；提 PR = +6 真机 +7 安全 +8 diff；3 lint/7 安全交给 hook/CI 自动化），明确「最低线不是 1-4，宣称完成前 5（及该场景 6）必须过」。
- **references 导航与交叉引用补全**：SKILL.md 参考文档列表加「何时读 + 对应章节」；5 篇 reference 开头加引导头并互链（eight-phases-rationale 回链本地开发清单、assertion-depth 补「CI 同样适用」、e2e-practice/test-pyramid/lessons-from-practice 加「何时读」）；lessons-from-practice 教训 5 快速模式与 SKILL 新清单对齐互链。

### 技术优化
- **重跑 skill-lint 验证改名 + CI 章节后结构合规**：
  - `harness_failure_audit`：**PASS**（hard 0 / warning 0 / info 0 / total 0，退出码 0）——改名与新增内容未破坏 frontmatter、引用或目录可达性。
  - `instruction_stability_gate assess`：**NOT_VERIFIED**（ISG-001/002/003/004）——与 1.0.1 状态一致，属流程指引型 skill 正常状态（不自带领域 checker、未声称「稳定完成」、ISG-002 为静态关键词对 e2e 视觉断言的模态误判，已用语境标注缓解）；未引入新增硬失效，不追修以免损害教学价值。

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
