# 变更日志

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
