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

### 2.1 诉讼 worker 的证据访问约定

诉讼 worker 读证据（PDF/图片/视频/3D 模型/取证件）的机制与代码项目依赖不同：

- **代码 worker 读 `node_modules`** 是隐式解析（npm 内部找路径），必须软链进 worktree 让其自然可达——见 `spawn-worker-deps.sh` 的 G31 补偿。
- **诉讼 worker 读证据** 是显式访问（agent 自己 `cat` 一个文件）。worker 在自己的 worktree 内**没有证据原件**（证据被 `.gitignore` 排除），但工作树中 md 产出和证据目录结构已存在，路径名可读。worker 只需从案件的 md 产出或目录命名里识别证据路径，再**用绝对路径**读主仓原件。

**PM spawn 诉讼 worker 时**，prompt 必须包含：

1. **主仓项目根**（用 git 命令取，不要硬编码）：
   ```
   PROJECT_ROOT=$(git rev-parse --show-toplevel)
   ```
2. **案件目录相对路径**（PM 只需告诉 worker 案件在主仓内的相对位置；绝对路径 worker 自己拼）：
   ```
   CASE_REL="<主仓内的案件目录相对路径，如 003 - 诉讼仲裁/<案件名>>"
   ```
3. **证据访问模板**（worker 按案件目录命名约定自主取证据）：
   ```bash
   # 1) 列出案件目录里证据材料类型（grep 已知子目录前缀）
   ls -la "$PROJECT_ROOT/$CASE_REL" | grep -E '0[1-9] -|1[0-2] -'
   # 2) 读特定证据文件（用 find 定位，不假设具体文件名）
   EVIDENCE=$(find "$PROJECT_ROOT/$CASE_REL" -name '*.pdf' -path '*/05*证据材料/*' | head -1)
   # 3) 读取它
   cat "$EVIDENCE"    # 文本型
   # 或用 OCR/Skill 处理扫描件
   ```
4. **产出写路径**（worker 在自己的 worktree 里，对应案件目录的子路径）：
   ```
   产出: <worktree>$CASE_REL/<约定的子目录，如 02 - 📄 案件分析>/证据目的表.md
   ```
5. **md 文档内的证据引用规范**（避免污染机器路径）：
   - 引证证据用**相对文件名**写进文档（如 `见 05 - 📎 证据材料/<证据文件名>.pdf`），**不要**写绝对路径。
   - worker run-time 读证据用绝对路径；文档成稿里只用相对名——文档可移植、可分享。

**反模式**（不要做）：
- 在 worktree 里软链证据目录 → 没必要，文档已成可定位证据相对路径，再走绝对路径读主仓即可。
- 把"绝对路径"或"具体目录名"硬编码进 prompt 模板 → 绑定到本机环境、泄露隐私、跨用户失效。
- 把绝对路径写进产出文档 → 污染文档、绑定本机。
- 让 worker 假定自己知道完整路径 → 必须告诉 worker 项目根和案件相对路径，由它自己拼绝对路径。

> 工程依据：常见做法是项目目录已经 `git init`（monorepo 或单案件），`.gitignore` 排除证据原件。worktree 只 checkout 文本，但通过 `git rev-parse --show-toplevel` + `find` 可动态定位证据原件绝对路径。这与代码 `node_modules` 必须软链的隐式解析场景不同：证据是**显式查找 + 显式访问**，无需软链补偿。

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
