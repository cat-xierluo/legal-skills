# Case Bundle 260705: 评估汇总

> 本文件记录 five-question-distill（现 legal-skill-alignment）v0.1.0 在 3 个法律场景上的端到端对齐厘清评估结果（T-001）。

## 场景覆盖

| Case | 领域 | 素材类型 | 素材数量 | 对齐路径 |
|------|------|---------|---------|---------|
| case-01 | 合同 | 样本×2 + SOP×1 | 3 份 | 有素材 |
| case-02 | 诉讼/知产 | 样本×1 + 证据目录×1 | 2 份 | 有素材 |
| case-03 | 合规 | 样本×1 + SOP×1 | 2 份 | 有素材 |

## 五问评估矩阵

| Case | 输入 | 输出 | 逻辑 | 交付 | 知识 | 五标识符 |
|------|------|------|------|------|------|----------|
| 01 | OK | OK | OK | 推断 | OK | OK |
| 02 | OK | OK | 部分推断 | OK | OK | OK |
| 03 | OK | OK | OK | 推断 | OK | 部分(缺stage细分) |

## T-001 断点清单

### B1: 第4问"向谁交付"推断依赖（严重度：中）
- **表现**：Case 01/03 的素材不直接说明终端用户，对齐厘清时从抬头/语气反推
- **根因**：SKILL.md 和 alignment-strategies.md 未定义"素材未覆盖某要素时的补全策略"
- **修复**：SKILL.md 步骤 1A.3 增加"素材未覆盖要素的补全策略"段

### B2: stage 枚举不完整（严重度：中）
- **表现**：Case 03 合规扫描的 stage 无法从现有枚举中选择，只能用 non_litigation
- **根因**：legal-domain-mapping.md 的 stage 枚举偏诉讼/合同，缺合规领域分段
- **修复**：legal-domain-mapping.md 扩展 stage 枚举

### B3: 单样本对齐通用性（严重度：低）
- **表现**：Case 02 只有 1 份样本，alignment-strategies.md 要求 2-3 份但未定义少样本策略
- **根因**：alignment-strategies.md 假设"充足样本"场景
- **修复**：alignment-strategies.md 增加"单样本/少样本处理策略"

### B4: 阈值和判断标准无处安放（严重度：中）
- **表现**：Case 01 的量化阈值（注册资本×5）、Case 03 的主观判断标准无处放
- **根因**：standard-prompt-output.md 模板没有"规则引擎/可配置参数"段
- **修复**：standard-prompt-output.md 增加可选的"规则引擎"段

### B5: 输出格式多样性（严重度：低）
- **表现**：Case 03 用表格输出，模板假设纯文本
- **根因**：standard-prompt-output.md 未说明支持多种输出格式
- **修复**：模板说明中增加"输出格式多样化指引"

### B6: skill-creator 可编译性（严重度：待测）
- **表现**：三个 prompt 五标识符齐全、格式符合模板，但未实测
- **修复**：需要实际喂 skill-creator 验证

## 字段映射检查

| legal-skill-creator 字段 | 映射来源 | Case 01 | Case 02 | Case 03 |
|------------------------|---------|---------|---------|---------|
| skill_family | 标识符 | supplier_service_contract_review | copyright_infringement_agent_statement | app_data_compliance_scan |
| jurisdiction | 标识符 | CN | CN | CN |
| stage | 标识符 | non_litigation | first_instance | non_litigation |
| party_role | 标识符 | buyer_counsel | plaintiff_counsel | compliance_counsel |
| doc_type | 标识符 | contract_review | agent_statement | compliance_report |
| 语料来源 | 三、素材溯源 | 2样本+1SOP | 1样本+证据目录 | 1样本+1SOP |
| 质量过滤标准 | 未明确 | 未填 | 未填 | 未填 |

**映射问题**：质量过滤标准（quality = gold）在所有三个 case 中都缺失——standard-prompt-output.md 模板中"语料来源"有可选标注但 SKILL.md 对齐流程未要求采集此信息。
