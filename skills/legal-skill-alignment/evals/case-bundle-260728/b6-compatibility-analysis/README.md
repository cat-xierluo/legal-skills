# T-001 B6: Legal Skill Brief v1 与通用 skill-creator 对接分析

> **任务**：T-001 B6（与下游端到端打通验证）
>
> **v0 状态**：待实测（v0 评测中 3 案例均未实测 skill-creator 编译成功率）
>
> **v1 进展**：本报告产出**理论对接分析 + 手动验证手册**，覆盖 3 个 v1 重对齐案例对通用 skill-creator 的兼容性。
>
> **实测说明**：本环境无法 spawn 独立 Claude 实例运行 skill-creator 主流程，**实际编译测试须手动执行**——手册见下文 §四。
>
> **关联文件**：
>
> - v0 基线：`evals/case-bundle-260705/EVALUATION.md`（B6 标记为"待测"）
> - v1 重对齐案例：`evals/case-bundle-260728/v1-realigned/`
> - 下游：通用 skill-creator skill 目录（路径以本机安装位置为准）

---

## 一、核心结论

**Legal Skill Brief v1 与通用 skill-creator 对接良好**，无需修改 Brief 规范本身即可让 skill-creator 跳过 Capture Intent + Interview 阶段直接进入 Write SKILL.md。

**三个潜在摩擦点已识别**：

| # | 摩擦点 | 严重度 | v1 Brief 状态 | 应对 |
|---|--------|--------|---------------|------|
| F1 | description 必须 ≤1024 字符且"pushy"风格 | 低 | 3 个 case 触发场景描述偏短（<200 字符），需要主 Claude 在 SKILL.md 生成时扩展 | skill-creator 会自动扩写；run_loop 也会反复优化 |
| F2 | 自定义元数据（skill_family 等）必须放在 `metadata:` 嵌套对象下 | **必须人工确认** | v1 Brief 元数据列在 Markdown bullet list（`- **skill_family**：xxx`），不是 YAML 嵌套结构 | 主 Claude 读 Brief 时会自然处理；但建议在 manual §四 验证步骤中显式检查生成的 draft SKILL.md |
| F3 | 测试用例（evals）必须从 Markdown 转 JSON | 低 | v1 Brief 未带 evals 用例（alignment 不产出 evals.json） | skill-creator 主 Claude 在 Write SKILL.md 阶段会提示用户补 evals；这是 design by intent |

---

## 二、逐案例对接分析

### 案例 01：供应商服务合同审查

**Brief 路径**：`evals/case-bundle-260728/v1-realigned/case-01-contract-review/prompt-output.md`

| skill-creator 期望 | v1 Brief 实际 | 对接状态 |
|--------------------|--------------|---------|
| 1. skill 让 Claude 做什么 | "供应商服务合同审查（8 大维度风险扫描）" | ✅ 明确 |
| 2. 何时触发（用户短语） | "企业与外部供应商签订服务合同前" + 触发词：`合同审查`、`签约前`、`供应商服务合同` | ✅ 描述清晰但偏短，依赖主 Claude 扩展 |
| 3. 期望输出格式 | "风险等级分色标注（高/中/低）+ 条款逐条批注 + 修改建议 + 法条依据" + "mixed 形态" | ✅ 明确 |
| 4. 是否需要 test cases | Brief 未带 evals | ⚠️ 需在 Write SKILL.md 阶段补 |
| **frontmatter 白名单** | skill_family=supplier-service-contract-review（kebab-case ✅） | ✅ 命名规范 |
| **metadata 嵌套** | Brief 中 `- **skill_family**：supplier-service-contract-review`（Markdown 列表） | ⚠️ 须由主 Claude 转为 `metadata: { skill_family: ... }` YAML 结构 |
| **description ≤1024 字符** | Brief 无 description 字段，须由主 Claude 从"触发场景 + 主要产出 + 质量标准"合成 | ✅ 主 Claude 自动生成 |
| **name kebab-case** | `supplier-service-contract-review`（34 字符） | ✅ 符合 |

**对接判定**：✅ **STATIC_COMPATIBILITY_REVIEW**（静态兼容性审查通过；**实测 NOT_VERIFIED**），仅 F1/F2/F3 三个待人工检查项。

### 案例 02：著作权侵权代理词

**Brief 路径**：`evals/case-bundle-260728/v1-realigned/case-02-copyright-litigation/prompt-output.md`

| skill-creator 期望 | v1 Brief 实际 | 对接状态 |
|--------------------|--------------|---------|
| 1. skill 让 Claude 做什么 | "起草原告代理词（一审）—— 三段式（事实 → 法律 → 结论）" | ✅ 明确 |
| 2. 何时触发 | "原告一审庭审前 1-2 周" + 触发词：`代理词`、`一审`、`著作权侵权`、`原告方` | ✅ 描述清晰 |
| 3. 期望输出格式 | "标准代理词格式（标题 / 尊敬的审判长 / ... / 落款）" | ✅ 明确 |
| 4. 是否需要 test cases | Brief 未带 evals | ⚠️ 需补 |
| **frontmatter 白名单** | skill_family=copyright-infringement-agent-statement（kebab-case ✅） | ✅ |
| **metadata 嵌套** | Markdown 列表格式 | ⚠️ 同 F2 |
| **description ≤1024 字符** | 触发场景 + 关键要件齐备 | ✅ |
| **name kebab-case** | `copyright-infringement-agent-statement`（37 字符） | ✅ |

**对接判定**：✅ **STATIC_COMPATIBILITY_REVIEW**（静态兼容性审查通过；**实测 NOT_VERIFIED**）。

**额外注意点**：本 case 标注 `高风险结论 = 是 / 必须执业律师复核`。skill-creator 主 Claude 在 Write SKILL.md 阶段应保留这个安全边界到 draft SKILL.md 的 body 或 success criteria 段。

### 案例 03：App 数据合规扫描

**Brief 路径**：`evals/case-bundle-260728/v1-realigned/case-03-data-compliance/prompt-output.md`

| skill-creator 期望 | v1 Brief 实际 | 对接状态 |
|--------------------|--------------|---------|
| 1. skill 让 Claude 做什么 | "App 数据合规扫描——四大维度（隐私政策 / 告知同意 / 数据安全 / 用户权利）" | ✅ 明确 |
| 2. 何时触发 | "App 上线后定期合规体检 / 监管新规出台后专项扫描 / 通报事件后整改核查" | ✅ 描述清晰 |
| 3. 期望输出格式 | **mixed 形态 + 5 列表格化**（含列名 + 颜色约定） | ✅ 极明确 |
| 4. 是否需要 test cases | Brief 未带 evals | ⚠️ 需补 |
| **frontmatter 白名单** | skill_family=app-data-compliance-scan（kebab-case ✅） | ✅ |
| **metadata 嵌套** | Markdown 列表格式 | ⚠️ 同 F2 |
| **description ≤1024 字符** | 触发场景 + 输出格式详细 | ✅ |
| **name kebab-case** | `app-data-compliance-scan`（24 字符） | ✅ |
| **scripts/ 建议** | Brief "需外部检索监管文件"，但未提供脚本 | ⚠️ 主 Claude 会建议"配一个 fetch_rules.py"，需用户确认是否创建 |

**对接判定**：✅ **STATIC_COMPATIBILITY_REVIEW**（静态兼容性审查通过；**实测 NOT_VERIFIED**）。

**额外注意点**：本 case 涉及大量法源（10+ 条监管文件），主 Claude 在 Write SKILL.md 阶段应**保留法源三列（jurisdiction / effective_date / verification_status）**到 draft SKILL.md 的 references 段或 knowledge base 表中。

---

## 三、与 v0 评测 B6 状态的对比

| 维度 | v0（待测） | v1（本分析） |
|------|-----------|--------------|
| 标识符协议 | snake_case 五标识符必填 | kebab-case identifier + snake_case stage/role 可选 metadata |
| 下游契约 | 硬绑定 legal-skill-creator | 中立（skill-creator / legal-skill-creator 均可） |
| F2 metadata 嵌套 | v0 五标识符顶层出现 → **会被 quick_validate 直接拒绝** | v1 改 metadata 嵌套 / 可选 → **不再触发拒绝** |
| F1 description 长度 | v0 五标识符占字符数多，description 极易超 1024 | v1 元数据移到 metadata 子对象，description 字符预算更宽松 |
| 触发场景描述 | v0 隐含在五问中，需主 Claude 反推 | v1 在 Brief 中显式列"触发场景"段 + 触发词列表 |

**结论**：v1 协议**解决**了 v0 评测中 B6 的两个潜在阻塞点（F2 / F1）。v1 Brief 顺利通过 skill-creator 对接的概率显著高于 v0。

---

## 四、手动验证手册（5 步）

如需实测，按以下步骤操作：

### Step 1：准备 Brief 输入文件

每个 case 把 prompt-output.md 内容复制到剪贴板（或保存为临时文件 `/tmp/brief-case-01.md`）。

### Step 2：启动 skill-creator 会话

在 Claude Code / Claude CLI 中：

```bash
cd <skill-creator 安装目录>
```

加载 skill-creator（通过 marketplace / settings.json 配置）。

### Step 3：发送"已有 draft"模式指令

向 Claude 发送：

```text
我已经把意图完整结构化在下面的 Brief 中（标题/触发场景/能力/输出/约束）。
请按 SKILL.md 第 1-3 步生成 draft SKILL.md，跳过访谈阶段。
输出目录：/tmp/test-skill-case-01/

<贴入 Brief v1 内容>
```

> **关键**：用"跳过访谈"措辞匹配 SKILL.md §22-24 的"已有 draft 模式"。

### Step 4：frontmatter 校验

```bash
python -m scripts.quick_validate /tmp/test-skill-case-01/
```

**期望输出**：`✓ Skill <name> is valid`

**特别检查**：

- `name` 是否 kebab-case
- `description` 是否 ≤1024 字符且含触发词
- 自定义字段（如 skill_family）**是否在 `metadata:` 子对象下**（不是顶层）

### Step 5：触发评估（可选）

准备 trigger eval JSON：

```json
[
  {"query": "我想审查一份供应商服务合同有什么风险", "should_trigger": true},
  {"query": "今天天气怎么样", "should_trigger": false}
]
```

跑评估：

```bash
python -m scripts.run_eval \
  --eval-set /tmp/trigger-evals-case-01.json \
  --skill-path /tmp/test-skill-case-01/ \
  --model claude-3-5-sonnet-latest \
  --verbose
```

判定标准：`passed >= total / 2`。

---

## 五、回归案例

把 3 个 v1 case 的"对接判定 = STATIC_COMPATIBILITY_REVIEW（静态通过 / 实测 NOT_VERIFIED）"作为 B6 的回归基线：
未来 v1 Brief 规范变更时，重新跑 §二 表格，对比"对接状态"列是否保持 ✅。

如果某个新 case 出现 ❌ 项，应：

1. 在 `evals/case-bundle-260728/b6-compatibility-analysis/` 下新建 `<case-NN>-b6-report.md`
2. 列出失败的 friction point 与原因
3. 决定是调整 Brief 规范（升级 v1.1）还是调整 skill-creator 的对接策略

---

## 六、实测状态记录

| case | 对接分析（静态） | 实测 | 实测结果 | 实测日期 | 实测人 |
|------|------------------|------|---------|---------|--------|
| case-01 | ✅ STATIC_COMPATIBILITY_REVIEW | NOT_VERIFIED（待跑） | — | — | — |
| case-02 | ✅ STATIC_COMPATIBILITY_REVIEW | NOT_VERIFIED（待跑） | — | — | — |
| case-03 | ✅ STATIC_COMPATIBILITY_REVIEW | NOT_VERIFIED（待跑） | — | — | — |

> **本表待人工填入**。实测后请把"待跑"改为"PASS / FAIL"并补实测结果摘要。

---

## 七、与 v0 评测 B6 状态的总结对照

| 状态 | v0 | v1 |
|------|-----|-----|
| 评测结论 | "三个 prompt 五标识符齐全、格式符合模板，但未实测" | "3 个 Brief 静态兼容性审查通过（STATIC_COMPATIBILITY_REVIEW），实测 NOT_VERIFIED 待跑" |
| 阻塞风险 | snake_case identifier 顶层 + 缺 metadata 嵌套 → quick_validate 拒绝风险 | 全部解决（kebab-case + metadata 嵌套 + 可选元数据） |
| 下游契约 | 单一下游（legal-skill-creator） | 双下游中立（skill-creator / legal-skill-creator） |
| 实测依赖 | 必须测 legal-skill-creator | 可测通用 skill-creator（本仓已部署，更易上手） |

**关键改进**：v1 把 B6 从"待测 + 阻塞风险高"变成"理论 PASS + 实测可手动跑"。这是 v0.x → v1.0.0 协议层重构（T-005）的核心价值兑现。