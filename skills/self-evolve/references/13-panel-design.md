# Localhost Review Panel

## 定位

面板是人工审阅和状态观察入口，不是调度控制器。它只绑定 loopback，读取外部数据根，并使用一次性访问令牌建立浏览器会话；受限人工决定还必须通过 Origin 与 nonce 校验。

启动：

```bash
python3 scripts/panel.py --host 127.0.0.1 --port 8765 --open
```

`--open` 会打开启动时生成的一次性认证 URL。未使用 `--open` 时，只打开终端打印的完整 URL，不要省略 `#token=...`。fragment 不会发送给 HTTP 服务；页面用它完成一次 POST 交换后立即从地址栏清除并使访问令牌失效。会话只写入当前 origin（scheme + host + port）的 `sessionStorage`，API 通过显式 Authorization 请求头携带，不设置 Cookie；关闭该浏览器会话后需要重启服务获取新入口。访问令牌不得写入日志、静态快照或持久化状态。

生成静态快照：

```bash
python3 scripts/render_panel.py
```

## 页面信息

### Overview

- 外部数据根布局与迁移状态；
- 旧 SessionEnd 残留诊断；
- 最近调度运行与失败原因；
- active/archive 来源覆盖；
- 待审、隔离、已决定、已应用和已验证数量。

### Review Inbox

- proposal ID、目标 Skill、机器处置和人工决定；
- privacy status 与产物哈希；
- change points、脱敏证据 ID 与新颖性判断；
- 接受、部分接受、拒绝、观察四类人工操作；
- applied commit 与 outcome（只展示规范存储中的数据）。

### Timeline / Clusters

- 时间范围、来源配额、cluster cohesion；
- 成员摘要与逻辑 evidence ID；
- 不显示 transcript 原文和完整私有路径。

### Runtime

- inventory、portrait、chain graph 最近更新时间；
- backfill 状态；
- 调度日志的有界尾部；
- quarantine 规则计数，不显示命中原文。

## 写操作边界

允许：

- 在已认证会话中通过 Origin + nonce 对既有 proposal 追加人工决定；
- 输入理由和部分接受条目；
- 刷新页面数据。

不允许：

- 修改任务启停或计划；
- 执行任何调度任务（面板不存在任务执行端点）；
- 编辑任意 YAML 或 shell 命令；
- 打开任意文件路径；
- 直接修改目标 Skill；
- 覆盖既有人工事件。

所有人工决定还必须经过 proposal store 的服务端校验；前端按钮状态不能作为安全边界。

## 安全要求

- 只接受 `127.0.0.1`、`localhost` 或 `::1`；
- 对每个请求校验精确的 loopback `Host` authority，拒绝 Host header poisoning；
- 裸根页只返回不含状态、proposal、nonce 或凭证的 bootstrap；所有状态 API 都必须校验显式 Authorization，匿名访问返回 401；
- 一次性访问令牌只保存在进程内和 URL fragment，fragment 不进入请求或日志；成功交换后立刻作废并从地址栏清除；
- 不使用认证 Cookie；会话保存在端口隔离的 `sessionStorage`，只由面板脚本显式发送到同源相对 API；
- 写请求必须带与当前服务 origin 完全一致的 `Origin`，并校验 nonce、Content-Type、body 大小和 proposal ID；
- 每次响应生成 CSP nonce，脚本只通过 nonce 加载，不使用 inline event handler；
- proposal 事件流损坏时 GET/POST 均返回明确错误并失败关闭，不展示部分投影；接受或部分接受前还必须重新读取当前唯一 Inbox 产物并核验 SHA-256；
- 响应不包含密钥、Bearer/JWT、挂载卷/主目录完整路径或原始 transcript；
- 静态快照不包含 nonce 或可写接口；
- 对 HTML/JSON 内容做转义，避免 transcript 数据形成脚本注入；
- 人工操作追加审计元数据，但不复制完整正文。

## 实操验收

1. 启动面板并确认只监听 loopback；匿名根页只有 bootstrap，匿名状态 API 返回 401；
2. 用 synthetic proposal 检查四类人工决定；
3. 确认一次性 fragment 成功换取 `sessionStorage` 会话、地址栏 fragment 被清除、Cookie 数量为 0，重复交换返回 403；
4. 确认无会话或无 nonce 写入失败；
5. 确认任意 `/api/tasks/<id>/run-now` 请求返回 404，页面中不存在任务执行按钮；
6. 确认机器 upsert 后人工决定仍保留；
7. 确认恶意 Host、跨站/缺失 Origin、错误 nonce 与损坏 proposal store 均失败关闭；
8. 访问另一个 loopback 端口，确认浏览器不会自动携带会话 Authorization 或 Cookie；
9. 截图或记录 DOM/API/CSP 断言，写入本技能工作记录。
