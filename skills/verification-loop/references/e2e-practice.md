# e2e 实践（Playwright / CI / fixture / 真机）

> 阶段 5（e2e）+ 阶段 6（真机）的落地做法。按项目类型选。

## e2e spec 怎么写（Playwright）

### 结构：fixture → 启动 → 操作 → 断言功能结果

```ts
// e2e/reader-renders.spec.ts（桌面 reader）
import { test, expect } from '@playwright/test';

test('打开 PDF 真渲染 + 文字层检测', async ({ page }) => {
  await page.goto('http://localhost:1420');  // dev server（或 build preview）
  // 1 触发打开（mock 拖入 / 点打开选 fixture）
  await page.evaluate(() => {
    window.dispatchEvent(new CustomEvent('faropdf://file-drop', { detail: { path: 'tests/fixtures/expert/reference.pdf' } }));
  });
  // 2 断言功能结果（非存在元素）
  await expect(page.locator('canvas.pdf-page')).toBeVisible();
  const hasPixels = await page.locator('canvas.pdf-page').evaluate(/* 像素非空 */);
  expect(hasPixels).toBe(true);
  const status = await page.locator('[data-textlayer-status]').getAttribute('data-textlayer-status');
  expect(status).not.toBe('unknown');
  expect(await page.locator('.pdf-page').count()).toBe(5);
});
```

### 断言深度

参照 `references/assertion-depth.md`——断言功能结果（像素 / 文字 / 状态），非存在元素。

## fixture 矩阵（受控复现）

e2e 用**受控 fixture**（入库 / 确定性生成），不依赖临时文件：

```
tests/fixtures/
├── expert/reference.pdf      # 正常基准（文字层）
├── reader/encrypted.pdf      # 加密（密码态）
├── reader/corrupt.pdf        # 损坏（错误态）
├── forms/reference-form.pdf  # 表单
└── ocr/scan-only-sample.pdf  # 扫描件（OCR / textLayer=missing）
```

每个 fixture 对应一个场景的 e2e spec（正常渲染 / 密码 / 损坏 / 表单 / OCR）。

## CI 门禁（e2e 必须在 CI）

```yaml
# .github/workflows/ci.yml
playwright:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: npm ci
    - run: npx playwright install --with-deps chromium
    - run: npm run build            # build 产物（不只 dev server）
    - run: npm run test:e2e         # 跑 e2e
    - uses: actions/upload-artifact@v4  # failure 上传 test-results（7 天）
      if: failure()
      with: { name: test-results, path: test-results/ }
```

**关键**：e2e 在 CI 跑（不只本地）；PR 合并前 e2e 必须绿。

## 真机验证（阶段 6，dev e2e 之外）

dev server e2e（localhost）不够。真机按项目类型：

### Tauri 桌面（WKWebView）

```bash
# 方式 1：build 产物实机
npm run tauri build
# 手动 / 脚本驱动产物（打开 PDF / 拖入 / 截图 / DOM 测量）

# 方式 2：etv（WKWebView inspector + tauri dev 真机 DOM）
WEBKIT_INSPECTOR_SERVER=127.0.0.1:9222 tauri dev
# 用 inspector 抓真机 DOM / 截图（脚本化）
```

真机抓 prod-only 问题（worker / 协议 / 路径，dev server 跑不出来）。

### Web（build 产物）

```bash
npm run build && npm run preview   # build 产物（非 dev server 热重载）
# Playwright 跑 preview（打包后路径 / worker / 分包行为）
```

### 服务（staging）

```bash
# staging 环境真实请求（真实 DB / 网络 / 凭据）
curl stg.example.com/api/xxx
# 或 Playwright request 跑 staging
```

## e2e 命名 + 组织

```
e2e/
├── reader-renders.spec.ts       # reader 核心（打开渲染 + textLayer）
├── drag-drop.spec.ts            # 拖入（mock 事件）
├── settings-panel.spec.ts       # 设置交互
├── mode-switch.spec.ts          # mode 切换 panel
└── fixture-matrix.spec.ts       # 多 fixture 场景矩阵
```

每个 spec 对应一个功能域，断言功能结果（非存在元素）。
