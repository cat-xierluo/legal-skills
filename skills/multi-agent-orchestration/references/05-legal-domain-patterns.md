# 并行 Agent 法律实务场景

> 来源：多会话并行 Agent 工作流研究 Part II
> 范围：法律项目任务拆解、诉讼/非诉模板、多 Agent 协同

---

## 1. 法律项目的任务拆解模式

法律工作与软件开发在任务拆解上有本质差异：

| 维度 | 软件开发 | 法律实务 |
|------|---------|---------|
| **产出物** | 代码文件 | 法律文书、研究报告、合同、意见书 |
| **版本控制** | Git（天然适配） | 文件系统 + 文档版本（需适配） |
| **任务粒度** | Issue → PR → Merge | 研究题 → 初稿 → 审核 → 定稿 |
| **并行模式** | 不同文件可并行 | 不同研究题/文档可并行 |
| **Review 标准** | 代码规范 + 测试 | 法律准确性 + 逻辑严密 + 格式规范 |
| **协作工具** | GitHub Issue/PR | 项目文件夹 + 任务清单（可映射到 Issue） |

## 2. 诉讼项目模板

诉讼项目的典型阶段和 Agent 分派方式：

```
┌─ Phase 1: 案件评估 ──────────────────────────────────────┐
│ [Research Agent] 案由检索 → 类案检索 → 管辖权分析         │
│ [Analysis Agent] 诉讼请求设计 → 风险评估 → 策略建议       │
│ ⚠️ 依赖关系：研究完成 → 分析开始                          │
├─ Phase 2: 证据整理 ──────────────────────────────────────┤
│ [Research Agent × N] 多个证据线索并行调研                  │
│   - 证人证言准备                                          │
│   - 书证收集与整理                                        │
│   - 电子证据固定                                          │
│ [Integration Agent] 证据目录编制 → 证明力分析             │
│ ✅ 证据线索之间可并行                                     │
├─ Phase 3: 法律文书 ──────────────────────────────────────┤
│ [Writer Agent] 起诉状/答辩状 → 代理词 → 法律意见书        │
│ [Review Agent] 法律准确性审查 → 逻辑审查 → 格式审查       │
│ ⚠️ 依赖关系：Phase 1+2 完成 → 文书起草                    │
├─ Phase 4: 庭审准备 ──────────────────────────────────────┤
│ [Analysis Agent] 争议焦点整理 → 对方论点预测              │
│ [Writer Agent] 代理意见 → 庭审提纲                        │
│ ✅ 焦点整理和论点预测可并行                               │
├─ Phase 5: 庭后跟进 ──────────────────────────────────────┤
│ [Writer Agent] 代理词补充 → 庭后意见                      │
│ [Integration Agent] 案件总结 → 经验沉淀                   │
└──────────────────────────────────────────────────────────┘
```

**诉讼项目的 Agent 路由矩阵**：

| 任务类型 | 推荐角色 | 说明 |
|---------|---------|------|
| 法条检索 | Research Agent | 精确法条查询 |
| 类案检索 | Research Agent | 判例检索和分析 |
| 证据整理 | Analysis Agent | 音频转写、OCR、证据固定 |
| 文书起草 | Writer Agent | 大模型直接生成 |
| 文书审核 | Review Agent | 法律准确性 + 逻辑审查 |
| 庭审预测 | Analysis Agent | 基于类案的推理 |

## 3. 非诉项目模板

非诉项目（以尽职调查和合同审查为例）：

```
┌─ 尽职调查项目 ──────────────────────────────────────────┐
│                                                          │
│ [Research Agent × N] 并行尽调模块：                      │
│   ├── 公司基本情况（工商、股权结构）                      │
│   ├── 资产情况（不动产、知识产权）                        │
│   ├── 合同与债权债务                                      │
│   ├── 劳动用工                                            │
│   ├── 诉讼仲裁                                            │
│   └── 合规与监管                                          │
│                                                          │
│ [Analysis Agent] 各模块风险汇总 → 风险等级评定            │
│ [Writer Agent] 尽调报告初稿 → 问题清单                    │
│ [Review Agent] 法律准确性 + 披露完整性审查                │
│ [Integration Agent] 最终报告整合                          │
│                                                          │
│ ✅ 尽调模块之间天然可并行                                 │
│ ⚠️ 风险汇总依赖各模块完成                                │
└──────────────────────────────────────────────────────────┘

┌─ 合同审查项目 ──────────────────────────────────────────┐
│                                                          │
│ [Research Agent] 交易背景调研 → 行业惯例检索              │
│ [Analysis Agent × N] 并行审查维度：                      │
│   ├── 合同主体资格                                        │
│   ├── 权利义务条款                                        │
│   ├── 违约责任                                            │
│   ├── 知识产权归属                                        │
│   ├── 保密与竞业                                          │
│   └── 争议解决机制                                        │
│ [Writer Agent] 审查意见书 → 修改建议                      │
│ [Review Agent] 整体一致性 + 遗漏检查                      │
│                                                          │
│ ✅ 审查维度之间天然可并行                                 │
└──────────────────────────────────────────────────────────┘
```

## 4. 法律"类 Issue"拆解方法论

法律项目不一定使用 GitHub Issue。任务源由具体项目约定；`cross-agent-coordination` 可按项目配置解析和分配任务，本 Skill 只负责把可执行任务拆给本地 Agent 会话。

### 4.1 任务载体对比

| 控制层组件 | 软件开发 | 法律实务 |
|-----------|---------|---------|
| **Task Registry** | GitHub Project / `.agents/tasks.md` | 项目配置的任务源 |
| **Issue** | GitHub Issue | 项目任务源中的 Task 条目 |
| **PR** | GitHub Pull Request | 文稿审查（Review Request） |
| **Branch** | Git Branch | 文档版本目录 / 文件副本 |
| **Worktree** | Git Worktree | 独立工作目录（每人/每个任务一个） |
| **Session** | tmux pane | tmux pane（同样适用） |
| **Review** | Code Review | 文书审核（法律准确性 + 逻辑 + 格式） |

### 4.2 法律项目的任务字段

```json
{
  "task_id": "LIT-001",
  "title": "检索 XX 案由的类案裁判规则",
  "project_type": "litigation",
  "phase": "case_assessment",
  "status": "in_progress",
  "priority": "high",
  "owner": "claude",
  "platform": "claude-code",
  "archetype": "research",
  "external_agents": [],
  "deliverable": "research_report.md",
  "depends_on": [],
  "review_policy": "legal_accuracy",
  "risk_level": "medium",
  "updated_at": "2026-05-04T16:00:00+08:00"
}
```

与软件开发相比新增的字段：
- `project_type`：`litigation`（诉讼）/ `non_contentious`（非诉）/ `legal_research`（法律研究）
- `phase`：项目阶段（对应上方模板中的 Phase 1-5）
- `external_agents`：需要调用的外部法律 Agent（按项目实际安装填写）
- `deliverable`：产出物类型
- `review_policy`：审核策略（`legal_accuracy` / `contract_review` / `compliance_check`）

### 4.3 拆解流程

```
用户输入上下文（案件事实/项目背景/客户需求）
    ↓
[Analysis Agent] 识别项目类型和阶段
    ↓
[Planning] 根据模板生成任务清单
    ↓
[Dependency Analysis] 标注并行/串行关系
    ↓
[项目任务源] 写入主状态
    ↓
[Dispatch] 按依赖图启动 Agent（tmux 可视化）
    ↓
[Monitor] 轮询完成状态
    ↓
[Integration] 汇总产出 → Review → 定稿
```

## 5. 多 Agent 协同的法律场景

### 5.1 Agent 选择策略

不同法律任务的最优 Agent 组合：

| 场景 | Agent 组合 | 编排模式 |
|------|-----------|---------|
| **诉讼全流程** | Research + Analysis + Writer + Review | 阶段串行，阶段内并行 |
| **尽调（多模块）** | Research × N + Analysis + Writer | 模块并行 → 汇总串行 |
| **合同审查（多维度）** | Analysis × N + Writer | 维度并行 → 整合串行 |
| **法律研究（深度）** | Research + Analysis | 串行（研究 → 分析） |
| **批量律师函** | Writer × N + Review | 完全并行 |

## 6. 使用边界

本文档只提供法律项目在多 Agent 本地执行层的拆分样例，不定义任务主状态、外部 Agent 注册表或法律模板文件路径。

- 任务来源、负责人、依赖和交接记录由 `cross-agent-coordination` 及项目任务源维护。
- 本 Skill 只负责把已确认可执行的任务分配到本地 session、worktree 和 PM 巡检流程中。
- 需要法律检索、OCR、语音转写等能力时，在 worker prompt 中说明调用对应 Skill，不在本参考文档中新增独立 catalog。
