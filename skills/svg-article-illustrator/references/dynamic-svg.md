# 动态 SVG 模式规范

本文档是**默认输出模式**的规范，支持 SMIL 动画效果。

## 模式特性

- 动态 SVG 效果：SMIL 动画标签
- Emoji 与动态效果结合
- 视觉复杂度提升：3-6 个视觉元素
- SVG 代码直接嵌入 Markdown 文件
- 公众号完美支持（原生 SMIL）

---

## 一、SMIL 动画基础

公众号仅支持 SMIL 动画（`<animate>`、`<animateTransform>`），禁止使用 CSS `@keyframes` 和 JavaScript。

| 标签 | 功能 | 应用场景 |
|------|------|---------|
| `<animate>` | 属性动画 | 颜色、透明度、线条偏移 |
| `<animateTransform>` | 变换动画 | 位移、旋转、缩放 |

---

## 二、核心动态效果

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
<text x="200" y="225" font-size="100" text-anchor="middle">😰</text>
<g>
  <text x="200" y="225" font-size="100" text-anchor="middle">😰</text>
  <animateTransform attributeName="transform" type="translate"
    values="0,0; 0,-12; 0,0" dur="3s" repeatCount="indefinite"
    calcMode="spline" keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"/>
</g>
```

### Emoji 脉冲动画

```xml
<g transform="translate(400, 225)">
  <text x="0" y="35" font-size="100" text-anchor="middle">🎯</text>
  <animateTransform attributeName="transform" type="scale"
    values="1; 1.08; 1" dur="2s" repeatCount="indefinite"
    calcMode="spline" keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"/>
</g>
```

### Emoji + 几何图形组合

```xml
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
