---
name: weekly-legal-briefing
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: 0.3.1
license: CC-BY-NC
description: 配置一次，定期自动生成行业/法律研报草稿（如科技型制造企业法律周报），人工复核后发布。设计风格同 industry-research-report（蓝皮书体例 + 抬头/配色/署名由 report-profile.md 配置），支持白名单信源过滤与案号回查，输出文件带 _DRAFT 标记，发布动作永远留给人工。建议在用户说"配一个周报 / 每周给客户发一份法律研报 / 客户要法律周报了怎么落地 / 顾问客户要定期触达"时使用；不要用于：单次行业情报底稿（用 industry-research-report）、自动邮件/群发（硬约束禁止）、客户名下的具体法律意见（用 opc-legal-counsel）。
---

# weekly-legal-briefing · 定时法律研报

## 定位

留存端的对外触达。**消费者是客户**——把"主动触达客户"变成一个定时任务,而不是想起来才发。

本 skill 是XX 律师法律 AI 课程体系（详见 `知识整理/课程体系/XX 律师法律AI课程主题体系.md`）中**客户关系主轴的触达端**。Skill 1 (industry-research-report) 做获客端背景情报,本 skill 做留存端定时触达,中间走既有套件（legal-proposal-generator / litigation-analysis）产出可复用物料。

⚠️ **硬约束**（本 skill 边界与 Skill 1 完全不同,这是两个 skill 不合并的核心理由）

- **永不自动外发** —— 本 skill 输出永远是 `_DRAFT` 草稿；邮件 / 微信群发 / 客户系统推送一律不做,发布动作物理上留给人工
- **白名单信源制** —— 不在 `config/sources-whitelist.txt` 的信源一律不入稿
- **案例必带案号** —— 入"案例研究"板块必须可在公开渠道回查,查不到案号的案例不入稿
- **配置先行** —— 第一次跑前必须先填 `config/report-profile.md`（个性化）+ `config/sources-whitelist.txt`（信源白名单）+ `config/audience-profile.md`（客户画像）
- **部署后调度由平台承担** —— 本 skill 只负责"跑一期",调度由 WorkBuddy / OpenClaw / Claude Code cron 等平台承担

## 触发场景

- "我要给 XX 客户配一个法律周报"
- "以后每周一给客户发一份法律研报"
- "客户要法律周报了,怎么落地"
- "每周自动生成一份 XX 行业的法律快讯"
- "设置一个定时任务,每周跑一次周报"

## 与 Skill 1 的关键差异

| 维度 | Skill 1 industry-research-report | Skill 2 weekly-legal-briefing |
|---|---|---|
| 目的 | 获客（律师自己用） | 留存（给客户看） |
| 输出 | 单次深度报告 | 周期性轻量周报 |
| 信源纪律 | 优先级分层（P1-P5）,非 P5 标注 | 严格白名单,白名单外默认丢弃 |
| 质量门禁 | 免责声明 + 溯源附录 | DRAFT 闸门 + 案号回查 + 信源可点 |
| 生命周期 | 快消品 | 订阅资产,存档累积 |
| 调度 | 按需拉 | 定时推（部署后由平台驱动） |
| 输出物后缀 | `{industry}_{region}_{YYYYMMDD}.pdf` | `..._第N期_DRAFT.pdf` |

## 个性化配置（三个文件,首次部署必填）

### 首启向导（首次使用 · 一次性）

> 同 Skill 1：见 `industry-research-report/SKILL.md` "首启向导"段。Agent 用 harness 实际提问机制（不绑死 tool）一次性问完 7 个核心问题(律所名 / 系列名 / 主色调 / 设计强度 / 封面变体 / 主办律师 / 联系方式),写入 `config/report-profile.md`(gitignore),后续所有周报从这里读。

### 1. `config/report-profile.md`（必填,继承 Skill 1 的体系）

> 与 Skill 1 共用同一份配置字段(主色 / 强调色 / 调色板组 / 封面变体 / 设计强度 全部继承 v0.3.0 的 5 个调色板);详见 `config/report-profile.example.md`。本 skill 在 Skill 1 字段基础上多两个字段:

| 字段 | 默认 | 说明 |
|---|---|---|
| `audience_label` | `科技型制造企业` | 客户画像标签,显示在封面"目标读者"位 |
| `period_label` | `第 N 期 · {YYYY-MM-DD}` | 期数标签模板,render.py 渲染时按当期替换 |

### 2. `config/audience-profile.md`（必填,客户画像）

决定选题过滤、信源白名单匹配的基线。建议结构：

```markdown
## 客户画像
- industry_focus: [科技型制造 / 具身智能 / 低空经济 / ...]
- employee_scale: [500-2000 人 / 2000+ 人 / ...]
- business_focus: [劳动 / 知识产权 / 投融资 / 跨境合规 / ...]
- risk_focus: [竞业限制 / 商业秘密 / 股权激励 / 数据合规 / ...]

## 选题优先级（决定本期选哪 3-5 条）
- 高频议题: [...]
- 行业动态: [...]
- 监管动向: [...]

## 联系人
- editor: {本期编辑署名}
- contact_wechat: {微信号}
- contact_phone: {电话}
```

### 3. `config/sources-whitelist.txt`（必填,白名单信源）

一行一个域名或公众号 ID,**白名单外信源默认丢弃**。建议起点：

```
# 官媒
xinhuanet.com
people.com.cn
jjjcb.com         # 经济参考报
stcn.com          # 证券时报
cs.com.cn         # 中国证券报
21jingji.com      # 21 世纪经济报道
yicai.com         # 第一财经

# 法律法规
gov.cn            # 国务院
court.gov.cn      # 最高人民法院
chinacourt.org    # 中国法院网
pkulaw.com        # 北大法宝（仅法规原文链接）

# 行业协会
caam.org.cn       # 中国汽车工业协会
semi.org.cn       # SEMI 中国

# 律所与法律自媒体（按需）
zhichanlaw.com    # 知产力
iphouse.cn        # IPR Daily
```

> 白名单更新规则：仅由律师本人增删；不得让 AI 自动扩列。

## IO 契约

### 输入

**配置（一次性）**：`config/report-profile.md` + `config/audience-profile.md` + `config/sources-whitelist.txt`

**运行参数（每次跑）**：
- `--period-number N`：期数（默认自动按 archive/ 已有文件递增）
- `--industry-keywords [k1 k2 ...]`：本期重点选题（默认从 audience-profile.md 的"选题优先级"提取）

### 输出物（带 _DRAFT 标记,永不脱 DRAFT）

- `archive/法律周报_{audience}_{YYYY}第{N}期_DRAFT.md` —— 中间稿
- `archive/法律周报_{audience}_{YYYY}第{N}期_DRAFT.pdf` —— 终稿（A4 精排,蓝皮书体例）
- `archive/法律周报_{audience}_{YYYY}第{N}期_DRAFT.meta.json` —— 元数据（含信源清单、案号清单、生成时间）

> **发布动作**：人工复核通过后,把 `_DRAFT` 后缀去掉（如 `cp ..._DRAFT.pdf ..._V1.pdf`）,**禁止** 通过本 skill 自动重命名或自动发送。

### 研报骨架（强制五段式）

1. **本期要点** —— 3-5 条,按板块（如 税 / 劳动 / 社保基数）
2. **案例研究** —— 聚焦 audience_profile 相关的典型案件,**必带案号 + 信源**
3. **本周动态** —— 白名单信源摘要,逐条注来源与日期
4. **给该类企业的三个实务提示**
5. **页脚** —— 本期编辑 / 联系电话（audience-profile 占位符）

> 完整模板见 `templates/briefing-skeleton.md`,五段必须齐全。

## 数据源依赖

### 检索纪律（白名单制）

- 仅检索 `config/sources-whitelist.txt` 中列出的域名 / 公众号
- 命中非白名单信源 → **丢弃,不标注,不入稿**
- 关键结论须至少 2 个白名单信源交叉验证

### 案例回查

- 入"案例研究"板块的每条案例必须含**案号 + 审理法院 + 裁判日期**
- 案号必须在 `https://wenshu.court.gov.cn`（中国裁判文书网）可检索
- 查不到案号的案例**不入稿**,改为标注"近期类案(待补案号)"

## SOP（单次生成流程）

1. **加载配置** —— 三个 config 文件；任一缺失则中止并提示
2. **选题提取** —— 从 audience-profile.md 的"选题优先级"或本期 --industry-keywords 取 3-5 条
3. **白名单信源检索** —— 网络检索每条选题,过滤白名单外结果
4. **案例回查** —— 对案例研究候选逐一查裁判文书网案号,过滤查不到案号的条目
5. **生成 markdown** —— 按 briefing-skeleton.md 五段式填充
6. **渲染 PDF** —— 同 Skill 1 管线（render.py + pdf.py,蓝皮书体例）
7. **写元数据 + 归档** —— 元数据 JSONL 增量追加到 `archive/_meta.jsonl`,便于年度服务报告素材汇总
8. **硬中止在 DRAFT** —— 本 skill 在此步物理结束,不得自动重命名 / 推送

## 质量纪律

- **信源白名单制** —— 不在白名单的信源一律不入稿
- **案例必带案号** —— 必带案号 / 审理法院 / 裁判日期；案号必可在裁判文书网回查
- **生成后自检清单** —— 每期自动生成一份 `archive/法律周报_..._DRAFT.checklist.md` 列出：信源逐条可点 / 日期在本期内 / 无臆测表述
- **发布前人工复核** —— skill 输出永远停在 DRAFT,这是硬规则

## 渲染管线（与 Skill 1 同源,蓝皮书体例）

```
briefing-skeleton.md (填充后的 md)
  → scripts/render.py            # md → A4 HTML
  → references/report-template.html + references/covers/cover-{C,D,E,F}.html
  → scripts/pdf.py               # HTML → PDF
```

与 Skill 1 渲染管线的差异：

- **封面 kicker 字段**：`本期 · 法律周报 · 第 N 期`
- **页脚右侧**：`footer_brand` 默认为 `法律周报 · 第 N 期`
- **元数据页**：多一项"信源白名单命中数 / 案例数 / 本期字数",便于复核

> 详细设计规范见 `references/design-spec.md`(与 Skill 1 同源,共享 `:root` 变量)。

## 调度挂接（平台无关设计）

skill 本体只管"跑一期",调度由部署平台承担。两平台各写一份部署说明：

### WorkBuddy 自动化任务

详见 `deploy/workbuddy-deploy.md`。三件套：
- 名称：`{audience} 法律周报`
- 工作时间：每周一 09:00
- 提示词：调用 `python3 scripts/render.py ... && python3 scripts/pdf.py ...`

### OpenClaw / Claude Code cron

详见 `deploy/openclaw-deploy.md`。三件套：
- 名称：`{audience} 周报`
- cron：`0 9 * * 1`（每周一 09:00）
- 命令：`python3 scripts/render.py -i ... && python3 scripts/pdf.py -i ...`
- 频道推送：可推送 `_DRAFT.pdf` 到频道,但**发布动作仍需人工在频道回复确认**

### 其他平台（crontab / launchd / Cloud Functions）

详见 `deploy/generic-cron-deploy.md`。

## 验收标准

- 连续跑 4 期（模拟一个月,每周一跑一次）
- 白名单外信源 **0 漏入**（用抽样核验）
- 案例板块抽查：案号 **100% 可在公开渠道回查**
- 复核体验：人工从 DRAFT 到可发布 ≤ **15 分钟/期**（超了说明生成质量不达标,需调白名单或选题）

## v1 不做什么（最小可用边界）

- 不做自动外发（邮件/微信群发一律不做,发布永远人工）
- 不做多客户个性化（v1 单 audience；v2 做 audience 多配置分报）
- 不做排版精修（页眉页脚用蓝皮书模板预置）
- 不接元典案例库（白名单信源 + 案号回查已够 v1 验证）
- 不做智能选题（v1 选题来自 audience-profile.md 显式声明）

## v2 迭代方向

- **多客户分报**：一份素材按 audience_profile 派生 N 份
- **年度服务报告衔接**：周报存档作为年度报告的"工作量证据源"（文件命名规则对齐）——客户关系主轴触达端的终点
- **与 industry-research-report 编排**：新行业客户用 Skill 1 建背景（获客）,用 Skill 2 持续跟踪（留存）,中段走既有套件——客户关系主轴 v2 全链成型
- **自动选题**（受控）：AI 基于 audience_profile 自动建议 3-5 条候选,人工勾选后生成

## 故障排除

| 现象 | 排查 |
|---|---|
| `sources-whitelist.txt 不存在` | 复制 `config/sources-whitelist.example.txt` 为 `config/sources-whitelist.txt`,填入真实白名单 |
| `audience-profile.md 不存在` | 复制 `config/audience-profile.example.md` 为 `config/audience-profile.md` |
| 案例板块所有条目被剔除 | 案号回查全部失败 → 优先排查裁判文书网连通性 + 案号格式 |
| 信源命中率 < 50% | 白名单可能过严,按 `references/source-priority.md` 提示扩充 |
| `playwright 未安装` | 同 Skill 1 |
| 自动外发误触发 | **不可能**——本 skill 没有外发代码路径；如有外发需求,请人工处理 |

## 引用资源

- 模板：`templates/briefing-skeleton.md` / `templates/checklist-template.md`
- 设计：`references/report-template.html` / `references/design-spec.md` / `references/covers/cover-{C,D,E,F}.html`（与 Skill 1 同源）
- 脚本：`scripts/render.py` / `scripts/pdf.py`（与 Skill 1 同源,可直接复用）
- 配置：`config/report-profile.example.md` / `config/audience-profile.example.md` / `config/sources-whitelist.example.txt`
- 部署：`deploy/workbuddy-deploy.md` / `deploy/openclaw-deploy.md` / `deploy/generic-cron-deploy.md`
- 归档：`archive/`（`_meta.jsonl` 累积,便于年度服务报告汇总）
