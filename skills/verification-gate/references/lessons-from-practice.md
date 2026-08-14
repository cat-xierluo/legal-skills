# 实践教训（反哺：跑 skill 时发现的覆盖不足）

> **何时读这篇**：跑 skill 踩坑、或想确认某阶段边界（pre-existing 失败怎么判、e2e 缺失、Tauri invoke、快速模式、真机证据）时。对应 SKILL.md 的 §阶段 4/5/6 与 §本地开发：哪些验证必要。

> 本 skill 在真实项目跑过后，发现的覆盖不足 + 补充规则。持续反哺（每次跑暴露新不足就加）。

## 教训 1：pre-existing 失败 vs 本次引入（阶段 4）

**场景**：跑阶段 4 单测，`npm test` 超时——但根因是 vitest 4.x + ESM pre-existing 环境冲突（CHANGELOG 早就记过，非本次改动引入）。

**skill 原来没说**：pre-existing 失败怎么算？是 FAIL（阻塞）还是 NOT_RUN（不阻塞）？

**补充规则**：
- 阶段 4（及任何阶段）失败时，区分**本次改动引入** vs **pre-existing 环境/依赖**：
  - 本次引入 → FAIL（阻塞，必修）。
  - pre-existing（CHANGELOG/历史记过、与本次改动文件无关、`git stash` 后 main 也复现）→ **NOT_RUN + 记精确原因 + 引用历史记录**，**不阻塞本次判定**（但报告必须披露）。
- 判据：`git stash && npm test`（main 干净态跑）——如果 main 也超时/失败 = pre-existing，不是本次。

## 教训 2：e2e 完全缺失（阶段 5）

**场景**：跑阶段 5，发现项目**根本没建 e2e**（无 `test:e2e` script + 无 `e2e/*.spec.ts`）。阶段 5 不是「e2e 跑了 FAIL」，是「无 e2e 可跑」。

**skill 原来没说**：项目没 e2e 基础时阶段 5 怎么判？

**补充规则**：
- e2e 缺失 = **FAIL（功能验证缺失）**，不是 NOT_RUN。理由：没 e2e = 功能不可验证 = 不能声称 behavior-complete（这正是「编译过 ≠ 功能可用」要防的）。
- 报告标「❌ e2e MISSING（无 spec）」，**建议**：「建 `<域>-renders.spec.ts`（打开 fixture + 断言功能结果），补阶段 5」。
- 例外：纯类型/重构/文档改动（无功能变），e2e 缺失可降 NOT_RUN（但这些改动本来就不要求 e2e）。

## 教训 3：Tauri 项目 e2e 难点（Playwright dev server ≠ Tauri webview）

**场景**：FaroPDF 是 Tauri 桌面。Playwright 跑 dev server（vite localhost:1420）= 浏览器（Chromium），**但 Tauri `invoke()` 在浏览器不工作**（没 Tauri runtime）→ reader 依赖 `invoke("read_pdf_file_from_path")` 打开 PDF，在 Playwright dev server 里 invoke 失败 → 打不开 PDF → e2e 断言不到渲染。

**skill 原来没说**：Tauri 项目 Playwright dev server 的 invoke 限制。

**补充规则**（Tauri 桌面项目分支补）：
- **Playwright dev server 局限**：前端跑，但 `@tauri-apps/api invoke` 失败（无 Tauri runtime）。依赖 invoke 的功能（打开文件 / 读路径 / IPC）**在 Playwright dev server 测不了**。
- **解法**（按可行性）：
  1. **mock invoke**：前端 e2e 注入 mock（`window.__TAURI_INTERNALS__.invoke = mockFn`），mock 返回 fixture bytes → 测渲染/UI（但不测真 IPC）。
  2. **真机 etv**（阶段 6）：`tauri dev`/`tauri build` 真实 WKWebView + inspector → 真 invoke → 测真功能。**Tauri 项目阶段 6 真机比阶段 5 dev e2e 更关键**。
  3. **Tauri 官方 e2e**（driver）：Tauri 提供 WebDriverIO/tauri-driver（驱动真 webview），但配置复杂。
- **结论**：Tauri 项目，阶段 5（dev e2e）测 UI/渲染（mock invoke），**阶段 6（真机 etv）测真功能（含 invoke）**——两者互补，不能只靠 dev e2e。

## 教训 4：build 慢可 skip（阶段 1）

**场景**：阶段 1 `npm run build`（vite build 产物）慢（几十秒~分钟）。但 typecheck（阶段 2）+ cargo check（阶段 1b）已覆盖编译。

**补充规则**：
- 阶段 1 build 慢时，可 **skip vite build**（用 typecheck + cargo check 替代），标 `NOT_RUN（typecheck + cargo check 已覆盖编译；vite build 产物验证留 CI）`。
- 但 **CI 必须 跑 build**（本地 skip，CI 不 skip——build 产物问题只在 build 暴露，如 worker 资产/分包/路径）。

## 教训 5：快速模式 vs 全量（时间预算）

**场景**：全 8 阶段跑（含 test/build/cargo）可能 >5min（test 超时）。本地迭代要快。

**补充规则**（快速模式）：
- **快速模式**（本地迭代 / 改一行）= SKILL.md §本地开发清单 的「日常改 bug/写功能」：`1 构建 → 2 类型 → 4 单测（改了逻辑就跑）→ 5 e2e（宣称修好前必跑）`。纯样式/类型改动可进一步压到 typecheck + lint + diff（秒级），e2e/真机留「声称完成前」。
- **标准模式**（PR 前）= 清单的「准备提 PR」：日常清单 + `6 真机` + `7 安全` + `8 Diff`。
- **选择**：按时间预算 + 改动域。小改 → 快速；功能改 / PR → 标准。

> 与 SKILL.md §本地开发：哪些验证必要 对齐——本教训的「快速/标准」就是该清单的两种场景；lint（3）在该清单中建议交 hook/CI 自动化，不占本地手动时间。

## 教训 6：真机证据来源（阶段 6）

**场景**：阶段 6 真机，PM（AI）没 GUI 能力，不能自己拖文件/点按钮/看 UI。基于**用户实机反馈**判 FAIL（用户：打开 PDF「文字层未知」）。

**补充规则**（阶段 6 证据来源）：
- 真机证据来源（优先级）：
  1. **自跑**（PM/AI 用 etv/截图/computer-use）—— 最可信，但 AI 受限（无 GUI / localhost 截图隔离）。
  2. **用户实机反馈**（用户跑 dev/build + 描述）—— 次可信，标「基于用户反馈」。
  3. **历史**（之前 run 的截图/日志）—— 辅助，标「历史证据」。
- 报告必须标真机证据来源（自跑 / 用户反馈 / 历史 / NOT_RUN）。**不能无证据判 PASS**。

## 教训 7：vitest/jsdom + pdfjs e2e 的具体落地坑（阶段 5）

**场景**：建 pdfjs 渲染 e2e（reader-renders.test.ts），用真 pdfjs + 真 fixture 驱动 `loadPdfFromBytes` 全链路。vitest 默认 jsdom 环境，踩两个 pdfjs 6 + jsdom/node 兼容坑——这些坑 skill 原来没写，e2e 第一次落地才发现。

**坑 1：jsdom 无 `DOMMatrix` → pdfjs 非 legacy build 模块顶层崩**
- `await import("pdfjs-dist")` 在 jsdom 抛 `ReferenceError: DOMMatrix is not defined`（pdfjs 6 非 legacy build 模块顶层引用 `DOMMatrix`，jsdom 不提供）。
- pdfjs 警告 `Please use the legacy build in Node.js environments`。
- **解法**：test adapter 用 `pdfjs-dist/legacy/build/pdf.mjs`（legacy build，node 兼容）。product 代码（真机 WKWebView 有 DOMMatrix）仍用非 legacy，不受影响——此差异本身是教训 3（test 环境 ≠ webview 环境）的实例。

**坑 2：node ESM loader 只认 `file:` / `data:` scheme → workerSrc 不能用 `import.meta.url`**
- jsdom 无真 Worker，pdfjs 走 fake worker（动态 import worker 脚本到主线程）。
- `new URL("pdfjs-dist/.../pdf.worker.mjs", import.meta.url).href` 在 vitest 下解析为 `http://...`（vite serve），node ESM loader 拒绝（`Only URLs with a scheme in: file and data are supported... received 'http:'`）→ fake worker setup failed。
- **解法**：`createRequire(import.meta.url).resolve("pdfjs-dist/legacy/build/pdf.worker.mjs")` 拿 worker 真路径 + `pathToFileURL(path).href` 转 `file:` URL，node ESM loader 支持。

**诊断价值**：这种 e2e（jsdom + legacy + `file:` worker）能**证伪「pdfjs 逻辑 bug」**——测试 PASS = pdfjs API 调用正确，把根因缩到「环境特异性」（webview worker 加载）。但 jsdom ≠ WKWebView，**真机 worker 行为仍需阶段 6**（教训 3）：jsdom / Chromium 的 worker 正常，不代表 WKWebView 的 `tauri://` scheme 下 worker 正常。

**结论**：pdfjs + Tauri 项目，阶段 5 e2e（jsdom）测 pdfjs 逻辑 + UI，阶段 6（真机 / inspector）测 WKWebView worker——两者互补，**jsdom 过 ≠ 真机过**。

## 教训 8：负向样式断言的 UA 默认值陷阱（阶段 5 / assertion-depth 的实例）

**场景**：断言主题色卡「非裸渲染」（防「写 className 不写 CSS」回归），写了 4 条负向断言：`radius not.toBe('0px')` / `borderWidth not.toBe('0px')` / `background not.toBe('rgba(0,0,0,0)')` / `padding not.toBe('0px')`。独立 review 实测 chromium UA 默认 button：`border: 2px`、`padding: 1px`、背景 `rgb(239,239,239)`——**4 条里 3 条恒真**，CSS 丢了照样绿。

**skill 原来没说**：负向断言（not.toBe 某值）在属性有非零 UA 默认时无鉴别力。

**补充规则**：
- 「非默认值」断言前先搞清 **UA 默认值**是什么：`border`（2px）、`padding`（1px）、`background`（灰）在 button 上都不是 0/透明。
- 正确写法二选一：
  1. **锚定 CSS 声明值**：`expect(radius).toBe('8px')`——最强，同时防「值改错」；
  2. **「≠ UA 默认值」成对断言**：`expect(['rgba(0,0,0,0)','rgb(239,239,239)']).not.toContain(bg)`——值随主题变、不便锚定精确值时用。
- 判断标准：把 CSS 规则删掉重跑，断言**必须变红**；删了还绿 = 恒真 = 假防线。

## 教训 9：Playwright config 不在仓库根目录，必须显式 --config（阶段 5）

**场景**：项目 config 在 `config/playwright.config.ts`（非根目录）。直接 `npx playwright test e2e/x.spec.ts` 不报「找不到 config」——Playwright 静默用**默认配置**跑：无 `baseURL`（`page.goto('/')` 报 `Cannot navigate to invalid URL`）、无 `webServer`（`ERR_CONNECTION_REFUSED`）。后者极易被「手动起 dev server」掩盖，测试还能全绿，但 `goto('/')` 类相对导航永远挂。

**skill 原来没说**：config 目录非标准位置时的症状与掩盖链。

**补充规则**：
- config 不在根目录的项目，**始终** `npx playwright test --config config/playwright.config.ts ...`（对齐 CI 命令）。
- 症状对照：`ERR_CONNECTION_REFUSED` 或 `Cannot navigate to invalid URL` → 先查是不是默认配置在跑（没走到你的 config），**不要**急着手动起 dev server 绕过——绕过后 webServer/baseURL 缺失问题被掩盖，相对路径断言照挂。
- 一次性 DOM 探针 spec（goto + evaluate dump `parentElement` 链 / `elementFromPoint` 命中 / class 清单，跑完删）比猜选择器快：一次探测解决了「IR 有三种 pre（编辑面 / 源码 marker / 渲染块）」的定位歧义。

## 教训 10：NOT_VERIFIED 整批移交用户 = 反模式（release 收尾）

**场景**：v0.7.0 发布时 5 个 feature 全挂「真机验证 NOT_VERIFIED，移交用户」。实际盘点：其中大部分（6 套主题切换/CSS 变量注入/重启保留/CSS 导入 sanitize/license 跳转/复制按钮 hover+反馈+剪贴板）是**纯 Web 层**，vite dev + Playwright 当场可验——用户一句话点破：「这些你可以直接推进，不一定要我人去查看」。

**skill 原来没说**：NOT_VERIFIED 的分层判定与收尾动作。

**补充规则**（release / 交付收尾时执行）：
- 把 NOT_VERIFIED 清单逐项二分：
  - **Web 层可验**（UI 渲染 / 交互 / DOM 断言 / localStorage 持久化 / 剪贴板（chromium grant 权限））→ Agent **当场写 spec 验证**，转正为回归 e2e，同步把口径从 NOT_VERIFIED 收窄；**不得整批移交用户**。
  - **真需真机**（系统 API 注册 / Tauri invoke 后端 / webview 特异行为 / 主观观感）→ 保留 NOT_VERIFIED，但**精确写明剩余范围**（不是整条 feature，而是「仅 WKWebView 剪贴板写入」这种粒度）。
- 判据：该项的功能面在浏览器 DOM 里存在吗？存在 → Playwright 可验。不存在（要 OS / Tauri runtime）→ 真机。
- 剪贴板：chromium `test.use({ permissions: ['clipboard-read','clipboard-write'] })` + `navigator.clipboard.readText()` 可断言真实内容，不必留真机。
- 「移交给用户」前自问：这份清单里有多少其实是我没跑 Playwright，而不是真验不了？

## 教训 11：测试套件「永不完成」比「测试失败」更危险（阶段 4）

**场景**：vitest 全量 240s+ 不退出（2026-07-28 起复现），归因「open handles」搁置数周，期间 CI 用 `test:e2e` 子集绕开。2026-08-14 修复悬挂（见教训 12）后全量第一次真正跑完——**立即暴露 3 条被掩盖数周的真实失败**（工具菜单去重后未更新的过期断言 ×2、无 tab 时必然失败的 DOM 断言 ×1）。

**skill 原来没说**：悬挂的「掩盖效应」——套件永不完成时，「跑不完」和「全绿」被混为一谈，所有真实失败一起被藏住。

**补充规则**：
- 「套件永不完成」按 **P0 基础设施缺陷**处理，不是「已知怪癖」。用子集绕开只能是**临时态**：必须登记任务 + 写明回归条件，不允许悄悄永久化（子集绕开每多存在一天，被掩盖的失败就多藏一天）。
- 判定「真的跑完」双条件：summary（`Test Files / Tests` 行）真的打印 **且** 进程真的退出。只看测试条目全 ✓ 不算数（✓ 会照常打印，卡的是收尾）。
- 顺带规律：CI 首跑常抓「本机路径假设」类 bug——如 spawn 候选硬编码 `/opt/homebrew/bin/node`，ubuntu runner 上 ENOENT。**spawn 子进程优先 `process.execPath`**（当前运行时二进制，必然存在、跨平台），不硬编码本机绝对路径；要留覆盖口用环境变量（如 `NODE_BINARY`）。

## 教训 12：React/Vitest 悬挂 = effect↔dispatch 无限循环（阶段 4 诊断 playbook）

**场景**：`npm test` 全量挂；单独跑某文件也挂；该文件所有测试 ✓ 但 summary 永不打印；worker 进程 CPU ~85% 忙循环数分钟。最终根因：测试 harness 写 `useEffect(() => store.openTab(...), [store])` **无查重守卫**，而 store 的 `OPEN_TAB` 每次生成新 id 追加新 tab（非幂等）→ dispatch 产生新 state → context value 引用变化 → effect 重跑 → 无限循环；React 19 下经 act 队列变成**微任务死循环**，vitest fork worker 永不退出。

**skill 原来没说**：悬挂类问题的系统诊断路径，以及「测试 harness 镜像生产守卫」这条反模式。

**诊断 playbook（按序，每步分钟级）**：
1. **停滞检测**：verbose reporter 跑全量，45s 输出行数不变 → 记下最后输出位置（区分「某测试没跑完」vs「全跑完后不退出」：所有文件都有 ✓ 但无 summary = 后者）。
2. **范围二分**：单文件跑（挂则文件内）→ `-t "describe 关键词"` 按 describe/test 二分（regex 可 `|` 连接分组），每轮给 ~70s 悬挂窗，6-8 轮定位到单条测试。
3. **忙/闲判定**：`ps -o %cpu -p <pid>`——**忙循环**（微任务/同步死循环）与**闲置挂起**（open handle/timer）是两条完全不同的路径，先分流再深入。
4. **忙循环抓栈**：macOS `sample <pid> 3` 看原生栈（卡在 `MicrotaskQueue::RunMicrotasks` = 微任务死循环）→ `kill -USR1 <pid>` 激活 node inspector + 裸 WebSocket CDP `Debugger.enable` + `Debugger.pause`，`Debugger.paused` 事件的 `callFrames` 就是死循环 JS 栈（本次抓到 `workLoopSync / performUnitOfWork ← flushActQueue ← act` = React act 队列无限 reconcile）。
5. **闲置挂起抓 handle**：`NODE_OPTIONS=--report-on-signal` + `kill -USR2` 出诊断报告，或 `why-is-node-running` 类工具列 active handles（注：vitest fork worker 下报告文件曾不落盘，inspector 路线更可靠）。

**根因反模式与修法**：
- 反模式：**在 effect 里 dispatch 到非幂等 store 且不带幂等守卫**。store 动作语义「每次调用产生新状态对象/新实体」（如每次 openTab 生成新 id）+ effect 依赖含 store value → 必然循环。
- 修法：harness **镜像生产代码的守卫**（如 `if (store.state.tabs.length === 0)` 再 openTab）。高发路径：生产接线有 `if (!exists)` 查重而测试 harness 漏抄——review 测试时专门检查「effect 里的 dispatch 是否有生产同款守卫」。
- 不要指望框架兜底：React 的 Maximum update depth 计数在「每轮经 act 队列微任务间隔」时会被重置，不会报错——循环可以安静地转到天荒地老。

## 反哺纪律

每次跑 verification-gate 暴露 skill 不足（覆盖盲区 / 规则不清 / 项目类型难点），加到本文件（教训 N）。skill 在实践中迭代，不一次写死。
