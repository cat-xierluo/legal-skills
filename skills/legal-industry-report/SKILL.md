---
name: legal-industry-report
homepage: https://github.com/cat-xierluo/legal-skills
author: 杨卫薪律师（微信ywxlaw）
version: 1.1.0
license: CC-BY-NC
description: 生成面向公开展示与广泛分发的正式行业法律报告，按月度或季度完成行业全景、政策监管、代表企业、法律风险、服务机会及可追溯信源研究。本技能应在用户需要“行业报告”“月报/季报”“对外展示的行业研究”时使用。不要用于日常客户触达、单一企业尽调、具体客户法律意见或自动发布。
---

# 行业报告

## 产品定位与路由

生成一份可供不特定潜在客户阅读的正式行业法律报告。典型频率是每月或每季度，目标是建立专业品牌、支持公开分发和形成业务入口；它不是内部速记，也不是针对具体客户的法律意见。

| 维度 | `legal-industry-report` | `legal-client-brief` |
|---|---|---|
| 使用阶段 | 月度/季度全面研究 | 日常/每周增量跟踪 |
| 核心关系 | 面向市场与潜在客户 | 维护既有客户关系 |
| 信息范围 | 行业全景、结构与趋势 | 截止日前后发生的变化 |
| 视觉语气 | 正式、机构化、可长期留存 | 紧凑、易扫读、适合社交渠道 |
| 交付状态 | `PUBLIC_REVIEW` | `DRAFT` |
| 发布动作 | 律师复核后另行发布 | 律师复核后另行发布 |

用户要发朋友圈、公众号日常更新，或只追踪最近一个周期时，改用 `legal-client-brief`。用户要按月/季形成完整行业作品时，使用本技能。

## 输入与缺口处理

| 输入 | 必填 | 默认 | 用途 |
|---|---|---|---|
| `industry` | 是 | 无 | 行业名称及口径 |
| `region` | 否 | 全国 | 政策、产业集群与企业范围 |
| `period` | 否 | 季度 | 月度或季度报告周期 |
| `focus` | 否 | 全景 | 劳动、知识产权、投融资、数据、跨境等 |
| `as_of` | 否 | 执行日 | 事实与有效性截点 |
| `preferred_sources` | 否 | 规则包 | 用户指定主管部门、协会、数据库或材料 |

- 缺 `industry`：停止并只追问这一项。
- 行业名称存在多个统计口径：列出候选口径与影响，不自行选第一个。
- 缺区域或重点：使用默认值，并在“研究边界与方法”写明。
- 行业规则未命中：使用通用规则，同时标记 `needs_custom_pack: true`，先补行业问题与信源，不冒充精准行业研究。
- 外部数据库不可用：切换到官方公开渠道或写“未采集/待复核”，不得补写推测值。

## 权限与安全边界

本技能会联网检索公开材料，读取本技能模板与用户明确提供的配置，并在用户指定目录写入 Markdown、HTML、PDF 和元数据。查询前对客户、案件和内部经营信息做最小必要脱敏。

本技能不会自动发送、上传、发布、安装依赖、扩张访问权限或读取用户全局 `.env`。公开报告避免出现真实客户名、未公开经营数据和无必要的自然人身份信息。

## 首次配置

1. 复制 `config/report-profile.example.md` 为 `config/report-profile.md`，填写品牌、编号、主办律师与视觉主题。
2. 如需增加细分行业，复制 `config/industry-rules.local.example.yaml` 为 `config/industry-rules.local.yaml`。
3. 如需排除域名，复制 `config/source-blacklist.example.txt` 为 `config/source-blacklist.local.txt`。

真实配置由根目录 `.gitignore` 排除。正式 PDF 前必须补齐 `report-profile.md`；预览可使用去具体化配置。

## 研究与生成流程

1. **固化研究边界**：确定 `industry / region / period / focus / as_of`，写明不覆盖范围。
2. **解析行业规则**：

   ```bash
   python3 scripts/resolve_industry_rules.py \
     --industry "<行业>" \
     --mode report \
     --output <研究计划.json>
   ```

   如存在本地补充，增加 `--overlay config/industry-rules.local.yaml`。读取输出中的研究问题、必备维度、指标、风险视角、信源角色和时效规则。
3. **建立证据账本**：每个关键结论记录“来源事实 / 模型归纳 / 律师判断 / 待核验事项”，并保留标题、发布者、日期、URL、检索时间和统计口径。
4. **全面采集**：覆盖宏观与规模、产业链、竞争格局、区域集群、政策监管、代表企业、争议风险和法律服务机会。规则包是最低清单，不是结论模板。
5. **处理冲突**：来源口径不一致时并列披露，不平均、不拼接成虚假确定值。
6. **起草报告**：使用 `templates/report-skeleton.md`。正式报告以解释和证据为主，不写成新闻摘要堆叠。
7. **运行门禁**：

   ```bash
   python3 scripts/validate_report.py --kind report --input <行业报告.md>
   ```

8. **构建交付件**：

   ```bash
   python3 scripts/build_report.py \
     --kind report \
     --input <行业报告.md> \
     --profile config/report-profile.md
   ```

9. **最终复核**：把 PDF 全页渲染为图片，检查封面、章节节奏、中文字体、表格、页码、裁切和空白页；律师再复核事实、有效性、法律判断和公开表达。

## 信源与判断纪律

- 按 `references/industry-rules.yaml` 选择“什么问题应查哪些一手来源”，按 `references/source-priority.md` 判断证据强度。
- 官方原文可单独证明其发布内容；行业规模、份额、趋势和影响判断原则上需两个独立来源。
- 只有一个来源时紧邻结论标注 `[单一信源]`，并写明能证明与不能证明的范围。
- 每条政策写发布机关、发布日期、施行日期和状态；无法确认有效性时标“待核验”。
- 每个关键数据写统计期、指标定义、区域口径和来源。转载同一稿件不算独立来源。
- 上市公司披露只能证明披露主体及文件所述事项；不得自动外推为全行业事实。
- 企业数据库未返回不等于不存在；使用“未见所查公开来源记录”并列明检索范围。

## 输出契约

默认生成到 Markdown 所在目录或 `output_dir`：

- `行业报告_<industry>_<region>_<period>_<YYYYMMDD>.md`：权威源稿。
- 同名 `.html`：可检查的渲染中间件。
- 同名 `.pdf`：A4 正式复核版。
- 同名 `.meta.json`：`PUBLIC_REVIEW` 状态、生成时间、文件哈希、信源 URL 与配置哈希。

报告必须包含：执行摘要、研究边界与方法、行业结构与市场、竞争格局与代表企业、政策监管与区域、法律风险与争议、服务机会与行动建议、附录与信源。

## Hard Fail

出现任一项即不得交付：

- 残留占位符、`[P?]` 或独立的 `...`。
- 免责声明缺失或晚于执行摘要。
- 关键事实无可点击来源，或单一来源未披露。
- 行业规则未命中却未披露通用回退。
- 主体识别有多个候选却自动选第一项。
- 把行业一般信息写成具体客户法律意见。
- PDF 为空、存在非 A4 页面、明显裁切/重叠/乱码、异常空白页，或未做最终可视复核。

自动门禁只证明结构、信源和文件属性，不证明法律判断正确；律师完成语义复核前保持 `NOT_VERIFIED`。

## 依赖

### 系统依赖

| 依赖 | 安装方式 |
|---|---|
| Python 3.10+ | macOS: `brew install python`<br>Linux: `sudo apt-get install python3` |
| Chromium | `python3 -m playwright install chromium` |
| Mermaid CLI（可选） | `npm install -g @mermaid-js/mermaid-cli`；缺失时降级为代码块 |

### Python 包

Markdown、PyYAML、BeautifulSoup、Jinja2、Playwright 与 PyMuPDF 统一安装：

```bash
python3 -m pip install -r scripts/requirements.txt
```

脚本在依赖缺失时给出安装提示，不会自动安装。

## 按需读取

- 行业规则与信源：`references/industry-rules.yaml`、`references/source-priority.md`
- 企业与隐私纪律：`references/data-discipline.md`
- 报告结构：`templates/report-skeleton.md`
- 视觉规范：`references/design-spec.md`、`references/palette-presets.md`
- 故障排查：依次运行 `validate_industry_rules.py`、`industry_rules_selftest.py`、`validate_report_selftest.py`
