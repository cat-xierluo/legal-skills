# Skill 质量意见报告

**报告日期**：YYYY-MM-DD  
**审查对象**：`<skill-path>`  
**Skill 名称**：`<skill-name>`  
**审查范围**：发布前验收 / 改造评估 / 第三方审查 / 回归检查  
**审查配置**：通用规则 / 项目规则 / 本地 review profile  
**归档位置**：未归档 / `archive/YYYYMMDD_HHMMSS_<target-slug>/`

## 零、审查单元发现

> 审查对象是仓库或 monorepo 时必须填写；审查对象是已明确的单个 Skill 目录时，可写“单 Skill 目录”。

| 单元路径 | 类型 | 是否纳入本次审查 | 说明 |
|----------|------|------------------|------|
| `<path>` | 单 Skill 目录 / 已确认 Skill / Skill-like 文档 / README 索引项 / 仓库治理文件 | 是 / 否 | `<为什么纳入或排除>` |

## 一、总体意见

**结论**：通过 / 有条件通过 / 暂不通过  
**主要原因**：`<用 1-3 句话说明最关键的质量判断>`

| 维度 | 状态 | 意见摘要 |
|------|------|----------|
| 审查单元发现 | ✅/⚠️/❌ | `<是否正确识别单 Skill、monorepo、Skill-like 文档或普通仓库>` |
| 结构与文件 | ✅/⚠️/❌ | `<目录结构、文件可达性、引用情况>` |
| Frontmatter 与触发 | ✅/⚠️/❌ | `<name / description / 元数据分层>` |
| 配置与隐私 | ✅/⚠️/❌ | `<example、本地配置隔离、公开内容去具体化>` |
| 安全评估 | ✅/⚠️/❌ | `<危险执行、敏感访问、数据外传、凭证、依赖、MCP、提示词安全>` |
| 发布治理 | ✅/⚠️/❌/不适用 | `<LICENSE、CHANGELOG、version、索引同步>` |
| 工作流与输出 | ✅/⚠️/❌ | `<执行步骤、依赖、脚本、输出验收>` |
| 业务流深度 | ✅/⚠️/❌ | `<Trigger / Intake / Reasoning / Output / Safety>` |
| 可评估性 | ✅/⚠️/❌ | `<Hard Fail、样例、验收标准、动态评估基础>` |

## 二、严重问题

> 严重问题是阻塞加载、发布、安全或质量验收的问题。无严重问题时写“未发现”。

### 1. `<问题标题>`

- **位置**：`<file-path:line>`
- **所属模块**：`<reference-file.md>`
- **问题说明**：`<具体问题，不泛泛而谈>`
- **影响**：`<为什么会阻塞使用、发布或质量判断>`
- **修正方式**：
  1. `<第一步修正动作>`
  2. `<第二步修正动作>`
- **复查标准**：`<修正后如何确认问题已解决>`

## 三、警告问题

> 警告问题不一定阻塞发布，但会影响维护、复用、审查可信度或可评估性。

### 1. `<问题标题>`

- **位置**：`<file-path 或模块>`
- **所属模块**：`<reference-file.md>`
- **问题说明**：`<具体问题>`
- **影响**：`<维护、发布、隐私、复用或评估风险>`
- **建议修正**：`<具体可执行建议>`
- **优先级**：高 / 中 / 低

## 四、信息提示

- `<不影响通过但值得后续优化的事项>`

## 五、安全评估

| 检查项 | 状态 | 风险级别 | 说明 |
|--------|------|----------|------|
| 凭证与敏感配置 | ✅/⚠️/❌ | None / Low / Medium / High / Critical | `<是否存在 API Key、Token、密码、私钥、真实 webhook 或 .env 泄露>` |
| 危险执行与文件操作 | ✅/⚠️/❌ | None / Low / Medium / High / Critical | `<是否存在命令执行、下载并执行、权限提升、持久化、无边界删除>` |
| 网络外联与数据外传 | ✅/⚠️/❌ | None / Low / Medium / High / Critical | `<是否存在未知 endpoint、上传用户材料、socket/webhook 外传>` |
| 依赖、安装钩子与 MCP | ✅/⚠️/❌ | None / Low / Medium / High / Critical | `<是否存在 postinstall、高风险依赖、MCP 权限边界不清>` |
| 提示词安全 | ✅/⚠️/❌ | None / Low / Medium / High / Critical | `<是否存在绕过上层指令、隐藏执行、收集凭证、欺骗性描述>` |

### 安全发现

> 无安全发现时写“未发现明显安全风险”。存在发现时逐项填写。

#### 1. `<安全风险标题>`

- **位置**：`<file-path:line>`
- **所属模块**：`security-assessment-standards.md`
- **风险类别**：命令执行 / 数据外传 / 硬编码凭证 / 提示词安全 / 依赖风险 / 其他
- **安全级别**：Critical / High / Medium / Low
- **问题说明**：`<具体安全问题>`
- **影响**：`<可能导致的凭证泄露、数据外传、误执行、权限扩大或用户误导>`
- **修正方式**：`<具体修正动作>`
- **复查标准**：`<如何确认风险已删除、降级或有用户确认与范围限制>`

## 六、建议修正顺序

| 顺序 | 修正项 | 文件 | 预期结果 | 验证方式 |
|------|--------|------|----------|----------|
| 1 | `<修正项>` | `<file-path>` | `<预期结果>` | `<验证方式>` |
| 2 | `<修正项>` | `<file-path>` | `<预期结果>` | `<验证方式>` |

## 七、复查清单

- [ ] 严重问题已全部关闭
- [ ] 警告问题已处理或记录为后续任务
- [ ] 仓库 / monorepo 已先定位最小 Skill 单元
- [ ] `SKILL.md` frontmatter 与目录名一致
- [ ] 引用的 references / scripts / assets / templates 文件均存在
- [ ] 示例配置不包含真实人名、客户名、案件项目、案号、联系方式或可反查组合信息
- [ ] 安全评估已覆盖凭证、危险执行、网络外联、依赖/MCP 和提示词安全
- [ ] 若进入发布流程，LICENSE、CHANGELOG、version、README / Marketplace 已同步
- [ ] 输出流程、验收标准和可评估性说明已补齐

## 八、最终处理意见

`<给出是否建议发布、是否需要二次审查、是否需要先完成指定修正项的结论。>`

## 九、审查依据

- `references/skill-standards.md`
- `references/repository-skill-discovery-standards.md`
- `references/structure-standards.md`
- `references/frontmatter-metadata-policy.md`
- `references/trigger-description-standards.md`
- `references/configuration-privacy-standards.md`
- `references/security-assessment-standards.md`
- `references/publishing-standards.md`
- `references/workflow-output-standards.md`
- `references/business-flow-rubric.md`
- `references/reporting-standards.md`
- `references/archive-standards.md`

## 十、归档说明

- **是否归档**：是 / 否
- **归档目录**：`archive/YYYYMMDD_HHMMSS_<target-slug>/`
- **归档文件**：`quality-opinion-report.md` / `review-metadata.json` / `evidence-index.md`
- **脱敏状态**：已检查 / 不适用 / 待处理
- **复查关系**：首次审查 / 复查，关联上次归档 `<archive-path>`
