---
name: verification-gate
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.0.2"
license: MIT
description: 代码改完后的验证门禁。完成 feature / 重大变更 / 创建 PR / 重构 / 声称「修完」前使用——跑 8 阶段验证，其中 e2e 功能 + 真机是 READY 硬门禁（编译过 ≠ 功能可用）。覆盖 Tauri 桌面 / Web / 服务 / Skill 四类分支。本地即可跑完整验证，CI 是可选自动化强化（平台不限 GitHub Actions）。不要用于：业务领域验证、Skill 质量审查（用 skill-lint）、纯文档变更、一次性脚本。
---

# Verification Gate（代码改完后的验证门禁）

本 skill 是「代码改完 → 声称完成 / 提交 PR」之间的**强制验证门禁**。核心解决一个问题：**编译过 ≠ 功能可用**。

> 直接教训：改完 reader worker 加载，`typecheck` / build / lint / 单测全过，就声称「修完」，实机却「文字层未知」（`textLayerStatus` 卡 unknown）崩——编译层根本抓不到运行时功能问题。这类坑的唯一解是 **e2e（功能验证）+ 真机**。

## 工作原则

- **先编译层（1-4），再功能层（5-6）**：编译层是前置门禁，但**不充分**；功能层（e2e + 真机）才是完成线。
- **e2e/真机是硬门禁**：5/6 不过 = NOT READY，无论 1-4 多干净。
- **断言功能结果，非「存在元素」**：教用户写 e2e 时断言「canvas 像素非空 / textLayerStatus ≠ unknown / 点击后面板真的弹出」，而非「存在 canvas / 存在按钮」（防伪渲染 / 假成功）。
- **Bug 修复必须新增复现测试**（回归规范）：修完一个 bug，加一条能复现该 bug 的 e2e/单测，防止回归。
- **不采信生产者（worker/PM 自己）自报 PASS**：跑实际命令，看实际输出。
- **按项目类型选验证命令**：Tauri 桌面 / Web / 服务 / Skill，命令不同（见 §项目类型分支）。

## 8 阶段验证

| # | 阶段 | 门禁 | 完成线 | CI |
|---|---|---|---|---|
| 1 | 构建（build / cargo check） | 失败则停，不继续 | 前置 | ✅ 进 CI（PR 阻断项） |
| 2 | 类型检查（typecheck） | 关键错误清零 | 前置 | ✅ 进 CI（PR 阻断项） |
| 3 | Lint（`--max-warnings=0` + 依赖环） | 零警告 + 无依赖环 | 前置 | ✅ 进 CI（PR 阻断项） |
| 4 | 单元测试（vitest 分层） | 通过 + 覆盖率达标 | 前置 | ✅ 进 CI（PR 阻断项） |
| **5** | **e2e 功能验证（Playwright）** | **功能结果断言**（非存在元素） | **核心完成线** | ✅ 进 CI（PR 阻断项，关键） |
| **6** | **真机验证（etv / build / staging）** | **真实运行时行为** | **核心完成线** | ⚠️ 通常本地 / staging 跑（CI 难模拟真机，按需） |
| 7 | 安全扫描（密钥 / debug 日志） | 无泄露 / 无遗留 console.log | 前置 | ✅ 进 CI（PR 阻断项） |
| 8 | Diff 审查（范围 / 越界） | 变更合规，无 forbidden 文件 | 前置 | ✅ 进 CI（PR 阻断项） |

> **CI 列说明**：✅ = 建议在 CI 自动跑、失败即阻断 PR 合并；⚠️ = 真机环境 CI 一般难以模拟，放本地或独立 staging 流水线跑。本地手动跑时 8 阶段全跑，CI 跑 1-5 + 7-8（缺真机）。

### 阶段 1-4：编译层（前置门禁，不充分）

```bash
# 1 构建
npm run build 2>&1 | tail -20          # 前端
cd src-tauri && cargo check 2>&1 | tail # Tauri Rust

# 2 类型检查
npm run typecheck 2>&1 | tail

# 3 Lint（严格：零警告 + 依赖环）
npm run lint -- --max-warnings=0 2>&1 | tail
npx depcruise --config .dependency-cruiser.cjs src 2>&1 | tail  # 依赖环（如有）

# 4 单元测试（分层）
npm test 2>&1 | tail -50                # vitest（unit + integration + dom 分层）
```

**门禁**：任一失败 → 停，修复后再继续。但这 4 层全过 **≠ 功能可用**。

### 阶段 5：e2e 功能验证（核心完成线）

**这是「编译过 ≠ 功能可用」的唯一解**。用 Playwright（或等价）驱动应用，断言**功能结果**。

```bash
npm run test:e2e -- e2e/reader-renders.spec.ts --workers=1
# 或项目既有：npm run verify:ui-layout（结构）/ verify:reader-e2e（功能）
```

**断言深度**——不只「存在元素」，断言功能结果（见 `references/assertion-depth.md`）。

**门禁**：e2e 不过 = NOT READY（不提交 PR / 不声称 behavior-complete / worker STATUS 不写 done）。

### 阶段 6：真机验证（核心完成线）

dev server e2e 不够——真实运行时（Tauri WKWebView / Web build 产物 / 服务 staging）行为可能不同。

| 项目类型 | 真机验证 |
|---|---|
| Tauri 桌面 | `npm run tauri build` 产物实机（或 etv：`WEBKIT_INSPECTOR_SERVER` + tauri dev 真机 DOM + 截图） |
| Web | `npm run build` + `vite preview`（build 产物，非 dev server） |
| 服务 | staging 环境真实请求 |

**门禁**：真机行为与 dev e2e 一致；prod-only 问题（worker/协议/路径）必须真机抓到。

### 阶段 7-8：安全 + Diff（前置）

```bash
# 7 安全
grep -rnE "sk-|api_key|password|token" --include="*.ts" --include="*.rs" src/ src-tauri/ 2>/dev/null | grep -viE "test|fixture|env|placeholder" | head
grep -rn "console.log" --include="*.ts" --include="*.tsx" src/ 2>/dev/null | head

# 8 Diff 审查
git diff --stat
git diff HEAD~1 --name-only   # 逐文件审：非预期变更 / 缺失错误处理 / forbidden 文件
```

## 项目类型分支（按项目选验证命令）

### Tauri 桌面

```bash
npm run build && cd src-tauri && cargo check   # 1 构建
npm run typecheck                                # 2 类型
npm run lint                                     # 3 lint
npm test                                         # 4 单测
npm run test:e2e -- e2e/reader-renders.spec.ts   # 5 e2e（打开 PDF 渲染 + textLayerStatus 断言）
# 6 真机：npm run tauri build 产物实机 / etv（WKWebView 真机 DOM + 截图）
```

真机验证做法见 `references/e2e-practice.md`（Tauri etv 段）。

### Web

```bash
npm run build && npm run typecheck && npm run lint && npm test   # 1-4
npm run test:e2e                                                  # 5 Playwright（CI 也跑）
# 6 真机：npm run build + vite preview（build 产物）
```

### 服务

```bash
npm run build && npm run typecheck && npm run lint   # 1-3
npm test                                              # 4 unit + integration
# 5 integration test（HTTP 请求断言响应）
# 6 真机：staging 环境真实请求
```

### Skill

引用 `skill-lint`（已有 Skill 创建质量审查）。本 skill 不重复 skill-lint 的职责。

## 触发时机

- 完成 feature 或重大代码变更后
- **创建 PR 之前**（PR 合并的硬门禁）
- 重构之后
- **声称「修完」「behavior-complete」「done」之前**（e2e/真机不过不声称）
- Bug 修复后（+ 新增复现测试）

**持续模式**：长会话中每 15 分钟或重大变更后执行（心智检查点：完成函数后 / 完成组件后 / 切换任务前）。

## 本地验证 vs CI 门禁（必须搞清楚）

**不需要 GitHub Actions 也能做完整验证。** 本 skill 的 8 阶段本质是「一组要在代码声称完成前跑的命令 + 判定标准」，它在哪跑、谁来跑是独立的：

- **本地验证**：你（或 AI 代理）手动跑 `build → typecheck → lint → test → test:e2e`，看实际输出，对照验证报告判定 READY / NOT READY。即时、灵活，但**靠自觉**——容易「编译过了就声称修完」（正是本 skill 要防的坑）。
- **CI 门禁**（GitHub Actions / GitLab CI / Gitea / Jenkins 等）：把**同一组命令**写进流水线，在 push / 开 PR 时自动跑，失败就**阻断 merge**。它不改变「验证什么」，只是把门禁变成**客观强制**——没过门禁的代码合不进去。

**关键认知**：

1. CI 不是「另一种验证」，是**同一套验证的自动化载体**。本地能过、CI 才能过；本地乱跳阶段，CI 会拦回来。
2. **平台不限 GitHub Actions**。可选：GitHub Actions、GitLab CI、Gitea Actions、Jenkins；本地也能用 `act`（本地跑 GitHub Actions）、`lefthook` / `husky` 的 pre-push hook 在提交前自动跑。
3. **没有 CI 也能用本 skill**——只要你在声称「修完 / 提 PR」前，老老实实本地跑完 8 阶段并填验证报告。CI 是「团队不用担心有人跳过门禁」的强化，不是前提。
4. **真机（阶段 6）CI 一般难模拟**：Tauri WKWebView、build 产物行为、staging 真实请求，通常放本地或独立 staging 流水线。CI 跑 1-5 + 7-8，真机缺口要在验证报告的「6 真机」栏记原因（NOT_RUN 需充分理由）。

> 落地建议：先本地把 8 阶段跑顺、验证报告模板用熟；再把它搬进 CI（见 `references/e2e-practice.md` 的「CI 门禁」通用模板）。两者结论必须一致——CI 红 = 本地 NOT READY。

## 本地开发：哪些验证必要（按场景的最低清单）

8 阶段不是每次都要亲力亲为——编译层（1-4）工具链逼你跑，**真正容易漏、也最该记住的是功能层（5-6）**，因为「编译过 ≠ 功能可用」。按场景取最低必要集：

### 日常改 bug / 写功能（本地循环中）

```
1 构建 → 2 类型 → 4 单测（改了逻辑就跑）→ 5 e2e（宣称修好前必跑）
```

- 1-2 顺手跑（build / typecheck 一把过）。
- 4 单测：纯逻辑改动必跑；只改样式可跳过。
- **5 e2e 是这条清单的灵魂**——改完宣称「修完」前必跑，断言功能真的出来（像素非空 / textLayerStatus ≠ unknown），这是编译层抓不到的坑的唯一解。

### 准备提 PR / 声称「修完」

```
日常清单 + 6 真机（至少 build 产物跑一遍）+ 7 安全（grep 自查）+ 8 Diff（看 git diff）
```

- 6 真机：dev 跑得好，build 产物 / 真机可能崩（worker / 路径 / 协议差异）。
- 7 安全：grep 密钥 / console.log，或交给 CI。
- 8 Diff：人工看 git diff，确认只改了该改的，没越界 / 误删 / 含 forbidden 文件。

### 能自动化就别手动记着跑（pre-push hook / CI 挡）

- 3 Lint：`husky` / `lefthook` pre-push 自动跑，或 CI 跑。
- 7 安全扫描：CI 跑更稳，不靠自觉。

### 关键认知

- **你本地必须亲力亲为的**：1-2-4 确认代码层面 OK + **5 e2e 确认功能真的可用**。
- **提 PR 前补的**：6 真机 + 8 看 diff。
- **能自动化就别手动的**：3 lint、7 安全。
- **最低线不是 1-4**：到你宣称「完成」那一步之前，5（及该场景下的 6）必须过。1-4 全过 ≠ 可以声称修完。

> 真实教训：worker 改完 typecheck / build / lint / 单测全过，实机 `textLayerStatus` 卡 unknown 崩——证明 1-4 全过 ≠ 功能可用，5/6 不过就是没修完。

## 最终输出：验证报告

```
| 阶段        | 结果                          |
|-------------|-------------------------------|
| 1 构建      | PASS / FAIL                   |
| 2 类型      | PASS / FAIL (X errors)        |
| 3 Lint      | PASS / FAIL (X warnings)      |
| 4 单测      | PASS / FAIL (X/Y, Z% cov)     |
| 5 e2e 功能  | PASS / FAIL (X specs)         |  ← 硬门禁
| 6 真机      | PASS / FAIL / NOT_RUN(记原因) |  ← 硬门禁
| 7 安全      | PASS / FAIL (X issues)        |
| 8 Diff      | X files, 范围合规/越界        |
| CI 门禁     | 1-5+7-8 全绿 / 有 job 红（阻断说明） |
| **Overall** | **READY / NOT READY for PR**  |
```

**READY 条件**：1-4 + 7-8 过 **且** 5 e2e 过 **且** 6 真机过（或 NOT_RUN 有充分原因）。**5/6 任一 FAIL = NOT READY**。

## 完成定义（落地）

代码改动声称「完成」必须：
1. 1-4 编译层全过（前置）。
2. **5 e2e 功能验证过**（核心）。
3. **6 真机验证过**（核心，桌面/Web/服务按类型）。
4. 7-8 安全 + Diff 合规。
5. Bug 修复**新增复现测试**（回归）。
6. 验证报告 Overall = READY。

**e2e/真机不过 = 未完成**：不提交 PR、不 merge、不 release、worker STATUS 不写 `done`、不向用户声称「修完」。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|------|----------|
| node / npm | 项目自带 |
| rust / cargo（Tauri 项目） | macOS: `brew install rust` |

### 项目依赖（按类型）

| 项目类型 | 依赖 | 用途 |
|---|---|---|
| 通用 | `vitest` / `eslint` / `tsc` | 单测 / lint / 类型 |
| 通用 | `playwright` | e2e 功能验证 |
| Tauri 桌面 | `@tauri-apps/cli` | tauri build / dev 真机 |
| 通用（可选） | `dependency-cruiser` | 依赖环检测（阶段 3） |

## 参考文档（references/，按需读取）

- `references/eight-phases-rationale.md`：**想搞懂「为什么是 8 阶段、编译过为啥不等于能用」**——各阶段证明/不证明什么、e2e+真机补什么盲区、反例。对应 §8 阶段验证 与 §本地开发：哪些验证必要。
- `references/assertion-depth.md`：**写 e2e 时**——断言功能结果 vs 只断言存在元素（防伪渲染/假成功），跨渲染/状态/交互/API 四类案例。对应 §阶段 5。
- `references/e2e-practice.md`：**落地 e2e / 真机 / CI**——Playwright spec 写法、fixture 矩阵、CI 通用模板（平台不限 GitHub Actions）、Tauri etv 真机。对应 §阶段 5/6 与 §本地 vs CI 门禁。
- `references/test-pyramid.md`：**组织单测 / verify 脚本 / 回归规范**——vitest 分层、build 内嵌 verify、bug 修复必加复现测试、lint 严格。对应 §阶段 3/4。
- `references/lessons-from-practice.md`：**跑 skill 踩过的坑**——pre-existing 失败判定、e2e 缺失、Tauri invoke 限制、快速模式 vs 全量、真机证据来源等，持续反哺。对应 §本地开发清单 的「快速模式」与 §阶段 4/5/6 边界。

## Related Skills

| 维度 | verification-gate | skill-lint |
|---|---|---|
| 定位 | **代码**改完后的验证门禁 | **Skill** 创建/改造后的质量审查 |
| 对象 | 代码项目（Tauri/Web/服务） | Skill 本身（SKILL.md/references/契约） |
| 关系 | 验证代码功能可用 | 验证 Skill 结构合规 |

代码项目用 verification-gate，Skill 用 skill-lint。改 Skill 的代码脚本（如 multi-agent-orchestration 的 spawn-worker.sh）两者都适用（先 skill-lint 审 Skill 结构，再 verification-gate 验脚本功能）。
