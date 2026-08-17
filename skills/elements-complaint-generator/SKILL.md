---
name: elements-complaint-generator
description: Use when converting 律师已写好的常规起诉状(md/docx)或对话描述为符合最高法 67 类官方要素式起诉状示范文本格式的 Word 文档(法〔2025〕82 号,2025-07-14 全国推广)。适用于民间借贷/离婚纠纷/机动车事故/劳动争议等所有 67 类民事/商事/行政/知产案由的要素式起诉状/答辩状生成。
license: CC-BY-NC
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.2.1"
---

# 要素式起诉状生成 Skill（elements-complaint-generator）

## 一、定位

在最高法 67 类官方要素式起诉状/答辩状模板（法〔2025〕82 号，2025-07-14 全国推广）上做锚点替换，从律师提供的「常规起诉状（Markdown 或 docx）/自然对话/结构化要素清单」中抽取信息，输出**像素级保真**的、符合现行法院立案格式的要素式 Word 文书。

### 1.1 分工铁律（Agent 与代码各司其职）

```
普通起诉状/对话 --[Agent(LLM) 抽取]--> elements.json --[纯代码(lxml) 替换]--> 要素式 docx
                    语义理解                                确定性格式保真
```

- **Agent 负责"抽取"**：读常规起诉状 → 按案由 Schema 产出 elements.json（人可复核）。语义理解是 LLM 强项，regex 只做兜底（`extract_from_markdown.py`）。
- **代码负责"填充"**：`fill_template.py` 在模板 XML 上做 `<w:t>` 跨 run 精确替换。格式保真是确定性任务，LLM 不碰。

### 1.2 v0.2 范围

| 维度 | v0.2 范围 |
|---|---|
| 模板 | **113 棵树全量入库**（法〔2025〕82 号完整版：上册42+中册28+下册43，编号01-68按上中下顺序） |
| 抽取 | **Agent 会话内抽取为主**；`extract_from_markdown.py` regex 为兜底 |
| 模板形态 | **解包 OOXML 源码树**（git 可 diff），渲染时复制→编辑→打包 |
| 替换引擎 | lxml 直接编辑 `<w:t>`（跨 run 精确替换，多 part 覆盖，`--verify-residual` 残留校验） |
| 模板版本 | 法〔2025〕82 号 2025-07-14 推广版（多渠道交叉比对一致） |

### 1.3 不适用场景

- 用户要的不是"要素式"格式（如要自由格式起诉状）→ 用 `legal-proposal-generator` 或人工起草
- 用户仅有扫描件 PDF → 先用 `legal-ocr` 转 md，再走本 skill
- 用户要批量生成同案由 100+ 份 → 暂不支持（后续加批量模式）

## 二、架构

```
┌────────────────────────────────────────────────┐
│ 输入：常规起诉状(md/docx) / 对话 / 要素文件      │
└───────────────────────┬────────────────────────┘
                        ▼
          ┌───────────────────────────┐
          │ Agent 按 Schema 抽要素     │ ← 语义理解（LLM）
          │ (regex 脚本兜底)           │
          └─────────────┬─────────────┘
                        ▼
          ┌───────────────────────────┐
          │ elements.json（人可复核）  │
          └─────────────┬─────────────┘
                        ▼
┌────────────────────────────────────────────────┐
│ fill_template.py（纯代码，确定性）              │
│  复制 templates/<案由>/ → lxml 编辑 <w:t>       │
│  <w:t> 跨 run 精确替换 → pack_docx 打包         │
│  → --verify-residual 残留校验                   │
└───────────────────────┬────────────────────────┘
                        ▼
          ┌───────────────────────────┐
          │ 要素式起诉状.docx          │ ← 法院立案可用
          └───────────────────────────┘
```

## 三、运行流程

### 3.1 主路径 — Agent 抽取（推荐）

```text
用户给常规起诉状（md/docx）或口述案件事实
  1. Agent 识别案由 → 09-private-lending
  2. Agent 读 references/case-types/09-private-lending.md §一 Schema
  3. Agent 直接产出 elements.json（存到案件目录）
  4. ⚠️ 请用户复核 elements.json（勾选项/缺失字段）
  5. 渲染：
     python scripts/fill_template.py \
       --case-type 09-private-lending \
       --elements <案件>/elements.json \
       --output <案件>/要素式起诉状.docx \
       --verify-residual "旧当事人名,旧电话"
```

### 3.2 兜底 — regex 抽取（Agent 不可用时）

```bash
python scripts/extract_from_markdown.py \
  --case-type 09-private-lending \
  --input 张三vs李四-起诉状.md \
  --output 张三vs李四-elements.json
# 之后同样人工复核 + fill_template
```

### 3.3 渲染细节（fill_template.py）

- 模板源 = `templates/<案由名>/`（解包 OOXML 树，git 可 diff）
- 渲染 = 复制树到临时目录 → lxml 编辑 word/*.xml（含页眉/页脚全部文本 part）→ 打包 docx
- 跨 run 精确替换：find 落在单 run 内保留前后字符；跨 run 时首 run 存前缀+新文本、末 run 存后缀、中间 run 清空——**不吞字、不破坏字体/段落/表格/勾选框**
- `--verify-residual "旧A,旧B"`：替换后扫描全文档残留旧串（防漏填/防旧案信息泄漏）

## 四、依赖与模板资产

### 4.1 运行依赖

| 工具 | macOS 安装 | 用途 |
|---|---|---|
| Python 3.11+ | 系统自带 | 运行 scripts |
| lxml | `pip3 install lxml` | XML 编辑（唯一硬依赖） |
| LibreOffice 25.x | `brew install --cask libreoffice` | 仅模板入库时用（OLE2→docx） |

### 4.2 模板资产

```
templates/                     # ★ 模板唯一权威源（113 棵 OOXML 源码树，git 可 diff）
  01-侮辱案刑事附带民事-刑事附带民事自诉状/   # 上册 01-21：刑事自诉4+民事9+商事8
  05-离婚纠纷-民事起诉状/                     #   （起诉状+答辩状成对）
  09-民间借贷纠纷-民事起诉状/                 # ← 规则已实现
  30-垄断纠纷-民事起诉状/                     # 中册 22-36：知产民事9+知产行政6+垄断行政
  44-行政处罚-行政起诉状/                     # 下册 37-68：海事4+环资3+行政11+行政答辩+国赔4+执行9
  55-行政答辩状/  60-强制执行申请书/           #   单文书目录（树名=编号-案由）

templates/templates-manifest.json             # v2 清单：树↔源文件↔SHA-256 溯源 + 命名规范化记录
```

**为什么用解包树而非 docx**：docx 是 zip 二进制（git diff 乱码）；解包后是纯文本 XML，模板迭代、官方版本更新、每次填充差异全部可 diff/可 review/可回滚。**每案由存完整树**（自包含、互不污染，不抽公共 base 防止格式铁律破防）。

### 4.3 模板入库流程（新案由 / 官方更新时）

```bash
# 完整版为原生 OOXML docx，直接批量解包入库（上中下顺序，编号 01-68）：
python scripts/ingest_full_templates.py \
  --source "~/Desktop/要素式起诉状模板/67类完整版(起诉状+答辩状+第三人意见陈述书)" \
  --templates templates --overwrite
# 若源是 OLE2 老格式（如 67类/ 平铺目录），先转再入：
python scripts/ole2_to_docx.py --input ~/Desktop/要素式起诉状模板/67类 --output /tmp/ecg-docx \
  --manifest templates/templates-manifest.json --include 'NN-*'
python scripts/unpack_docx.py --input /tmp/ecg-docx --output templates --overwrite
# ③ 反向打包（校验/出件用）
python scripts/pack_docx.py --tree templates/06-买卖合同纠纷-民事起诉状 --output 检查.docx
```

## 五、要素 Schema

详见 `references/case-types/09-private-lending.md`（完整字段定义 + 字段填充规则表）。

- 顶层：`当事人 / 诉讼请求 / 约定管辖和诉前保全 / 事实与理由 / 对纠纷解决方式的意愿 / 具状人_签字_盖章 / 具状日期`
- 当事人含 `原告/被告/第三人/委托诉讼代理人`（当前实现第一个原告/被告/委托代理人）
- 字段类型：str / bool（checkbox）/ enum / list

## 六、模板版本管理

- **当前版本**：法〔2025〕82 号，2025-07-14 全国推广
- **下次复查**：2026-11-17（每半年核查官方更新）
- 官方更新时：重跑 §4.3 入库流程 → `git diff templates/` 直接看到官方改了什么 → 检查规则是否需调整 → 跑回归

## 七、案由扩展步骤

以 06 买卖合同纠纷为例：

1. **模板入库**：§4.3 流程（ole2_to_docx → unpack_docx）
2. **写 Schema 文档**：参考 09，写 `references/case-types/06-sale.md`（含 §一 Schema + §二 填充规则表；先对模板树做 occurrence 映射勘察）
3. **写规则集**：`fill_template.py` 加 `build_rules_06_sale()` + `CASE_TYPE_TO_TREE` 映射
4. **抽取**：Agent 直接按 03 Schema 抽；如需 regex 兜底再在 `extract_from_markdown.py` 的 `CASE_TYPE_TO_EXTRACTOR` 加
5. **测试**：`tests/fixtures/` 加样例；跑 `tests/run_e2e.sh` 回归

## 八、限制与已知问题

- 仅 09 民间借贷规则完整；其余 112 棵树已入库、规则待写（05 离婚为下一优先）
- 仅自然人当事人；法人/非法人组织要素保留空白
- 多原告/多被告/多代理人（模板"可复制粘贴扩容"条款）尚未实现自动复制行
- 长文本多段 cell（如"事实与理由"12 段结构）的段落数保持尚未实现（v0.3 计划：XML 重建多段落）
- lxml 重序列化后建议用 Word/WPS 打开核对一次（个别扩展命名空间模板可能报"需修复"）

## 九、版本

- 当前版本：`0.2.1`（2026-08-17）
- 设计稿：`docs/plans/2026-08-17-elements-complaint-generator-design.md`（不入仓）