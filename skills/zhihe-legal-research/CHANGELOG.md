# 变更日志

## [1.2.1] - 2026-04-08

### 新增

- 手机号持久化存储：登录后自动保存手机号，token 过期时可省略手机号直接发送验证码
- 自动重登流程：检测到 token 失效后只需提供验证码即可完成重登

### 修复

- 处理服务端 500 错误：token 过期时服务端返回 HTML 而非 JSON，导致 auth check 崩溃
- 修复报告下载：报告 API 不返回 `has_report` 字段，改用 `code` 状态码判断
- 修复 Unicode 文件名：中文全角问号 `？` 导致 `mkdir` 失败，改用 python3 处理
- 修复归档文件名：`result.md` 改为主题命名，Word 转 MD 使用 `_报告.md` 后缀避免覆盖
- 修复 query 提取：monitor.sh 从 status API 提取 query（result API 不含该字段）
- 修复 JSON 注入：`submit_query`、`send_code`、`verify_code` 改用 `jq` 构造 JSON

### 改进

- 配置文件从 `config` 重命名为 `.env`，更符合惯例
- 归档帮助文本更新为实际目录结构

## [1.2.0] - 2026-04-06

### 改进

- 重写异步任务处理机制：去掉 Sub Agent 后台监控，改为用户主动查询，兼容 Claude Code 和 OpenClaw
- 去掉"每次消息前自动检查结果"机制，避免旧结果污染当前对话
- 新增 Claude Code 增强模式：使用 `Bash run_in_background` 可选后台监控
- 清理 completed.json/notified.json 中的残留空 query 旧数据
- Front Matter 规范化：补充 homepage、author、version 字段，license 格式统一
- 修复 name 字段大小写（Zhihe-Legal-Research → zhihe-legal-research）
- 更新交互示例文档，移除 Sub Agent 相关示例

## [1.1.0] - 2026-03-10

### 新增

- Sub Agent 后台监控机制：提交问题后自动启动 Sub Agent 监控
- 状态持久化：任务状态保存到 assets/ 目录
- 主动通知：每次用户发消息时自动检查已完成任务
- 新增 monitor.sh 脚本：管理后台监控和结果通知
- 支持用户在等待期间继续其他任务

### 改进

- 用户无需手动发"查看结果"，系统自动检测并通知
- 优化用户体验：提交后可做别的事，完成后主动告知

## [1.0.0] - 2026-03-10

### 新增

- 初始版本发布
- 支持登录认证（手机号 + 验证码）
- 支持提交法律研究问题
- 支持查询任务状态和获取结果
- 支持获取 docx 格式研究报告
- 支持阻塞式轮询等待（wait 命令）
- 支持查看历史记录
- Token 管理脚本（存储到 assets/config）
- 将所有 curl 命令封装为独立脚本
- 将 API 文档移至 references/
- 添加配置模板 config.example
