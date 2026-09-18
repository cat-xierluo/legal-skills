---
name: yuandian-law-search
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.9.1"
license: MIT
description: 元典涵摄式法律研究中间层。本技能应在查询中国法律法规或案例，或根据案件事实、争议焦点、既有法律分析报告制定检索策略、查找正反类案、形成精选依据或可追溯报告时使用；先做要件涵摄与检索缺口分析，再按向量、关键词和结构化字段调用元典 API/MCP，并由 Agent 逐条精选。不要用于替代完整证据审查、诉讼方案或正式法律意见。
---

# 元典法条与案例检索

先用“涵摄—假设检验”模型把案件事实和诉讼立场转换为法律要件、事实映射、正反命题与检索缺口，再按元典开放平台的向量、关键词和结构化过滤机制调用 API 或 MCP。完整响应只是候选池；Agent 逐条复核形成精选依据，默认在对话中交付，用户明确要求时才生成正式报告。**每次 API 调用消耗 1-50 积分**（视接口而定）。

## 数据留存与隐私警示

本技能在提供便利的同时会产生本地留存与外部传输，使用前请知悉：

- **本地归档**：每次检索的原始响应与 per-call 结构化底稿会自动写入 `archive/`（按 `YD_PROJECT` 或日期归类），并默认在运行命令的工作目录生成一份 `.md` 工作副本（供 Agent 复核，不是正式交付；当工作目录恰为 skill 根目录时自动跳过）。`--no-report` 仅跳过 `.md` 报告（archive 与工作目录两份），**仍会写 archive JSON**；`--no-cwd-report` 仅跳过工作目录副本；`--no-archive` 才会关闭全部本地留存（JSON 与 `.md` 都不写，查重仍读已有归档，命中即免请求——但新查询不再入缓存，下次同查询可能重复消耗积分）；`--archive-dir`（或环境变量 `YD_ARCHIVE_DIR`）可指定归档目录。归档写入失败（如目录不可写）只降级为 stderr 告警，**不会吞掉已取得的响应、不会自动重试**。这些文件可能包含案由、当事人、裁判文书正文等敏感内容，**请勿将其提交至公开仓库、复制进案件交付目录或随意分享**。
- **外部传输**：检索请求与（如幻觉检测）待查文本会发送至元典开放平台 `open.chineselaw.com`。提交给 `hall-detect` 等接口的文本可能包含案卷事实、合同或客户信息，**建议先脱敏再提交**。平台侧的留存策略以其服务条款为准。
- **敏感内容最小化**：案例文书、企业信息含个人或商业敏感数据，引用与归档时遵循"最小必要"原则，避免大段全文外泄。

## 所需权限

本技能运行需要以下本地能力，均限定在检索与归档目的内：

- **网络访问**：检索请求仅发送到 `open.chineselaw.com`（HTTPS）；`--network-check` 还会对 `ydzk.chineselaw.com` 做 DNS/TLS 连通性检查，不发送案件内容。
- **文件系统读写**：可读取 `scripts/.env`（API Key）；写入 `archive/`（可用 `--archive-dir`/`YD_ARCHIVE_DIR` 重定向）与当前工作目录的报告副本（`.md` 副本可经 `--no-report`/`--no-cwd-report` 跳过；全部留存经 `--no-archive` 关闭）。
- **环境变量**：读取 `YD_API_KEY`（鉴权）、`YD_STRATEGY`/`YD_PROJECT`（检索策略与归类）等；`yd-run` 以干净环境启动 Python，仅保留必要变量。
- **本地代码执行**：通过 `scripts/yd-run` 调用 Python 检索脚本；不安装第三方运行时、不执行自动更新。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|---|---|
| Python 3 | macOS：`brew install python`<br>Linux：`sudo apt-get install python3` |

无需安装第三方 Python 包。

## 前置要求（实际调用元典前自动检测）

执行元典 API 请求前，**必须先执行以下检测流程**，确认 API Key 已就绪。仅做轻量案件研判、生成/校验查询计划、查看本地归档或整理既有 MCP 输出时，不要求 API Key；密钥缺失不得阻止交付无 API 检索方案。

### 检测步骤

1. **检测 API Key 来源**：优先检查当前环境的 `YD_API_KEY`；未设置时再检查 `scripts/.env`
2. **检测 API Key**：确认值非空且不是占位符 `your-api-key-here`
3. **若检测失败**，停止外部 API 调用，保留已经完成的检索方案，并向用户提示：

```
⚠️ 元典 API Key 未配置。请按以下步骤获取并配置：

1. 注册/登录：访问 https://open.chineselaw.com ，使用手机号注册
2. 创建 API Key：登录后在个人中心创建 Key
3. 配置密钥：将 Key 填入以下文件

   scripts/.env
   ─────────────
   YD_API_KEY=sk-你的密钥(此处替换为真实 Key)
   # YD_STRATEGY=balanced
   ─────────────

调用按接口消耗 1-50 积分，需在平台充值。
配置完成后重新发起检索即可。
```

4. **若检测通过**，继续执行用户请求的检索命令

### 检测命令

```bash
# 检测环境变量或 .env，不输出密钥内容
if [ -n "${YD_API_KEY:-}" ]; then
  echo "API Key 已就绪（环境变量）"
elif [ -f "scripts/.env" ] && \
     grep -qE '^YD_API_KEY=.+$' scripts/.env && \
     ! grep -q '^YD_API_KEY=your-api-key-here$' scripts/.env; then
  echo "API Key 已就绪（scripts/.env）"
else
  echo "API Key 未配置"
fi

# 读取检索策略
STRATEGY=$(grep '^YD_STRATEGY=' scripts/.env 2>/dev/null | cut -d'=' -f2)
echo "当前策略：${STRATEGY:-balanced}"
```

## 网络环境与推荐调用入口

默认使用 `scripts/yd-run` 执行检索，而不是直接调用底层 `yd_search.py`。`yd-run` 会以干净环境启动 Python：清除 Codex/代理相关环境变量，保留必要系统变量及 `YD_API_KEY`、`YD_STRATEGY`、`YD_PROJECT`，并继续读取 `scripts/.env` 和 `archive/` 缓存。

```bash
scripts/yd-run search "正当防卫的限度" --sxx 现行有效
```

若遇到 `nodename nor servname provided, or not known` 或其他网络错误，先执行无积分消耗的网络检查：

```bash
scripts/yd-run --network-check
```

注意：`yd-run` 只能避免进程环境变量、代理变量和 PATH 漂移造成的影响；若运行环境本身禁网，或系统代理/VPN 接管 DNS，仍需在用户已授权的联网环境中执行。

## 检索机制感知主流程（案件检索默认）

当用户描述事实结构、争议焦点、诉讼立场，或问"类似案件怎么判""能不能主张 XX""对方抗辩怎么办"时，**先完成案件检索主流程，再调用接口**（DEC-006）。简单法条/案号/纯概念检索（`detail` / `case-detail` / 单条 `search`）不启动本流程，直接看下方接口速查。

1. **形成检索简报** → 明确请求／抗辩路径、争点、决定性事实、待补事实和必须排除的近邻案型。
2. **建立涵摄矩阵** → 为每个争点拆出候选大前提、法律要件／例外／后果、法律化事实、证明状态和暂定涵摄；区分法律检索缺口与事实／证据缺口。
3. **派生正反命题与查询** → 只有 `legal_research` 缺口才能生成 query；每个决定性争点至少 1 条支持命题 + 1 条反向命题，一查询只承载一个缺口。
4. **小样本试检** → 先用少量候选验证接口与表达；向量接口负责发现，关键词、结构化字段和详情接口负责复检／核验。
5. **对位复核与策略修正** → Agent 按 HIGH / MEDIUM / LOW / MISMATCH 审查主体、请求权基础、行为链条和决定性事实；后端分数不替代法律相关性。
6. **形成精选来源** → 仅将 HIGH/MEDIUM、已核验、已映射命题且说明本案适用理由的材料写入 `selected-sources.json`；核心依据必须为 HIGH，正式报告最多 12 条，完整召回只归档。
7. **按需交付** → 默认在对话中给结论与少量精选依据；用户明确要求正式报告或落盘时，才由 `consolidate` 消费精选清单。

信息不足时按"最小必要"补问（最多 1 轮，只问会改变检索路径的最关键问题），不空跑查询；事实不足但不影响查询方向的，标注假设继续。

完整涵摄矩阵、接口路由、近邻排除和 research plan 合同见 [`references/07-research-middleware.md`](references/07-research-middleware.md)；精选来源、输出模式和报告门禁见 [`references/08-selected-sources-delivery.md`](references/08-selected-sources-delivery.md)。

案件检索形成机器可读 `research-plan.json` 后，**必须先过统一合同门禁再调用 API/MCP**：

```bash
scripts/validate-research-contract.py --plan research-plan.json
```

正式报告前还必须运行：

```bash
scripts/validate-research-contract.py \
  --plan research-plan.json \
  --selection selected-sources.json
```

退出码非 0 时停止调用或报告生成。门禁检查涵摄缺口、命题／查询映射、真实 CLI 字段归属和精选来源合同；它不根据关键词替 Agent 判断实体法律相关性。

> 下方「接口速查」是执行第 3 步查询矩阵时"按机制选接口"的依据，不是检索的起点。

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

读取 `scripts/.env` 中的 `YD_STRATEGY` 配置（默认 `balanced`）。三种策略只决定调用预算、确认流程和检索深度，不得改变案件争点、正反命题、近邻排除或接口字段适配原则。

**用户的明确指令始终优先于策略默认行为。**

### 通用规则（所有策略共享）

每次 API 调用消耗 1-50 积分（视接口而定）。以下规则不受策略影响：

1. **必须调用 API**：需要引用具体法条文号 / 需要确认时效性 / 用户明确要求检索 / 案例检索 / AI 对自身记忆不确定
2. **可以不调用**：纯概念性问题 / 对话中已检索过相同内容 / 用户未要求查找 / 用户明确说不需要查
3. **积分消耗模式**：大部分接口每次 5-10 积分，幻觉检测 50 积分，轻量企业检索 1 积分。法条检索通常一次足够。案例检索是两阶段消耗（摘要 10 + 详情 每个 10）
4. **接口分层**：核心（search·keyword·detail·case·case-semantic）、扩展（regulation·regulation-detail·case-detail·case --authority-only）、附属（enterprise·enterprise-detail·enterprise-search·enterprise-base·enterprise-summary·enterprise-list）、专项（hall-detect）
5. **正反命题不因省钱省略**：每个决定性争点仍须保留支持与反向路径；成本策略只调节每条路径的首次调用数量和是否自动加深

### 均衡策略（balanced，默认）

正确性优先，同时控制重复调用。

- **核心接口**：直接使用，无需确认
- **扩展接口**：调用前告知用户将消耗积分，等待确认
- **附属接口**：仅当用户明确要求时使用
- **case-detail**：先展示摘要，由用户主动选择感兴趣的案例后再调用
- **补充检索**：同一命题首轮只选最合适的一种模式；若对位复核诊断出零命中、低对位或接口误选，再按 `fallback_path` 换表达或接口
- **积分报告**：每次检索后说明消耗和累计

### 省钱策略（economical）

在 balanced 基础上进一步收紧，最大限度减少积分消耗。

- **核心接口**：直接使用，但应先检查归档缓存是否有类似结果
- **扩展接口**：需用户二次确认（第一次只展示摘要和积分提醒，等用户再次确认后才调用）
- **附属接口**：仅当用户明确要求时使用，同样需确认
- **case-detail**：仅当用户指定具体案例编号时才调用，不主动提供"是否查看详情"选项
- **补充检索**：每个正反命题先执行最小查询集、一次只用一种模式；零命中或低对位时仍执行一次有诊断依据的降级路径，不得直接宣称“无相关法条/类案”
- **积分报告**：每次检索后详细报告，并提醒可用的节约手段

### 激进策略（aggressive）

在已确定争点和授权范围内不限制普通检索积分，最大化精度和覆盖面；仍遵守隐私、明确范围和检索前门禁。

- **普通检索接口**：查询矩阵通过门禁后直接使用；`hall-detect` 涉及待查文本外传，仍须用户明确要求
- **case-detail**：自动获取最相关的 2-3 个案例的完整判决书，不需用户逐一选择
- **补充检索**：对同一命题同时运行语义+关键词双检索，候选合并去重后仍由 Agent 逐条精选，不因调用更多而扩大正文
- **积分报告**：简要说明消耗即可，不强调节约
- **额外行为**：法条检索后发现与当前命题直接相关的法规（如司法解释），可追加 regulation 检索；歧义会改变检索路径时仍先做一轮最小必要补问，不用宽泛检索代替争点确认

### 接口策略速查

部分接口在通用规则之上有特殊行为约束（按积分成本或权限敏感度划分）：

| 接口 | 积分 | balanced | economical | aggressive |
|------|------|----------|-----------|------------|
| **hall-detect** | 50 | 用户明确要求时才使用，需确认"检测需要 50 积分" | 二次确认（第一次仅展示积分提醒，等用户再次确认才调用） | 仍须用户明确要求；可免二次确认，但先提示 50 积分和待查文本将外传 |
| **enterprise-search** | 1 | 直接使用，无需确认 | 优先检查缓存，未命中时直接使用（仅 1 积分） | 直接使用 |
| **enterprise-base / enterprise-summary** | 10 | 用户明确要求时使用，告知积分消耗 | 需二次确认 | 直接使用 |
| **enterprise-list** | 5-10/次 | 用户指定类型时调用，提醒多种类型会累积积分 | 每次只查一种类型，展示全部可用类型让用户选择 | 企业尽调场景可一次性查询多个相关类型（如涉诉+行政处罚+失信） |

## 关键词扩展与典型工作流

先从检索命题提取稳定字面词。简单法条检索可按上位、并列或程序—实体关系扩展；案件检索的 `--expand` 只在首轮零命中或低对位、且已诊断为字面覆盖不足时使用，不作为默认广撒网。详见：

- [`references/01-keyword-expansion.md`](references/01-keyword-expansion.md) — 关键词扩展三原则、`--expand` 参数、分阶段检索示例、策略兼容性
- [`references/02-typical-workflows.md`](references/02-typical-workflows.md) — 法条 / 案例 / 关键词精确 / 企业尽调 / 幻觉检测 / 企业风险排查六大场景 + AI 向用户反馈的 8 条原则（含 per-call 报告落盘与禁止复制到目标目录的硬规则）

## 检索模式选择

每个领域有**语义检索**和**关键词检索**两种模式。

| | 语义检索 | 关键词检索 |
|---|---|---|
| **子命令** | `search`（法条）/ `case-semantic`（案例） | `keyword`（法条）/ `case`（案例） |
| **输入** | 自然语言问题或描述 | 精确关键词组合 |
| **匹配** | 语义相似度，概念关联 | 字面匹配，AND/OR 逻辑 |
| **返回量** | economical 8 / balanced 12 / aggressive 20 条候选 | 通常 10 条；aggressive 可到 20 条候选 |

**用语义检索**：需要发现未知规范、裁判用语或事实结构类案 → 作为候选发现入口，不把召回量等同于交付量
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
- [检索机制感知型中间层执行合同](references/07-research-middleware.md)
- [Agent 精选来源与交付门禁](references/08-selected-sources-delivery.md)

### 接口清单与 API 端点文档

`endpoints/MANIFEST.json` 是全部 35 个已适配接口的权威索引，记录端点、子命令、分层、分类和平台排查历史；详细请求字段与响应结构见同目录 `01-35-*.md`。日常法律检索优先读取 `01-09`，企业与专项接口按需读取 `10-35`。

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

原始端点调试使用 `scripts/yd-run raw /open/law_vector_search "正当防卫" --extra '{"fatiao_filter":{"sxx":["现行有效"]}}'`。维护脚本或字段映射后运行 `python3 scripts/verify-runtime-contracts.py`，无网络检查 CLI→payload 映射与查询门禁。

## 法律检索报告（consolidate）

`consolidate` 只在用户明确要求正式报告或落盘时使用。它必须读取已经通过校验的 `research-plan.json` 与 Agent 生成的 `selected-sources.json`；缺失、空清单、超过 12 条、未核验、无命题映射、`LOW/MISMATCH` 或决定性命题无去向时失败关闭。

报告保持 7 节结论先行结构，但第六节只渲染精选来源：规范性法源按核心／补充和法律位阶排序，案例单独分组。完整 MCP/API 响应与 per-call 报告只归档并在第七节列调用轨迹，不复制正文。

```bash
scripts/yd-run consolidate \
  --title "案件主题" \
  --project "case-project" \
  --case "案情：..." \
  --strategy "涵摄缺口、查询路由和复检过程：..." \
  --analysis "结合精选依据完成的分析：..." \
  --conclusion "附条件的一句话结论：..." \
  --research-plan research-plan.json \
  --selection selected-sources.json \
  --include "可选：仅归档／列示的原始查询子串"
```

正式报告工作流、项目包、输出结构和失败条件见 [`references/03-report-consolidation.md`](references/03-report-consolidation.md)；精选清单 schema 与逐条复核规则见 [`references/08-selected-sources-delivery.md`](references/08-selected-sources-delivery.md)。

## 目标目录归档规范（强制）

目标目录（通常是案件文件夹 `02 - 案件分析` / `03 - 法律研究` 等）与 AI 进程的 CWD 是不同的两个位置。
目标目录只允许出现：正式法律检索报告 + 外部素材 + 用户明确要求交接的精选研究包 + 基于报告再生成的下游文件；
**禁止** per-call 检索记录、检索明细 JSON、AI 进程 CWD 的工作副本。

完整规则见：

[`references/03-report-consolidation.md`](references/03-report-consolidation.md#目标目录归档规范强制)

## MCP 协同工作流（v1.6.0+）

元典官方 MCP（https://open.chineselaw.com/mcp-config）已发布，3 个 servers：yuandian-law（法律法规）、yuandian-case（案例文书）、yuandian-company（企业信息）。MCP 只替换数据接入层，具体工具仍分别对应向量、关键词、结构化字段和详情机制。本 Skill 在调用前完成涵摄式研究计划，在调用后完成 Agent 精选；MCP 返回不能直接成为正式报告正文。

完整工作流（元典 MCP 接入配置、五步法、ingest 归档和精选门禁）见：

[`references/05-mcp-workflow.md`](references/05-mcp-workflow.md)
