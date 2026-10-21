# HTML 幻灯片页面模板

AI 生成幻灯片时可参考的页面类型模板。每种模板提供完整的 HTML 结构，可直接使用或组合变体。

生成前先参考 `references/layout-theme-playbook.md` 选择版式家族，再从本文件挑选页面模板。所有模板默认服务 16:9 固定画幅（1000×562.5px），并遵守 PPTX 稳定性规则：文字使用语义标签、背景放父容器、图片使用本地路径、不要依赖滚动。

---

## 1. 封面页

```html
<div class="slide" style="background-color: var(--primary); justify-content: center; align-items: center; text-align: center;">
  <h1 style="font-size: 49px; font-weight: 700; color: var(--text-light); margin-bottom: 16px;">
    演示文稿标题
  </h1>
  <h2 style="font-size: 28px; color: var(--accent); margin-bottom: 32px;">
    副标题
  </h2>
  <p style="font-size: 16px; color: var(--text-muted);">
    日期 · 地点 · 作者
  </p>
</div>
```

---

## 2. 标题 + 要点列表页

```html
<div class="slide" style="background-color: var(--bg-light); padding: 40px 60px;">
  <h2 style="font-size: 36px; font-weight: 700; color: var(--text-primary); margin-bottom: 30px;">
    页面标题
  </h2>
  <ul style="font-size: 18px; color: var(--text-primary); line-height: 1.8; padding-left: 24px;">
    <li>要点一</li>
    <li>要点二</li>
    <li>要点三</li>
    <li>要点四</li>
  </ul>
</div>
```

---

## 3. 左右分栏页

```html
<div class="slide" style="background-color: var(--bg-white); padding: 40px 60px;">
  <h2 style="font-size: 36px; font-weight: 700; color: var(--text-primary); margin-bottom: 30px;">
    页面标题
  </h2>
  <div style="display: flex; gap: 40px;">
    <div style="flex: 1;">
      <h3 style="font-size: 22px; color: var(--accent); margin-bottom: 12px;">左栏标题</h3>
      <p style="font-size: 16px; color: var(--text-primary); line-height: 1.6;">左栏内容</p>
    </div>
    <div style="flex: 1;">
      <h3 style="font-size: 22px; color: var(--accent); margin-bottom: 12px;">右栏标题</h3>
      <p style="font-size: 16px; color: var(--text-primary); line-height: 1.6;">右栏内容</p>
    </div>
  </div>
</div>
```

---

## 4. 特性卡片网格页

```html
<div class="slide" style="background-color: var(--bg-light); padding: 40px 60px;">
  <h2 style="font-size: 36px; font-weight: 700; color: var(--text-primary); margin-bottom: 30px;">
    页面标题
  </h2>
  <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px;">
    <div style="background: var(--bg-white); border-radius: 8px; padding: 20px;">
      <h3 style="font-size: 18px; color: var(--accent); margin-bottom: 8px;">卡片标题</h3>
      <p style="font-size: 14px; color: var(--text-muted);">卡片描述</p>
    </div>
    <!-- 重复更多卡片 -->
  </div>
</div>
```

---

## 5. 数据表格页

```html
<div class="slide" style="background-color: var(--bg-white); padding: 40px 60px;">
  <h2 style="font-size: 36px; font-weight: 700; color: var(--text-primary); margin-bottom: 30px;">
    数据展示
  </h2>
  <table style="width: 100%; border-collapse: collapse; font-size: 16px;">
    <thead>
      <tr>
        <th style="background: var(--accent); color: var(--bg-white); padding: 12px; text-align: left;">
          列标题
        </th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding: 10px 12px; border-bottom: 1px solid #e5e5e5;">数据</td>
      </tr>
    </tbody>
  </table>
</div>
```

---

## 6. 引言/金句页

```html
<div class="slide" style="background-color: var(--primary); justify-content: center; align-items: center; padding: 60px;">
  <p style="font-size: 32px; font-style: italic; color: var(--accent); text-align: center; max-width: 80%; line-height: 1.5;">
    "引言内容放这里，不超过三行。"
  </p>
  <p style="font-size: 16px; color: var(--text-muted); margin-top: 24px;">
    — 出处 / 作者
  </p>
</div>
```

---

## 7. 大数据展示页

```html
<div class="slide" style="background-color: var(--bg-light); padding: 40px 60px;">
  <h2 style="font-size: 36px; font-weight: 700; color: var(--text-primary); margin-bottom: 30px;">
    关键数据
  </h2>
  <div style="display: flex; gap: 60px; justify-content: center; align-items: center; flex: 1;">
    <div style="text-align: center;">
      <p style="font-size: 64px; font-weight: 700; color: var(--accent);">98%</p>
      <p style="font-size: 16px; color: var(--text-muted);">指标一</p>
    </div>
    <div style="text-align: center;">
      <p style="font-size: 64px; font-weight: 700; color: var(--accent);">2.5M</p>
      <p style="font-size: 16px; color: var(--text-muted);">指标二</p>
    </div>
    <div style="text-align: center;">
      <p style="font-size: 64px; font-weight: 700; color: var(--accent);">150+</p>
      <p style="font-size: 16px; color: var(--text-muted);">指标三</p>
    </div>
  </div>
</div>
```

---

## 8. 章节分隔页

```html
<div class="slide" style="background-color: var(--primary); justify-content: center; align-items: flex-start; padding: 40px 60px;">
  <p style="font-size: 12px; color: var(--accent); margin-bottom: 12px;">PART 02</p>
  <h1 style="font-size: 42px; font-weight: 700; color: var(--text-light);">
    章节标题
  </h1>
  <div style="width: 60px; height: 3px; background: var(--accent); margin-top: 16px;"></div>
</div>
```

---

## 9. 横向时间线页

适用于案件经过、项目里程碑、法规演进。每个节点只写“时间 + 事件 + 意义”。

```html
<div class="slide" style="background-color: var(--bg-light); padding: 40px 60px; position: relative;">
  <p style="font-size: 12px; color: var(--accent); letter-spacing: 2px; margin-bottom: 8px;">TIMELINE</p>
  <h2 style="font-size: 34px; color: var(--text-primary); margin-bottom: 70px;">案件关键时间线</h2>
  <div style="position: absolute; left: 90px; right: 90px; top: 270px; height: 2px; background: rgba(0,0,0,0.12);"></div>
  <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 28px;">
    <div style="position: relative; padding-top: 26px;">
      <div style="position: absolute; top: -10px; left: 0; width: 16px; height: 16px; border-radius: 50%; background: var(--accent);"></div>
      <p style="font-size: 14px; color: var(--accent); font-weight: 700; margin-bottom: 8px;">2026.01</p>
      <h3 style="font-size: 18px; color: var(--text-primary); margin-bottom: 8px;">合同签署</h3>
      <p style="font-size: 13px; color: var(--text-muted); line-height: 1.6;">确立交易基础与主要付款节点。</p>
    </div>
    <!-- 复制 3 个节点 -->
  </div>
</div>
```

---

## 10. 纵向流程页

适用于诉讼流程、合规整改路径、课程操作步骤。步骤标题用动词开头。

```html
<div class="slide" style="background-color: var(--bg-white); padding: 40px 60px; position: relative;">
  <h2 style="font-size: 34px; color: var(--text-primary); margin-bottom: 28px;">证据固定四步法</h2>
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 22px;">
    <div style="padding: 20px 22px; border-left: 4px solid var(--accent); background: var(--bg-light); border-radius: 8px;">
      <p style="font-size: 13px; color: var(--accent); font-weight: 700; margin-bottom: 8px;">STEP 01</p>
      <h3 style="font-size: 20px; color: var(--text-primary); margin-bottom: 8px;">识别争议事实</h3>
      <p style="font-size: 14px; color: var(--text-muted); line-height: 1.6;">把待证明事实拆成主体、时间、行为、结果四类。</p>
    </div>
    <!-- STEP 02-04 -->
  </div>
</div>
```

---

## 11. 对比矩阵页

适用于方案比较、路径选择、风险等级说明。推荐 2-4 列、3-6 行。

```html
<div class="slide" style="background-color: var(--bg-light); padding: 40px 60px;">
  <h2 style="font-size: 34px; color: var(--text-primary); margin-bottom: 28px;">三种处理路径比较</h2>
  <table style="width: 100%; border-collapse: collapse; font-size: 14px; background: var(--bg-white);">
    <thead>
      <tr>
        <th style="width: 22%; padding: 12px; text-align: left; background: var(--primary); color: #fff;">维度</th>
        <th style="padding: 12px; text-align: left; background: var(--primary); color: #fff;">协商</th>
        <th style="padding: 12px; text-align: left; background: var(--accent); color: #fff;">诉讼</th>
        <th style="padding: 12px; text-align: left; background: var(--primary); color: #fff;">仲裁</th>
      </tr>
    </thead>
    <tbody>
      <tr><td style="padding: 12px; border-bottom: 1px solid #E5E7EB;">周期</td><td style="padding: 12px; border-bottom: 1px solid #E5E7EB;">短</td><td style="padding: 12px; border-bottom: 1px solid #E5E7EB;">中</td><td style="padding: 12px; border-bottom: 1px solid #E5E7EB;">中短</td></tr>
      <tr><td style="padding: 12px; border-bottom: 1px solid #E5E7EB;">强制力</td><td style="padding: 12px; border-bottom: 1px solid #E5E7EB;">弱</td><td style="padding: 12px; border-bottom: 1px solid #E5E7EB;">强</td><td style="padding: 12px; border-bottom: 1px solid #E5E7EB;">强</td></tr>
      <tr><td style="padding: 12px;">适用</td><td style="padding: 12px;">关系仍可维护</td><td style="padding: 12px;">证据充分且需执行</td><td style="padding: 12px;">合同有仲裁条款</td></tr>
    </tbody>
  </table>
</div>
```

---

## 12. KPI 数据看板页

适用于阶段成效、报告摘要、关键指标。每个数字必须有口径说明。

```html
<div class="slide" style="background-color: var(--primary); padding: 42px 60px; color: #fff;">
  <p style="font-size: 12px; color: var(--accent); letter-spacing: 2px; margin-bottom: 10px;">KEY METRICS</p>
  <h2 style="font-size: 34px; margin-bottom: 36px;">本阶段工作结果</h2>
  <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px;">
    <div style="background: rgba(255,255,255,0.06); border-radius: 10px; padding: 22px;">
      <p style="font-size: 44px; color: var(--accent); font-weight: 800; margin-bottom: 8px;">12</p>
      <h3 style="font-size: 16px; margin-bottom: 8px;">核心证据</h3>
      <p style="font-size: 12px; color: rgba(255,255,255,0.68); line-height: 1.5;">已完成编号、来源和证明目的整理。</p>
    </div>
    <!-- 复制 3 个指标卡片 -->
  </div>
</div>
```

---

## 13. 案例 / 证据卡片页

适用于判例拆解、证据链说明、合同条款风险页。强调可回溯来源。

```html
<div class="slide" style="background-color: var(--bg-light); padding: 40px 60px;">
  <h2 style="font-size: 32px; color: var(--text-primary); margin-bottom: 24px;">证据 E-03：聊天记录截图</h2>
  <div style="display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 28px;">
    <div style="background: var(--bg-white); border-radius: 10px; padding: 24px; border-left: 4px solid var(--accent);">
      <p style="font-size: 13px; color: var(--accent); font-weight: 700; margin-bottom: 10px;">证明目的</p>
      <h3 style="font-size: 22px; color: var(--text-primary); margin-bottom: 14px;">证明对方已确认交付标准</h3>
      <p style="font-size: 15px; color: var(--text-muted); line-height: 1.7;">截图显示 2026 年 3 月 8 日双方确认“以最终验收清单为准”，可用于回应对方关于口头变更的抗辩。</p>
      <p style="font-size: 11px; color: var(--text-muted); margin-top: 18px;">来源：微信聊天记录导出，第 18-21 页</p>
    </div>
    <div style="background: #111827; border-radius: 10px; padding: 20px;">
      <p style="font-size: 13px; color: var(--accent); margin-bottom: 12px;">风险提示</p>
      <ul style="padding-left: 18px;">
        <li style="font-size: 14px; color: rgba(255,255,255,0.82); line-height: 1.8;">需补充原始载体或公证记录</li>
        <li style="font-size: 14px; color: rgba(255,255,255,0.82); line-height: 1.8;">需与合同附件形成印证</li>
      </ul>
    </div>
  </div>
</div>
```

---

## 14. 法律培训讲义页

适用于“规则解释 + 练习题 + 操作提示”的课程页面。

```html
<div class="slide" style="background-color: var(--bg-white); padding: 40px 60px;">
  <p style="font-size: 12px; color: var(--accent); letter-spacing: 2px; margin-bottom: 8px;">TRAINING</p>
  <h2 style="font-size: 32px; color: var(--text-primary); margin-bottom: 24px;">如何判断证据是否足以支撑主张？</h2>
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 28px;">
    <div style="background: var(--bg-light); border-radius: 10px; padding: 22px;">
      <h3 style="font-size: 20px; color: var(--text-primary); margin-bottom: 14px;">判断规则</h3>
      <ul style="padding-left: 20px;">
        <li style="font-size: 14px; color: var(--text-muted); line-height: 1.8;">能否对应待证事实</li>
        <li style="font-size: 14px; color: var(--text-muted); line-height: 1.8;">能否说明主体、时间、行为</li>
        <li style="font-size: 14px; color: var(--text-muted); line-height: 1.8;">能否与其他证据相互印证</li>
      </ul>
    </div>
    <div style="background: var(--primary); border-radius: 10px; padding: 22px;">
      <h3 style="font-size: 20px; color: #fff; margin-bottom: 14px;">课堂练习</h3>
      <p style="font-size: 14px; color: rgba(255,255,255,0.78); line-height: 1.8;">给定一份聊天记录和付款截图，请判断它们分别能证明什么、不能证明什么。</p>
      <p style="font-size: 13px; color: var(--accent); margin-top: 16px;">输出：待证事实 → 证据编号 → 证明强度</p>
    </div>
  </div>
</div>
```

---

## 15. 风险矩阵页

适用于法律风险分级、整改优先级、合同条款审查摘要。

```html
<div class="slide" style="background-color: var(--bg-light); padding: 40px 60px;">
  <h2 style="font-size: 32px; color: var(--text-primary); margin-bottom: 26px;">合同风险优先级</h2>
  <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px;">
    <div style="background: #7F1D1D; border-radius: 10px; padding: 22px;">
      <p style="font-size: 12px; color: rgba(255,255,255,0.7); margin-bottom: 8px;">HIGH</p>
      <h3 style="font-size: 20px; color: #fff; margin-bottom: 10px;">必须修改</h3>
      <p style="font-size: 13px; color: rgba(255,255,255,0.82); line-height: 1.6;">付款条件不明确、违约责任缺失、核心义务不可执行。</p>
    </div>
    <div style="background: #92400E; border-radius: 10px; padding: 22px;">
      <p style="font-size: 12px; color: rgba(255,255,255,0.7); margin-bottom: 8px;">MEDIUM</p>
      <h3 style="font-size: 20px; color: #fff; margin-bottom: 10px;">建议优化</h3>
      <p style="font-size: 13px; color: rgba(255,255,255,0.82); line-height: 1.6;">验收流程、通知方式、资料交付清单需要进一步明确。</p>
    </div>
    <div style="background: #14532D; border-radius: 10px; padding: 22px;">
      <p style="font-size: 12px; color: rgba(255,255,255,0.7); margin-bottom: 8px;">LOW</p>
      <h3 style="font-size: 20px; color: #fff; margin-bottom: 10px;">可接受</h3>
      <p style="font-size: 13px; color: rgba(255,255,255,0.82); line-height: 1.6;">表述可更严谨，但不影响主要商业安排。</p>
    </div>
  </div>
</div>
```

---

## CSS 动画类（浏览器演示模式）

以下动画类仅在浏览器直接演示时有效，PPTX 转换会忽略动画。

```css
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideInLeft { from { transform: translateX(-50px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
@keyframes slideInRight { from { transform: translateX(50px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
@keyframes slideInUp { from { transform: translateY(30px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
@keyframes scaleIn { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }

.animate-fade { animation: fadeIn 0.8s ease forwards; }
.animate-slide-left { animation: slideInLeft 0.6s ease forwards; }
.animate-slide-right { animation: slideInRight 0.6s ease forwards; }
.animate-slide-up { animation: slideInUp 0.6s ease forwards; }
.animate-scale { animation: scaleIn 0.5s ease forwards; }

.delay-1 { animation-delay: 0.1s; opacity: 0; }
.delay-2 { animation-delay: 0.2s; opacity: 0; }
.delay-3 { animation-delay: 0.3s; opacity: 0; }
.delay-4 { animation-delay: 0.4s; opacity: 0; }
```

---

## 浏览器演示控制器

如果需要将 HTML 幻灯片在浏览器中直接演示（键盘翻页、全屏、触摸支持），可使用以下 JS 控制器。

### 主入口 HTML

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>演示文稿</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: #000; }
    #slideFrame { width: 100%; height: 100%; border: none; transition: opacity 0.2s ease; }
    .page-info { position: fixed; bottom: 20px; left: 20px; background: rgba(0,0,0,0.6);
      color: #fff; padding: 8px 16px; border-radius: 8px; font-size: 14px; z-index: 1000; }
    .nav-controls { position: fixed; bottom: 20px; right: 20px; display: flex; gap: 10px; z-index: 1000; }
    .nav-btn { width: 40px; height: 40px; border: none; border-radius: 8px;
      background: rgba(255,255,255,0.2); color: #fff; font-size: 18px; cursor: pointer; }
    .nav-btn:hover { background: rgba(255,255,255,0.4); }
  </style>
</head>
<body>
  <iframe id="slideFrame" src="slides/01-cover.html"></iframe>
  <div class="page-info"><span id="pageIndicator">1 / N</span></div>
  <div class="nav-controls">
    <button class="nav-btn" id="prevBtn">◀</button>
    <button class="nav-btn" id="nextBtn">▶</button>
  </div>
  <script>
    // 键盘控制：← → 翻页，F 全屏，Home/End 首末页
    // 触摸支持：左右滑动翻页
  </script>
</body>
</html>
```

详细的 `SlideController` 完整代码见 `references/styles/raw/templates.md`。
