# 变更日志

## [0.2.5] - 2026-04-19

### 改进

- 精简目录结构：12 目录 → 9 目录，68 文件 → 63 文件
- 扁平化 `assets/output-templates/` → `assets/template-*.md`，消除不必要的二级目录
- 扁平化 `references/industry/` → `references/industry-*.md`，加前缀区分
- 扁平化 `references/local-policies/opc/` → `references/local-policies/opc-*.md`，消除三级嵌套
- 删除 4 个冗余子目录 README（examples/evals/industry/output-templates）
- 删除 `assets/compliance-quick-ref.md`，消除与 references/ 的知识重复，改为直接加载对应核心领域文件

### 移除

- `DISCLAIMER.md`（免责声明已整合到 SKILL.md 和 README.md）
- `examples/README.md`、`evals/README.md`、`references/industry/README.md`、`assets/output-templates/README.md`

### 文档完善

- 2026-04-22：按独立仓库 README 新规范重写首页，强化 OPC / AI 小微企业法律顾问定位、典型咨询场景、输出产物、安装方式、边界责任、核心设计、质量支撑、关键文件、Legal Skills 关联项目导流、作者联系入口和微信二维码

## [0.2.4] - 2026-04-19

### 新增

- 新增 `evals/assertions.json`，为 10 条重点评测样本沉淀 40 条机器可读断言
- 新增 `scripts/check-evals.py`，支持评测样本结构检查、路径存在性检查和可选回答文本断言检查

### 改进

- 将评测体系从“样本 + 人工评分”推进到“样本 + 人工评分 + 机器可读断言 + 半自动检查脚本”
- 更新 `evals/README.md`，补充断言文件结构、脚本运行方式和回答文件约定
- 更新 `README.md`，补充机器可读断言与评测脚本入口
- 同步 `SKILL.md` 与 `evals/evals.json` 版本号到 `0.2.4`

### 技术优化

- `scripts/check-evals.py` 仅使用 Python 标准库，不引入额外依赖
- 在 `SKILL.md` 依赖章节说明脚本运行所需的 Python 3 环境

### 待办事项

- 用真实回答跑一轮断言检查，并根据误判情况校准关键词
- 继续处理原始 OCR 归档和地方覆盖层

## [0.2.3] - 2026-04-19

### 新增

- 新增 `evals/manual-review.md`，为 10 条重点评测样本提供 10 分制人工评分说明
- 在人工评分说明中增加硬失败条件，用于识别地方规则误用、单领域割裂回答、未触发升级等严重问题

### 改进

- 更新 `evals/README.md`，将 `manual-review.md` 纳入评测体系
- 更新 `README.md`，补充重点样本人工评分说明入口
- 同步 `SKILL.md` 版本号到 `0.2.3`

### 文档完善

- 更新 `TASKS.md`，将重点样本人工评分说明标记完成
- 更新 `DECISIONS.md`，记录先补人工评分说明、暂不继续扩题的原因

### 待办事项

- 继续补机器可读断言或半自动化评测脚本
- 继续处理原始 OCR 归档和地方覆盖层

## [0.2.2] - 2026-04-19

### 改进

- 将 `references/ip.md`、`references/employment.md`、`references/data-compliance.md`、`references/regulatory.md`、`references/disputes.md` 统一为“负责范围 / 关键事实 / 分析方法 / 联动领域 / 风险信号 / 定向检索指引 / 升级条件”结构
- 将 `evals/evals.json` 从 18 条扩充到 24 条，补充 IP、劳动、数据、监管、争议和跨领域综合判断场景
- 同步 `SKILL.md` 版本号到 `0.2.2`

### 文档完善

- 更新 `README.md`，同步当前评测样本规模和后续完善方向
- 更新 `TASKS.md`，将全部核心领域 reference 结构统一和 24 条评测样本标记完成
- 更新 `DECISIONS.md`，记录“先统一全部核心领域结构，再补断言”的阶段性决策

### 待办事项

- 为重点评测样本补充人工评分说明或断言
- 清理原始 OCR 归档或进一步隔离其读取入口
- 继续补地方覆盖层和更多行业 overlay

## [0.2.1] - 2026-04-19

### 改进

- 将 `SKILL.md` frontmatter 的许可证字段从 `CC-BY-NC-SA-4.0` 调整为 `CC-BY-NC`
- 将 `references/contracts.md` 与 `references/tax.md` 重写为“负责范围 / 关键事实 / 分析方法 / 联动领域 / 风险信号 / 定向检索指引 / 升级条件”的统一结构
- 将 `evals/evals.json` 从 12 条扩充到 18 条，并为重点样本补充下一跳与样稿映射字段

### 文档完善

- 更新 `README.md`，同步许可证与评测规模说明
- 更新 `TASKS.md`，将样稿映射、成长阶段与行业 overlay 评测接入标记完成
- 更新 `DECISIONS.md`，记录许可证切换与评测协议扩展的原因
- 更新 `evals/README.md`，补充 `expected_next_hop` 与 `recommended_assets` 字段说明

### 待办事项

- 继续把其余核心领域文件统一成“分析方法 + 联动领域 + 定向检索指引”结构
- 将评测样本扩充到 20-30 条，并补人工评分说明
- 继续扩充地方覆盖层和行业场景包

## [0.2.0] - 2026-04-18

### 新增

- 新增 `references/growth-financing.md`，作为成长阶段专项模块，处理融资分诊、股权激励、顾问股 / 干股 / 期权 / 技术入股问题
- 新增 `references/industry/` 目录与 `ai-saas.md`、`ecommerce.md`、`agency-outsourcing.md` 三个首批行业场景包
- 新增 `examples/` 目录与 3 个公开示例问题，便于 GitHub 访客快速理解 skill 的输出方式

### 改进

- 更新 `SKILL.md`，把 skill 进一步收口为“法律分诊 + 综合分析 + 定向检索编排器”
- 在执行流程中新增“下一跳协议”，明确核心领域、成长阶段模块、行业 overlay、地方覆盖层、输出资产和官方核验的调用顺序
- 在 `README.md` 中补充成长阶段模块、行业 overlay 和 examples 入口

### 文档完善

- 更新 `TASKS.md`，将成长阶段模块、行业 overlay、公开 examples 和下一跳协议标记完成
- 更新 `DECISIONS.md`，记录“不要继续堆 FAQ，而是引入专项模块与 overlay”的架构决策
- 同步 `evals/evals.json` 版本号到 `0.2.0`

### 待办事项

- 将成长阶段模块与行业 overlay 补进评测样本
- 继续把现有核心领域文件统一成“分析方法 + 联动领域 + 定向检索指引”结构
- 继续扩充地方覆盖层和行业场景包

## [0.1.7] - 2026-04-18

### 改进

- 更新 `SKILL.md`，明确“领域只是分析视角，不是答案边界”，要求复杂问题按全盘视角做跨领域综合判断
- 更新多领域路由规则，将内部分析进一步区分为主领域、联动领域和核验领域
- 在质量要求中加入“不得按单一领域孤立回答跨领域经营问题”

### 文档完善

- 更新 `TASKS.md`，新增成长阶段模块、行业 overlay 和领域结构统一化的后续任务
- 更新 `DECISIONS.md`，记录“全盘视角优先”的架构调整

### 待办事项

- 增加融资 / 股权激励分析框架
- 增加行业化场景包
- 扩充可验证跨领域综合判断的评测样本

## [0.1.6] - 2026-04-18

### 新增

- 新增 `README.md`，作为面向 GitHub 访客的公开入口文档
- 补充使用边界与免责说明

### 改进

- 调整 `SKILL.md` 参考文件引用，精简非核心法律内容
- 更新 `SKILL.md` 版本号与最后更新时间，恢复“以法律工具为核心”的对外定位

### 文档完善

- 更新 `TASKS.md`，记录开源发布文档补齐情况
- 更新 `DECISIONS.md`，记录内容精简与定位调整的决策

### 待办事项

- 增加公开示例问题或 `examples/` 目录
- 继续扩充评测样本和地方覆盖层

## [0.1.5] - 2026-04-11

### 新增

- 新增 `references/business-context.md`，整合 OPC 创业者画像与经营场景分析
- 新增 `references/local-policies/opc/06-姑苏区专项政策.md`，含姑苏区最高 200 万奖励、沧浪街道赋能平台、OPC 创业人才贷（交行/工行）详情

### 改进

- 更新 `references/local-policies/opc/01-国家政策背景.md`，补充江苏省省级政策（省人社厅提案、算力网络、省级基金）、沧浪街道赋能平台、OPC 创业人才贷等增量内容
- 更新 `references/local-policies/opc/00-使用说明.md`，将 06-姑苏区专项政策.md 纳入读取顺序
- 更新 `SKILL.md` 参考文件列表，纳入新增文件，版本升至 0.1.5

### 待办事项

- 继续扩充地方 OPC 资料（其他城市/省份）
- 评测样本扩容到 20-30 条

## [0.1.4] - 2026-04-10

### 新增

- 新增 `assets/output-samples/README.md`，统一说明标准输出样稿的用途和组合方式
- 新增 `assets/output-samples/ai-launch-report.md`，提供 AI 产品上线核查样稿
- 新增 `assets/output-samples/opc-separation-report.md`，提供公私分离体检 / 补救样稿
- 新增 `assets/output-samples/contract-review-report.md`，提供合同审查意见样稿

### 改进

- 更新 `SKILL.md`，把标准输出样稿接入资产调用规则和输出资产列表
- 将“AI 产品上线”“公私分离体检”“合同审查”三类高频场景从抽象输出协议进一步落成可复用样稿

### 文档完善

- 更新 `TASKS.md`，将三套标准输出样稿标记完成，并新增后续联动任务
- 更新 `DECISIONS.md`，记录将样稿独立收拢到 `assets/output-samples/` 的决策

### 待办事项

- 将标准输出样稿与评测样本建立映射
- 视使用频率补更多分诊 / 应对样稿

## [0.1.3] - 2026-04-10

### 新增

- 新增 `evals/evals.json`，建立首批 12 条评测样本
- 新增 `evals/README.md`，说明评测样本的分层结构和使用方式

### 改进

- 将评测样本明确拆分为 `foundation`（小微企业基础盘）和 `reinforcement`（OPC / AI 强化层）两组
- 为每条样本补充预期路由、地方覆盖层预期、升级边界预期和回答要点，便于后续做回归检查
- 更新 `SKILL.md`，补充评测样本入口并同步版本号

### 文档完善

- 更新 `TASKS.md`，将首批 12 条评测样本落地并保留后续扩容任务
- 更新 `DECISIONS.md`，记录采用“先定型 12 条，再扩充到 20-30 条”的评测建设策略

### 待办事项

- 将评测样本继续扩充到 20-30 条
- 为重点场景补充断言或人工评分说明

## [0.1.2] - 2026-04-10

### 改进

- 将地方 OPC 资料目录从 `references/opc-policy/` 进一步收拢为 `references/local-policies/opc/`
- 更新 `SKILL.md`，明确地方覆盖层统一从 `references/local-policies/opc/` 加载
- 新增地方资料目录说明文件，降低后续代理误把地方政策当成全国规则的风险

### 文档完善

- 更新 `DECISIONS.md`，记录地方资料目录重构决策
- 更新 `TASKS.md`，同步地方目录结构调整

### 待办事项

- 按城市 / 省份继续扩充地方 OPC 资料

## [0.1.1] - 2026-04-09

### 改进

- 将技能定位进一步校正为“**小微企业基础盘 + OPC/AI 专项层**”，明确基础治理、股权、合同、税务、劳动等内容仍是默认骨架
- 更新 `SKILL.md`，新增“双层定位”和“先看基础盘，再看 OPC 增量”的处理原则
- 补强 `references/governance.md`，新增联合创始人、技术入股、代持、股权安排等高频治理问题

### 文档完善

- 更新 `DECISIONS.md`，记录定位从“OPC 专项优先”调整为“双层定位”的原因

### 待办事项

- 在评测样本中同时覆盖基础盘问题和 OPC 专项问题

## [0.1.0] - 2026-04-09

### 新增

- 新增 `references/ai-compliance.md`，将 AI 产品上线、公示、标识、备案 / 登记核验、投诉处置独立成领域
- 新增 `references/opc-policy/05-青岛指引-结构化摘录.md`，替代直接读取原始 OCR
- 新建技能级 `TASKS.md`、`DECISIONS.md`、`CHANGELOG.md`、`LICENSE.txt`

### 改进

- 重写 `SKILL.md`，建立定位、输入协议、输出协议、多领域路由和升级边界
- 将地域规则改为“全国基线 + 地方覆盖层”
- 将 `references/data-compliance.md` 改为更贴近中国法语境的表达，删除容易误导的固定时限口径
- 将 `references/governance.md` 聚焦到 OPC 高频治理问题
- 更新 `assets/risk-checklist.md`，新增 OPC 红线和 AI 产品上线检查项
- 更新 `assets/compliance-quick-ref.md`，补充 AI 专项规则并删除高时效性税率数字

### 技术优化

- 修正原技能“写 9 个领域、实际 8 个”的结构错误
- 明确 `04-青岛OPC合规指引全文.md` 仅作为 OCR 归档，不再默认直接加载
- 将回答目标从“知识堆叠”收敛为“结论 + 缺口 + 风险 + 动作 + 升级边界”

### 待办事项

- 增加评测样本
- 增加标准输出样稿
- 后续移除原始 OCR 文件
