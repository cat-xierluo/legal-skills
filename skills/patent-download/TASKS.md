# 任务列表

> 本技能的任务清单，记录待办、进行中和已完成的任务。

## 📋 待办任务

- [ ] 发布流程：marketplace.json 收录 patent-download 条目（version 填 2.6.0）
- [ ] 发布流程：根 README.md 添加技能列表行 + 最近更新区
- [ ] 在独立 worktree 内完成提交（git add + commit）
- [ ] 补充润桐 RainPat 平台支持（服务器维护恢复后评估）
- [ ] 完善 uyanip 浏览器下载：监听 download 事件保存文件（当前流程跑通但未保存）
- [ ] 完善 gpic / pss 浏览器下载：实现真正的 PDF 保存逻辑
- [ ] 研究 uyanip / gpic / pss 的 API 接入（当前为 TODO 桩）
- [ ] 处理 epub 平台的验证码/反爬（或确认依赖 download.py 旧入口即可）

## 🚧 进行中任务

- [x] 发布前 skill-lint 审查与问题修复（v2.6.0）

## ✅ 已完成任务

- [x] 多平台架构搭建（cli.py 统一入口 + platforms/ 模块化）
- [x] Google Patents 通道接入（patent-downloader SDK）
- [x] 凭证环境变量化改造（v2.2.0）
- [x] 技术债务清理与文档一致性修复（v2.3.0）
- [x] 6 个脚本外部依赖防护（v2.4.0）
- [x] 凭证隔离安全加固 + check_leak 防泄露自检（v2.5.0）
- [x] 隐私去具体化（真实公司名泛化）
- [x] 发布定位拓宽（中国专利 → 通用专利）
- [x] 文档清理（删除 pss_cookies.txt 残留引用）
- [x] EXAMPLES.md 下沉到 references/examples.md（渐进式披露）
- [x] 半成品平台显式标注实验性 + 静默失败改提示
- [x] LICENSE.txt 版权行统一为项目规范
- [x] SKILL.md 依赖章节重构（开箱即用 / 需安装两档）
- [x] 工作流修正：迁移到独立 worktree 推进，不污染主工作区

---
**最后更新**：2026-07-23
