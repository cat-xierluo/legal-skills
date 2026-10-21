# Slide Aesthetics Guide

> 这是给 Subagent 生成幻灯片页面时的首要设计参考。技术规范请参考 principles.md。

## Design Philosophy

在写代码之前，先理解上下文并确定一个**大胆的美学方向**：

- **Purpose**: 这个幻灯片解决什么问题？谁在看？
- **Tone**: 选择一个明确的风格方向：
  - 极简克制 / 极繁华丽
  - 复古未来 / 有机自然
  - 奢华精致 / 玩味童趣
  - 杂志编辑 / 粗野主义
  - 装饰艺术 / 柔和粉彩
  - 工业实用 / 科技赛博
- **Differentiation**: 什么让观众记住这个演示？一个令人难忘的视觉记忆点是什么？

**关键原则**: 选择一个清晰的概念方向，精准执行。大胆的极繁和精致的极简都可行——关键是意图明确，而非强度高低。

---

## Typography 字体选择

### 推荐字体组合

为幻灯片场景优化——兼顾可读性与个性：

**Display 标题字体（选一）:**
- Sora — 几何感，现代科技
- DM Sans — 友好，专业平衡
- Outfit — 圆润，亲和力强
- Manrope — 清晰，略带个性
- Poppins — 几何圆润，流行感

**Body 正文字体（选一）:**
- Source Sans 3 — 高可读性，专业
- Nunito Sans — 柔和，友好
- Work Sans — 中性，适应性强

### 字体使用原则

- 标题用 Display 字体，正文用 Body 字体
- 避免在一个演示中使用超过 2 种字体
- 字重对比：标题 `font-bold` (700)，正文 `font-normal` (400)

### 禁止使用

- ❌ Arial, Helvetica — 过于通用
- ❌ Inter, Roboto — AI 生成的典型标志
- ❌ Times New Roman — 不适合屏幕演示
- ❌ Comic Sans — 除非有意为之

---

## Motion & Micro-interactions 动效

### 入场动画

使用 staggered reveals 创造节奏感：

```jsx
// 使用 framer-motion
import { motion } from 'framer-motion';

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
};

<motion.div variants={container} initial="hidden" animate="show">
  <motion.div variants={item}>Item 1</motion.div>
  <motion.div variants={item}>Item 2</motion.div>
</motion.div>
```

### 推荐动画模式

| 场景 | 动画 | 参数 |
|------|------|------|
| 卡片入场 | fade + slide up | `opacity: 0→1, y: 20→0` |
| 标题入场 | fade + scale | `opacity: 0→1, scale: 0.95→1` |
| 列表项 | stagger reveal | `staggerChildren: 0.1` |
| 数字变化 | count up | 使用 `framer-motion` 的 `useSpring` |
| 图表 | draw path | `pathLength: 0→1` |

### Hover 状态

```jsx
// 卡片悬停效果
<motion.div
  whileHover={{
    scale: 1.02,
    boxShadow: "0 20px 40px rgba(0,0,0,0.2)"
  }}
  transition={{ type: "spring", stiffness: 300 }}
>
```

### 过渡时机

- `duration: 0.3` — 快速响应（hover、点击）
- `duration: 0.5` — 标准过渡（页面切换）
- `duration: 0.8` — 戏剧性入场（首屏动画）

---

## Color & Theme 配色

### 原则

- **主导色 + 锐利强调色** 优于 胆怯的均匀分布
- 使用 CSS 变量保持一致性（见 principles.md）
- 深色主题：背景要够深，文字对比要够强
- 浅色主题：避免纯白，用微妙的暖/冷灰

### 禁止的配色

- ❌ 紫色渐变 + 白色背景（AI 生成的典型标志）
- ❌ 彩虹渐变（除非是 Pride 主题）
- ❌ 过于饱和的霓虹色作为大面积使用

---

## Spatial Composition 空间构图

### 打破常规

- **非对称布局** — 不要总是居中对齐
- **重叠元素** — 卡片、图片可以部分重叠
- **对角线流动** — 引导视线从左上到右下
- **打破网格** — 偶尔让元素突破边界
- **大胆留白** 或 **控制密度** — 两者都可行，但要有意为之

### 布局示例

```
传统（避免）:          大胆（推荐）:
┌─────────────┐       ┌─────────────┐
│   Title     │       │ Title       │
├─────────────┤       │     ┌───────┤
│ Card  Card  │       │ Card│ Card  │
│ Card  Card  │       └─────┴───────┘
└─────────────┘              ↑ 重叠
```

---

## Backgrounds & Visual Details 背景与细节

### 创造氛围感

不要默认使用纯色背景。添加深度和氛围：

**渐变光晕:**
```css
.glow {
  background: radial-gradient(
    ellipse at 30% 20%,
    theme('colors.primary.500/20') 0%,
    transparent 50%
  );
}
```

**噪点纹理:**
```css
.noise {
  background-image: url("data:image/svg+xml,..."); /* 噪点 SVG */
  opacity: 0.03;
}
```

**几何图案:**
- 点阵网格
- 细线网格
- 放射状线条

### 装饰元素

- 模糊光斑（`blur-3xl` + 低透明度）
- 渐变边框（`border-transparent` + gradient background）
- 微妙的阴影层次

---

## Anti-AI-Slop Checklist 反 AI 通用风格

### 每个 Slide 必检

- [ ] 没有使用 Inter/Roboto/Arial 字体
- [ ] 没有紫色渐变 + 白底的组合
- [ ] 配色有明确的主导色，不是均匀分布
- [ ] 布局有变化，不是千篇一律的卡片网格
- [ ] 有至少一个视觉记忆点
- [ ] 背景有氛围感，不是纯色

### 记住

Claude 有能力创造非凡的创意作品。不要保守——充分展现跳出框架思考的能力，全力投入一个独特的视觉愿景。

每个设计都应该不同。在浅色/深色主题、不同字体、不同美学之间变化。**永远不要**在多次生成中收敛到相同的选择。
