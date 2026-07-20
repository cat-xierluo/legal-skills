---
name: yuandian-law-search
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.7.5"
license: MIT
description: 元典法条与案例检索。本技能应在需要查询中国法律法规条文、检索相关案例、为法律分析提供数据支撑时使用。
---

# 元典法条与案例检索

通过元典开放平台 API 检索中国法律法规条文和案例。**每次 API 调用消耗 1-50 积分**（视接口而定）。所有检索结果会自动归档到本地，方便后续回溯。

## 前置要求（每次调用前自动检测）

每次使用本技能前，**必须先执行以下检测流程**，确认 API Key 已就绪：

### 检测步骤

1. **检测 `.env` 文件**：检查 `scripts/.env` 是否存在
2. **检测 API Key**：读取文件中 `YD_API_KEY` 的值，确认非空且不是占位符 `your-api-key-here`
3. **若检测失败**，向用户提示以下引导信息并终止：

```
⚠️ 元典 API Key 未配置。请按以下步骤获取并配置：

1. 注册/登录：访问 https://open.chineselaw.com ，使用手机号注册
2. 创建 API Key：登录后在个人中心创建 Key
3. 配置密钥：将 Key 填入以下文件

   scripts/.env
   ─────────────
   YD_API_KEY=sk-你的密钥
   # YD_STRATEGY=balanced
   ─────────────

每次调用消耗 10 积分，需在平台充值。
配置完成后重新发起检索即可。
```

4. **若检测通过**，继续执行用户请求的检索命令

### 检测命令

```bash
# 检测 .env 文件和 API Key
if [ -f "scripts/.env" ]; then
  KEY=$(grep '^YD_API_KEY=' scripts/.env | cut -d'=' -f2)
  if [ -n "$KEY" ] && [ "$KEY" != "your-api-key-here" ]; then
    echo "API Key 已就绪"
  else
    echo "API Key 未配置"
  fi
else
  echo ".env 文件不存在"
fi

# 读取检索策略
STRATEGY=$(grep '^YD_STRATEGY=' scripts/.env 2>/dev/null | cut -d'=' -f2)
echo "当前策略：${STRATEGY:-balanced}"
```

## 网络环境与推荐调用入口

默认使用 `scripts/yd-run` 执行检索，而不是直接调用底层 `yd_search.py`。`yd-run` 会以干净环境启动 Python：清除 Codex/代理相关环境变量，保留 `HOME`、`PATH`、语言环境、`YD_API_KEY`、`YD_STRATEGY`，并继续读取 `scripts/.env` 和 `archive/` 缓存。

```bash
scripts/yd-run search "正当防卫的限度" --sxx 现行有效
```

若遇到 `nodename nor servname provided, or not known` 或其他网络错误，先执行无积分消耗的网络检查：

```bash
scripts/yd-run --network-check
```

注意：`yd-run` 只能避免 Codex 进程环境变量、代理变量和 PATH 漂移造成的影响；如果 Codex 本身以网络沙箱启动，或系统代理/VPN 接管 DNS，子进程仍会受到系统级网络策略影响。终端 Codex 应使用 `--sandbox danger-full-access --ask-for-approval never` 启动。

## 接口速查

本技能共 35 个接口，分为四层。选择规则：

1. 用户问"XX法怎么规定的" → 先用 `search` 语义检索
2. 用户问"关于XX的法律条文" → 用 `keyword` 关键词检索
3. 用户问"民法典第XX条" → 用 `detail` 精确获取
4. 用户给出明确案由/关键词并要求精确筛选案例 → 用 `case` 关键词检索（默认普通案例）
5. 用户描述事实结构、争议焦点或问"类似案件怎么判" → 优先用 `case-semantic` 语义检索
6. 用户要求更深入了解某案例 → 提醒用户将消耗积分，确认后用 `case-detail`
7. 用户要求企业背景调查 → 先用 `enterprise-search` 定位，再用 `enterprise-base`/`enterprise-summary` 获取详情
8. 用户要求查询企业分项信息（涉诉、商标、专利等） → 用 `enterprise-list --type TYPE`
9. 用户要求检测文本中法规/案例是否准确 → 用 `hall-detect`

**核心接口（默认使用）：** `search` · `keyword` · `detail` · `case` · `case-semantic`
**扩展接口（需确认）：** `regulation` · `regulation-detail` · `case-detail` · `case --authority-only`
**附属接口（仅限明确要求）：** `enterprise` · `enterprise-detail` · `enterprise-search` · `enterprise-base` · `enterprise-summary` · `enterprise-list`
**专项接口（仅限明确要求）：** `hall-detect`

## 调用策略

读取 `scripts/.env` 中的 `YD_STRATEGY` 配置（默认 `balanced`）。三种策略决定了 AI 的接口使用、确认流程和补充检索行为。

**用户的明确指令始终优先于策略默认行为。**

### 通用规则（所有策略共享）

每次 API 调用消耗 1-50 积分（视接口而定）。以下规则不受策略影响：

1. **必须调用 API**：需要引用具体法条文号 / 需要确认时效性 / 用户明确要求检索 / 案例检索 / AI 对自身记忆不确定
2. **可以不调用**：纯概念性问题 / 对话中已检索过相同内容 / 用户未要求查找 / 用户明确说不需要查
3. **积分消耗模式**：大部分接口每次 5-10 积分，幻觉检测 50 积分，轻量企业检索 1 积分。法条检索通常一次足够。案例检索是两阶段消耗（摘要 10 + 详情 每个 10）
4. **接口分层**：核心（search·keyword·detail·case·case-semantic）、扩展（regulation·regulation-detail·case-detail·case --authority-only）、附属（enterprise·enterprise-detail·enterprise-search·enterprise-base·enterprise-summary·enterprise-list）、专项（hall-detect）

### 均衡策略（balanced，默认）

即当前"正确性优先"策略，不改变现有行为。

- **核心接口**：直接使用，无需确认
- **扩展接口**：调用前告知用户将消耗积分，等待确认
- **附属接口**：仅当用户明确要求时使用
- **case-detail**：先展示摘要，由用户主动选择感兴趣的案例后再调用
- **补充检索**：不主动运行语义+关键词双检索，选择最合适的一种
- **积分报告**：每次检索后说明消耗和累计

### 省钱策略（economical）

在 balanced 基础上进一步收紧，最大限度减少积分消耗。

- **核心接口**：直接使用，但应先检查归档缓存是否有类似结果
- **扩展接口**：需用户二次确认（第一次只展示摘要和积分提醒，等用户再次确认后才调用）
- **附属接口**：仅当用户明确要求时使用，同样需确认
- **case-detail**：仅当用户指定具体案例编号时才调用，不主动提供"是否查看详情"选项
- **补充检索**：不运行补充检索，一次只用一种模式
- **积分报告**：每次检索后详细报告，并提醒可用的节约手段

### 激进策略（aggressive）

不考虑积分消耗，最大化检索精度和覆盖面。

- **所有接口**：直接使用，无需确认
- **case-detail**：自动获取最相关的 2-3 个案例的完整判决书，不需用户逐一选择
- **补充检索**：对同一问题同时运行语义+关键词双检索，合并去重后展示
- **积分报告**：简要说明消耗即可，不强调节约
- **额外行为**：法条检索后发现相关法规（如司法解释），主动追加 regulation 检索；用户需求模糊时，宁可多查也不漏查

### 接口策略速查

部分接口在通用规则之上有特殊行为约束（按积分成本或权限敏感度划分）：

| 接口 | 积分 | balanced | economical | aggressive |
|------|------|----------|-----------|------------|
| **hall-detect** | 50 | 用户明确要求时才使用，需确认"检测需要 50 积分" | 二次确认（第一次仅展示积分提醒，等用户再次确认才调用） | 可主动对用户引用的法条/案例做幻觉核验 |
| **enterprise-search** | 1 | 直接使用，无需确认 | 优先检查缓存，未命中时直接使用（仅 1 积分） | 直接使用 |
| **enterprise-base / enterprise-summary** | 10 | 用户明确要求时使用，告知积分消耗 | 需二次确认 | 直接使用 |
| **enterprise-list** | 5-10/次 | 用户指定类型时调用，提醒多种类型会累积积分 | 每次只查一种类型，展示全部可用类型让用户选择 | 企业尽调场景可一次性查询多个相关类型（如涉诉+行政处罚+失信） |

## 关键词扩展与典型工作流

AI 在执行检索前应主动扩展关键词（上位概念 / 并列概念 / 程序-实体关联），
并在多场景下遵循典型工作流与积分反馈原则。详见：

- [`references/01-keyword-expansion.md`](references/01-keyword-expansion.md) — 关键词扩展三原则、`--expand` 参数、分阶段检索示例、策略兼容性
- [`references/02-typical-workflows.md`](references/02-typical-workflows.md) — 法条 / 案例 / 关键词精确 / 企业尽调 / 幻觉检测 / 企业风险排查六大场景 + AI 向用户反馈的 8 条原则（含 per-call 报告落盘与禁止复制到目标目录的硬规则）

## 检索模式选择

每个领域有**语义检索**和**关键词检索**两种模式。

| | 语义检索 | 关键词检索 |
|---|---|---|
| **子命令** | `search`（法条）/ `case-semantic`（案例） | `keyword`（法条）/ `case`（案例） |
| **输入** | 自然语言问题或描述 | 精确关键词组合 |
| **匹配** | 语义相似度，概念关联 | 字面匹配，AND/OR 逻辑 |
| **返回量** | 默认 45 条 | 默认 10 条 |

**用语义检索**：用户提出法律问题 / 描述场景 / 不确定关键词 / 需要广覆盖 → 不确定时默认用
**用关键词检索**：用户给出明确关键词 / 需要 AND/OR 逻辑 / 需按日期、效力级别、法院等精确筛选 / 语义检索结果不够聚焦
**案例检索红线**：综合案件和类案对标的第一轮优先 `case-semantic`；`case` 只放 4-6 个高信息密度关键词，避免长事实结构默认 AND 导致零命中。

此外需区分检索法条还是案例："XX的法律依据" → 法条检索；"有没有相关案例" → 案例检索；兼要法条和案例 → 先法条后案例，两次调用。

## 核心接口用法

### 1. 法条语义检索（search）

```bash
scripts/yd-run search "正当防卫的限度" --sxx 现行有效
```

### 2. 法条关键词检索（keyword）

```bash
scripts/yd-run keyword "人工智能 监管" \
  --effect1 法律 --sxx 现行有效 \
  --fbrq-start 2022-01-01 --fbrq-end 2026-03-01
```

### 3. 法条详情检索（detail）

```bash
scripts/yd-run detail "民法典" --ft-name "第十五条"
```

### 4. 案例关键词检索（case）

```bash
# 普通案例（默认）
scripts/yd-run case "买卖合同纠纷" --province 广西

# 权威案例（扩展，需确认）
scripts/yd-run case "买卖合同纠纷" --province 广西 --authority-only
```

### 5. 案例语义检索（case-semantic）

```bash
scripts/yd-run case-semantic "正当防卫的限度" --jarq-start 2020-01-01
```

## 扩展接口用法

### 6. 法规关键词检索（regulation）

```bash
scripts/yd-run regulation "数据安全" --effect1 法律 --sxx 现行有效
```

### 7. 法规详情（regulation-detail）

```bash
scripts/yd-run regulation-detail --name "中华人民共和国数据安全法"
```

### 8. 案例详情（case-detail）

```bash
scripts/yd-run case-detail --type ptal --ah "（2025）桂09民终192号"
```

### 9. 企业检索（enterprise）

```bash
scripts/yd-run enterprise "华为" --num 5
```

### 10. 企业详情（enterprise-detail）

```bash
scripts/yd-run enterprise-detail --credit-code "9144030071526726XG"
```

## 幻觉检测

### 11. 法规/法条/案例幻觉检测（hall-detect）

检测文本中引用的法规、法条、案例是否存在幻觉（是否真实存在、内容是否准确）。**每次调用消耗 50 积分**。

```bash
scripts/yd-run hall-detect "根据《中华人民共和国数据保护法》第35条规定，数据处理者应当..."
```

返回结果包含：
- **法规检测**：每条法规是否真实存在（law_exists），语义比对结论和相似度
- **案例检测**：每条案例是否真实存在，基本事实和裁判要点
- **高亮文本**：标注了检测结果的原文本

## 企业全息画像

企业信息类接口（`enterprise-search` / `enterprise-base` / `enterprise-summary` / `enterprise-list`）的完整用法、`--type` 可选维度（涉诉、商标、专利、对外投资、股权冻结等 20 类）与积分消耗表见：

[`references/06-enterprise-portrait.md`](references/06-enterprise-portrait.md)

## 通用参数说明

### 法条检索通用筛选

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `--effect1` | 效力级别（可多次指定） | 宪法、法律、司法解释、行政法规、部门规章、地方性法规 等 |
| `--sxx` | 时效性（可多次指定） | 现行有效、失效、已被修改、部分失效、尚未生效 |
| `--keep-industry` | 保留默认剔除的办案无关条目 | 无需取值（flag） |

> **默认剔除办案无关条目**：`search` / `keyword` / `regulation` 默认过滤 `effect1 ∈ {行业/团体规范, 地方律协规定, 行政机关工作文件, 党内法规, 军事法规规章}` 的条目（律协指引、课题公告/答复函、党纪规定、军队规定等——非法律渊源或与一般民商事/刑事办案无关）。footer 提示剔除数量；涉党纪/涉军等特殊案件需要时加 `--keep-industry` 保留。`archive/` 原始数据仍完整，仅过滤显示与 `.md` 报告。

### 案例检索通用筛选

| 参数 | 说明 |
|------|------|
| `--province` / `--xzqh-p` | 省份筛选 |
| `--jarq-start / --jarq-end` | 结案日期范围 |
| `--cj` | 法院层级：最高/高级/中级/基层 |
| `--wenshu-type` | 案件类型：刑事案件/民事案件/行政案件 |

## Reference 文档索引

### 工作流指南

- [关键词扩展与分阶段检索](references/01-keyword-expansion.md)
- [典型工作流与用户引导](references/02-typical-workflows.md)
- [法律检索报告与目标目录归档](references/03-report-consolidation.md)
- [法律检索报告 7 节设计原理](references/04-report-design-notes.md)
- [MCP 协同工作流](references/05-mcp-workflow.md)
- [企业全息画像](references/06-enterprise-portrait.md)

### 接口清单与 API 端点文档

`endpoints/MANIFEST.json` 记录全部已适配接口的元数据（端点、子命令、分层、分类），以及平台接口排查历史。下次排查新增接口时，更新该文件的 `check_history` 即可。

| # | 文件 | 接口 |
|---|------|------|
| 01 | [law-vector-search.md](endpoints/01-law-vector-search.md) | 法条语义检索 |
| 02 | [law-keyword-search.md](endpoints/02-law-keyword-search.md) | 法条关键词检索 |
| 03 | [law-detail.md](endpoints/03-law-detail.md) | 法条详情 |
| 04 | [case-semantic-search.md](endpoints/04-case-semantic-search.md) | 案例语义检索 |
| 05 | [case-keyword-search.md](endpoints/05-case-keyword-search.md) | 普通案例关键词检索 |
| 06 | [case-keyword-search-authority.md](endpoints/06-case-keyword-search-authority.md) | 权威案例关键词检索 |
| 07 | [case-detail.md](endpoints/07-case-detail.md) | 案例详情 |
| 08 | [regulation-search.md](endpoints/08-regulation-search.md) | 法规关键词检索 |
| 09 | [regulation-detail.md](endpoints/09-regulation-detail.md) | 法规详情 |
| 10 | [enterprise-search.md](endpoints/10-enterprise-search.md) | 企业名称检索 |
| 11 | [enterprise-detail.md](endpoints/11-enterprise-detail.md) | 企业详情 |
| 12 | [hall-detect.md](endpoints/12-hall-detect.md) | 幻觉检测 |
| 13 | [enterprise-search-lightweight.md](endpoints/13-enterprise-search-lightweight.md) | 企业检索（轻量） |
| 14 | [enterprise-base-info.md](endpoints/14-enterprise-base-info.md) | 企业基本信息 |
| 15 | [enterprise-aggregation-summary.md](endpoints/15-enterprise-aggregation-summary.md) | 企业聚合总览 |
| 16 | [enterprise-out-invest.md](endpoints/16-enterprise-out-invest.md) | 对外投资 |
| 17 | [enterprise-brand.md](endpoints/17-enterprise-brand.md) | 商标 |
| 18 | [enterprise-patent.md](endpoints/18-enterprise-patent.md) | 专利 |
| 19 | [enterprise-soft-right.md](endpoints/19-enterprise-soft-right.md) | 软件著作权 |
| 20 | [enterprise-works-right.md](endpoints/20-enterprise-works-right.md) | 作品著作权 |
| 21 | [enterprise-icp.md](endpoints/21-enterprise-icp.md) | 网站备案 |
| 22 | [enterprise-change-info.md](endpoints/22-enterprise-change-info.md) | 变更记录 |
| 23 | [enterprise-writ-agg.md](endpoints/23-enterprise-writ-agg.md) | 涉诉信息统计 |
| 24 | [enterprise-writ-list.md](endpoints/24-enterprise-writ-list.md) | 涉诉文书 |
| 25 | [enterprise-court-session-notice.md](endpoints/25-enterprise-court-session-notice.md) | 开庭公告 |
| 26 | [enterprise-court-notice.md](endpoints/26-enterprise-court-notice.md) | 法院公告 |
| 27 | [enterprise-executions.md](endpoints/27-enterprise-executions.md) | 失信被执行人 |
| 28 | [enterprise-executed-person.md](endpoints/28-enterprise-executed-person.md) | 被执行人 |
| 29 | [enterprise-frozen-equity.md](endpoints/29-enterprise-frozen-equity.md) | 股权冻结 |
| 30 | [enterprise-punishment.md](endpoints/30-enterprise-punishment.md) | 行政处罚 |
| 31 | [enterprise-pledge.md](endpoints/31-enterprise-pledge.md) | 股权出质 |
| 32 | [enterprise-guaranty.md](endpoints/32-enterprise-guaranty.md) | 对外担保 |
| 33 | [enterprise-abnormal-operation.md](endpoints/33-enterprise-abnormal-operation.md) | 经营异常 |
| 34 | [enterprise-corporate-tax.md](endpoints/34-enterprise-corporate-tax.md) | 欠税公告 |
| 35 | [enterprise-serious-illegal.md](endpoints/35-enterprise-serious-illegal.md) | 严重违法 |

## 历史检索记录

每次 API 调用的完整结果会自动归档到 `archive/` 目录。当用户提到"之前查过什么"时，AI 可以直接从归档中提取历史结果，无需重新调用 API。

**按检索目的归类（`YD_PROJECT`）**：每个研究任务开始时，AI/用户设 `YD_PROJECT` 环境变量（如 `export YD_PROJECT=0713-商标在先使用权`，或行内 `YD_PROJECT=0713-商标案 scripts/yd-run search ...`），该任务的所有检索自动归到 `archive/<YD_PROJECT>/` 一个文件夹下，便于追溯。未设时按日期 `archive/YYYYMMDD/` 兜底，不再平铺根目录。**缓存查重全局生效**——同一问题在不同 project 下会命中已有归档，不重复消耗积分。

`archive/<project>/<ts>_<query>.json` 是机器可读版（response/query/fingerprint/source_urls 全字段），同名 `.md` 是人类可读版（结构化报告），两者一一对应。同一份报告的副本会同步写入用户运行命令时的工作目录（`<CWD>/<ts>_<query>.md`），便于附卷；当 CWD 恰为 skill 根目录时自动跳过（避免污染 skill 目录）。

浏览历史记录：

```bash
scripts/yd-run archive-list
scripts/yd-run archive-list --keyword "正当防卫"
```

如果用户说"之前查正当防卫的时候看到一个案例"，AI 应先用 `archive-list --keyword "正当防卫"` 找到对应的归档文件，然后直接读取其中的 `response` 字段返回给用户。这不需要消耗积分。

## 调试

```bash
scripts/yd-run raw /open/law_vector_search "正当防卫" --extra '{"fatiao_filter":{"sxx":["现行有效"]}}'
```

## 法律检索报告（consolidate）

多次检索之后，把 per-call 报告汇总成一份完整的法律检索报告。**这是律师/客户看的交付物**，per-call 报告是数据底稿。

### 7 节"结论先行"标准结构

**核心原则**：用户最想知道的是**最终结论**（能不能做、怎么做、风险在哪），法条和案例只是用来核实结论的支撑材料。所以结构应是 **结论先行 → 分析支撑 → 检索底稿垫后**。

模板文件位于 `templates/legal-research-report.md`；`scripts/yd-run consolidate` 会按同一结构自动生成报告。

1. **案情简介** — 当事人、争议焦点、当前阶段（最少必要）
2. **检索目的与问题** — 本次检索要回答的法律问题（1-3 个核心 Q）
3. **检索结论** ⭐ — **最先读到的内容**：
   - 3.1 一句话定性（"能做/不能做" + 法律依据）
   - 3.2 核心论点的判例支撑速查（用表格/列表，让用户 30 秒内 get 到）
   - 3.3 风险点（诚实告知，不要只说好的）
   - 3.4 后续行动（具体可执行的步骤）
4. **分析与判断** — 抗辩应对、法条适用、诉讼请求结构、赔偿酌定、证据准备
5. **检索思路与方法** — 关键词组合、筛选条件、检索顺序（备查）
6. **检索结果** — 按 endpoint 分组：6.1 法律依据 / 6.2 司法案例 / 6.3 行政法规 / 6.4 其他（核实材料）
7. **检索明细** — 表格，链接到每条 per-call 报告（末尾，使用可回溯本地链接）

### 检索报告质量要求

- **结论区必须能独立阅读**：3.1-3.4 应让律师、客户或法官先得到答案，再决定是否看底稿
- **核心依据用表格速查**：不要让读者从几十条法条/案例中自行拼结论
- **方法区保留检索痕迹**：写清关键词、筛选条件、平台、时间、纳入规则
- **结果区只放支撑材料**：法条、案例、法规按类型分组，不替代第四节分析
- **风险必须明示**：包括不利类案、法律适用分歧、地域差异、时效或证据缺口
- **无法确认的信息标注待补充**：不要把检索不到或材料未提及的事实写成确定结论

> **节号从 1 重新编号**（案情=1，结论=3，结果=6，明细=7），不沿用 1-6 顺序编号；体现"结论在第 3 节"的视觉位置。

**反例**（曾出现过的旧版结构）：
- 案情 → 目的 → 思路 → 检索结果 → 分析 → 结论
- 用户反馈：检索结果（法条案例）全是"核实材料"，要翻到最后才看到结论 → 太累
- 新版：结论放到第 3 节，用户看完 3.1-3.4 就能得到 80% 答案

末尾附"本次检索明细"表格，链接到每条 per-call 报告。

### 调用方式

```bash
scripts/yd-run consolidate \
    --title "张某买卖合同违约金调整" \
    --project "case-2024-zhangsan" \
    --case "案情：..." \
    --strategy "检索思路：..." \
    --analysis "分析与判断：..." \
    --conclusion "一句话结论：..." \
    --risks "主要风险：..." \
    --next-actions "后续行动：..." \
    --include "违约金,高空抛物"
```

- `--case` / `--strategy` / `--analysis` 必填：AI 显式传本次任务的案情/思路/判断
- `--include` 必填：逗号分隔的查询子串，明确指定"本次任务范围"（不取最近 N 条）
  - 匹配规则：CWD 中所有符合 `<8位时间戳>_<6位时间戳>_<查询>.md` 命名的 .md 文件，文件名包含任一子串即被纳入
- `--project` 可选：项目子目录名。默认从 `--title` slugify（如 "张某买卖合同违约金调整" → "张某买卖合同违约金调整"）。用于 `archive/<project>/` 归类
- `--title` / `--purpose` / `--conclusion` / `--risks` / `--next-actions` / `--output` 可选
  - `--purpose` 不传则基于检索词自动生成
  - `--conclusion` 强烈建议传入；不传会在 3.1 保留补写提示
  - `--risks` / `--next-actions` 不传会保留补写提示
  - `--output` 默认同时写 CWD 和 `archive/<project>/`；指定则只写到指定路径

### 项目子目录组织

consolidate 会把这次任务的所有文件归类到 `archive/<project>/` 子目录：

```
archive/
  case-2024-zhangsan/
    20260610_192031_货款逾期违约金_司法实践.json   ← 从 archive/ 根目录移入
    20260610_192031_货款逾期违约金_司法实践.md    ← 从 CWD 复制
    20260610_192032_逾期付款_违约金_调整.json
    20260610_192032_逾期付款_违约金_调整.md
    20260610_192058_法律检索报告.md                ← 主交付物
```

- **.md 复制**（CWD 保留工作副本）：用户的工作目录不被破坏
- **.json 移动**（archive 根目录已清理）：避免根目录重复积累，扁平区只放"in-flight 暂存"
- 重复运行 consolidate 同一项目：idempotent，文件已在子目录则跳过

### 与 per-call 报告的关系

```
多次 yd-run 检索（自动写 per-call .md 到 archive + CWD）
       ↓
AI 汇总判断后调 consolidate --project "case-x"
       ↓
创建 archive/case-x/，.md 复制进来，.json 移进来，法律检索报告写进去
       ↓
CWD 也有法律检索报告副本，per-call .md 仍在 CWD（工作副本）
       ↓
报告末尾的"检索明细表"链接回 archive/case-x/ 里的副本
```

per-call .md 是数据底稿，可独立查看；session 报告是主交付物，附案情/思路/判断；项目子目录是组织容器。

## 目标目录归档规范（强制）

目标目录（通常是案件文件夹 `02 - 案件分析` / `03 - 法律研究` 等）与 AI 进程的 CWD 是不同的两个位置。
目标目录只允许出现：整合后的法律检索报告 + 外部素材 + 基于整合报告再生成的下游文件；
**禁止** per-call 检索记录、检索明细 JSON、AI 进程 CWD 的工作副本。

完整规则（标准工作流 4 步、反例、验证清单 4 条）见：

[`references/03-report-consolidation.md`](references/03-report-consolidation.md#目标目录归档规范强制)

## MCP 协同工作流（v1.6.0+）

元典官方 MCP（https://open.chineselaw.com/mcp-config）已发布，3 个 servers：yuandian-law（法律法规）、yuandian-case（案例文书）、yuandian-company（企业信息）。本 skill 的价值现在转向"**归档 + 法律检索报告生成**"——数据接入由 MCP 负责，本 skill 负责沉淀。

完整工作流（元典 MCP 接入配置、Agent 三步法、ingest 子命令、模式选型表）见：

[`references/05-mcp-workflow.md`](references/05-mcp-workflow.md)

## 版本更新

脚本每 7 天自动检测远程版本。也可手动检查：

```bash
# 检查是否有新版本（会显示最近提交记录）
scripts/yd-run check-update

# 执行更新（仅下载本 skill 目录下的文件，不影响其他目录）
scripts/yd-run do-update
```

`do-update` 仅更新 `yuandian-law-search/` 目录下的文件，不会修改 `.env`（API Key）和 `archive/`（历史检索记录）。
