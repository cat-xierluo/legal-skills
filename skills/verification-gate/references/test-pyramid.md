# 测试金字塔 + verify 脚本 + 回归规范

> 阶段 3（lint）+ 阶段 4（单测分层）+ 回归规范的落地做法。

## 测试金字塔分层（阶段 4）

单测不只一层——按职责分（防层级混乱：unit 里塞 integration / integration 缺环境）。

| 层 | 职责 | 环境 | 速度 |
|---|---|---|---|
| unit | 纯逻辑（无 DOM / 无 IO） | node | 快 |
| dom | 组件 / DOM（jsdom） | jsdom | 中 |
| integration | 多模块协作（真实依赖） | node / jsdom | 中 |
| credentialed | 需凭据（独立，CI 可选） | node + 凭据 | 慢 |

### vitest project 配置

```ts
// vitest.config.ts
export default defineConfig({
  test: {
    projects: [
      { test: { name: 'unit', dir: 'src', include: ['**/*.unit.test.ts'] } },
      { test: { name: 'dom', dir: 'src', environment: 'jsdom', include: ['**/*.dom.test.tsx'] } },
      { test: { name: 'integration', dir: 'src', include: ['**/*.integration.test.ts'] } },
    ],
  },
});
```

### classification 检查（防层级混乱）

跑测试前先检查「测试放对层」——unit 不依赖 DOM / integration 不 mock 核心依赖。脚本化（如 `scripts/check-test-classification.mjs`），CI 跑。

## verify 脚本（确定性验证，不只 test）

除了 test（逻辑），还要 verify（契约/资源合规）：

| 脚本 | 验证 |
|---|---|
| `verify:ui-layout` | DOM 结构 / 几何（UI 改动门禁） |
| `verify:theme-css` | 主题 CSS 合规 |
| `verify:license` | 许可证合规 |
| `verify:agent-docs` | 文档契约 |

### build 内嵌 verify（关键）

```json
"build": "npm run verify:license && vite build && npm run verify:theme-css"
```

**build 前后跑 verify**——不只 typecheck，还验证资源/契约。build 产物确定性可信。

## 回归规范（Bug 修复必须新增复现测试）

**规则**：修完一个 bug，**必须加一条能复现该 bug 的测试**（e2e 或单测）。

### 做法

1. 修 bug 前，先写复现测试（红：测试失败，复现 bug）。
2. 修代码（测试变绿）。
3. 提交（代码 + 复现测试）。

### 为什么

- 防回归：下次同样 bug，复现测试拦住。
- 没 复现测试的 bug 修复，typecheck 过但 bug 可能再出现（没断言守住）。

### 案例

- Bug：打开 PDF 显示「文字层未知」（`textLayerStatus` 卡 unknown）。
- 复现测试：`e2e/reader-renders.spec.ts` 断言 `textLayerStatus ≠ unknown`。
- 修后：测试绿。下次 `textLayerStatus` 再卡 unknown，e2e 红，拦住。

## lint 严格（阶段 3）

```json
"lint": "eslint . --max-warnings=0 && npm run lint:deps"
"lint:deps": "depcruise --config .dependency-cruiser.cjs src"
```

- `--max-warnings=0`：零警告（不只 error，warning 也拦）。
- `lint:deps`：dependency-cruiser **依赖环检测**（防循环依赖）。

## 完整验证命令（按项目类型组合）

```bash
# 通用
npm run typecheck && npm run lint && npm test                    # 1-4 编译层
npm run test:e2e                                                  # 5 e2e
# 6 真机（按类型：tauri build / vite preview / staging）

# Tauri 桌面
npm run build && cd src-tauri && cargo check && cd .. \
  && npm run typecheck && npm run lint && npm test \
  && npm run test:e2e \
  && npm run tauri build  # 真机产物
```
