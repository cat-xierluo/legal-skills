# Runtime 会话来源支持矩阵

适用范围：公开版工作流（`scripts/public_workflow.py scan`）经 `scripts/runtime_sessions.py` 的只读适配。当前 ADAPTER_VERSION=14（版本沿革见文末）。所有读取只读、不访问凭证、不写来源数据库；目录发现不等于全格式支持。

本表描述被扫描的**会话来源**，不认证发起扫描的**调用宿主**。调用方只要具备脚本执行与本机文件访问条件，就可走相同流程；例如 Qoder 可作为待验调用环境，而其自身会话来源仍未正式接入。Qoder 宿主完整链路为 `NOT_VERIFIED`，使用条件见 [公开版工作流](18-public-workflow.md#调用宿主与会话来源)。

## 支持矩阵

| Runtime | 本机存储 | 适配格式 | 消息结构 | 完整性标记 | 空会话/失败分类 |
|---|---|---|---|---|---|
| Claude Code | `~/.claude/projects`（现行）与 `~/.claude/transcripts`（历史顶层） | `claude` jsonl | 现行信封 `type`+`message.role/content`；历史顶层方言 `role`+`content` 或 `type`+`content`；纯 `tool_use` 记录视为已知形态 | `transcript` / `sampled_transcript`（超预算时头中尾抽样） | 零行文件→`empty_session`（记账 filtered）；坏行→`invalid_or_empty_jsonl`；无法识别→`unsupported_jsonl_schema`（均 failed） |
| Codex | `~/.codex/{sessions,archived_sessions,_quarantine}`（`CODEX_HOME` 可覆写） | `codex` jsonl | `session_meta` / `event_msg` / `response_item` / `turn_context` | 同上 | 坏行/空文件→`invalid_or_empty_jsonl`；未知→`unsupported_jsonl_schema` |
| WorkBuddy / CodeBuddy | `~/.workbuddy`、`~/.codebuddy` 下的 `projects`（顶层 role 方言）与 `traces/trace_*.json` | `claude` jsonl + `trace` json | projects 用 `type=message` + 顶层 `role` + 顶层 `content`（`input_text`/`output_text` 块）；工具行 `function_call` 带 `message={usage}` 不算对话行。trace 取 `generation` span 的 `<user_query>` 与 choices 回复，跨 span 前缀去重 | `transcript` / `sampled_transcript` | 无 generation span→`no_conversation_messages`（failed）；空文件→`empty_session` |
| QwenWorkCN | `~/.qwenworkcn/projects` | `claude` jsonl | 与 Claude Code 同源信封（`sessionId`/`parentUuid`/`message`/`cwd`），含 `type=thinking` 推理块 | `transcript` / `sampled_transcript` | 坏行→`invalid_or_empty_jsonl`；未知→`unsupported_jsonl_schema` |
| Gemini | `~/.gemini/tmp/**/chats/session-*.json` | `gemini` json | `messages[].type ∈ {user, gemini}` | `transcript` | 结构有效但无对话→`empty_session`（filtered）；结构不符→`unsupported_gemini_schema`（failed） |
| ZCode | `~/.zcode/v2/tasks-index.sqlite`（`ZCODE_DATA_BASE_DIR` 可覆写） | `zcode-index` sqlite 只读 | 任务 `searchable_text` 索引摘录，无角色边界 | `index_excerpt`（超 24k 字符头中尾抽样） | 行缺失/读取中变更→`source_changed_during_read`；空文本→`index_text_unavailable`（均 failed） |

工具回显隔离：user 侧按来源消息结构抽取外层文本，`tool_result` 块不计入用户轮；assistant 侧独立抽取。角色归类与已知噪声过滤不证明真人身份。空会话在报告中标记"空会话 · 无对话内容"，不占用失败统计。

## ZCode 完整消息探测结论（只读）

授权范围内未发现完整对话源，保持索引摘录降级，不宣称"已完整支持"：

- `~/.zcode/cli/log/zcode-YYYY-MM-DD.jsonl`：运行时遥测（事件名/计数/长度，如 `turn.phase.started`、`model.request.completed`），无消息正文；滚动保留约 7 天。
- `~/.zcode/cli/exec/sess_<uuid>/call_*.log`：工具调用输出留存，非完整对话。
- `~/.zcode/v2/tasks-index.sqlite`：任务搜索索引（现用来源）。
- `~/.zcode/v2/checkpoints/`：工作区压缩清单；`state.json` 指向加密 manifest（`encryptedSizeBytes`）——读取需解密，超出只读授权，按计划停止条件不接入。

## 未接入 Runtime 与补充来源方法

`qwen`、`qoder`、`qoderworkcn`、`openclaw`、`hermes`、`opencode`、`cursor`、`trae` 的目录存在时显示 `unsupported`（格式待接入），不猜测解析、不假装覆盖。ZCode 完整消息读取超出当前适配范围。用户显式补充来源：

```bash
python3 scripts/public_workflow.py scan --source runtime:claude|codex|trace|gemini=目录
```

`--source` 可重复；显式来源记入 scan_profile，随后续定时调用自动复用。只有拿到该平台本机真实格式证据后才新增 adapter。

## 去重与计数口径

- 文件级：同一路径（realpath）跨来源只计一次。
- 会话级：证据按 `session_ref`（内容语义哈希）去重；跨 Runtime 副本合并 `source_aliases`，不增加虚假独立会话数；`cumulative.duplicate_views` 记录副本数。
- 索引与完整消息并存时（当前仅 ZCode 索引，无并存方）：按 `session_ref` 内容级去重，不重复计数。
- adapter 升级（ADAPTER_VERSION 变更）会重读全部会话，包括此前 failed 的——修复后自动复活，无需清账本。

## 版本沿革

- v14：附件头与宿主样板从用户轮分离（附件头不要求出现在轮首），只有 `## My request:` 之后文本保留为用户原话；宿主标签未闭合、跨类型错配或嵌套时整轮拒绝。v13 成对剥离逻辑保留；不作真人身份认证。
- v13：剥离同一用户轮中已识别的 `<in-app-browser-context>` / `<external_codex_apps_open_page>` 宿主上下文块，并去除 `## My request:` 分隔标记；其余文本仍按 user-role 来源处理，不作真人身份认证。
- v12：用户轮来源保留助手轮之后的 user-role 文本，过滤已识别的 AGENTS 注入、命令包装、宿主提示、子代理/任务通知及派工提示；保留真实存储格式中的 Codex `response_item` 用户轮并折叠相邻镜像，修正 WorkBuddy/CodeBuddy 顶层 role 映射，按每会话字符预算保留后续轮次。
- v10：扫描摘录新增 `user_excerpts` 用户轮来源，用于画像“用户明确纠偏”校验。
- v8：修复三种真实会话形态导致的读取失败——助手回合只含 `type=thinking` 块（提取器按设计丢弃，白名单此前判为未知载荷）、WorkBuddy/CodeBuddy 工具行 `function_call` 带 `message={usage}` 被误判为对话行、WorkBuddy/CodeBuddy 顶层 `role` 方言不被提取器识别（"加载成功但文本为空"）。QwenWorkCN 接入来源表（Claude 同源）。adapter 升至 v8，旧版误记的 failed/filtered 行自动重读修正。
- v7：ZCode 源库改临时副本快照查询（WAL 独有提交可见+指纹变化检测）；账本/源库预检全走副本（无伴生 WAL 模式主库原地 ro 也会建伴生）；孤立伴生（主库缺失）显式 read_failed；dict text message 放行。
- v6：载荷白名单按提取器实际可理解形态收紧（未知 type 块暴露）；字符串 message 合法化；ZCode 源库打开零副作用化（当时为 immutable 直连，v7 改快照）。
- v5：新增 `unsupported_message_payload`（content 为不可解析新结构显式失败）；dream_sweep 消费循环补逐会话 OSError 兜底。
- v4：识别历史顶层 `role`+`content`、`type`+`content` 方言与纯 `tool_use` 会话；零行文件与空 Gemini 会话分类为 `empty_session`（filtered）而非读取失败。
- v3（1.8.0 基线）：初始矩阵（Claude/Codex/WorkBuddy/CodeBuddy/Gemini/ZCode 索引 + unsupported 列表）。
