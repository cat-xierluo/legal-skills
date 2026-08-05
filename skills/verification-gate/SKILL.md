---
name: verification-loop
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.0.1"
license: MIT
description: 代码改完后的验证门禁。完成 feature / 重大变更 / 创建 PR / 重构 / 声称「修完」前使用——跑 8 阶段验证，其中 e2e 功能 + 真机是 READY 硬门禁（编译过 ≠ 功能可用）。覆盖 Tauri 桌面 / Web / 服务 / Skill 四类分支。不要用于：业务领域验证、Skill 质量审查（用 skill-lint）、纯文档变更、一次性脚本。
---

# Verification Loop（代码改完后的验证门禁）

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

| # | 阶段 | 门禁 | 完成线 |
|---|---|---|---|
| 1 | 构建（build / cargo check） | 失败则停，不继续 | 前置 |
| 2 | 类型检查（typecheck） | 关键错误清零 | 前置 |
| 3 | Lint（`--max-warnings=0` + 依赖环） | 零警告 + 无依赖环 | 前置 |
| 4 | 单元测试（vitest 分层） | 通过 + 覆盖率达标 | 前置 |
| **5** | **e2e 功能验证（Playwright）** | **功能结果断言**（非存在元素） | **核心完成线** |
| **6** | **真机验证（etv / build / staging）** | **真实运行时行为** | **核心完成线** |
| 7 | 安全扫描（密钥 / debug 日志） | 无泄露 / 无遗留 console.log | 前置 |
| 8 | Diff 审查（范围 / 越界） | 变更合规，无 forbidden 文件 | 前置 |

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

- `references/eight-phases-rationale.md`：为什么 8 阶段（e2e + 真机补编译层盲区）。
- `references/assertion-depth.md`：断言深度指南（功能结果 vs 存在元素，跨项目案例）。
- `references/e2e-practice.md`：e2e / CI / fixture / 真机实践（Playwright + etv）。
- `references/test-pyramid.md`：测试金字塔 + verify 脚本 + 回归规范 + lint 严格。
- `references/lessons-from-practice.md`：实践教训（跑 skill 发现的覆盖不足，持续反哺）。

## Related Skills

| 维度 | verification-loop | skill-lint |
|---|---|---|
| 定位 | **代码**改完后的验证门禁 | **Skill** 创建/改造后的质量审查 |
| 对象 | 代码项目（Tauri/Web/服务） | Skill 本身（SKILL.md/references/契约） |
| 关系 | 验证代码功能可用 | 验证 Skill 结构合规 |

代码项目用 verification-loop，Skill 用 skill-lint。改 Skill 的代码脚本（如 multi-agent-orchestration 的 spawn-worker.sh）两者都适用（先 skill-lint 审 Skill 结构，再 verification-loop 验脚本功能）。
