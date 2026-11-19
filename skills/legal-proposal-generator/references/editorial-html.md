# 设计版 HTML

对方需要在浏览器阅读或打印方案时，从已经审定的 Markdown 生成单文件 HTML。同一方案保留 Markdown 作为内容源，可继续按需生成可编辑 Word。

## 选择方案模板

从 Magazine Studio 的 Legal Proposal 场景提炼两种表达方式。每份文稿可选择一个需要视觉强调的章节，其余内容沿原顺序连续排版。

| 模板 | 适用场景 | 排版方式 |
| --- | --- | --- |
| [服务蓝图](../templates/html-service-blueprint.md) | 服务范围已明确，客户需要看清推进步骤 | 按源稿有序列表显示连续服务阶段，窄屏和打印时纵向排列 |
| [决策策略](../templates/html-decision-strategy.md) | 下一步取决于证据、授权或其他前提 | 同行对照核验条件、建议动作和风险边界，突出动作列 |

复制模板后以审定内容替换示例字段和正文。在首部用 `html_scene` 选择 `service_blueprint` 或 `decision_strategy`，并以 `html_section` 指定一个唯一的 `##` 章标题文字。服务蓝图章节使用一个有序列表。决策策略章节使用一个三列表格，至少写一条决策记录。两种版式只强调源稿已有的信息和关系。省略这两个字段时使用[连续阅读样例](../html/example.md)的通用版式。

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
python3 html/render.py --input templates/html-service-blueprint.md --output service-blueprint.html
python3 html/render.py --input templates/html-decision-strategy.md --output decision-strategy.html
```

将 `--input` 换成审定源稿路径，并给 `--output` 一个尚不存在的文件名。生成的 HTML 带样式和已嵌入的图件，浏览器可离线打开。受众点击正文中的来源链接时才会导航至对应站点。

检查标题、金额、条件、来源和附录与源稿一致。实际打开 HTML，检查目录跳转和窄屏表格。需要 PDF 时在浏览器选择 A4 打印并逐页复核封面、长表格和附录。复杂跨栏、逐页定版或特定品牌版式由可用的 Designer 后端按同一源稿处理。
