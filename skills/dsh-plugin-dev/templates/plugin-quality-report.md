# DSH 插件质量意见报告

**报告日期**：YYYY-MM-DD
**审查对象**：`<插件路径>`
**插件名称**：`<package-name>`
**审查范围**：设计预检 / 快速审查 / 正式验收（发布前）
**审查配置**：默认规则 / `config/harness-path.local.yaml`
**候选 commit**：`<git rev-parse HEAD>`（正式验收必填）

## 一、总体意见

**结论**：可发布 / 需修复后复审 / 未验证（NOT_VERIFIED）

**一句话理由**：`<最关键的一条>`

## 二、harness 溯源（lint.mjs §0 输出）

| 项 | 值 |
|---|---|
| harness 根 | `<路径>`（解析来源：--harness-root / DSH_HARNESS_ROOT / config） |
| DSH 版本 | `<x.y.z-rc.n>`（官方 `dsh --version` 门 + 根 manifest 交叉） |
| harness git commit | `<rev-parse HEAD>` |
| 平台模块表 | `<N> 项（packages/client/web/src/platform.ts）` |

> 本报告全部对账结论只对该版本 + commit 有效；harness 升级后须重跑 §1。

## 三、§1 机械层（scripts/lint.mjs 输出摘要，退出码 = FAIL 数）

| 检查 | 结果 |
|---|---|
| 声明一致性（bundle/client/exports） | PASS / FAIL |
| DSH 依赖钉定版本 ↔ harness 版本 | PASS / WARN 清单 |
| client 工件契约（banner/footer/后缀） | PASS / FAIL / NA |
| 产物 bare require ↔ 模块表对账 | PASS / FAIL / WARN（builtin 待人工确认） |
| 构建配置 external ↔ 基线 ∪ dsh.client.external | PASS / FAIL / WARN（声明体未识别转人工） |
| dsh.client.inject 目标存在性 + devDep 双保险 | PASS / FAIL / WARN 清单 |
| dsh.client.external（自引用/基线冗余/死行） | PASS / FAIL / WARN 清单 |
| 主题变量声明集对账 | PASS / FAIL / NA |
| 硬编码文案与 zh/en 词典平价 | PASS / FAIL / WARN 清单 |
| 入口与脚本卫生 | PASS / WARN 清单 |
| 当前态文档版本声明 | PASS / WARN 清单 |

## 四、§2 事实层（引用 → 源码溯源）

| 引用（事件/slot/API） | harness 源码位置 | 判定 |
|---|---|---|
| `agent/pre-step` | `packages/core/agent/src/runtime-types.ts` | PASS / FAIL |

## 五、§3 契约层

| # | 契约项 | 结果 | 备注 |
|---|---|---|---|
| 1 | lossless JSON（无 undefined 泄漏） | PASS / FAIL / NA | |
| 2 | DSL 限制（无嵌套对象/as const） | | |
| 3 | client 工件契约（含 externals 推导） | | |
| 4 | client 纯度（无越界值导入） | | |
| 5 | 子进程异步 + signal | | |
| 6 | 显式传参（无静默默认依赖） | | |
| 7 | fail-loud / 可选服务降级明示 | | |
| 8 | 退码分类（域结果不 throw） | | |
| 9 | 构建管线不吞退出码 | | |
| 10 | HMR 边界已知（历史结论，按当前版本复核；更新需重启取证） | | |
| 11 | 主题变量仅引用 harness 声明集 | | |
| 12 | 产品文案走类型化 locale | | |

## 六、§4 文档层

CHANGELOG / DECISIONS / ROADMAP / ARCHITECTURE 与实际改动同步情况：`<逐项>`
当前态文档过期版本声明（lint.mjs §9 WARN 清单）：`<逐项>`

## 七、§5 候选绑定证据（正式验收）

| 证据 | 状态 |
|---|---|
| 候选 commit 记录 | |
| 干净 profile 安装 + `--dump-config` 出层 | |
| node half boot 无错 + tool 真实调用 | |
| `__DSH_BOOT__` 含本包 + bundle 可下 | |
| 浏览器渲染截图 | |

## 八、需修复清单

1. `<FAIL 项 + 修复建议>`

## 九、NOT_VERIFIED 项

`<无法确认的能力/未取得的证据，明示不推断>`
