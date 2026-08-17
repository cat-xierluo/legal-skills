# 变更日志 — elements-complaint-generator

## 0.2.1（2026-08-17）— 67 类完整版全量入库（113 棵树）+ 三项渲染 bug 修复

### 全量模板入库
- 新增 `scripts/ingest_full_templates.py`：按法〔2025〕82 号**完整版**（上中下三册）批量入库，113 棵树（上 42 / 中 28 / 下 43），编号 01-68 即上中下顺序；完整版为**原生 OOXML docx**（无需 soffice 转换，零损失解包）
- 树命名 `<NN>-<案由>[-<文书类型>]`；源文件 5 处命名笔误规范化（缺"状"、42 号误标环境污染、38 号"人参"→"人身"等，manifest anomalies 留痕）
- `templates/templates-manifest.json` 升级 v2：113 条树↔源文件↔SHA-256 溯源
- 旧 01/02 树退役（源自 67类/ 平铺目录的 soffice 转换版，已被完整版原生树取代）；case-type key `02-private-lending` → **`09-private-lending`**（对齐完整版编号：离婚=05、民间借贷=09）

### 渲染 bug 修复（换新树回归时暴露的潜伏问题）
- **标签吃字**：`make_text_replace_rule` 此前把 match_text 整体换成裸值（"姓名："被吃掉只剩"张三"）→ 改为默认 `append=True` 保留标签（"姓名：张三"）；含空白复合占位（"第    条"→"第三条"）走 `append=False` + transform
- **性别误勾**：勾选只替换第一个 □，被告为"女"时勾到"男"→ 新增 `make_gender_rule` 按"男□/女□"值勾选
- **子串双勾**："了解□"是"不了解□"的子串，调解意愿区出现双 ☑ 且第 5 处漏勾 → 新增 `replace_option_check`（前字符≠"不"的独立选项才勾）+ benefits 循环跳过已含 ☑ 的段
- **段落拆分适配**：完整版原生 docx 中"是□/否□"分属不同段落（如"实际清偿之日止：是□"），相关 match_text 收窄锚定

### 回归
- 新树 sample：applied=71，8/8 标签保留断言 + 8/8 勾选正确性断言全绿（性别男☑×1/女☑×1、了解☑ 单勾×6、双勾 0、漏勾 0）
- e2e（md→extract→fill）：断言升级为带标签形态后全绿

## 0.2.0（2026-08-17）— OOXML 源码树架构

### 架构调整（DEC-056）
- **模板形态**：`assets/templates-docx/`（zip 二进制）退役 → **`templates/<案由>/` 解包 OOXML 源码树**为唯一权威源；模板变更 git 逐行 diff 可见，每案由完整树自包含（不抽公共 base 防格式混搭）
- **替换引擎**：python-docx → **lxml 直接编辑 `<w:t>`**：跨 run 精确替换（单 run 保留前后字符；跨 run 首尾存前后缀、中间清空），不吞字、不破坏字体/段落/表格/勾选框
- **多 part 覆盖**：word/document.xml + header*/footer* 全部文本 part
- **新增 `--verify-residual`**：替换后扫描残留旧串（防漏填/旧案信息泄漏）
- **分工明确**：Agent(LLM) 负责要素抽取（语义理解）；纯代码负责格式保真替换（确定性）；regex 抽取器降级为兜底

### 新增脚本
- `scripts/unpack_docx.py`：docx → OOXML 源码树（模板入库）
- `scripts/pack_docx.py`：OOXML 树 → docx（打包/校验/出件）
- skill 内 `.gitignore`：排除 `tests/output/` 运行产物（生成的 docx/elements.json 不入库）

### 回归验证（对比 v0.1 基线）
- sample fixture：applied 69→71，☑=22 持平
- e2e（md 抽取）：applied 45 持平，☑ 15→**17**（lxml 元素去重顺带修复合并单元格勾选 bug）
- 输出结构：6 表/36 段与模板一致，python-docx 可独立打开

### 命名决策
- 保留 `elements-complaint-generator`（用户终审；候选 element-style-complaint-generator 未采纳）

## 0.1.0（2026-08-17）— MVP 首版

### 新增
- **skill 主体**：在 `skills/elements-complaint-generator/` 建目录
- **SKILL.md**：技能定义、运行流程、依赖、限制
- **references/case-types/02-private-lending.md**：民间借贷要素 Schema + 字段填充规则
- **assets/templates-docx/02-民间借贷纠纷民事起诉状.docx**：LibreOffice OLE2→OOXML 转换产物（保真）
- **assets/templates-docx/01-离婚纠纷民事起诉状.docx**：预留案由（规则待实现）
- **templates/templates-manifest.json**：模板 SHA-256 元数据
- **scripts/ole2_to_docx.py**：批量 OLE2→docx 转换（带 `--include glob` 精确选择）
- **scripts/fill_template.py**：要素→docx 锚点替换核心渲染器
- **scripts/extract_from_markdown.py**：C 入口 md→要素抽取器
- **tests/fixtures/02-private-lending-complaint.md**：端到端测试用起诉状
- **tests/fixtures/02-private-lending-sample.json**：手工构造 elements.json（用于 fill_template 单测）

### 已知限制（v0.1 留待 v0.2）
- 仅 02 民间借贷规则完整实现；01 离婚规则未写
- 仅 C 入口（md）；A 对话、B 结构化文件入口未实现
- 仅自然人当事人；法人/非法人组织要素保留空白
- 委托代理人姓名抽取有边界 bug（复杂格式漏抽）
- 5 处"调解好处"勾选去重偶发问题

### 技术选型
- 路线 A：OOXML 解包 + 锚点替换（保字体）
- LibreOffice 25.8.4.2（macOS via brew cask）OLE2→docx
- python-docx 0.8.11
- 模板版本：法〔2025〕82 号 2025-07-14 推广版（多渠道交叉比对一致）