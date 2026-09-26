# MCP 优先，按需归档

有可用元典 MCP 时直接调用，不另跑 API。MCP 是接入方式，不是统一搜索算法；以当前客户端公开的工具 schema 为准，选择其中的语义、关键词、详情或结构化筛选工具。

## 默认执行

1. 单个明确法律问题：保留决定性事实，直接调用相应工具。
2. 未指定的可选参数留给工具默认值；不用本地 `YD_STRATEGY` 覆盖。
3. 复核候选的适用性及文本支持，给精选答复；仅因有明确未解决问题才追加。
4. 用户要求报告时，整理实际执行过的查询和精选来源，见 [报告生成](03-report-consolidation.md)。

不把研究计划 JSON、CLI 校验、`ingest`、正反两轮查询或固定数量详情设为 MCP 前置条件。也不要求每个对话答复都生成精选 JSON。

## 配置与机制依据

配置以 [元典官方 MCP 页面](https://open.chineselaw.com/mcp-config/) 和客户端支持方式为准。仓库 `scripts/.mcp.json.example` 是部分服务的模板，不是官方服务全量清单，也不保证不同客户端采用同样的工具名称。

2026-09-22 核对的官方说明：

- [法条语义检索](https://open.chineselaw.com/api-square/17/) 与 [案例语义检索](https://open.chineselaw.com/api-square/16/) 暴露 `query`、`rewrite_flag`（默认 false）与 `return_num`（默认 45）。后端未公开完整算法细节，不推断其 embedding、重排模型或精度保证。
- [普通案例关键词检索](https://open.chineselaw.com/api-square/7/) 支持关键词及结构化字段，默认 AND、top_k 10。
- 若当前 MCP schema 与页面不同，遵循当前工具实际参数并记录差异，不能机械透传 CLI 字段。
- 案例语义返回可以含平台整理的内容；“内容完整”不保证是原判逐字全文。

这些默认值可能变化，运行时不靠 Skill 硬编码来冒充服务端默认。

## 可选：归档已有响应文件

只有需要留痕且工具已提供响应文件时，再使用：

```bash
scripts/yd-run --no-report ingest --query "本次法律问题" \
  --endpoint "/open/law_vector_search" --input /absolute/path/result.json
```

该操作不再次请求 API。不要通过大段 echo 或人工转写重建整个响应；没有原始文件时保留调用记录和具体来源链接，不编造 archive_ref。原始响应只供复核，不自动纳入正式报告。普通检索无需为了留痕完成这一步。
