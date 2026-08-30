---
name: legal-client-brief
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: 1.1.0
license: CC-BY-NC
description: 为既有客户画像生成每日、每周或事件触发的行业法律简报草稿，并同时形成完整简报、朋友圈文案和公众号文章三件套；执行增量窗口、白名单信源、案例核验和 DRAFT 人工发布门禁。本技能应在用户需要“客户简报”“每日/每周追踪”“朋友圈或公众号日常触达”时使用。不要用于全面月报/季报、具体客户法律意见或自动发布。
---

# 客户简报

## 产品定位与路由

生成面向既有客户的高频信息触达包。典型频率是每日、每周或重大事件触发，目标是持续提供有用信息并维护关系，不重复制作完整行业研究。

| 维度 | `legal-client-brief` | `legal-industry-report` |
|---|---|---|
| 使用阶段 | 日常/每周增量跟踪 | 月度/季度全面研究 |
| 核心关系 | 既有客户维护 | 市场展示与潜客获取 |
| 信息范围 | 本窗口内的新变化 | 行业全景、结构与趋势 |
| 交付 | 简报 + 朋友圈 + 公众号 | 一份正式报告 |
| 视觉语气 | 紧凑、移动端友好 | 正式、机构化、可留存 |
| 状态 | 永远先停在 `DRAFT` | `PUBLIC_REVIEW` |

用户需要形成长期可展示的月报或季报时，改用 `legal-industry-report`。本技能不得把上一期全文换日期后重新发布；没有有效增量时，应输出“本期无值得触达的重要变化”，而不是凑条目。

## 真实能力边界

本技能负责“跑一期”：读取画像、限定窗口、检索、核验、起草三个渠道稿、校验和本地打包。纯 cron、launchd 或 CI 只能重新打包已有 Markdown；周期性研究必须由能联网研究的 Agent 调度器触发。

本技能不发送微信、朋友圈、公众号、邮件或客户系统消息，不自动去掉 `DRAFT`，不修改信源白名单。所有发布动作由律师在本技能之外完成。

## 输入与配置

首次使用复制并填写：

1. `config/report-profile.example.md` → `config/report-profile.md`：品牌、编辑人和简报视觉。
2. `config/audience-profile.example.md` → `config/audience-profile.md`：既有客户的去标识化行业画像、业务重点和风险主题。
3. `config/sources-whitelist.example.txt` → `config/sources-whitelist.txt`：正文与两个渠道稿允许引用的域名。
4. 可选：`config/industry-rules.local.example.yaml` → `config/industry-rules.local.yaml`：细分行业补充规则。

真实配置由根目录 `.gitignore` 排除；前三项缺一即停止，不用默认值生成客户向草稿。

每期参数：

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `period_start` / `period_end` | 是 | 无 | 增量信息窗口 |
| `cadence` | 是 | 无 | `daily`、`weekly` 或 `event` |
| `industry_keywords` | 否 | 客户画像 | 本期检索词 |
| `previous_cutoff` | 否 | 上期截止日 | 去重和判断新变化 |
| `max_items` | 否 | 5 | 重点变化上限 |

## 权限与安全边界

本技能会把脱敏关键词发送给白名单内公开网站或用户授权数据库，读取本地配置和模板，并写入 Markdown、HTML、PDF、元数据与复核清单。

客户画像只写行业、规模区间、业务阶段和风险主题；避免真实客户全称、联系人账号、未公开经营数据和无必要的自然人信息。白名单外页面可作线索发现，但不得进入事实链、正文、朋友圈稿或公众号稿。

## 单期生成流程

1. **加载窗口与画像**：检查配置，确认 `cadence / period_start / period_end / previous_cutoff`。
2. **解析行业规则**：

   ```bash
   python3 scripts/resolve_industry_rules.py \
     --industry "<行业>" \
     --mode brief \
     --output <追踪计划.json>
   ```

   规则包给出应监测事件和客户相关性问题，但候选信源仍必须经过本地白名单。
3. **只找增量**：记录标题、发布者、发布日期、URL、是否在窗口内、相对上期的新变化、与客户画像的关系及采用/剔除理由。
4. **选择 1—5 条信号**：优先选“新、真、与客户有关、能转化为行动”的事项。没有足够价值时不凑数。
5. **核验案例**：案例必须有案号、法院、裁判日期、核验链接与核验日期；无法核验则写“本期未收录可核验案例”。
6. **起草三件套**：
   - `templates/brief-skeleton.md`：完整简报，解释变化、客户相关性和行动建议。
   - `templates/moments-copy.md`：朋友圈短文案，突出一个核心信号和一个行动提示。
   - `templates/wechat-draft.md`：公众号文章草稿，适合移动阅读并保留信源与免责声明。
7. **运行门禁**：

   ```bash
   python3 scripts/validate_report.py \
     --kind brief \
     --input <客户简报_DRAFT.md> \
     --whitelist config/sources-whitelist.txt

   python3 scripts/validate_channels.py \
     --moments <朋友圈_DRAFT.md> \
     --wechat <公众号_DRAFT.md> \
     --whitelist config/sources-whitelist.txt \
     --brief <客户简报_DRAFT.md>
   ```

8. **构建草稿包**：

   ```bash
   python3 scripts/build_report.py \
     --kind brief \
     --input <客户简报_DRAFT.md> \
     --moments-copy <朋友圈_DRAFT.md> \
     --wechat-draft <公众号_DRAFT.md> \
     --profile config/report-profile.md \
     --audience-profile config/audience-profile.md \
     --whitelist config/sources-whitelist.txt \
     --cadence weekly \
     --period-start <YYYY-MM-DD> \
     --period-end <YYYY-MM-DD>
   ```

9. **可视与人工复核**：把 PDF 全页渲染为图片，检查紧凑度、表格、裁切和异常空白；逐条打开信源，复核法律含义与渠道表达。
10. **停在 DRAFT**：只报告本地路径、自动门禁结果和待人工判断事项。

## 三渠道写作纪律

- **完整简报**：回答“发生了什么、为什么与这类客户有关、现在能做什么”。
- **朋友圈**：一个核心判断、最多三个要点、一个轻量行动提示；不堆链接、不写确定性个案结论。
- **公众号**：标题和导语可传播，正文仍须保留事实边界、来源和免责声明；不得把营销口号写成法律结论。
- 三份稿件的事实、日期和结论方向必须一致；渠道压缩只能减少信息，不能改变事实。

## 输出契约

- `客户简报_<audience>_<cadence>_<period_end>_DRAFT.md`
- 同名 `.html`、`.pdf`、`.meta.json`、`.checklist.md`
- `朋友圈_<audience>_<period_end>_DRAFT.md`
- `公众号_<audience>_<period_end>_DRAFT.md`

元数据状态固定为 `DRAFT`，绑定三份 Markdown、PDF、画像、白名单和品牌配置的哈希。

## Hard Fail

出现任一项即停止：

- 三个必需配置缺失、为空或 `report_kind` 不是 `brief`。
- 任一三件套文件缺失 `_DRAFT` 文件名或正文 DRAFT 标识。
- 残留占位符、`[P?]` 或独立的 `...`。
- 任一文件出现白名单外 URL。
- 重点变化不在窗口内，或没有说明相对上期的新变化。
- 案例证据字段不全且未改写为“本期未收录可核验案例”。
- 三份稿件事实冲突，或把行业信息写成针对具体客户的确定性法律意见。
- PDF 为空、非 A4、明显裁切/重叠/乱码或存在异常空白页。
- 任何自动发送、外部推送或自动去掉 `DRAFT` 的路径。

自动门禁不证明法律判断与渠道传播效果正确；律师复核前保持 `NOT_VERIFIED`。

## 调度

按部署环境只读取一份：

- Agent 自动化平台：`deploy/workbuddy-deploy.md`
- OpenClaw 或其他 Agent 调度器：`deploy/openclaw-deploy.md`
- 纯 cron / launchd / CI 能力边界：`deploy/generic-cron-deploy.md`

## 依赖

Python 包统一安装：

```bash
python3 -m pip install -r scripts/requirements.txt
python3 -m playwright install chromium
```

Mermaid CLI 为可选依赖：`npm install -g @mermaid-js/mermaid-cli`。缺失时降级为代码块；脚本不会自动安装。

## 按需读取

- 行业规则：`references/industry-rules.yaml`
- 完整简报与渠道模板：`templates/brief-skeleton.md`、`templates/moments-copy.md`、`templates/wechat-draft.md`
- 人工复核：`templates/checklist-template.md`
- 视觉规范：`references/design-spec.md`
- 故障排查：依次运行 `validate_industry_rules.py`、`industry_rules_selftest.py`、`validate_report_selftest.py`、`validate_channels_selftest.py`
