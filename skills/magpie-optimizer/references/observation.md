# 观测合同与数据口径

## 主要来源

| 数据 | 来源 | 覆盖边界 |
|---|---|---|
| 请求、概览、时序、来源分列 | GET /v1/magpie/usage/requests | period/day筛选及分页；读取到的全部不等于平台全部账单 |
| 上下文分项、增长、缓存 | 本机 routing/YYYY-MM-DD.jsonl 或 gz | 保留历史样本；无匹配样本写缺失 |
| 会话、项目摘要、工具与Skill计数 | Magpie sessions.json缓存v19 | 按文件汇总，可能包含主线程/子任务；不与请求账直接相加 |
| 供应商与分组状态 | providers.json字段白名单 | 无密钥/账号/路径；启用不保证额度和可调用性 |
| 额度 | magpie_route.py inspect --live | 多窗口分别读取；订阅until不等于积分批次到期 |

本机配置路径尊重 XDG_CONFIG_HOME，缓存尊重 XDG_CACHE_HOME。HTTP仅允许数字回环地址、限定GET路径、不经环境代理、不跟随重定向，不读取网关密钥。脚本不启动桌面内部Web API；/api/context 与公开网关不是同一路径。

## 等待、分页与接续

首次索引可能耗时。默认单次180秒、总预算600秒、每页500条、最多100页；--timeout/--budget/--max-pages可调。有界等待交给运行中的进程，主Agent每约一分钟报告进展，不重复并发扫描。超时或读取错误保存 PENDING/PARTIAL，保留已读页的offset、count、SHA和总量。

当前CLI重新采集会从头核验；部分观察可用于有限诊断，不提供跨进程盲接旧offset。接续时优先选择已结束日期并重取，利用Magpie自身索引缓存；超大窗口缩小日期后分段读取，分别保留覆盖，禁止只改旧状态为完整。未来服务若提供稳定游标再升级真正断点续传。

完整分页后，跨多页重读首屏与total，防止常见偏移；无法排除上游在读期间以相同总量替换中间页，故不声称事务快照。总量变化、重复页、请求级跨页重叠、空页未达total、最终回查失败均保留PARTIAL。只读首屏时是样本。

schema `magpie-observation.v1`。ledger含原生/网关/上报聚合与投影rows；context、native独立状态。完整请求账与局部上下文/工具缓存可同时存在，不用单一总PASS遮盖缺口。context_summary 只计算有效主请求，压缩计数是tokens显著下降的启发式推断。未知窗口不补默认容量；提示词大于声明窗口标记元数据冲突，不按大于100%的比率推断真实溢出；未读到缓存计数不当0%命中。局部缓存/路由读失败保留已取得请求账。

## 诊断

schema `magpie-diagnosis.v1`，绑定观察内容哈希。每条含fact、hypothesis、suggested_action、verification_metric、evidence，不写自动完成/浪费判决。当前工具定义10%、结果15%、窗口70%、错误加重试2%是检查对象的筛选阈值；不表示用户任务违规或低效。先确认样本、缓存和任务目标，再提出调整。

CLI可读 magpie sessions --days N --json 进行日期/模型/项目统计；具体shell命令需要按需读取原始调用参数并脱敏，工具名exec/terminal/js的频次不能解释成shell内部rg/git等频次。缺Skill计数保持未知。
