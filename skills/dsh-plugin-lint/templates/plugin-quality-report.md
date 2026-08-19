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

## 二、§1 机械层（scripts/lint.mjs 输出摘要）

| 检查 | 结果 |
|---|---|
| 声明一致性（bundle/client/exports） | PASS / FAIL |
| client 工件契约（banner/footer/后缀） | PASS / FAIL / NA |
| 入口与脚本卫生 | PASS / WARN 清单 |

## 三、§2 事实层（引用 → 源码溯源）

| 引用（事件/slot/API） | harness 源码位置 | 判定 |
|---|---|---|
| `agent/pre-step` | `packages/core/agent/src/runtime-types.ts` | PASS / FAIL |

## 四、§3 契约层

| # | 契约项 | 结果 | 备注 |
|---|---|---|---|
| 1 | lossless JSON（无 undefined 泄漏） | PASS / FAIL / NA | |
| 2 | DSL 限制（无嵌套对象/as const） | | |
| 3 | client 工件契约 | | |
| 4 | client 纯度（无越界值导入） | | |
| 5 | 子进程异步 + signal | | |
| 6 | 显式传参（无静默默认依赖） | | |
| 7 | fail-loud / 可选服务降级明示 | | |
| 8 | 退码分类（域结果不 throw） | | |
| 9 | 构建管线不吞退出码 | | |
| 10 | HMR 边界已知（更新需重启） | | |

## 五、§4 文档层

CHANGELOG / DECISIONS / ROADMAP / ARCHITECTURE 与实际改动同步情况：`<逐项>`

## 六、§5 候选绑定证据（正式验收）

| 证据 | 状态 |
|---|---|
| 候选 commit 记录 | |
| 干净 profile 安装 + `--dump-config` 出层 | |
| node half boot 无错 + tool 真实调用 | |
| `__DSH_BOOT__` 含本包 + bundle 可下 | |
| 浏览器渲染截图 | |

## 七、需修复清单

1. `<FAIL 项 + 修复建议>`

## 八、NOT_VERIFIED 项

`<无法确认的能力/未取得的证据，明示不推断>`