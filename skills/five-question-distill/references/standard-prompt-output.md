# 标准 Prompt 输出模板

本文档定义本 Skill 的最终产出格式——一份可被 `legal-skill-creator` 直接消费的标准 prompt。对应 SKILL.md 步骤 3。

## 输出模板

```markdown
# Skill 编译请求：{skill_name 中文名}

> 以下 prompt 由 five-question-distill 蒸馏产出，请调用 legal-skill-creator 编译为正式 Skill。

## 一、标识符（必填，对齐 legal-skill-creator 第二章）

- **skill_family**：{kebab-case 英文标识，如 ip_copyright_demand_letter}
- **jurisdiction**：{CN / HK / US / ...}
- **stage**：{pre_litigation / first_instance / second_instance / enforcement / non_litigation / ...}
- **party_role**：{rights_holder_counsel / defendant_counsel / licensee_counsel / ...}
- **doc_type**：{demand_letter / complaint / answer / contract_review / due_diligence_report / ...}

## 二、五问要素

### 1. 输入什么（Inputs）

**必要输入**：
- {输入项 1，含格式要求}
- {输入项 2}

**可选输入**：
- {可选项 1}

**信息来源**：{用户上传 / 公开检索 / 律所内部库}

### 2. 输出什么（Outputs）

**主要产出**：{产出名}
**格式要求**：{章节结构 / 字数 / 抬头落款}
**质量标准**：{什么算"做得好"，可量化的标准}

### 3. 处理逻辑（Workflow）

**主流程**：
1. {步骤 1}
2. {步骤 2}
   - 决策点：{条件} → {分支 A / 分支 B}
3. {步骤 3}
   - 质量检查点：{谁 review 什么}

**异常路径**：
- {异常 1} → {应对}

### 4. 向谁交付（Context.Delivery）

**终端用户角色**：{律师同行 / 客户 / 法官 / 对方}
**触发场景**：{什么情况下用这个 Skill}
**语气基调**：{正式威慑 / 平和可读 / 中性专业}

### 5. 需要哪些知识支撑（Knowledge Base）

**法律依据**：
- {法条 / 司法解释，精确到条}

**范本来源**：
- {内部范本 / 公开模板，路径或描述}

**风险清单**：
- {风险点 1}
- {风险点 2}

**风格偏好**：
- {用词 / 句式 / 语气特征}

## 三、素材溯源（可选）

- 样本来源：{N 份，路径或描述}
- SOP 来源：{路径或描述}
- Q&A 来源：{路径或描述}

## 四、待确认清单

- [ ] {要素}：{为什么待确认 + 建议补充方式}
```

## 模板填充示例（合同审查）

```markdown
# Skill 编译请求：劳动合同风险审查

## 一、标识符

- skill_family：labor_contract_review
- jurisdiction：CN
- stage：non_litigation
- party_role：employer_counsel
- doc_type：contract_review

## 二、五问要素

### 1. 输入什么
必要输入：劳动合同全文（.docx）、企业所属行业、用工形式（全日制/非全日制/劳务派遣）
可选输入：历史同类合同、企业内部用工制度
信息来源：用户上传

### 2. 输出什么
主要产出：合同审查意见书
格式要求：风险等级分级（高/中/低）+ 条款逐条批注 + 修改建议
质量标准：每条风险标注法条依据，不臆测

### 3. 处理逻辑
1. 解析合同结构，识别合同类型
2. 逐条扫描 8 大风险维度（试用期/工时/工资/社保/解除/竞业/保密/违约金）
   - 决策点：用工形式为劳务派遣时，跳过竞业限制维度，增加派遣协议合规检查
3. 生成风险清单与修改建议
   - 质量检查点：执业律师对高风险项复核

### 4. 向谁交付
终端用户角色：企业 HR + 外部律师
触发场景：企业新签或续签劳动合同时
语气基调：中性专业，提示风险但不吓唬

### 5. 知识支撑
法律依据：《劳动合同法》第 17/19/20/23/25 条；《劳务派遣暂行规定》
范本来源：律所内部劳动合同范本库
风险清单：8 大维度风险清单（详见素材 sample_001~005）
风格偏好：法条引用精确到条，禁止使用"可能违法"等模糊表述
```

## 与 legal-skill-creator 的对接说明

`legal-skill-creator` 第二章"向用户确认的信息"要求的六个字段，本 prompt 已全部覆盖：

| legal-skill-creator 字段 | 本 prompt 对应位置 |
|------------------------|------------------|
| 技能家族标识 | 标识符.skill_family |
| 法域与程序阶段 | 标识符.jurisdiction + stage |
| 当事人侧别 | 标识符.party_role |
| 文书类型 | 标识符.doc_type |
| 语料来源 | 三、素材溯源 |
| 质量过滤标准 | 三、素材溯源（可选标注 quality = gold） |

调用 skill creator 时，把本 prompt 整体作为输入即可。
