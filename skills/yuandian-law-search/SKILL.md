---
name: yuandian-law-search
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: "1.1.1"
license: MIT
description: 元典法条与案例检索。本技能应在需要查询中国法律法规条文、检索相关案例、为法律分析提供数据支撑时使用。
---

# 元典法条与案例检索

通过元典开放平台 API 检索中国法律法规条文和案例。**每次 API 调用消耗 10 积分**。所有检索结果会自动归档到本地，方便后续回溯。

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
```

## 接口速查

本技能共 11 个接口，分为三层。选择规则：

1. 用户问"XX法怎么规定的" → 先用 `search` 语义检索
2. 用户问"关于XX的法律条文" → 用 `keyword` 关键词检索
3. 用户问"民法典第XX条" → 用 `detail` 精确获取
4. 用户问"有没有XX相关的案例" → 用 `case` 关键词检索（默认普通案例）
5. 用户问"类似XX的案件怎么判的" → 用 `case-semantic` 语义检索
6. 用户要求更深入了解某案例 → 提醒用户将消耗积分，确认后用 `case-detail`

**核心接口（默认使用）：** `search` · `keyword` · `detail` · `case` · `case-semantic`
**扩展接口（需确认）：** `regulation` · `regulation-detail` · `case-detail` · `case --authority-only`
**附属接口（仅限明确要求）：** `enterprise` · `enterprise-detail`

## 调用策略：正确性优先

每次 API 调用消耗 10 积分，应避免浪费。但**正确性始终优先于积分节约**——AI 的记忆可能存在幻觉或过时，涉及法律条文的精确引用时宁可多查一次。

### 必须调用 API 的情况

1. **需要引用具体法条文号**：如"民法典第184条"——AI 可能记错条文内容或条号对应
2. **需要确认时效性**：如"XX法是否现行有效"——法律修订频繁，AI 训练数据可能已过时
3. **用户明确要求检索**："帮我查一下""有没有相关的案例"
4. **案例检索**：用户需要具体裁判文书支持论证
5. **AI 对自身记忆不确定**：涉及近年修改的法律法规、司法解释等

### 可以不调用的情况

1. **法律概念解释**：纯概念性问题（如"什么是善意取得"），不涉及具体条文引用
2. **已有信息足够**：当前对话中已检索过相同或充分覆盖的内容
3. **用户只是在讨论**：用户陈述观点或进行法律分析，未要求查找法条/案例
4. **用户明确说不需要查**：如"不用查，你就告诉我大概意思"

### 积分消耗模式

每个接口每次调用均为 10 积分，但不同场景的实际消耗差异很大：

**法条检索**通常一次调用即可满足需求（语义检索结果已含法条全文，无需再调 `detail`）。

**案例检索是两阶段消耗**，需特别注意：
1. `case` / `case-semantic` 返回案例摘要列表 → **10 积分**
2. 若需查看某个案例的完整文书，每调一次 `case-detail` → **再消耗 10 积分**

因此，如果检索到 5 个案例并逐一查看详情，总消耗为 10 + 5×10 = **60 积分**。AI 代理在调用 `case-detail` 前应**告知用户将额外消耗积分并确认**。

### 节约积分的做法

1. **一查多用**：一次检索结果在对话中充分引用，避免重复检索
2. **优先语义检索**：`search` 返回结果最全面，一次通常即可覆盖需求
3. **避免法条链式调用**：不要先 `search` 再逐条 `detail`——语义检索已含法条全文
4. **案例详情谨慎调用**：先用摘要筛选出最相关的 1-2 个案例，再调 `case-detail`，不要对全部结果逐一查看
5. **善用筛选参数**：用 `--sxx 现行有效`、`--effect1 法律`、`--province` 等缩小范围
6. **利用历史归档**：所有检索结果自动保存到 `archive/`，用户提到"之前查过什么"时可直接从归档中提取，无需重新消耗积分

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
4. **等待用户主动触发**：不要自动获取完整判决书。如用户对某个案例感兴趣，可说"帮我看看第2个案例的完整判决书"——此时再调 case-detail（每个 10 积分）

### 关键词精确检索场景

用户问："帮我找广西的买卖合同纠纷判决书"

1. AI 进行案例关键词检索（10 积分）
2. 关键词检索返回的摘要较短，仅含基本信息（案号、法院、简要内容）
3. 向用户展示结果列表和积分消耗
4. 等待用户选择：如用户对某个案例感兴趣，再获取完整判决书（每个 10 积分）

### AI 向用户反馈的原则

1. **每次检索后主动说明积分消耗**："本次检索消耗 10 积分"
2. **多步检索时告知累计消耗**："本次检索消耗 10 积分（本次对话累计 30 积分）"
3. **完整判决书必须由用户主动触发**：先展示摘要，让用户选择感兴趣的案例，不要自动获取全文
4. **案例语义检索的摘要通常已够用**：只有用户明确要求查看完整判决书时才深入
5. **法条语义检索已含全文**：不需要额外补充
6. **用自然语言与用户沟通**：不要向用户暴露命令行语法，AI 后台执行脚本即可

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
