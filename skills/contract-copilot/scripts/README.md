# Contract Copilot Scripts

合同审查文档操作脚本，支持两类能力：

- 底层 API：`ContractReviewer`（批注、修订、替换、文本读取）
- 一体化流程：`apply_review_plan.py`（批量执行审查计划 + 生成审查报告）

## 依赖

- 必需 Python 包：`defusedxml`、`lxml`
- DOCX 编辑与验证功能内嵌在 `scripts/docx/` 中，无需外部依赖
- 可选系统依赖：`pwsh` / `powershell`（Windows 包装器）

推荐先执行：

```bash
python3 -m pip install -r scripts/requirements.txt
```

完整安装说明、目录结构要求与常见报错排查见：`../references/setup-dependencies.md`

## 目录结构

```
scripts/
  review/              审查流程
    apply_review_plan.py   流程编排入口
    plan_loader.py         审查计划加载与校验
    action_executor.py     动作分发与节点定位
    enrich_review_plan.py  计划字段自动补全
    review_runtime.py      审查人配置与上下文记忆
    archive_service.py     归档服务
  report/              报告生成
    reporting.py           Markdown 审查意见书
    report_docx.py         Word 审查意见书
  docx/                文档引擎
    document.py            Document / DocxXMLEditor 核心
    utilities.py           XML 编辑器
    validation.py          轻量级结构校验
    reviewer.py            ContractReviewer 高层封装
    pack.py                DOCX 打包
```

## 脚本清单

- `run_apply_review_plan.ps1`：Windows / 中文路径兼容包装器（调用 Python 主入口并回拷结果）
- `review/`：审查流程相关脚本（详见上方目录结构）
- `report/`：报告生成相关脚本
- `docx/`：DOCX 文档编辑引擎

## 一体化执行（推荐）

```bash
python scripts/review/apply_review_plan.py \
  --input /path/to/合同.docx \
  --plan /path/to/review-plan.json \
  --output /path/to/合同_审核修订版.docx
```

默认会在用户目录生成：

- `合同_审核修订版.docx`（修订批注一体版）
- `合同_审核修订版_审查报告.docx`

默认还会在 `contract-copilot/archive/<时间戳_合同名>/` 归档目录内留存：

- `review-plan.json`
- `合同_审核修订版_审查报告.md`
- `合同_审核修订版_执行日志.json`
- 输出 DOCX、副本报告 DOCX 与 `manifest.json`

可选参数：

- `--report`：指定 Markdown 报告输出路径（默认随归档进入 `archive/`）
- `--report-docx`：指定 Word 报告输出路径
- `--log`：指定执行日志路径（默认随归档进入 `archive/`）
- `--archive-dir`：指定归档根目录（默认 `contract-copilot/archive`）
- `--no-archive`：关闭归档，并把 Markdown 报告 / 执行日志直接写到输出目录（调试模式）
- `--archive-no-input`：归档时不复制原始输入 DOCX
- `--author` / `--initials`：指定批注与修订作者信息
- `--organization` / `--department`：指定审查意见书署名中的律所/公司与可选部门
- `--client-name`：指定客户名称；未提供时优先从历史记录或合同主体推断
- `--party-role`：指定审查立场，支持 `甲方 / 乙方 / 中立 / 其他`
- `--review-intensity`：指定审查口径，支持 `克制 / 常规 / 强势`
- `--no-validate`：跳过 DOCX 校验
- `--no-enrich-plan`：关闭计划策略字段自动补全（默认开启）
- `--edit-policy`：自动分流策略，支持 `revise-first` / `balanced` / `comment-first`

执行语义：

- 若存在失败项，脚本仍会写出输出 DOCX、Word 报告和归档留痕，但会返回非零退出码。
- Markdown / Word 对外报告默认采用“审查意见书”体例：前部先写“致：收件方”开篇、合同概况、综合审查意见与重要风险提示，后部再按正式意见逐项展开，并附声明与出具信息。
- Word 版审查意见书默认采用深蓝标题、仿宋正文、浅底元信息卡、棕色标签高亮和页脚页码，保持 OOXML 直出，不依赖额外模板引擎。
- Word 版审查意见书默认采用更紧凑的正式件参数：左右页边距已压到 `1440`，正文、元信息和列表段落的行距/段距同步缩小。
- Word 版审查意见书中的项目符号/编号列表使用 OOXML 原生 `numbering.xml`，不再用普通段落模拟列表。
- “详细审查意见”在 Word 中会按单项表格渲染，逐项展示风险等级、条款位置、审查意见、原条款、建议修改和法律依据。
- “详细审查意见”表格会进一步收紧：标签列较窄、内容列更宽，表格行距压到 `260`，单元格上下内边距归零，减少无效换行和空白。
- 生成或人工编写 `review-plan.json` 时，应同步参照 `references/revision-strategy.md`：留空项默认只批注，准确法条默认不因冗长而删减，能局部删减/补入的不要整段重写。
- 默认外部模式是“修订批注一体版”：确定性问题直接修订，留空项/事实待补项保持批注，P0 / P1 的重大直接修订默认再保留解释性批注；程序优化型、说明型和低必要性问题默认只进意见书。
- 默认交付模式下，用户目录只保留审核修订版 DOCX 与 Word 报告；Markdown 报告、执行日志和审查计划副本默认进入 `archive/`。
- 命中质量、失败项和其他执行统计默认只保留在 `*_执行日志.json`，不写入对外报告。
- 默认自动分流策略为更克制的 `revise-first`：即便存在明确改文载荷，也会先判断该问题是否值得直接落文；纯优化型、程序型和说明型条款可自动退出 Word 页面，仅保留在意见书。
- 修订执行层已支持“多段最小差异修订 + 审查密度收敛”：同一 run 内优先做局部短语替换/删除；跨 run 时优先做段落内片段修订；若同一条款内存在多处变化，会尽量拆成多组局部 `w:del / w:ins`，但当某个条款会炸出过多单字级/标点级碎修订时，执行器会自动把相邻微小差异并成更少的核心修订块，只有命不中或已有跟踪修改干扰时才退到更粗颗粒 fallback。
- 若留空/占位项被上游计划误写成 `replace`，执行器会自动降为 `comment`，避免把负责人、联系方式、附件等待填信息直接代填进正文。
- 若本地不存在审查人配置、缺少姓名/机构，或当前环境尚未确认过该身份配置，脚本会先读取 `config/reviewer_profile.example.json`，再在交互模式下询问或确认审查人姓名、律所/公司名称和可选部门，并保存到 `config/reviewer_profile.json`；若是非交互环境，则要求显式传入 `--author` 与 `--organization`。
- 该配置只保存在当前本地 skill 的 `config/` 目录，不会自动上传；后续可直接通过自然语言让助手帮你修改。
- 若用户未明确客户名称、审查立场或审查口径，脚本会先读取 `config/review_memory.json`；命中同名合同历史记录时默认沿用，未命中时在交互模式下询问并保存。该记忆文件以 `config/review_memory.example.json` 为模板生成，也只保存在当前本地 skill 的 `config/` 目录。
- 审查口径与动作策略现已拆开：`review_intensity` 只影响风险识别与表达强弱，`edit_policy` 才决定自动分流时更偏向直接修订、平衡处理还是优先批注。
- 若未显式传入 `--edit-policy`，默认仍采用 `revise-first`；因此即便本轮口径是 `克制`，系统对确定性问题也仍可直接修订。
- 写入 Word 的批注与修订时间戳会先读取本机当前时区与本地时间，再以本次命令执行时点为起点按“两层错峰”规则自动向后错开：同一条审查意见内部的修订/批注批次默认相隔 `1-2` 分钟，不同审查意见之间继续保持 `5-10` 分钟的大间隔；`w:date` 使用本地时区偏移格式写入，避免出现 UTC 直显或早于实际接单/执行时点的时间。
- Word 批注作者会显示为 `姓名｜机构`；Markdown / Word 审查意见书仍分开显示姓名、机构/公司和部门。
- 生成的 Markdown / Word 审查意见书会自动带出同一份审查人、机构/公司和部门信息。
- 若审查项未显式提供 `comment`，系统会自动生成多行结构化批注：`风险等级 / 风险点 / 条款位置 / 说明 / 修改建议 / 可选建议措辞`。

## PowerShell 包装器（Windows 推荐）

```powershell
pwsh -File ./scripts/run_apply_review_plan.ps1 `
  -InputPath "C:\合同\设计委托合同.docx" `
  -PlanPath "C:\合同\review-plan.json" `
  -OutputPath "C:\合同\设计委托合同_审核修订版.docx" `
  --author "张三律师" `
  --organization "某某律师事务所" `
  --no-validate
```

包装器定位：

- 仍以 `apply_review_plan.py` 作为唯一真实执行链路，不复制一套 PowerShell 版审查逻辑。
- 自动把 `input / plan / output / report / report-docx / log` staging 到 ASCII 临时目录，降低中文路径和路径编码差异带来的失败概率。
- 默认会把审核修订版和 Word 审查意见书拷回用户原始目录；若使用 `--no-archive`，也会把 Markdown 报告和执行日志一并拷回。
- 显式传入的 `--report`、`--report-docx`、`--log`、`--archive-dir` 会在临时目录执行后再回拷到目标位置。

包装器参数：

- `-InputPath`：输入 DOCX
- `-PlanPath`：审查计划 JSON
- `-OutputPath`：输出 DOCX
- `-PythonCommand`：可选，显式指定 Python 解释器
- 其余参数：按原样透传给 `apply_review_plan.py`

建议场景：

- Windows 用户直接运行本 skill
- 合同、计划文件或输出目录位于中文路径
- OneDrive / 企业网盘等同步目录下的本地路径兼容性不稳定

## 生成阶段：自动补全计划字段（推荐）

```bash
python scripts/review/enrich_review_plan.py \
  --input /path/to/review-plan.json \
  --output /path/to/review-plan_enriched.json
```

常用参数：

- `--in-place`：直接覆盖原计划文件
- `--output`：指定输出路径（默认生成 `*_enriched.json`）

## 审查计划 JSON 结构

```json
{
  "meta": {
    "project_name": "采购项目A",
    "contract_name": "设备采购合同",
    "client_name": "甲公司",
    "reviewer": "法务张三",
    "party_role": "甲方",
    "review_intensity": "强势",
    "edit_policy": "revise-first"
  },
  "summary": {
    "contract_type": "设备采购合同",
    "parties": {
      "party_a": "甲公司",
      "party_b": "乙公司"
    },
    "contract_amount": "人民币 500 万元",
    "contract_term": "2026-01-01 至 2026-12-31",
    "business_overview": "本合同约定设备供货、安装调试和分阶段验收。",
    "key_milestones": [
      "合同生效后 10 日内支付预付款",
      "设备到场后 5 日内完成初验"
    ],
    "overall_risk": "中风险",
    "core_conclusion": "有条件可签",
    "key_recommendations": [
      "先处理付款节点与验收标准",
      "补充责任上限和不可抗力细化"
    ]
  },
  "findings": [
    {
      "id": "R001",
      "risk_level": "P0",
      "clause": "第8条违约责任",
      "risk": "责任范围明显失衡",
      "suggestion": "补充责任上限并增加例外",
      "action": "auto",
      "target_text": "甲方承担全部责任",
      "recommended_text": "双方各自就其违约行为承担相应责任；任何一方责任以合同总价的 30% 为限。"
    },
    {
      "id": "R002",
      "risk_level": "P1",
      "action": "replace",
      "tag": "w:r",
      "target_text": "五个工作日内付款",
      "occurrence": 1,
      "replacement_text": "十个工作日内付款",
      "comment": "付款周期建议与验收流程匹配。"
    },
    {
      "id": "R003",
      "risk_level": "P1",
      "action": "auto",
      "needs_negotiation": true,
      "selector": {
        "tag": "w:p",
        "line_number": [420, 435],
        "contains": "违约责任"
      },
      "comment": "同文案多处出现时，建议使用 selector 精准定位。"
    },
    {
      "id": "R004",
      "risk_level": "P2",
      "action": "auto",
      "deterministic_edit": true,
      "target_text": "本合同壹式贰份",
      "replacement_text": "本合同一式二份"
    }
  ]
}
```

`action` 支持：`comment` / `report-only` / `delete` / `insert` / `replace` / `auto` / `none`。
未显式提供 `comment` 时，`comment/auto` 会自动生成结构化批注。
`auto` 分流规则：
- 默认策略为 `revise-first`，可通过 `--edit-policy` 或 `meta.edit_policy` 改为 `balanced` / `comment-first`。
- 命中谈判/确认信号（如 `needs_negotiation=true`）时，按 `comment` 执行。
- 命中确定性修订信号（如 `deterministic_edit=true`）且存在改文载荷时，按 `replace/insert/delete` 执行。
- 命中程序优化型、说明型、低必要性信号时，可按 `report-only` 执行，仅写入审查意见书，不写入 Word 正文。
- 在 `revise-first` 下，若未显式提供 `replacement_text`，但提供了可直接落文的 `recommended_text`，系统会先过一层“是否值得直接落文”的收束判断；通过后才会将其提升为直接替换文本。
- 显式动作优先，只有 `action=auto` 时才触发自动判定。

若缺少 `needs_negotiation` / `deterministic_edit`，会在以下时机自动补全：

- 执行 `apply_review_plan.py`（默认自动补全，可用 `--no-enrich-plan` 关闭）
- 执行 `enrich_review_plan.py`（用于生成阶段提前固化补全结果）

可选 `selector` 支持 `tag`、`attrs`、`line_number`、`contains`、`occurrence` 组合定位。
顶层也支持 `occurrence`，用于在重复文本场景下指定第几处命中。
`replace` 的标签优先级为：`selector.tag > finding.tag > action 默认值`。
若 `replace` 未提供 `target_text`，将直接按 `selector` 定位节点替换。
当 `replace/delete` 的目标文本被 Word 拆分到多个 `w:r` 中时，脚本会回退到段落级文本重写，以尽量保持自动化可落地；若同一文本出现多次，仍建议优先提供 `selector` 或 `occurrence` 保持定位确定性。

## Python API（底层可编排）

```python
from scripts import ContractReviewer

reviewer = ContractReviewer("workspace/unpacked")
reviewer.add_comment_by_text("甲方承担全部责任", "P0：责任范围过宽")
reviewer.replace_text(
    old_text="五个工作日内付款",
    new_text="十个工作日内付款",
    tag="w:r",
    comment_text="与验收流程保持一致"
)
reviewer.save()
```

## 独立报告渲染

```bash
python scripts/report/reporting.py \
  --plan /path/to/review-plan.json \
  --execution /path/to/执行日志.json \
  --output /path/to/审查报告.md \
  --output-docx /path/to/审查报告.docx
```

## 回归测试

```bash
PYTHONPATH=contract-copilot python3 -m unittest discover -s contract-copilot/scripts/tests -v
```

PowerShell 包装器的集成测试位于 `scripts/tests/test_apply_review_plan_integration.py`。当本机未安装 `pwsh / powershell` 时，该测试会自动跳过。

高级用法：

- 可通过环境变量 `CONTRACT_COPILOT_CONFIG_DIR` 覆盖本地配置目录，便于测试或多环境隔离。
- 可通过环境变量 `CONTRACT_COPILOT_REVIEW_MEMORY` 与 `CONTRACT_COPILOT_REVIEW_MEMORY_EXAMPLE` 覆盖审查上下文记忆文件路径，便于测试或多环境隔离。
