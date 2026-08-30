---
name: elements-complaint-generator
description: Use when converting 律师已写好的常规起诉状(md/docx)或对话描述为符合最高法 67 类官方要素式起诉状示范文本格式的 Word 文档(法〔2025〕82 号,2025-07-14 全国推广)。适用于民间借贷/离婚纠纷/机动车事故/劳动争议等所有 67 类民事/商事/行政/知产案由的要素式起诉状/答辩状生成。
license: MIT
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "0.15.0"
---

# 要素式起诉状生成 Skill（elements-complaint-generator）

## 一、定位

在最高法 67 类官方要素式起诉状/答辩状模板（法〔2025〕82 号，2025-07-14 全国推广）上做锚点替换，从律师提供的「常规起诉状（Markdown 或 docx）/自然对话/结构化要素清单」中抽取信息，输出通过 DOCX 结构检查与真实 PDF 渲染门禁的要素式 Word 候选文书。法律内容和个案立案要求仍由律师复核。

### 1.1 分工铁律（Agent 与代码各司其职）

```
普通起诉状/对话 --[Agent(LLM) 抽取]--> elements.json --[纯代码(lxml) 替换]--> 要素式 docx
                    语义理解                                确定性模板填充
```

- **Agent 负责"抽取"**：读常规起诉状 → 按案由 Schema 产出 elements.json（人可复核）。语义理解是 LLM 强项，regex 只做兜底（`extract_from_markdown.py`）。
- **代码负责"填充与客观版式门禁"**：`fill_template.py` 在模板 XML 上做 `<w:t>` 跨 run 精确替换，再由独立检查器验证结构和真实 PDF 几何；LLM 不直接修改 OOXML。

### 1.2 当前范围（v0.15）

| 维度 | 范围 |
|---|---|
| 模板 | **113 棵树全量入库**（法〔2025〕82 号完整版：上册42+中册28+下册43，编号01-68按上中下顺序） |
| 抽取 | **Agent 会话内抽取为主**；`extract_from_markdown.py` regex 为兜底 |
| 模板形态 | **解包 OOXML 源码树**（git 可 diff），渲染时复制→编辑→打包；**22 案由已替换为法院实际发放件基准**（2 表结构，DEC-011） |
| 替换引擎 | lxml 直接编辑 `<w:t>`（跨 run 精确替换，多 part 覆盖，`--verify-residual` 残留校验） |
| 版式门禁 | 默认把候选 DOCX 交给 LibreOffice 真实渲染，再检查 A4、表格居中/列宽、跨页行、连续页码和空白页；失败不覆盖目标文件 |
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
│  → 残留校验 → DOCX 静态门禁 → PDF 真实渲染门禁 │
└───────────────────────┬────────────────────────┘
                        ▼
          ┌───────────────────────────┐
          │ 要素式起诉状.docx          │ ← 候选交付件，律师复核
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
# 精调 key 示例：09-private-lending / 22-copyright / 60-enforcement / 65-objection；两位编号（如 06）走通用级
python scripts/fill_template.py \
  --case-type 09-private-lending \
  --elements <案件>/elements.json \
  --output <案件>/要素式起诉状.docx \
  --verify-residual "旧当事人名,旧电话"
```

- 复制 templates/<树>/ → lxml 编辑 `<w:t>`（跨 run 精确替换，多 part 覆盖）→ 打包
- 通用规则（当事人/调解/具状）与案由规则分层复用（DEC-001/002 铁律）
- `--verify-residual` 残留校验防旧案信息泄漏
- 默认 `--layout-check rendered`：先在临时候选件上执行 DOCX 不变量检查，再用 LibreOffice 转 PDF 检查真实页面；任一步失败均非零退出，且不覆盖已有目标文件。
- `--layout-check docx` 只供开发期批量回归，不能据此交付；`--layout-check off` 仅用于定位门禁自身问题，不能据此声称版式通过。
- 版式例外统一写入 `config/layout-policy.json`。当前仅 22 著作权法院基准件明确不带页码，禁止由全局规则自行补页码。

### 3.4 回归

`bash tests/run_e2e.sh` — 内容断言与 68 编号冒烟 + 113 棵树 DOCX 版式静态门禁 + 21 类文书真实 PDF 渲染 + 版式违规正反例。

## 四、依赖与模板资产

### 4.1 运行依赖

| 工具 | macOS 安装 | 用途 |
|---|---|---|
| Python 3.11+ | 系统自带 | 运行 scripts |
| lxml | `pip3 install lxml` | XML 编辑与 DOCX 版式检查（硬依赖） |
| PyMuPDF | `pip3 install pymupdf` | 读取真实渲染 PDF 的页面几何与页码（默认交付路径需要） |
| LibreOffice 25.x | `brew install --cask libreoffice`<br>Linux: `sudo apt-get install libreoffice` | 默认交付路径的 DOCX→PDF 真实渲染；模板入库时也用于 OLE2→docx |

首次运行默认渲染路径前安装 Python 依赖：`pip3 install lxml pymupdf`。缺少 LibreOffice 或 PyMuPDF 时，脚本会明确报错并拒绝发布目标文件，不会静默降级为“已验证”。

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
- 多原告/多被告/多代理人（模板"可复制粘贴扩容"条款）尚未实现自动复制行（自然人 3-4 号块复制已支持；代理人目前单槽位）
- 长文本多段 cell（如"事实与理由"12 段结构）的段落数保持尚未实现（v0.3 计划：XML 重建多段落）
- 当前已完成 113/113 模板静态版式检查和 21/21 文书家族真实渲染抽样；68 棵主文书逐树长文本压力渲染与页面截图矩阵仍在任务队列中，不能把抽样结果扩大解释为所有极端内容长度均已验证。
- LibreOffice 渲染门禁用于发现客观几何问题；模板使用的 `方正书宋_GBK`、`方正小标宋_GBK` 等字体别名若在运行环境中不存在，PDF 文字层仍可能完整但中文字形不可见。当前 `DOMAIN_VERIFIED` 不包含跨机器字体可用性结论；正式提交前仍应在实际 Word/WPS 环境核对字体、内容、签章位置和当地法院要求。

## 九、权限与数据边界

- 脚本只在 `tempfile.mkdtemp()` 临时目录内复制模板树并渲染，渲染后自动 `shutil.rmtree()` 清理临时目录（不触碰用户数据）。
- `ingest_full_templates.py --overwrite` 可覆盖 `templates/` 下指定模板树（显式参数，非默认行为）。
- 不向网络发送任何案件内容；`--verify-residual` 只做本地扫描。

## 十、版本

- 当前版本：`0.15.0`（2026-08-30）
- 0.15.0：新增独立 DOCX/PDF 版式门禁和逐模板例外策略；统一表格显式居中、固定列宽、零缩进与禁止非必要拆行；保留横竖版边界并修复宽表方向；页码改为连续 PAGE 域并补齐节页脚引用；候选件先验后发布；113/113 静态检查、21/21 文书家族真实 PDF 渲染和 10 个正反例通过
- 0.14.0：22 模板源替换为法院件基准（DEC-011）；几何宽度感知边距（推翻 1800 归一）；引擎补链（22 权项/客体/停止侵权/关联无/费用行布局无关/代理人勾选/住所地字段名映射修复/skipped 明细）；250612 案 260826 MD 端到端 48/48 断言通过
- 0.13.5：新增渲染后强制 QA 清单（references/qa-checklist.md），收敛 250612 案实战问题（模板几何/表合并/第三人串填/引擎规则缺口/人工修补铁律）
- 0.13.4（2026-08-22）
- 覆盖：113/113 模板树（68 主文书精调 + 45 答辩状）
- 格式修复：节合并（主体连续+调解/证据独立分页）、页边距归一（25mm）、页脚 PAGE 域
- 设计稿：`docs/plans/2026-08-17-elements-complaint-generator-design.md`（不入仓）

---

## 十一、渲染后强制 QA（2026-08-28 新增，v0.13.5）

**任何渲染输出在交付前必须先通过自动版式门禁，再完整执行 [渲染后 QA 清单](references/qa-checklist.md)**（源自 250612 武景怡案五轮返工实战复盘）。人工视觉复核只补充机器难以判断的法律内容、签章位置和局部观感，不能替代自动门禁。要点：

1. **问题归属三分**：入库模板（表拆分/表宽 9344 溢出/字段跨 tc）、渲染引擎（知产案由规则缺口、第三人串填、标签被吞、勾选静默跳过）、人工修补（ 反引用字面量、宽松正则误插）——排障先分责。
2. **基准原则**：几何与三表形态以**法院实际发放件**为准（实测法院件表宽 ~7008，入库模板 9344 溢出 A4）。
3. **六步 QA**：几何→结构（3 表/行宽校验）→勾选（含第三人两□全空、代理人有☑特别授权☑）→字段（住所地/客体五要素/金额标签+数值）→唯一性（被告三要素各 1 次、=0）→20 项自动断言全过才覆盖目标件。
4. **人工修补铁律**：只在单元格内改文本、repl 禁反引用、/tmp 过检后一次性覆盖。

引擎层待修清单见 qa-checklist.md 第四节（知产权项规则链、代理勾选规则、occurrence 串填、标签保留、内置几何后处理、skipped 明细打印）。
