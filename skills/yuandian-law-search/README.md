# 元典法律检索 (yuandian-law-search)

优先调用可用的元典 MCP，无 MCP 时走 API；轻量理解法律问题，复核候选的实际适用性，按需输出精选报告。普通单争点无需完整涵摄矩阵或 JSON，不自动语义＋关键词双检索，也不按 aggressive 配置批量取详情。

## 快速开始

已有元典 MCP：直接让 Agent 使用工具，无需配置本地 Python 或 API Key。工具可选参数遵循当前 schema，未设置的使用服务端默认。

没有 MCP：配置环境变量 `YD_API_KEY` 或参照 `scripts/.env.example` 填写 Key。CLI 使用 Python 3 标准库，无第三方依赖。

```bash
scripts/yd-run --no-report detail "中华人民共和国民法典" --ft-name "第六百九十二条"
scripts/yd-run --no-report case-semantic "员工离职带走客户名单，如何认定商业秘密侵权"
```

`--no-report` 不写 Markdown，但仍写原始 JSON；`--no-archive` 才关闭检索留存。原始响应不是正式报告，不提交到公开仓库。归档目录可经 `--archive-dir` 或 `YD_ARCHIVE_DIR` 设置，缓存命中不重复请求或扣积分。缓存不替代对规范最新状态的核验。

详细配置、费用与网络排查见 [API 入口](references/09-api-usage.md)，MCP 的可选归档见 [MCP 指南](references/05-mcp-workflow.md)。

## 中间层保留什么

- 把问题问准：保留能改变适用的事实，不粘贴全案、不凭记忆预定结论。
- 把材料选准：分数高不等于能用，同案由不等于同争点。
- 只补真正的缺口：已有结果足够即停止；事实缺失不靠更多查询掩盖。
- 报告只放必要依据：法规与案例分组，解释适用前提，未核实的明确披露。

涵摄仍是法律判断方法，但不要求每次展开表格。只有多争点关联、决定性规则冲突或明确的深度研究需求，才加载 [完整研究合同](references/07-research-middleware.md)。

## 生成报告

仅在用户要求时生成。普通报告使用 focused 轻量记录，输出四节简版，查询轨迹折叠置后；复杂报告保留原七节格式。两者共用精选来源门禁，禁止原始召回整体进入正文。12条是上限，不是目标。

输入示例与命令见 [报告生成](references/03-report-consolidation.md)。未形成文件化报告的普通对话，不需要两份 JSON。

## 本轮验证与边界

v1.10.0 用保证期间、客户名单、过户尾款、租赁保证金四类去身份化问题完成8次真实 API 请求，发现近邻规范和关键事实错位；用两条已核验规则生成简版报告。离线回归覆盖默认／显式参数、日期映射、归档失败、focused 合同和原始召回隔离。

这不是同模型多轮 Agent A/B。尚未测得首工具时延、reasoning token 或总 token 降幅；未连接真实 MCP 做端到端验证。旧 aggressive 配置保留但不再控制普通检索。CLI 仍可能展示大量原生候选，不宣称所有上下文开销已解决。

完整变化见 [CHANGELOG](CHANGELOG.md)，历史版本事实保留在那里。此 Skill 不替代完整证据审查、诉讼方案或正式法律意见。

## 许可证与作者

MIT License，见 [LICENSE.txt](LICENSE.txt)。杨卫薪律师（微信 ywxlaw）。
