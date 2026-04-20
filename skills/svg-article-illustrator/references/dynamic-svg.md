# 动态 SVG 模式规范

本文档是**默认输出模式**的规范，支持 SMIL 动画效果。

## 模式特性

- 动态 SVG 效果：SMIL 动画标签
- Emoji 与动态效果结合
- 视觉复杂度提升：3-6 个视觉元素
- SVG 代码直接嵌入 Markdown 文件
- 公众号完美支持（原生 SMIL）
- ⚠️ **背景色强制要求**：SVG 画布必须设置非白色背景色（见下方详述）

---

## 一、SMIL 动画基础

公众号仅支持 SMIL 动画（`<animate>`、`<animateTransform>`），禁止使用 CSS `@keyframes` 和 JavaScript。

| 标签 | 功能 | 应用场景 |
|------|------|---------|
| `<animate>` | 属性动画 | 颜色、透明度、线条偏移 |
| `<animateTransform>` | 变换动画 | 位移、旋转、缩放 |

---

## 二、⚠️ 背景色强制要求

**【前置要求 - 最高优先级】**

所有动态 SVG 画布 **必须设置非白色背景色**，禁止使用纯白 `#FFFFFF` 作为画布背景。

**原因**：
1. 纯白背景导致圆角、边框等视觉元素与背景融为一体，无法区分
2. 白色背景与内容对比度不足，视觉层次感差
3. 无法体现设计感和专业性

**背景色选择**：
```svg
<!-- ❌ 错误：纯白背景 -->
<svg viewBox="0 0 800 450">
  <rect x="60" y="60" width="680" height="330" rx="12" fill="#FFFFFF"/>
</svg>

<!-- ✅ 正确：浅色背景 -->
<svg viewBox="0 0 800 450">
  <rect x="0" y="0" width="800" height="450" fill="#F0F4F8"/>
  <!-- 圆角框元素 rx="10" -->
  <rect x="60" y="60" width="680" height="330" rx="10" fill="rgba(255,255,255,0.8)" stroke="#D0D8E0"/>
</svg>
```

**同一篇文章内的每张配图按序号轮流使用不同背景色**。背景色从以下色库选择：
- `#F5F5F5` `#F8F9FA` `#FAF8F5` `#FAF0E6` `#F0F4F8`
- `#E8F5E8` `#FFF0F5` `#F3E8F8` `#E0F0F8` `#FFFBE6`

---

## 三、核心动态效果

### 效果 1：浮动动画

多角色元素上下浮动

```xml
<circle cx="200" cy="200" r="50" fill="#4A90E2">
  <animateTransform attributeName="transform" type="translate"
    values="0,0; 0,-10; 0,0" dur="3s" repeatCount="indefinite"
    calcMode="spline" keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"/>
</circle>
```

**参数**：
- 浮动幅度：8-15px
- 浮动周期：2-4 秒
- 多角色错峰：0.5-1 秒

### 效果 2：虚线框流动

强调框架边界

```xml
<rect x="100" y="100" width="600" height="250" fill="none"
  stroke="#4A90E2" stroke-width="3" rx="10" stroke-dasharray="10,5">
  <animate attributeName="stroke-dashoffset" from="30" to="0"
    dur="1s" repeatCount="indefinite"/>
</rect>
```

**参数**：
- 虚线 `10,5`
- 流动 0.8-1.5 秒

### 效果 4：背景浮动圆形（全场漂移）

在画布背景层放置 2-3 个大半径圆形，利用 `animateTransform type="translate"` 实现贯穿整个画布的漂移动画。为文章配图增加生动感。

```xml
<circle cx="100" cy="100" r="90" fill="#D4A574" fill-opacity="0.06">
  <animateTransform attributeName="transform" type="translate"
    values="0,0; 600,700; 0,0" dur="18s" repeatCount="indefinite"/>
</circle>
<circle cx="700" cy="200" r="70" fill="#10B981" fill-opacity="0.05">
  <animateTransform attributeName="transform" type="translate"
    values="0,0; -600,500; 0,0" dur="15s" repeatCount="indefinite"/>
</circle>
<circle cx="400" cy="750" r="55" fill="#435c68" fill-opacity="0.05">
  <animateTransform attributeName="transform" type="translate"
    values="0,0; 0,-600; 0,0" dur="12s" repeatCount="indefinite"/>
</circle>
```

**参数**：
- 圆形半径：50-100px（较大，视觉存在感强）
- 透明度：0.04-0.08（极淡，装饰性不抢主体内容）
- 颜色：使用配色方案中的主色或辅色
- 位移距离：横跨整个画布（300-600px）
- 动画周期：12-20 秒（较慢，优雅不眼花）
- 多球方向错开：水平、垂直、对角线等不同方向

**应用场景**：
- 作者卡片、结尾引导等需要"有气场"的设计
- 作为全局背景层，不影响前景内容

**⚠️ 注意事项**：
- 圆形必须放在所有内容元素之前（背景层）
- 位移终点不能超出画布边界
- 建议放在 SVG 顶层 `<g>` 的最前面，之后再放内容层

### 效果 3：箭头绘制

展示流程指向

```xml
<defs>
  <marker id="arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
    <polygon points="0 0, 10 3.5, 0 7" fill="#4A90E2"/>
  </marker>
</defs>
<line x1="200" y1="200" x2="600" y2="200" stroke="#4A90E2"
  stroke-width="4" marker-end="url(#arrow)"
  stroke-dasharray="400" stroke-dashoffset="400">
  <animate attributeName="stroke-dashoffset" from="400" to="0"
    dur="1.5s" repeatCount="indefinite"/>
</line>
```

**参数**：
- 线条粗 3-5px
- 绘制 1-2 秒

---

## 三、Emoji 动态效果

### Emoji 浮动动画

```xml
<!-- ✅ 正确：用 x/y 定位，内层 g 做浮动动画 -->
<g>
  <text x="200" y="225" font-size="100" text-anchor="middle">😰</text>
  <g>
    <animateTransform attributeName="transform" type="translate"
      values="0,0; 0,-12; 0,0" dur="3s" repeatCount="indefinite"
      calcMode="spline" keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"/>
  </g>
</g>
```

### Emoji 脉冲动画

```xml
<!-- ✅ 正确：translate 定位 + scale 动画（scale 不覆盖 translate） -->
<g transform="translate(400, 225)">
  <text x="0" y="35" font-size="100" text-anchor="middle">🎯</text>
  <animateTransform attributeName="transform" type="scale"
    values="1; 1.08; 1" dur="2s" repeatCount="indefinite"
    calcMode="spline" keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"/>
</g>
```

### Emoji + 几何图形组合

```xml
<!-- ✅ 正确：translate 定位 + opacity 动画（不冲突） -->
<g transform="translate(400, 225)">
  <circle cx="0" cy="0" r="90" fill="#E8F4F8">
    <animate attributeName="fill-opacity" values="0.6; 1; 0.6"
      dur="3s" repeatCount="indefinite"/>
  </circle>
  <text x="0" y="35" font-size="100" text-anchor="middle">🚀</text>
</g>
```

---

## 四、动态效果使用原则

### 逻辑性动态效果优先

**最重要**：动态效果必须服务于**逻辑关系的表达**，而非单纯的装饰。

**优先级表**：

| 优先级 | 动态效果类型 | 作用 | 必须使用场景 |
|--------|------------|------|------------|
| **最高** | 箭头绘制动画 | 展示指向、流程、因果关系 | 所有包含箭头/连接线的图 |
| **最高** | 虚线框流动动画 | 强调框架、边界、范围 | 所有包含虚线框的图 |
| **高** | 线条流动动画 | 展示数据/信息流动 | 流程图、关系图 |
| **中** | 脉冲动画 | 强调核心元素 | 中心概念、关键节点 |
| **低** | 浮动动画 | 增加生动感 | emoji、角色元素 |

### 严格规则

- 有箭头必须动画、有虚线框必须动画
- 逻辑先于装饰：先确保逻辑关系动画，再考虑 emoji 浮动
- **禁止静态箭头**

### 推荐使用场景

多角色场景（浮动）、强调框架（虚线流动）、流程指向（箭头绘制）、核心元素（脉冲）、状态变化（颜色渐变）

### 谨慎使用

单元素场景、信息密集、需要稳定感的内容

### 组合原则

- 主次分明：1-2 种主要动画
- 节奏协调
- 方向一致
- 错峰展示

---

## 五、成功标准

- 布局多样化，动态效果自然流畅
- 公众号显示正常，动画无卡顿
- 在丰富性和可读性之间保持平衡
- 逻辑性动画优先于装饰性动画

---

## 六、⚠️ 兼容性警告

### 🚨 禁止 transform + animateTransform translate 组合

**这是最常见的问题！** 当外层有 `transform="translate(x,y)"`，内层又有 `<animateTransform type="translate">` 时，动画会**完全覆盖**外层的定位，导致元素飞到左上角 (0,0)。

```svg
<!-- ❌ 错误：translate 定位 + translate 动画 = 元素堆到左上角 -->
<g transform="translate(180, 200)">
  <circle cx="0" cy="0" r="80" fill="#4A90E2"/>
  <animateTransform type="translate" values="0,0; 0,-12; 0,0"/>
</g>

<!-- ✅ 正确方法1：直接用 cx/cy 定位，内层包一层做动画 -->
<g>
  <circle cx="180" cy="200" r="80" fill="#4A90E2"/>
  <g>
    <animateTransform type="translate" values="0,0; 0,-12; 0,0" dur="3s" repeatCount="indefinite"/>
  </g>
</g>

<!-- ✅ 正确方法2：translate 定位 + scale 动画（scale不会覆盖translate） -->
<g transform="translate(180, 200)">
  <circle cx="0" cy="0" r="80" fill="#4A90E2"/>
  <animateTransform type="scale" values="1; 1.1; 1" dur="2s" repeatCount="indefinite"/>
</g>

<!-- ✅ 正确方法3：纯 emoji 浮动，用 x/y 定位 -->
<text x="180" y="235" font-size="80" text-anchor="middle">🐎</text>
<g>
  <animateTransform type="translate" values="0,0; 0,-12; 0,0" dur="3s" repeatCount="indefinite"/>
</g>
```

**核心原则**：
- `transform="translate()"` 只能和 `type="scale"` 动画组合
- 要做 `type="translate"` 浮动动画，必须直接用 `cx/cy` 或 `x/y` 定位
- 永远不要嵌套两层 `translate`（一个静态一个动态）

### 禁止使用 SVG Filter

**微信环境不兼容**：使用 `<g filter="url(#shadow)">` 会导致 SMIL 动画无法在微信中显示。

```svg
<!-- ❌ 错误：filter 会导致动画失效 -->
<g filter="url(#shadow)">
  <rect ...>
    <animateTransform attributeName="transform" .../>
  </rect>
</g>

<!-- ✅ 正确：直接使用 transform 定位 -->
<g transform="translate(100, 120)">
  <rect ...>
    <animateTransform attributeName="transform" .../>
  </rect>
</g>
```

**解决方案**：
1. 禁止在任何 SVG 元素上使用 `filter` 属性
2. 使用 `transform` 替代 filter 进行视觉定位
3. 阴影效果可以用边框颜色深浅或背景色区分来替代

### 禁止渐变填充 + 动画组合

**微信环境不兼容**：当 `fill="url(#gradient)"` 和 `<animateTransform>` 在同一个元素上时，渐变无法显示。

```svg
<!-- ❌ 错误：渐变和动画在同一元素上 -->
<rect fill="url(#gradient)">
  <animateTransform attributeName="transform" .../>
</rect>

<!-- ✅ 推荐：直接使用纯色 -->
<rect fill="#10B981">
  <animateTransform attributeName="transform" .../>
</rect>
```

### 🚫 禁止所有渐变填充

**公众号不支持所有渐变**：即使静态的渐变背景也无法渲染，请使用纯色。

```svg
<!-- ❌ 错误：渐变背景 -->
<linearGradient id="bgGrad">...</linearGradient>
<rect fill="url(#bgGrad)"/>

<!-- ✅ 正确：使用纯色 -->
<rect fill="#f8f9fa"/>
```

---

## 七、✅ 动画组合速查表

| 定位方式 | 可用动画类型 | 示例 |
|---------|------------|------|
| `transform="translate()"` | `type="scale"` | ✅ 脉冲缩放 |
| `transform="translate()"` | `type="rotate"` | ✅ 旋转 |
| `transform="translate()"` | `type="translate"` | ❌ **禁止！会覆盖定位** |
| `cx/cy` 或 `x/y` 直接定位 | `type="translate"` | ✅ 浮动动画 |
| 任意定位 | `<animate>` 属性动画 | ✅ 颜色、透明度等 |

**记忆口诀**：
> translate 定位只能配 scale/rotate，要做浮动必须用 x/y/cx/cy 直接定位！
