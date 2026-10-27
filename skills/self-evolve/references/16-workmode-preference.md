# 工作模式偏好账本(self-evolve 内部)

## 定位

self-evolve 自己维护的偏好账本,维度 = **工作模式偏好**(focus / correction / sediment / recurrence)。和 info-evaluator 的**内容评分偏好**(content_value / selection_capacity)分家:两者各自单一权威源,不互相替代。

为什么分家:info-evaluator 的偏好服务内容选品(给文章打分),scope 固定内容维度;self-evolve 的核心使命是自我迭代,该回答「我专注什么 / 反复纠正什么 / 什么该沉淀 / 哪些 skill 反复调用」——这是工作模式维度,info-evaluator 不管。把内容评分偏好搬进 self-evolve 会越界 + 双头维护;新建工作模式维度是填补空白。

## 数据流

```
session-summaries + dream_sweep topic-clusters
  │ workmode_extract.py(复用 iteration_report 归因常量 + build_packet 隐私网关 + sha256[:16])
  │   → 信号候选,按 (scope, sub_topic) 聚成跨 ≥2 session 的 cluster
  ▼
runtime/preference-bridge/workmode-packet.json(schema self-evolve-preference-evidence-v1)
  │ workmode_ledger.py analyze(SiliconFlow DeepSeek-V3.2,enable_thinking=False,temperature 0.0)
  │   prompt 硬列 scope 白名单 → normalize 硬/软问题过滤
  ▼
runtime/workmode-preference/ledger.json + events.jsonl(四维状态机账本)
  │ panel GET /api/workmode-candidates(只读投影)
  ▼
panel「偏好审阅」tab(卡片 + 接受/观察/拒绝)
  │ 用户决定 → POST .../decision(revision 绑定)→ events.jsonl 仅追加
```

## scope 维度

| scope | 含义 | 证据来源 |
|---|---|---|
| focus | 专注方向（通用默认分类或本地 JSON 覆盖，多标签匹配） | `workmode_config.load_focus_config()` |
| correction | 纠错模式(skill 边界/约束缺失/纠正短语/问法) | `_SKILL_BOUNDARY_RE`/`_HIDDEN_CONSTRAINT_RE`/`_CORRECTION_PHRASE_RE`/`_Q_FORM_RE` |
| sediment | 该沉淀的资产信号 | `upgrade_signals` + `article_signals` |
| recurrence | 反复 skill 调用模式(主动 vs 自动 cron) | `related_skills` |

polarity = prefer / avoid / constraint。

### 可选本地分类

新用户缺省使用项目开发、内容创作、学习与教学、流程改进四类；这是通用关键词初筛，不是已确认的个人偏好。需要自定义时把 `config/workmode.example.json` 复制为 `config/workmode.local.json`，使用 `focus_keywords` 完整定义分类，可用 `focus_extra_keywords` 为已定义分类添加触发词。该 JSON 仅需标准库，实际文件被 Git 忽略并在发行时硬排除。

周报与偏好提取共享同一配置；坏 JSON、未知/重复字段或非法值会报错，不回显配置内容、不静默回退。既有账本与事件保持原样，既有分类需要在本地覆盖中保留原标签，才能延续同一 `topic_key` 与聚类 ID；修改分类标签不会自动改写既有记录。模型提示词根据证据包归纳，不内置维护者业务方向。

`workmode_ledger.py` 的 `analyze` 在配置了 `SILICONFLOW_API_KEY` 时把脱敏证据包 POST 到独立模型端点做结构化归纳；缺 Key 或调用失败时降级为 `analysis_unavailable`（不产候选、退出码 0），不报错中断。该调用不属于公开流程默认入口；旧调度模板的 `weekly-workmode-analyze` 启用后会按周期触发它。

## 四维状态机(照搬 info-evaluator)

| 维度 | 字段 | 取值 |
|---|---|---|
| 机器 | machine_disposition | candidate / filtered / duplicate / covered |
| 人工 | human_decision | pending / accepted / rejected / observe |
| 应用 | application | not_applied / applied(version) |
| 结果 | outcome | pending / verified / failed / inconclusive |

- `candidate_id` = `wmp-` + sha256(scope\0polarity\0claim.casefold())[:16](确定性;同 claim 在不同运行中是同一行)
- `revision` = sha256({candidate_id, evidence_ids, source_session_hashes, counter_evidence_ids, model, source_digest})[:20](证据变 → revision 变 → 旧决定不匹配 → 回 pending)
- 决定仅追加 `events.jsonl`,不改 `ledger.json` 主体
- **accepted ≠ applied**:应用是离线人工门槛(照搬 info-evaluator)

## 跨会话门槛

每个 cluster 必须 ≥2 个 session 且 ≥2 条跨会话 evidence。这保证偏好是「反复出现」而非一次性——和 info-evaluator preference_ledger 一致。evidence_id 含 scope/sub,避免不同 cluster 共用同文本时 id 冲突。

## 隐私

- session hash = sha256[:16](和 `deep_dream.build_packet` 一致),不存原始 session_id
- evidence text / claim / rationale / reason 复用 self-evolve `privacy_gate`(`validate_text` + `validate_untrusted_source`),比 info-evaluator 的 `FORBIDDEN_TEXT` 更全(路径/邮箱/手机/身份证/银行卡/组织名/prompt injection/secret)
- 账本/事件 `chmod 0600`,原子写 + fsync + fcntl.flock;corrupt 事件/identity fail-closed 阻断变更

## 与 info-evaluator 的边界

| | self-evolve workmode | info-evaluator content |
|---|---|---|
| scope | focus/correction/sediment/recurrence | content_value/selection_capacity |
| 证据源 | self-evolve session-summaries + clusters | self-evolve 导出的 evidence-packet(DEC-047) |
| 账本位置 | `runtime/workmode-preference/` | `info-evaluator/assets/preferences/` |
| 审阅 | self-evolve panel「偏好审阅」tab | content-registry dashboard |

self-evolve 仍向 info-evaluator 单向导出内容评分证据(`export_preference_evidence`,DEC-047 不变)。workmode 是新增维度,不动那条链。

## 整合接口(为统一工作台铺路)

- 账本 schema 与 info-evaluator 同源(四维状态机 + 哈希公式同构)
- panel 投影函数(`collect_workmode_candidates`)设计成可接受 `source` 参数(将来 content 投影并进同一 tab)
- workmode-packet 与 evidence-packet 字段契约一致(`evidence_id` / `source_session_id_hash` / `text`)

长期愿景:多个 skill 各自跑通「data-root + 审计前端」模式后,汇总到统一工作台。现阶段先发散、不整合。

## CLI

```bash
# 仅提炼证据包(不调模型)
python3 scripts/workmode_extract.py --since 14d

# 提炼 + 分析 + 入账(幂等:source_digest 未变则零模型调用)
python3 scripts/workmode_pipeline.py --since 14d

# 固定响应离线回放(测试,不调模型)
python3 scripts/workmode_pipeline.py --response-file response.json

# 账本 CLI
python3 scripts/workmode_ledger.py analyze --packet workmode-packet.json --response-file r.json --dry-run
python3 scripts/workmode_ledger.py list --decision pending
python3 scripts/workmode_ledger.py decide wmp-xxxxxxxxxxxxxxxx --revision <20-hex> --decision accepted --reason "..."
```

## 依赖

- 模型:SiliconFlow DeepSeek-V3.2,`SILICONFLOW_API_KEY`(env);缺失时 pipeline 降级为 `analysis_unavailable`(extract 仍成功,returncode 0)
- 无跨 skill import:模型薄客户端内置,不依赖 info-evaluator 的 lib
- 调度：`workmode_analyze` 注册于 `scheduler_run.COMMAND_SPECS`；需要旧调度时由用户在本地 `config/scheduled_tasks.yaml` 显式配置和启用。
