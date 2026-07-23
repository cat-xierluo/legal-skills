# 主题（Theme）

本目录存放手绘配图 skill 的视觉主题文件。每个主题是一个 JSON 文件，定义一组配色（重点色、纸面色、墨线色），让不同团队、律所或作者复用同一套构图与流程，只替换色彩。

## 内置主题

| 文件 | 主题 | 重点色 | 适用 |
| :--- | :--- | :--- | :--- |
| `blue-gray.json` | 蓝灰（默认） | `#435C68` | 法律、公众号长文、编辑类 |
| `ink-black.json` | 墨黑（中性通用） | `#2A2A28` | 极简、无品牌色需求 |
| `terracotta.json` | 赭石（暖调示例） | `#A65A3D` | 人文、文化、生活方式 |

`blue-gray` 是原作者的个人定制主题，也是 `config/style.json` 的默认激活主题。

## 如何切换主题

三选一，优先级从高到低：

1. **命令行参数**（单次出图）：

   ```bash
   python scripts/generate_prompts.py --outline outline.json --out prompts.json --theme ink-black
   ```

2. **大纲级覆盖**（写在 outline JSON 里，整篇文章生效）：

   ```json
   {
     "title": "...",
     "style": { "theme": "terracotta" }
   }
   ```

3. **改默认激活主题**（长期生效，所有出图都用它）：

   编辑 `config/style.json`，把 `active_theme` 改成主题名（即文件名去掉 `.json`）：

   ```json
   { "active_theme": "ink-black" }
   ```

切换主题后，`generate_prompts.py` 会从 `themes/<name>.json` 读取配色注入到 prompt，无需改 SKILL.md 或任何硬编码。

## 如何创建自己的主题

适合律所、品牌号或个人作者注入自己的主题色。只需新建一个 JSON 文件：

```bash
# 文件名即主题名，例如 themes/my-firm.json
```

内容模板：

```json
{
  "name": "my-firm",
  "display_name": "XX律所主题",
  "description": "律所品牌色 + 暖米白底 + 近黑墨线",
  "colors": {
    "accent_name": "firm-navy",
    "accent_color": "#1F3A5F",
    "paper_background": "#FAF9F5",
    "paper_surface": "#F2EEE3",
    "ink_color": "#141413"
  },
  "recommended_for": ["律所", "品牌"]
}
```

字段说明：

- `name`：主题名，与文件名（去掉 `.json`）一致。
- `display_name`：展示名。
- `colors.accent_name`：重点色的英文语义名，会写进 prompt（如 `firm-navy`）。**不要用品牌真名**，避免泄字。
- `colors.accent_color`：重点色 hex，整篇文章唯一的强调色。
- `colors.paper_background` / `paper_surface`：暖米白底色。建议保持低饱和暖白，保证可读性。
- `colors.ink_color`：近黑墨线色，建议接近 `#141413`。
- `recommended_for`：适用场景标签，便于选择。

激活并测试：

```bash
python scripts/generate_prompts.py --outline assets/outline_sample.json --out /tmp/test-prompts.json --theme my-firm
# 检查输出 prompt 中的 accent_color 是否为你的律所色
grep "accent_color\|#1F3A5F" /tmp/test-prompts.json
```

## 色值覆盖层（不改主题微调）

如果只想临时改一个色值、不想新建主题，在 `config/style.json` 的 `overrides` 里写：

```json
{
  "active_theme": "blue-gray",
  "overrides": {
    "accent_color": "#3A4F5C"
  }
}
```

`overrides` 的优先级高于主题，低于命令行 `--theme` 和 outline `style.accent_color`。

## 主题规范要点

1. **重点色唯一**：一篇文章只用一种重点色，不要在一个主题里放多色。
2. **纸面色低饱和暖白**：避免高饱和背景，否则手绘墨线对比度下降。
3. **墨线色接近黑**：保证轮廓清晰，避免灰色墨线。
4. **`accent_name` 用语义英文**：会进入英文 prompt，避免中文或品牌真名。
5. **文件名即主题名**：`themes/<name>.json`，`--theme <name>` 和 `active_theme` 都用这个 name。
