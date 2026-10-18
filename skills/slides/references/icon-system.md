# icon 图标运用体系

> 三档尺寸 + 语义聚类的图标运用体系,面向中文 browser-deck(1280×720 固定画布 + Lucide 线性图标 + 蓝金主题)。与 `style-reference.md`(字号刻度/组件)、`cn-deck-polish.md`(中文避坑)互补——那两份讲"字与版式",本份专讲"图标怎么选、放多大、怎么和字组合"。
>
> **直接痛点**:LLM 生成时极易把所有 icon 一律塞 16-20px,导致"加了 icon 但太小、起不到识别作用"。本份用三档尺寸 + 语义映射把这件事钉死。

## 1. 三档尺寸:按用途分档,不是按感觉

固定 1280×720 画布对应 px(不是 vw/vh):

| 档位 | px | 用途 | 典型场景 |
|---|---|---|---|
| **lg** | 56–72 | pillar/章节卡主图、单独成视觉锚的大图标 | 分节 hero 图标、value-spine 主图、flywheel 中心 |
| **md** | 32–40 | **识别主力档**:列表项 icon+文字组合、卡片标题前缀 | delivery stage、roadmap card、value-tier、对比页 icon disc |
| **sm** | 18–22 | 行内附属标记、tag 徽标、句中点缀 | callout 角标、meta 行小图标、句内 inline |

### 硬规则

- **凡是要起"图像化识别"作用的图标,最低走 md 档(32px 起),不允许用 sm 充数。** 这是"icon 没起到作用"的根因——默认走 sm。
- 配 disc/圆形容器时,**容器与图标同步放大**(如 md 档:disc 46–52px + svg 26–30px),不要只放大 svg 撑满小 disc(显挤),也不要大 disc 配小 svg(显空)。
- 一页内同用途的 icon 必须同档(如 delivery 5 个 stage 全 md、roadmap 4 张卡全 md),不允许大小混用。

## 2. 法律语义簇映射(什么概念配什么 icon)

选 icon 不要凭感觉挑,**按内容语义查簇**。基于现有 14 个 symbol(bot/message/file-text/scan-text/search/mic/shield-check/workflow/matter-pipeline/skill-playbook/human-agent/knowledge-asset/judgment-loop/evidence-chain)+ 建议扩展:

| 语义簇 | 首选 icon | 什么时候用 |
|---|---|---|
| **AI / Agent** | `bot`(AI 助手)、`message`(对话/对话史)、`workflow`(流程编排)、`human-agent`(人机协作)、`sparkles`(生成/魔法,扩展) | 讲 Agent、ChatBot、人机关系、生成动作 |
| **法律载体** | `file-text`(文书)、`scan-text`(OCR)、`shield-check`(合规/风控/护栏) | 合同、判决书、卷宗、合规审查、OCR 场景 |
| **检索分析** | `search`(检索)、`mic`(ASR 转录)、`judgment-loop`(裁判循环)、`crosshair`(精准命中,扩展) | 法律检索、语音转文字、判决分析、类案定位 |
| **案件流程** | `matter-pipeline`(案件流水线)、`evidence-chain`(证据链)、`route`(替代路径,扩展) | 收案→交付链、证据组织、流程对比 |
| **知识资产** | `skill-playbook`(技能手册)、`knowledge-asset`(知识资产)、`book-open`(法条库,扩展) | Skill 沉淀、Playbook、知识库、复用资产 |
| **对错判断**(对比页专用) | `check-circle`(do,扩展)、`x-circle`(don't,扩展)、`compass`(方向/判断锚点,扩展) | 讲/不讲、do/don't、正反对比 |

**生成法**:拿到一页主题关键词 → 反查上表所属簇 → 取首选 icon;若该页是对比/选择,优先用"对错判断"簇。一页内跨簇时,每个 icon 仍按各自语义选,但尺寸统一同档。

## 3. icon-text inline 组合:三条硬 spec

icon 和文字贴一起时(列表项、卡片标题前缀),必须满足:

1. **外层 `display:flex;align-items:center`**(垂直居中对齐,否则 icon 顶在文字基线/中线偏移)。
2. **gap 用 em 不用 px**:正文级 icon-text 取 `0.6–0.8em`,标题级取 `0.4–0.5em`。em 随字号缩放,px 会导致不同字号下错位。
3. **icon 高度 ≥ 文字 cap-height 的 1.4 倍**,否则视觉上 icon 被"吃掉"显小。实操:正文 14-16px 配 md icon(32px+ in disc,或 26px+ bare);标题 20-24px 配 md-lg icon。

```html
<!-- ✅ 正文级 combo:disc 46 + svg 26 + em gap -->
<div style="display:flex;align-items:center;gap:7px">
  <span style="width:46px;height:46px;border-radius:50%;display:grid;place-items:center;background:var(--ink);color:var(--gold)">
    <svg class="deck-icon" style="width:26px;height:26px"><use href="#icon-search"/></svg>
  </span>
  <span class="when">法律检索</span>
</div>

<!-- ❌ 反例:icon 走 sm(20px)裸贴,被文字吃掉,起不到识别 -->
<svg style="width:20px;height:20px"/><span>法律检索</span>
```

## 4. 扩展 icon 的引入原则

- 优先用现有 14 个;确需新 icon(如对比页要 check-circle/x-circle)时,补 Lucide 同风格线性 symbol(`fill:none;stroke:currentColor;stroke-width:2;stroke-linecap/linejoin:round`),内联进同一 `<svg defs>` 块,保持单文件离线。
- **不外链** Lucide CDN/unsplash 等线上图标库(违反单文件离线)。

---

**生成时**:每页先定"这页 icon 起识别还是点缀"→ 识别用途全 md 起、点缀才 sm;再按 §2 语义簇选具体 icon;最后 §3 spec 组合。**审计时 grep**:所有 `width:1[0-9]px;height:1[0-9]px` 和 `width:2[0-2]px` 的 deck-icon,逐一确认是否真该走 sm(多数应升 md)。
