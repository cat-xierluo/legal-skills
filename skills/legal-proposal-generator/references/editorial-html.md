# 设计版 HTML

对方需要在浏览器阅读或打印方案时，从已经审定的 Markdown 生成单文件 HTML。封面、章节导航和连续正文借鉴 Magazine Studio 的章节层级、留白、表格和引文排版。同一方案保留 Markdown 作为内容源，可继续按需生成可编辑 Word。

## 准备源稿

- 沿用 Word 源稿的单行封面字段 `law_firm`、`client`、`lawyer`、`date`，可填 `subtitle`。以唯一的 `#` 开始正文，`##` 一级章节进入目录。已有 `title` 时须与 `#` 标题一致。
- 附页内容在源稿写为末尾独立章节。团队、资质和案例只使用本次确认可交付的内容。排版器从显式输入取材。
- 正文支持 Markdown 段落、列表、表格、引文、加粗和 HTTP(S) 引用。表格数据行的列数须与表头一致。HTML 标签作为文本显示，Mermaid 等代码块作为代码显示。图件先导出为本篇目录内的 PNG 或 JPEG，以相对路径引用，单张上限 8 MiB。

## 生成与复核

需要 Python 3.10+ 和 `markdown-it-py`。缺少依赖时可在当前 Python 环境安装已验证的版本。

```bash
python3 -m pip install markdown-it-py==4.2.0
```

在 Skill 根目录生成示例。

```bash
python3 html/render.py --input html/example.md --output proposal-example.html
```

将 `--input` 换成审定源稿路径，并给 `--output` 一个尚不存在的文件名。生成的 HTML 带样式和已嵌入的图件，浏览器可离线打开。受众点击正文中的来源链接时才会导航至对应站点。

检查标题、金额、条件、来源和附录与源稿一致。实际打开 HTML，检查目录跳转和窄屏表格。需要 PDF 时在浏览器选择 A4 打印并逐页复核封面、长表格和附录。复杂跨栏、逐页定版或特定品牌版式由可用的 Designer 后端按同一源稿处理。
