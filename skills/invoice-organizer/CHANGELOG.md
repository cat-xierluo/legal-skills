## [0.1.1] - 2026-06-22

### 改进
- 更名 invoice-reimbursement → invoice-organizer（原 reimbursement 窄化为报销，organizer 涵盖识别+归档+清单全流程且不限于差旅，见 DECISIONS D2）
- 精简 frontmatter description，下沉执行细节（提取字段/回溯上下文/填事由/切换清单形态）到正文
- frontmatter 补 version 字段并升至 0.1.1，与 CHANGELOG 同步
- 新增「验收标准」节：Hard Fail 5 条 + 可机判完成条件 + 典型场景自检，补齐可评估性

### 修复
- 去具体化：示例与文档中的真实人名/发票号/酒店名/案件名/微信号替换为占位符

## [0.1.0] - 2026-06-21

### 新增
- 发票 PDF 文本提取脚本（`scripts/extract_invoice.py`，pdftotext 封装，批量提取，缺失依赖优雅提示）
- 铁路电子客票、增值税电子普通发票（住宿/服务）字段识别指南（`references/invoice-field-guide.md`）
- 按购买方抬头匹配所属项目并复制归档（不移动原件）
- 清单生成（默认报销清单，可切换消费清单/对账流水等）：报销信息表 + 凭证明细表（序号/日期/类型/摘要/金额/发票号）+ 合计
- 默认输出风格规范（`references/output-template.md`）：无 emoji、无说明性备注、人名不带证件号、文件名 YYMMDD 前缀、类型不限于差旅
- 向上回溯读取项目上下文，自动填补报销信息（事由/案号/日期/路线），脚本 `scripts/find_project_context.py` + `references/project-context-guide.md`
