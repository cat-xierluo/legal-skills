# 断言深度指南（功能结果 vs 存在元素）

> **何时读这篇**：写 e2e（阶段 5）/ 真机（阶段 6）断言时。对应 SKILL.md 的 §阶段 5。

> 核心原则：**断言功能结果，不只「存在元素」**。防「伪渲染 / 假成功」——元素存在不代表功能对。本原则在本地 e2e 与 CI e2e 中同样适用（见 `references/e2e-practice.md` 的 CI 门禁）。

## 反模式（只断言存在，弱）

```ts
// ❌ canvas 存在不代表渲染了内容（可能空白 0x0）
expect(page.locator('canvas')).toBeTruthy();

// ❌ svg 存在不代表渲染对（可能有框无字）
expect(page.locator('svg')).toBeTruthy();

// ❌ 按钮存在不代表点击有效
expect(page.locator('#settings-btn')).toBeTruthy();
```

## 正模式（断言功能结果，强）

### 渲染类（canvas / svg / 图片）

```ts
// ✅ canvas 像素非空（真有内容，非空白）
const canvas = page.locator('canvas');
const hasPixels = await canvas.evaluate((c: HTMLCanvasElement) => {
  const ctx = c.getContext('2d')!;
  const data = ctx.getImageData(0, 0, c.width, c.height).data;
  return data.some((v) => v !== 0);
});
expect(hasPixels).toBe(true);

// ✅ svg 节点文字可见（防「有框无字」伪渲染）
await expect(page.locator('svg foreignObject text')).toContainText(['开始', '结束']);

// ✅ bbox 尺寸非 0（真有尺寸）
const box = await page.locator('svg').boundingBox();
expect(box!.width).toBeGreaterThan(10);
expect(box!.height).toBeGreaterThan(10);
```

### 状态类（加载 / 检测结果）

```ts
// ✅ 状态不是默认/未知值（检测真的跑了）
const status = await page.locator('[data-textlayer-status]').getAttribute('data-textlayer-status');
expect(status).not.toBe('unknown');  // 文字层检测成功

// ✅ 页数正确（PDF 真解析了，不只「打开」）
expect(await page.locator('.pdf-page').count()).toBe(5);
```

### 交互类（点击 / 切换）

```ts
// ✅ 点击后状态真的变（面板 open，不只按钮存在）
await page.click('[aria-label="设置"]');
await expect(page.locator('[role="dialog"][aria-label="设置"]')).toBeVisible();

// ✅ mode 切换后对应 panel 出现（bbox 非空）
await page.click('[aria-label="A 批注"]');
const panel = page.locator('.annotation-toolbar');
const box = await panel.boundingBox();
expect(box).not.toBeNull();
expect(box!.width).toBeGreaterThan(0);
```

### 视觉 / CSS 类（className → 真实渲染）

CSS 层无编译期验证：`className="xxx"` 引用不存在的 class，浏览器静默忽略，tsc/eslint/vitest/build **全都不报错**。「写 className 不写 CSS」这类回归唯一抓手是运行时 `getComputedStyle` 断言。

```ts
// ❌ 弱：元素存在不代表有样式（可能是 UA 裸渲染）
expect(page.locator('.settings-theme-card')).toBeVisible();

// ✅ 强：锚定 CSS 声明值（最强——同时防「CSS 丢失」与「值改错」）
const style = await card.evaluate((el) => {
  const cs = getComputedStyle(el);
  return { radius: cs.borderRadius, borderWidth: cs.borderTopWidth };
});
expect(style.radius).toBe('8px');        // 来自 .settings-theme-card { border-radius: 8px }
expect(style.borderWidth).toBe('1px');

// ✅ 强：值随主题/状态变时，断言「≠ UA 默认值」（成对，防恒真）
expect(['rgba(0, 0, 0, 0)', 'rgb(239, 239, 239)']).not.toContain(style.background);
//   ↑ chromium UA 裸 button 默认背景是 rgb(239,239,239)——只断言非透明会漏掉裸渲染
```

**负向断言的 UA 默认值陷阱**：`not.toBe('0px')` 对 `border`（UA 默认 2px）、`padding`（1px）、button `background`（灰）**恒真**，删掉 CSS 照样绿。自检法：把 CSS 规则删了重跑，断言必须变红。

**文案断言的前提**：断言 UI 文本（「已复制」「0/2」）依赖应用默认 locale 稳定（硬编码而非 navigator 检测）——spec 顶部注明该依赖，未来默认 locale 改为浏览器检测时需同步调整。

### API / 服务类

```ts
// ✅ 响应内容正确（不只 200）
const res = await request.post('/api/ocr', { data: { ... } });
expect(res.status()).toBe(200);
const body = await res.json();
expect(body.text).toContain('预期文字');  // 内容对
expect(body.pages).toBe(5);               // 结构对
```

## 判断标准

问自己：**「这个断言过了，功能就一定对吗？」**

- 如果「不一定」（canvas 存在但可能空白）→ 断言不够深，加功能结果断言。
- 如果「一定」（像素非空 + 文字可见 + 状态正确）→ 断言够深。

| 断言 | 弱（不够） | 强（够） |
|---|---|---|
| 元素 | `toBeTruthy()` / `count() > 0` | + bbox 像素 / 文字内容 / 属性值 |
| 渲染 | 元素存在 | + 像素非空 / 节点文字 / 尺寸 |
| 交互 | 按钮存在 | + 点击后状态变化（panel open / data 更新） |
| API | status 200 | + body 内容正确 |
