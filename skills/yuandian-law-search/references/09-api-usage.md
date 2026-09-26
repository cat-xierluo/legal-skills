# 无 MCP 时的 API 入口

使用本 Skill 的 `scripts/yd-run` 启动标准库 Python CLI。示例路径相对于 Skill；在案件目录工作时使用该脚本的绝对路径，输入文件也优先用绝对路径。

## 鉴权

优先读取环境变量 `YD_API_KEY`，其次读取 `scripts/.env`。脚本会检查缺失和占位值；不要另行输出密钥。首次配置可参照 `scripts/.env.example`，Key 从 [元典开放平台](https://open.chineselaw.com) 获取。未配置时提示用户配置，不能阻止独立的 MCP 路径。

## 常用入口

```bash
scripts/yd-run --no-report detail "中华人民共和国民法典" --ft-name "第六百九十二条"
scripts/yd-run --no-report search "普通房屋租赁中履约保证金的性质及违约金调减"
scripts/yd-run --no-report case-semantic "员工离职带走客户名单，何种信息和保密措施构成商业秘密"
scripts/yd-run --no-report case "房屋买卖 过户 尾款 同时履行"
scripts/yd-run --no-report keyword "违约金" --fgmc "中华人民共和国民法典"
```

全局留存参数放在子命令前。普通调用不再继承 aggressive 的参数；语义默认不发送 rewrite_flag/return_num，关键词不隐式增加 top_k。需要覆盖时显式用 `--return-num`、`--rewrite-flag`／`--no-rewrite`、`--top-k`，以各子命令 `--help` 为准。不要固定预设候选数或自动双查。

法条 `detail` 支持 `--reference-date`。案例详情使用 `case-detail --type ptal --id ...` 或 `--ah ...`；权威案例类型用 qwal。案例语义和关键词的日期／筛选字段不同，读取具体 `--help`，不要猜参数。

企业信息、法规全文、幻觉检测等扩展接口只在用户要求的范围内使用，按需查 `scripts/yd-run --help`、`endpoints/` 或 [企业画像](06-enterprise-portrait.md)，不作为普通法律检索默认步骤。本地 adapter 的接口清单不等于官网全部服务。

## 网络与费用

普通法条／案例接口标价通常为每次10积分，价格以平台为准；缓存命中不请求网络、不消耗新积分。不要仅为补写 Markdown 底稿重复请求。

`yd-run` 清理代理等环境变量并传递鉴权、归类和归档目录设置，不改变系统权限。网络失败先运行无积分的 `scripts/yd-run --network-check`，核查 DNS/TLS；受限环境需按宿主权限流程处理，不盲目重试。响应已返回但归档失败时仍交付响应并告警，不再次请求。

API 原始 JSON 默认归档；正式报告只消费 Agent 精选，见 [报告生成](03-report-consolidation.md)。
