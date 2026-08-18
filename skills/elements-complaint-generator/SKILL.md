---
name: elements-complaint-generator
description: Use when converting 律师已写好的常规起诉状(md/docx)或对话描述为符合最高法 67 类官方要素式起诉状示范文本格式的 Word 文档(法〔2025〕82 号,2025-07-14 全国推广)。适用于民间借贷/离婚纠纷/机动车事故/劳动争议等所有 67 类民事/商事/行政/知产案由的要素式起诉状/答辩状生成。
license: CC-BY-NC
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.12.0"
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

### 1.2 v0.3 范围

| 维度 | v0.3 范围 |
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

## 三、运行流程（三段式：案由匹配 → 两段抽取 → 渲染）

### 3.1 ① 案由匹配

```text
读用户材料（起诉状 md/docx / 口述）→ 对照 references/case-routing.md
→ 确定案由编号 + case-type key + 模板树 + reference 文档
→ 拿不准时列 2-3 个候选案由请用户选
```

### 3.2 ② 要素抽取（通用块 + 案由特定块）

按 `references/extraction-prompt-template.md` 执行：
- **通用块**（common-elements.md）：当事人 / 代理人 / 调解意愿 / 具状人
- **案由特定块**（case-types/{{key}}.md §一）：诉讼请求勾选与金额 / 保全 / 事实与理由
- 纪律：材料没有→留空；枚举用选项原文；日期 ISO；产出 elements.json 后**必须用户复核**
- 兜底：Agent 不可用时 `extract_from_markdown.py`（09/05 已实现 regex 兜底）

### 3.3 ③ 渲染（纯代码）

```bash
python scripts/fill_template.py \
  --case-type 06 \   # 两位编号=通用级；精调级：05-divorce / 09-private-lending / 06-sale / 15-labor / 21-traffic
  --elements <案件>/elements.json \
  --output <案件>/要素式起诉状.docx \
  --verify-residual "旧当事人名,旧电话"
```

- 复制 templates/<树>/ → lxml 编辑 `<w:t>`（跨 run 精确替换，多 part 覆盖）→ 打包
- 通用规则（当事人/调解/具状）与案由规则分层复用（DEC-001/002 铁律）
- `--verify-residual` 残留校验防旧案信息泄漏

### 3.4 回归

`bash tests/run_e2e.sh` — 双案由精调回归（带标签断言+哨兵）+ **全 68 编号通用级冒烟**（tests/smoke_all.py）

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

## 五、要素 Schema（三层 reference）

| 层 | 文档 | 覆盖 |
|---|---|---|
| 通用层 | `references/common-elements.md` | 当事人/代理人/调解意愿/落款等跨案由要素（证据：113 棵树扫描，28 签名组） |
| 路由层 | `references/case-routing.md`（脚本生成，勿手改） | 113 棵树索引：案由/册/文书/树/key/支持状态/关键词 |
| 案由层 | `references/case-types/NN-*.md` | 案由特定要素；**骨架由 `dump_template_fields.py` 从模板树反推生成**，人/Agent 补要素路径与抽取提示 |

**68/68 全部定稿**：case-types/ 目录覆盖全部编号（14 份手写详版 + 54 份程序化生成精简版）；骨架 `skeletons/` 66 份全字段清单。

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
2. **写 Schema 文档**：`python scripts/dump_template_fields.py --tree templates/06-买卖合同纠纷-民事起诉状 --output references/case-types/06-sale-skeleton.md` 生成骨架 → 补要素路径/occurrence 映射/抽取提示（通用块直接引用 common-elements.md，不重复定义）
3. **写规则集**：`fill_template.py` 加 `build_rules_06_sale()` + `CASE_TYPE_TO_TREE` 映射
4. **抽取**：Agent 直接按 06 Schema 抽；如需 regex 兜底再在 `extract_from_markdown.py` 的 `CASE_TYPE_TO_EXTRACTOR` 加
5. **测试**：`tests/fixtures/` 加样例；跑 `tests/run_e2e.sh` 回归

## 八、限制与已知问题

- **68/68 全案由精调完毕**：63 个 build_rules 构建器（叠加模式：通用层+家族工厂+案由特定）覆盖全部编号
- 答辩状/第三人意见陈述书 45 棵树**不接入**（用户裁示：skill 定位聚焦起诉状生成）
- 通用级当事人为顺序语义（自然人1/自然人2）——法人原告案由（物业/公益诉讼/执行类）中自然人1 可能是对方当事人，Agent 抽取按骨架指引
- 答辩状/第三人意见陈述书 45 棵树未接入（形态差异大：角色为答辩人、无调解块）
- 仅自然人当事人；法人/非法人组织要素保留空白
- 多原告/多被告/多代理人（模板"可复制粘贴扩容"条款）尚未实现自动复制行
- 长文本多段 cell（如"事实与理由"12 段结构）的段落数保持尚未实现（v0.3 计划：XML 重建多段落）
- lxml 重序列化后建议用 Word/WPS 打开核对一次（个别扩展命名空间模板可能报"需修复"）

## 九、版本

- 当前版本：`0.12.0`（2026-08-18）
- 设计稿：`docs/plans/2026-08-17-elements-complaint-generator-design.md`（不入仓）