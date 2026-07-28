# CHANGELOG

## [1.6.0] - 2026-07-28

### 修复

- **商品清单生成脚本落地（P0-7）**：新增仓库根目录 `script.py`，替换此前 README 与 SKILL.md 中调用但不存在的脚本；内置 openpyxl 缺失提示、模板表头校验、类别（1-45）/类似群（4 位数字）/商品名称非空校验、禁止静默覆盖（需 `--force` 显式覆盖）；同步更新 SKILL.md 代码示例与 README 安装说明，消除对未定义 `goods_list` 的依赖。
- **尼斯分类 NCL13 眼镜迁移残留（P0-5）**：清除 `class-09.md` 顶部“本类尤其包括”中残留的“眼镜，隐形眼镜”“眼镜套”，与 `class-10.md` 已收入的 1011 眼镜及附件类似群对齐；其余类的全量 transfer/delete 复核留作后续。
- **输入清单补官方检索证据字段（P0-4）**：`service-intake-checklist.md` 新增“官方在先商标检索证据”段（检索来源、时间、检索式、覆盖类别、申请主体、Vienna 图形要素、检索结论）；缺失时显式标注“未检索/不可评级”，为相对理由门禁留接口。
- **发布版本同步（P0-8）**：根 `.claude-plugin/marketplace.json` 与根 `README.md` 的 trademark-assistant 版本 1.5.4 → 1.6.0；下载标“待发布”，不提前写入未构建的 zip 链接；最近更新区补 v1.6.0 记录。
- **商标说明口径修正（P0-1）**：删除“所有商标申请均需撰写商标说明”的错误口径，改为按商标类型判断，并补充外文商标、三维标志、颜色组合、声音标志等特殊类型填写要求；明确“显著性属需举证的法律判断，不在商标说明中认定”；删除指南中“通过长期使用已具备显著性”“两部分均需保护”等易误导模板。
- **服务主体表述弱化（P0-2）**：由“由中国执业律师提供法律服务支持”改为“由杨卫薪律师维护（作者为中国执业律师）”，明确输出为初步研判、不替代律师/代理机构正式意见、不当然形成律师委托关系。
- **可注册性拆分与未检索门禁（P0-3）**：相对理由评估明确为“须以官方在先商标检索证据为前提”，未检索时标“未检索/不可评级”且总体不得评低风险；output-contract 风险等级拆为绝对/相对/总体三行；低风险定义收紧为“绝对无碍 + 相对有检索证据”两者缺一不可。

### 备注

- 本轮覆盖 P0 的硬缺陷（P0-7/5/4/8）与法律口径（P0-1/2/3）；仅余 P0-6（法源治理与 2027 法律切换）留作后续里程碑。
- NCL13 全量迁移复核、benchmark 与领域 checker 仍未完成，质量标记维持 `NOT_VERIFIED`。

## [1.5.5] - 2026-07-27

### 文档完善

- 2026-07-28：完成一轮 skill-lint 快速审计，将法律口径、在先检索证据门禁、NCL13 数据迁移残留、Excel 可执行性、2027 法律切换、法源治理、隐私归档、发布同步与可评估性升级路线记录到 `TASKS.md` 和 `DECISIONS.md`；本次未修改运行行为，质量状态为 `NOT_VERIFIED`

### 修复

- **核心流程索引路径断裂**：修正 `references/classification-planning-guide.md` 与 `references/registrability-prescreen-guide.md` 中残留的 `legal-basis/` 路径前缀，恢复对尼斯分类索引与商标审查审理指南索引的可达性
- **README 微信二维码 URL**：补回 `docs/` 前缀，修正 raw.githubusercontent 链接 404

### 改进

- **商标说明图像分析工具表**：移除环境专属的 `mcp__MiniMax__understand_image`，改为 `Read` 首选 + `mcp__zai-mcp-server__analyze_image` 备选，降低对特定 MCP 的硬依赖
- **依赖说明统一**：openpyxl 统一为 `uv run --with openpyxl` 按需运行，消除 SKILL.md 与 README.md 之间 pip/uv 不一致；同步修正"系统依赖"表自相矛盾表述
- **订正历史 license 措辞**：1.5.1 条目由 CC BY-NC-SA 4.0 更正为实际的 CC BY-NC 4.0

### 移除

- 删除过时的尼斯分类 NCL12-2025 旧版目录（约 1.1M）及 SKILL.md / README.md / legal-basis-index.md 中的关联引用，避免双版本并行带来的检索歧义

## [1.5.4] - 2026-04-10

### 修复

- **无效引用移除**：从 `SKILL.md` 的关键参考资料中移除不存在的 `README.md` 引用，避免误导执行路径

### 文档完善

- `SKILL.md` 当前关键参考资料统一收敛到 `references/` 与 `templates/` 下的实际存在文件
- 2026-04-22：按独立仓库 README 新规范重写首页，补充中国商标申请定位、典型咨询场景、申请材料产物、安装依赖、使用边界、核心设计、关键文件、Legal Skills 关联项目导流、作者联系入口和微信二维码

## [1.5.3] - 2026-03-24

### 新增

- 新增"适用范围"章节，明确本技能的适用边界：
  - 主要适用于中国大陆商标注册申请
  - 法律依据均为中国国内法律法规
  - 类别规划部分可适用于国际商标申请（尼斯分类为国际标准）
  - 可注册性初筛等法律判断内容仅适用于中国商标申请
  - 服务主体为中国执业律师，仅具备中国大陆法律服务资质

### 改进

- 更新 description 字段，明确"面向中国商标申请"和"基于尼斯分类（国际商标分类），引用中国法律法规"

## [1.5.2] - 2026-03-24

### 修正

- 版本号更新，用于重新发布到 ClawHub

## [1.5.1] - 2026-03-24

### 修正

- 更新 license 为 CC BY-NC 4.0（非商业用途授权）

## [1.5.0] - 2026-03-24

### 新增

- **商标说明撰写功能**：新增商标说明输出模块，支持申请材料准备阶段
- **图形商标分析流程**：对于图形/组合商标，集成图像理解工具（MCP）分析商标设计特征
- **商品清单生成**：基于官方模板 `templates/导入商品信息.xlsx` 生成可导入商标系统的 Excel 文件
- **申请材料归档**：新增 `archive/` 目录结构，支持申请方案、商品清单、商标说明的归档

### 改进

- **执行流程重构**：分为两阶段
  - 阶段一：咨询与规划（类别规划、可注册性初筛）
  - 阶段二：申请材料准备（商品清单、商标说明、归档）
- **触发条件扩展**：新增"客户已确定设计方案，需要撰写商标说明"和"需要准备商标申请材料"两个触发场景

### 文档完善

- 更新 `SKILL.md`：新增商标说明撰写、图形商标分析流程、商品清单输出格式等章节
- 更新 `references/trademark-description-guide.md`：
  - 新增"图形/组合商标分析流程"专节
  - 新增图像理解工具使用说明（`mcp__zai-mcp-server__analyze_image` 等）
  - 新增分析提示词模板和设计特征描述技巧
- 新增 `templates/导入商品信息.xlsx`：官方商品清单导入模板

### 依赖

- 新增 Python 包依赖：`openpyxl`（用于生成 Excel 商品清单）

## [1.4.6] - 2026-02-08

### 修复

- 修复 `references/legal-basis/trademark-infringement-criteria-interpretation-and-application.md` 案例21中的明显 OCR 错句，恢复段落可读性
- 修复“信息不足时风险等级输出”规则冲突：统一使用“待补充（信息不足，暂不评级）”

### 文档完善

- 同步更新 `SKILL.md`、`references/output-contract.md`、`references/service-intake-checklist.md`、`references/registrability-prescreen-guide.md` 的风险口径
- 在 `DECISIONS.md` 新增本轮决策（D018），在 `TASKS.md` 新增并勾选本轮任务

## [1.4.5] - 2026-02-08

### 改进

- 取消“双轨交付”，统一为单一 Markdown 结构化报告
- `references/output-contract.md` 删除结构化 JSON 交付块，避免执行分叉

### 文档完善

- `SKILL.md`、`README.md` 同步更新为“仅输出一个版本”
- 在 `DECISIONS.md` 新增本轮决策（D017），在 `TASKS.md` 新增并勾选本轮任务

## [1.4.4] - 2026-02-08

### 改进

- 明确交付采用“双轨”：客户正式版仅输出 Markdown，内部留档/系统对接版可附加结构化 JSON
- 将 `references/output-contract.md` 的结构化区块调整为“仅内部版，可选”，避免正式文档出现 JSON

### 文档完善

- `SKILL.md`、`README.md` 同步补充“正式版不含 JSON”的约束说明
- 在 `DECISIONS.md` 新增本轮决策（D016），在 `TASKS.md` 新增并勾选本轮任务

## [1.4.3] - 2026-02-08

### 改进

- 将“免责声明 + 升级建议”从可选提示升级为每次交付的强制输出要求
- 在高风险与复杂争议场景中新增律师咨询引导：杨卫薪律师（微信 `ywxlaw`）

### 技术优化

- 在 `references/output-contract.md` 的结构化 JSON 中新增 `escalation` 字段组，支持自动化流程识别升级动作

### 文档完善

- `SKILL.md`、`references/registrability-prescreen-guide.md`、`README.md` 同步补充升级建议与律师咨询入口说明
- 在 `DECISIONS.md` 新增本轮决策（D015），在 `TASKS.md` 新增并勾选本轮任务

## [1.4.2] - 2026-02-08

### 改进

- 修复 `references/classification-planning-guide.md` 与 `references/registrability-prescreen-guide.md` 的索引路径写法，统一为相对 `references/` 目录可点击路径
- `SKILL.md` 精简为“索引入口优先”，不再展开审查指南与尼斯分类分文件范围

### 技术优化

- 在 `references/output-contract.md` 新增结构化 JSON 交付块，固定字段键名与风险等级枚举，便于自动化复用

### 文档完善

- `README.md` 明确承接 chapter/class 分文件范围说明
- 在 `DECISIONS.md` 新增本轮优化决策（D014），在 `TASKS.md` 新增并勾选本轮优化任务

## [1.4.1] - 2026-02-08

### 改进

- Skill 英文标识由 `trademark-intelligent-assistant` 调整为 `trademark-registration-assistant`
- 技能目录同步更名为 `skills/trademark-registration-assistant`

### 文档完善

- `SKILL.md` 的 `name` 字段同步改为 `trademark-registration-assistant`
- `README.md` 标题与目录树名称同步更新
- 在 `DECISIONS.md` 新增更名决策（D013），在 `TASKS.md` 新增并勾选本次更名任务

## [1.4.0] - 2026-02-08

### 新增

- 新增尼斯分类 2026 版本目录：`references/legal-basis/nice-classification-v13-2026/`
- 新增 2026 版本总索引：`references/legal-basis/nice-classification-v13-2026/nice-classification-v13-2026-index.md`

### 改进

- 基于国家知识产权局 NCL13-2026 官方对照表完成批量迁移，覆盖编码项改名、编号调整、删项与增项
- 在对应类似群补充 `2026 增加项（NCL13）` 与 `2026 修订备注（NCL13）`，增强可追溯性与检索性

### 技术优化

- 迁移流程改为直接解析官方 PDF 文本，降低本地 OCR 断行噪声对更新准确性的影响
- 保留 `nice-classification-v12-2025/` 作为历史回溯版本，形成双版本并行结构

### 文档完善

- 默认引用路径切换到 `v13-2026`：`SKILL.md`、`README.md`、`references/classification-planning-guide.md`、`references/legal-basis/legal-basis-index.md`
- 在 `DECISIONS.md` 新增迁移决策（D012），在 `TASKS.md` 新增并勾选本次迁移任务

## [1.3.4] - 2026-02-08

### 改进

- 将 3 个通用 `index.md` 重命名为语义化索引文件，便于快速区分与检索：
  - `references/legal-basis/index.md` → `references/legal-basis/legal-basis-index.md`
  - `references/legal-basis/trademark-examination-and-adjudication-guidelines/index.md` → `references/legal-basis/trademark-examination-and-adjudication-guidelines/trademark-examination-and-adjudication-guidelines-index.md`
  - `references/legal-basis/nice-classification-v12-2025/index.md` → `references/legal-basis/nice-classification-v12-2025/nice-classification-v12-2025-index.md`

### 文档完善

- 同步更新 `SKILL.md`、`README.md`、`references/legal-basis/legal-basis-index.md`、`references/classification-planning-guide.md`、`references/registrability-prescreen-guide.md` 的索引引用路径
- 在 `DECISIONS.md` 新增索引语义化命名决策（D011）
- 在 `TASKS.md` 新增并勾选本次索引命名优化任务

## [1.3.3] - 2026-02-08

### 改进

- 将审查指南目录由 `references/legal-basis/trademark-examination-and-adjudication-guidelines-20220101/` 重命名为 `references/legal-basis/trademark-examination-and-adjudication-guidelines/`
- 同步移除审查指南索引与章节标题中的 `(20220101)` 后缀，统一命名风格

### 文档完善

- 同步更新 `SKILL.md`、`README.md`、`references/legal-basis/legal-basis-index.md`、`references/registrability-prescreen-guide.md` 的引用路径
- 在 `DECISIONS.md` 新增目录去日期后缀决策（D010）
- 在 `TASKS.md` 新增并勾选本次命名精简任务

## [1.3.2] - 2026-02-08

### 改进

- 对尼斯分类与审查指南分文件执行第二轮排版精修，统一标题空格、注释块结构与段落断句风格
- 将超长注释行改为分条呈现（重点优化 `class-37.md` 的跨类似群注释），提升可读性与检索定位效率

### 修复

- 修复 OCR 导致的数字断裂（如 6 位编码被拆为 `5+1`）及个别标题/正文粘连问题（如 `chapter-27.md`）
- 清理残留的孤立 `##`/`###` 标记行，避免 Markdown 结构噪音

### 技术优化

- 完成二次质量校验：`class-01.md` 至 `class-45.md`、`chapter-01.md` 至 `chapter-43.md` 文件完整，类号标题一致
- 将尼斯分类与审查指南分文件的 `long_lines_gt260` 降为 `0`，降低上下文加载与人工复核成本

### 文档完善

- 在 `DECISIONS.md` 新增排版精修决策（D009）
- 在 `TASKS.md` 新增并勾选“第二轮精修排版”任务

## [1.3.1] - 2026-02-08

### 修复

- 完成尼斯分类分文件完整性校验：`class-01.md` 至 `class-45.md` 均存在且类号一致，无跨类串档
- 修复尼斯分类分文件中 OCR 导致的中文词内断行与空白行断词问题，提升检索与阅读连贯性

### 技术优化

- 对审查指南分章节文件执行同一套保守断行清洗策略，降低跨行断词噪声
- 保留分章节/分类目录结构与原有索引路径，不改变调用入口

### 文档完善

- 在 `DECISIONS.md` 增补 OCR 清洗与完整性校验决策（D008）
- 在 `TASKS.md` 增补并勾选本次质量校验任务

## [1.3.0] - 2026-02-08

### 新增

- 新增审查指南分文件目录：`references/legal-basis/trademark-examination-and-adjudication-guidelines/`
- 新增审查指南总索引：`references/legal-basis/trademark-examination-and-adjudication-guidelines/trademark-examination-and-adjudication-guidelines-index.md`

### 改进

- 将审查指南总表拆分为 43 个章节文件（`chapter-01.md` 至 `chapter-43.md`），支持按章按需读取
- 依据检索流程改为“先索引、再定向读取章节文件”，减少上下文消耗

### 文档完善

- 更新 `SKILL.md`、`README.md`、`references/legal-basis/legal-basis-index.md` 的新路径和使用说明
- 在 `DECISIONS.md` 追加拆分决策记录（D007）

### 技术优化

- 删除原始超长审查指南文件，降低单文件读取成本，提高检索效率

### 待办事项

- 视高频咨询场景补充“审查指南章节到风险类型”的映射索引

## [1.2.0] - 2026-02-08

### 新增

- 新增尼斯分类分文件目录：`references/legal-basis/nice-classification-v12-2025/`
- 新增尼斯分类总索引：`references/legal-basis/nice-classification-v12-2025/nice-classification-v12-2025-index.md`
- 新增法律依据总索引：`references/legal-basis/legal-basis-index.md`

### 改进

- 将尼斯分类总表拆分为 45 个类别文件（`class-01.md` 至 `class-45.md`），支持按类按需读取
- 类别规划流程改为“先索引、再定向读取类别文件”，减少上下文消耗

### 文档完善

- 更新 `SKILL.md`、`README.md`、`references/classification-planning-guide.md` 的新路径和使用说明
- 在 `DECISIONS.md` 追加拆分决策记录（D006）

### 技术优化

- 删除原始超长总表文件，降低单文件读取成本，提高检索效率

### 待办事项

- 视使用频率补充服务类（35-45）快捷索引模板
- 评估是否对侵权判断标准补充“情形到条款”反向索引

## [1.1.2] - 2026-02-08

### 改进

- 将 `references/legal-basis/` 下的法律依据文件名统一改为英文语义命名，提升跨平台与跨终端兼容性

### 文档完善

- 更新 `SKILL.md` 中法律依据示例引用为英文文件名
- 在 `DECISIONS.md` 追加依据文件命名规范化决策记录（D005）

### 技术优化

- 通过统一英文文件名减少编码与路径转义问题，便于自动化脚本和插件市场消费

## [1.1.1] - 2026-02-08

### 改进

- 删除 `archive/` 下的历史资料与本地环境残留文件，简化技能目录结构

### 文档完善

- 更新 `README.md` 的目录结构与说明，移除对 `archive/` 的引用
- 在 `DECISIONS.md` 追加目录清理决策记录（D004）

### 技术优化

- 保留服务化主路径：`SKILL.md` + `references/` + 协作文档，减少非必要上下文噪音

## [1.1.0] - 2026-02-07

### 新增

- 新增服务化参考文档：
  - `references/service-intake-checklist.md`
  - `references/classification-planning-guide.md`
  - `references/registrability-prescreen-guide.md`
  - `references/output-contract.md`

### 改进

- 将 Skill 核心能力从 Coze 部署导向改为通用服务导向，支持直接执行商标类别规划与可注册性初筛
- 将知识依据目录统一为 `references/legal-basis/`，与服务规则分离

### 文档完善

- 重写 `SKILL.md`，明确触发条件、输入要求、执行流程、输出要求和服务边界
- 重写 `README.md`，明确“非 Coze 依赖”的使用方式
- 在 `DECISIONS.md` 追加去 Coze 化决策记录（D003）

### 技术优化

- 将 Coze 历史资料归档到 `archive/legacy-coze/`，减少主流程上下文噪音
- 将本地环境残留文件归档到 `archive/local-artifacts/`，清理技能根目录结构

### 待办事项

- 增补脚本化工具以支持标准化输出
- 建立案例回归测试与版本验收机制

## [1.0.1] - 2026-02-07

### 改进

- 统一 Skill 英文标识：目录名由 `skills/商标智能助手` 调整为 `skills/trademark-intelligent-assistant`
- `SKILL.md` 的 `name` 字段同步改为 `trademark-intelligent-assistant`，保持与目录名一致

### 文档完善

- 同步修正 `README.md`、`TASKS.md` 的路径与命名引用
- 在 `DECISIONS.md` 追加命名标准化决策记录（D002）

## [1.0.0] - 2026-02-07

### 新增

- 新增 `SKILL.md`，定义技能触发场景、输入要求、工作流、输出模板与合规边界
- 新增协作文档：`DECISIONS.md`、`TASKS.md`、`CHANGELOG.md`
- 新增 `LICENSE.txt`，补充技能许可说明

### 改进

- 将原资料目录重构为 `references/knowledge-base/`、`references/coze-config/`、`references/implementation/` 三层结构

### 文档完善

- 重写 `README.md` 为 Skill 入口文档，提供使用路径与资料索引

### 技术优化

- 保留原始资料内容，仅做目录重排，降低迁移风险并提升可追溯性

### 待办事项

- 增补脚本化工具以支持标准化输出
- 建立案例回归测试与版本验收机制
