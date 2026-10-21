# 风格库

从 HTML 幻灯片提取的风格定义，供 AI 生成新内容时引用。

## 使用方式

### 1. 提取风格

```bash
node scripts/extract-style.js 现有幻灯片.html --save 风格名称
```

### 2. 列出可用风格

```bash
node scripts/extract-style.js --list
```

### 3. AI 生成时引用

让 AI 读取风格 JSON 文件，按照其中的配色、字体、布局参数生成新 HTML。

## 风格文件格式

每个 `.json` 文件包含以下字段：

```json
{
  "name": "风格名称",
  "source": "来源说明",
  "slideDimensions": { "width": 1000, "height": 562.5 },
  "colors": {
    "backgrounds": ["#18181B"],
    "textColors": ["#FFFFFF", "#18181B"],
    "accents": ["#D97706"],
    "palette": ["#18181B", "#D97706", "#FAFAF8"]
  },
  "typography": {
    "fontFamilies": ["PingFang SC"],
    "titleSizes": [49.7],
    "bodySizes": [18]
  },
  "layout": {
    "positioning": "absolute",
    "marginPattern": [62, 39],
    "contentWidth": 876
  }
}
```

`source` 描述风格的来龙去脉（提取自哪个课件 / 自建于哪个场景）。当前 38 个内置预设均为本技能自建或从实际课件提取，无外部参照。**未来若新增预设参照了外部项目的配色/字体，必须同时写 `attribution` 字段**：`{ "name": 上游项目名, "url": 上游仓库地址, "scope": 参照范围声明 }`，并在 `--list-styles` 输出与文档中保持可见。
