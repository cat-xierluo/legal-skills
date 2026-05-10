---
name: yuandian-law-search
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.3.0"
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

## 接口速查

本技能共 35 个接口，分为四层。选择规则：

1. 用户问"XX法怎么规定的" → 先用 `search` 语义检索
2. 用户问"关于XX的法律条文" → 用 `keyword` 关键词检索
3. 用户问"民法典第XX条" → 用 `detail` 精确获取
4. 用户问"有没有XX相关的案例" → 用 `case` 关键词检索（默认普通案例）
5. 用户问"类似XX的案件怎么判的" → 用 `case-semantic` 语义检索
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

## 典型工作流与用户引导

AI 在完成检索后，应**主动告知用户检索结果摘要和积分消耗**，并根据场景推荐后续操作。

### 法条研究场景

用户问："正当防卫在什么情况下会超过必要限度？"

1. AI 进行法条语义检索（10 积分）
2. 向用户展示关键法条内容（如刑法第20条、民法典总则编司法解释第31条等）
3. 告知用户积分消耗："本次检索消耗 10 积分"
4. 主动推荐后续操作："如果需要了解相关判例，我可以帮你找案例"

### 案例研究场景

用户问："有没有防卫过当的实际案例？"

1. AI 进行案例语义检索（10 积分）
2. 案例语义检索返回的摘要已包含争议焦点和裁判要旨，大多数情况下已够用
3. 向用户展示案例摘要，告知积分消耗
4. **case-detail 的触发取决于策略**：
   - **balanced / economical**：等待用户主动触发。如用户对某个案例感兴趣，可说"帮我看看第2个案例的完整判决书"——此时再调 case-detail（每个 10 积分）
   - **aggressive**：AI 自动获取最相关的 2-3 个案例详情，无需用户指令

### 关键词精确检索场景

用户问："帮我找广西的买卖合同纠纷判决书"

1. AI 进行案例关键词检索（10 积分）
2. 关键词检索返回的摘要较短，仅含基本信息（案号、法院、简要内容）
3. 向用户展示结果列表和积分消耗
4. 等待用户选择：如用户对某个案例感兴趣，再获取完整判决书（每个 10 积分）

> **策略提示**：aggressive 模式下，AI 会自动对结果中最相关的 2-3 个案例调用 case-detail，无需等待用户指令。

### AI 向用户反馈的原则

1. **每次检索后主动说明积分消耗**："本次检索消耗 10 积分"
2. **多步检索时告知累计消耗**："本次检索消耗 10 积分（本次对话累计 30 积分）"
3. **完整判决书的触发取决于策略**：balanced/economical 由用户主动触发；aggressive 由 AI 自动获取最相关的 2-3 个
4. **案例语义检索的摘要通常已够用**：只有用户明确要求查看完整判决书时才深入（aggressive 除外）
5. **法条语义检索已含全文**：不需要额外补充
6. **用自然语言与用户沟通**：不要向用户暴露命令行语法，AI 后台执行脚本即可
7. **补充检索取决于策略**：balanced/economical 一次只用一种检索模式；aggressive 对重要问题自动同时运行语义+关键词检索，合并去重

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

此外需区分检索法条还是案例："XX的法律依据" → 法条检索；"有没有相关案例" → 案例检索；兼要法条和案例 → 先法条后案例，两次调用。

## 核心接口用法

### 1. 法条语义检索（search）

```bash
python3 scripts/yd_search.py search "正当防卫的限度" --sxx 现行有效
```

### 2. 法条关键词检索（keyword）

```bash
python3 scripts/yd_search.py keyword "人工智能 监管" \
  --effect1 法律 --sxx 现行有效 \
  --fbrq-start 2022-01-01 --fbrq-end 2026-03-01
```

### 3. 法条详情检索（detail）

```bash
python3 scripts/yd_search.py detail "民法典" --ft-name "第十五条"
```

### 4. 案例关键词检索（case）

```bash
# 普通案例（默认）
python3 scripts/yd_search.py case "买卖合同纠纷" --province 广西

# 权威案例（扩展，需确认）
python3 scripts/yd_search.py case "买卖合同纠纷" --province 广西 --authority-only
```

### 5. 案例语义检索（case-semantic）

```bash
python3 scripts/yd_search.py case-semantic "正当防卫的限度" --jarq-start 2020-01-01
```

## 扩展接口用法

### 6. 法规关键词检索（regulation）

```bash
python3 scripts/yd_search.py regulation "数据安全" --effect1 法律 --sxx 现行有效
```

### 7. 法规详情（regulation-detail）

```bash
python3 scripts/yd_search.py regulation-detail --name "中华人民共和国数据安全法"
```

### 8. 案例详情（case-detail）

```bash
python3 scripts/yd_search.py case-detail --type ptal --ah "（2025）桂09民终192号"
```

### 9. 企业检索（enterprise）

```bash
python3 scripts/yd_search.py enterprise "华为" --num 5
```

### 10. 企业详情（enterprise-detail）

```bash
python3 scripts/yd_search.py enterprise-detail --credit-code "9144030071526726XG"
```

## 幻觉检测

### 11. 法规/法条/案例幻觉检测（hall-detect）

检测文本中引用的法规、法条、案例是否存在幻觉（是否真实存在、内容是否准确）。**每次调用消耗 50 积分**。

```bash
python3 scripts/yd_search.py hall-detect "根据《中华人民共和国数据保护法》第35条规定，数据处理者应当..."
```

返回结果包含：
- **法规检测**：每条法规是否真实存在（law_exists），语义比对结论和相似度
- **案例检测**：每条案例是否真实存在，基本事实和裁判要点
- **高亮文本**：标注了检测结果的原文本

## 企业全息画像

### 12. 企业检索（轻量候选列表，enterprise-search）

**每次调用消耗 1 积分**。按名称检索企业，返回候选列表（仅含 ID、名称、信用代码），用于定位目标企业后调用其他企业接口。

```bash
python3 scripts/yd_search.py enterprise-search "华为" --top-k 5
```

### 13. 企业基本信息（enterprise-base）

根据企业 ID 或统一社会信用代码获取企业完整信息（含股东、核心成员、分支机构等）。

```bash
python3 scripts/yd_search.py enterprise-base --uscc "9144030071526726XG"
```

### 14. 企业聚合总览（enterprise-summary）

一次调用获取企业各维度数据的统计摘要。

```bash
python3 scripts/yd_search.py enterprise-summary --id "企业ID"
```

### 15. 企业分项列表（enterprise-list）

查询企业各维度详细记录，支持分页。**每次调用消耗 5-10 积分**（涉诉统计和涉诉文书 10 积分，其余 5 积分）。

```bash
# 查询企业涉诉文书
python3 scripts/yd_search.py enterprise-list --type writ-list --uscc "9144030071526726XG"

# 查询企业对外投资
python3 scripts/yd_search.py enterprise-list --type invest --uscc "9144030071526726XG" --page 1 --size 10

# 查询企业商标
python3 scripts/yd_search.py enterprise-list --type brand --uscc "9144030071526726XG"
```

#### 可用类型

| TYPE | 名称 | 积分 |
|------|------|------|
| invest | 对外投资 | 5 |
| brand | 商标 | 5 |
| patent | 专利 | 5 |
| soft-right | 软件著作权 | 5 |
| works-right | 作品著作权 | 5 |
| icp | 网站备案 | 5 |
| change-info | 变更记录 | 5 |
| writ-agg | 涉诉信息统计 | 10 |
| writ-list | 涉诉文书 | 10 |
| court-session | 开庭公告 | 5 |
| court-notice | 法院公告 | 5 |
| execution | 失信被执行人 | 5 |
| executed-person | 被执行人 | 5 |
| frozen-equity | 股权冻结 | 5 |
| punishment | 行政处罚 | 5 |
| pledge | 股权出质 | 5 |
| guaranty | 对外担保 | 5 |
| abnormal | 经营异常 | 5 |
| tax | 欠税公告 | 5 |
| serious-illegal | 严重违法 | 5 |

## 通用参数说明

### 法条检索通用筛选

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `--effect1` | 效力级别（可多次指定） | 宪法、法律、司法解释、行政法规、部门规章、地方性法规 等 |
| `--sxx` | 时效性（可多次指定） | 现行有效、失效、已被修改、部分失效、尚未生效 |

### 案例检索通用筛选

| 参数 | 说明 |
|------|------|
| `--province` / `--xzqh-p` | 省份筛选 |
| `--jarq-start / --jarq-end` | 结案日期范围 |
| `--cj` | 法院层级：最高/高级/中级/基层 |
| `--wenshu-type` | 案件类型：刑事案件/民事案件/行政案件 |

## Reference 文档索引

### 接口清单

`references/MANIFEST.json` 记录全部已适配接口的元数据（端点、子命令、分层、分类），以及平台接口排查历史。下次排查新增接口时，更新该文件的 `check_history` 即可。

### API 端点文档

| # | 文件 | 接口 |
|---|------|------|
| 01 | [law-vector-search.md](references/01-law-vector-search.md) | 法条语义检索 |
| 02 | [law-keyword-search.md](references/02-law-keyword-search.md) | 法条关键词检索 |
| 03 | [law-detail.md](references/03-law-detail.md) | 法条详情 |
| 04 | [case-semantic-search.md](references/04-case-semantic-search.md) | 案例语义检索 |
| 05 | [case-keyword-search.md](references/05-case-keyword-search.md) | 普通案例关键词检索 |
| 06 | [case-keyword-search-authority.md](references/06-case-keyword-search-authority.md) | 权威案例关键词检索 |
| 07 | [case-detail.md](references/07-case-detail.md) | 案例详情 |
| 08 | [regulation-search.md](references/08-regulation-search.md) | 法规关键词检索 |
| 09 | [regulation-detail.md](references/09-regulation-detail.md) | 法规详情 |
| 10 | [enterprise-search.md](references/10-enterprise-search.md) | 企业名称检索 |
| 11 | [enterprise-detail.md](references/11-enterprise-detail.md) | 企业详情 |
| 12 | [hall-detect.md](references/12-hall-detect.md) | 幻觉检测 |
| 13 | [enterprise-search-lightweight.md](references/13-enterprise-search-lightweight.md) | 企业检索（轻量） |
| 14 | [enterprise-base-info.md](references/14-enterprise-base-info.md) | 企业基本信息 |
| 15 | [enterprise-aggregation-summary.md](references/15-enterprise-aggregation-summary.md) | 企业聚合总览 |
| 16 | [enterprise-out-invest.md](references/16-enterprise-out-invest.md) | 对外投资 |
| 17 | [enterprise-brand.md](references/17-enterprise-brand.md) | 商标 |
| 18 | [enterprise-patent.md](references/18-enterprise-patent.md) | 专利 |
| 19 | [enterprise-soft-right.md](references/19-enterprise-soft-right.md) | 软件著作权 |
| 20 | [enterprise-works-right.md](references/20-enterprise-works-right.md) | 作品著作权 |
| 21 | [enterprise-icp.md](references/21-enterprise-icp.md) | 网站备案 |
| 22 | [enterprise-change-info.md](references/22-enterprise-change-info.md) | 变更记录 |
| 23 | [enterprise-writ-agg.md](references/23-enterprise-writ-agg.md) | 涉诉信息统计 |
| 24 | [enterprise-writ-list.md](references/24-enterprise-writ-list.md) | 涉诉文书 |
| 25 | [enterprise-court-session-notice.md](references/25-enterprise-court-session-notice.md) | 开庭公告 |
| 26 | [enterprise-court-notice.md](references/26-enterprise-court-notice.md) | 法院公告 |
| 27 | [enterprise-executions.md](references/27-enterprise-executions.md) | 失信被执行人 |
| 28 | [enterprise-executed-person.md](references/28-enterprise-executed-person.md) | 被执行人 |
| 29 | [enterprise-frozen-equity.md](references/29-enterprise-frozen-equity.md) | 股权冻结 |
| 30 | [enterprise-punishment.md](references/30-enterprise-punishment.md) | 行政处罚 |
| 31 | [enterprise-pledge.md](references/31-enterprise-pledge.md) | 股权出质 |
| 32 | [enterprise-guaranty.md](references/32-enterprise-guaranty.md) | 对外担保 |
| 33 | [enterprise-abnormal-operation.md](references/33-enterprise-abnormal-operation.md) | 经营异常 |
| 34 | [enterprise-corporate-tax.md](references/34-enterprise-corporate-tax.md) | 欠税公告 |
| 35 | [enterprise-serious-illegal.md](references/35-enterprise-serious-illegal.md) | 严重违法 |

## 历史检索记录

每次 API 调用的完整结果会自动归档到 `archive/` 目录。当用户提到"之前查过什么"时，AI 可以直接从归档中提取历史结果，无需重新调用 API。

浏览历史记录：

```bash
python3 scripts/yd_search.py archive-list
python3 scripts/yd_search.py archive-list --keyword "正当防卫"
```

如果用户说"之前查正当防卫的时候看到一个案例"，AI 应先用 `archive-list --keyword "正当防卫"` 找到对应的归档文件，然后直接读取其中的 `response` 字段返回给用户。这不需要消耗积分。

## 调试

```bash
python3 scripts/yd_search.py raw /open/law_vector_search "正当防卫" --extra '{"fatiao_filter":{"sxx":["现行有效"]}}'
```

## 版本更新

脚本每 7 天自动检测远程版本。也可手动检查：

```bash
# 检查是否有新版本（会显示最近提交记录）
python3 scripts/yd_search.py check-update

# 执行更新（仅下载本 skill 目录下的文件，不影响其他目录）
python3 scripts/yd_search.py do-update
```

`do-update` 仅更新 `yuandian-law-search/` 目录下的文件，不会修改 `.env`（API Key）和 `archive/`（历史检索记录）。
