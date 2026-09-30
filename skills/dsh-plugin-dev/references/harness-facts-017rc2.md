# 0.1.7-rc.2 事实快照（Desktop 2.0.15 实测）

日期：2026-09-29。事实源：本机 `/Applications/DSH Desktop.app/Contents/Resources/app/node_modules/@deepseek-ai/`（内嵌 = 真实契约）+ npm registry + 桌面仓库 releases。升级后逐条复核，不采信本文记忆。

## 版本矩阵

| 组件 | 版本 | 说明 |
|---|---|---|
| DSH Desktop 外壳 | 2.0.15 | anywhere-labs/deepseek-harness-desktop 最新 release（2026-09-25）；更新走 electron-updater GitHub feed |
| 内嵌运行时 | `@deepseek-ai/dsh*` 全部 **0.1.7-rc.2** | = npm dist-tag `latest`；`next` = 0.2.0-rc.1（预发布，无桌面内嵌） |
| cordis | 4.0.4 | provide/notify/Service/effect/inject 等待语义在位 |
| Electron / node | 44.0.0 / v24.18.1 | 宿主日志头部可查 |
| 源码固定 | dsh-v0.1.7-rc.2 @ 477b4f420553e8a52c2fbccc464d7561b239c443 | deepseek-ai/deepseek-harness，2026-09-24 |

## 与 0.1.2 规范（本技能 references/dsh-plugin-development-standards.md）的差异清单

1. **内嵌树 .d.ts 全部剥离**——类型核对用 npm 分发包或 `dsh-tool-cordis/lib/types/api-catalog.js`（全量类型声明库）。
2. `PreStepDecision`/`ToolRunContext` 不在原包（dsh-agent/dsh-tools）导出面——0.1.2 式 import 失败；声明在 api-catalog（5855/7503/7416）。
3. `sessionProjections` 服务成熟可用（register/onChanged/stateOf；stateVersion 必填、wire 必需、数字 turnId）——见 projection-cookbook。
4. `agents` 服务、`agent/pre-step` waterfall、`connection.rpc/fetch`、`slots.inject/register`、`sidebar.footer.action` 槽位、patch insert 机制：运行时形状与 0.1.2 一致（合同插件差距调研逐项核对）。
5. 插件依赖钉 0.1.2-rc.1 在 0.1.7 宿主下的 dedupe 行为未验证（双版本 schema 漂移风险，适配时优先处理）。
6. `dsh-code-runtime` 内嵌树缺失（源码零引用则低影响）。

## 关键包速查（Host 侧）

| 包 | 用途 | 要点 |
|---|---|---|
| dsh-session-projection | 会话状态投影 | stateVersion 必填；通知只走 wire；onChanged(session,key,value,seq) |
| dsh-session | 会话日志/SessionStore | KNOWN_SESSION_EVENT_TYPES:79；Session.id=header.id；fork/buildForkSeed |
| dsh-agent / dsh-agent-loop | agent 注册与循环 | agents 服务 create/resume/get；turn/start data.turn 数字 |
| dsh-client-ui-session | client 会话绑定 | UiSession（session/session-maybe 作用域、bindingSource/provide）；inject=["sessions","slots","remote"] |
| dsh-client-ui-slots | client 扩展点 | SlotCore/renderSlot/use<Name>；SidebarFooterActionOwnerProps 类类型在 api-catalog |
| dsh-client-connection | Host↔Client 通道 | Host: rpc.handle/fetch.register；Client: installConnection + 恢复配置 |
| dsh-storage-domain | 业务持久化 | defineDomain/open、domain/changed 事件（schema 化 KV） |
| dsh-plugin-manager | 装载/组合 | bundleComponentManifests、declaredRows（insert 行校验 :1884） |
| dsh-package-manifest | manifest 权威 | name/version 必填；manifestVersion 可选不强制 |

## 插件 Config / settings 机制（2026-09-30 核查）

- 模块命名导出 `Config` 即声明（cordis registry 读 `plugin.Config`）；校验走 `~standard.validate` **同步**契约；volatile 字段（meta.volatile）解析为 `{get()}` 活引用 + `Symbol.for('cosmokit.volatile.write')` 写协议；loader `_commitVolatile` 编辑后移植新值免重挂载。
- 零依赖手写 schema 三暗门：vendor 须声明 `'schemastery'` 方言（loader equalExceptVolatile 唯一 vendor 分支，diff.ts）、volatile **子节点**自身须带 toJSON（plainSchema 调 `new z(child.toJSON())`）、validate 同步。
- 已知告警：0.1.7 的 settings 服务无 register()（market #677）——宿主侧告警非插件错误。
- 全链路引证：dsh-plugins `docs/research/2026-09-30-dsh-settings-mechanism.md`。

## 存储域补充事实（2026-09-30/10-01 核查）

- **加表不升 version**：域 descriptor 新增表在旧存储上按空表载入（json 后端 `snapshot.tables[table] ?? {}`），同 version 不触发 version-mismatch——**升 version 反而会把已落盘单元 brick**（PR #59 审查对拍真实后端源码）。
- **`domain/changed` 事件**：每写耐久后按写序 emit 一次，载荷 `{domain, table, key, operation: 'put'|'deleted', value?}`（携带新快照非旧值）；监听者抛错宿主兜底；**进程内事件**（第二宿主进程不可见）。事件源用官方，不自建存储层事件。
- 已知宿主侧观察（headless lab，定因中）：经 `configEditor.edit → hmr.runExclusive` 的写路径在 headless 组合抛 `HMR is disposed`；bizlink 条目 disable→enable 的 enable 段偶发 `cannot create effect on inactive context`。写路径宿主级验证归 GUI 组合窗口（dsh-plugins triage-p3-hmr.md）。

## 观测点

- 宿主日志：`~/Library/Application Support/DSH Desktop/logs/host/dsh-<date>.log`（[I/W] 前缀、logger 名=插件 name）。
- 桌面日志：同目录 `dsh-<date>.log`（启动头含版本/run id/proxy）。
- dsh-market 已知告警：0.1.7 的 settings 服务无 register()（#677）——非插件错误，勿误判。
