# Reference 24 — sub2api 四条积分 lane 的 summary 生产方与临期调度

> 本文档是 SKILL.md 第 7 节"Backend、额度与依赖"的按需参考。读取时机：要为 sub2api 网关覆盖的四条积分通道接入真实额度信号、搭建/排障 sub2api lane 的 summary 生产链路，或设计"临期积分优先消化"的派发策略时。**本文档是纯知识文档：任何脚本永不读取它。**

## 1. 定位与数据边界

sub2api（本仓库 `参考项目/sub2api`）是把本机多个 AI 订阅登录态（腾讯 CodeBuddy / 千问办公 Qoder 系 / LobsterAI / AutoClaw 智谱）转成本机 OpenAI/Anthropic 双协议网关（`http://127.0.0.1:8787`）的服务。四条通道各自有积分/额度，且**过期策略不同**：

| lane | 过期策略 | 额度来源 | 数据形态 |
|---|---|---|---|
| `qwenworkai` | qodercn 专属包有 expires_at；千问办公每日 100 **当日过期** | 网关 `qwenwork_upstream.quota_summary()`（直查官方 `/api` 端点，无签名墙） | `remaining_total` 双池合计 + per-app 分项 |
| `lobsterai` | campaign 积分逐条 `expires_at`（每日登录奖励 100/条，滚动过期） | 网关 `lobster_upstream._fetch_credit_data()` | `remaining` + `credit_items[]` 逐条临期 |
| `autoclaw` | JWT 有效期可读；积分端点已探明（细节与接线卡点见 sub2api 仓库 DEC-029，未接线前 lane 为 health-only） | 网关 `zai_upstream.credentials_status()` | 当前仅 health（`resets_at`/余量待接线后补） |
| `codebuddy` | 积分余额经聊天响应 `credit_used` 增量观测；无独立查询端点 | 网关 account pool summary | 仅 health + `account_count` |

**公私边界**（对齐 Reference 21 的 zcode 模式）：公开侧（本 Skill）只做中立合同 `quota-aware-routing.summary.v1` 的消费方与合并写入方；凭证解密、签名、官方 API 直查全部在 sub2api 网关侧完成。本 Skill 的 `scripts/quota_summary_sub2api.py` 只 HTTP 拉网关 `/ui/api/quota`，**不接触任何凭证文件**。

## 2. 数据流

```
sub2api 网关（8787，launchd 常驻）
  └─ GET /ui/api/quota                    ← 2026-09-14 新增聚合端点
       ├─ qwenwork_upstream.quota_summary()
       ├─ lobster_upstream._fetch_credit_data()
       ├─ zai_upstream.credentials_status()
       └─ get_account_pool().summary()
       输出：quota-aware-routing.summary.v1（schema 同名，lanes 键 = 网关通道名）
              │
              ▼
scripts/quota_summary_sub2api.py --gateway-url http://127.0.0.1:8787 --out <summary_path>
  合并语义（与 21-zcode-quota-producer 一致）：
    - 只替换 COVERED_LANES（qwenworkai/lobsterai/autoclaw/codebuddy）
    - 其余 lane（glm-api/minimax/zcode/…）原样保留，generated_at 不续期
    - 网关不可达 → exit 1 不写文件（fail-closed，绝不编造数据）
              │
              ▼
route-summary.json（与其他生产方共用一份）
              │
              ▼
route_suggest.py（评分选 lane） / quota_preflight.py（派单前预检门）
```

## 3. lane 记录字段（v1 合同内，附加键消费方忽略）

```json
{
  "type": "fuel",                      // qwenworkai=fuel；lobsterai/autoclaw/codebuddy=reservoir
  "health": "ok",                      // ok | unavailable
  "remaining_total": 7238.0,           // qw 双池合计（qodercn 5138 + qwenwork 2100）
  "remaining": 6599.84,                // lobster 归一化余量
  "expires_at": "2026-09-29T15:02:39", // lobster 最早过期分项
  "credit_items": [                    // lobster 逐条临期（PM 派发前看这里）
    {"type": "campaign", "label": "每日登录奖励", "remaining": 100.0, "expires_at": "..."}
  ],
  "updated_at": "<本 lane 数据时刻>",   // 溯源
  "source": "sub2api-gateway"
}
```

## 4. 临期调度策略（expiry_burn scene）——只做边缘消耗，不进正常派发

**边界（用户定稿 2026-09-14）**：临期积分 lane（`qwenworkai` / `lobsterai`）**不进任何 `tier_policy` 链**——`route_suggest` 对不在链内的 lane 不会自动推荐，正常 tier 派发（L0/L1/L2/multimodal）零影响。消耗临期积分只有两条路径：

1. **PM 显式选路**（主路径）：当且仅当一个**已通过价值门**的任务本身就是边缘批量型（scene ∈ `expiry_burn` / `overnight_batch` / `long_tail_cleanup`），PM 才显式 `--provider sub2api-qw-flash` / `sub2api-lobster-flash` 派发。判据：
   - **qw**：UTC+8 傍晚后 `remaining_total` 中千问办公池大额未用（每日 100 不吃清零）→ 边缘批量任务（文档整理/批量提取/初筛清单）派 qw；CLI 分钟级时延，并发 cap 2，不派交互式任务
   - **lobster**：`credit_items` 中 7 天内到期分项合计 ≥ 300 → overnight_batch 优先 lobster（cap 1）
2. **外围边缘任务源**：如私仓 idle-task-runner 这类常驻"闲时消化器"按自己的节奏显式指定 provider 消耗——skill 只做选路合同，**不生成 quota-burn 工作**（SKILL.md §7 硬约束：额度只为已通过价值门的任务选路）。

**判定纪律**：先有任务（价值门已过、类型匹配边缘批量），再看临期数据选路——顺序不可颠倒；绝不为消化积分而发明任务。lane `health != ok` 或 summary 过期 → 预检门拒绝，回退正常 lane，不因临期放宽健康门槛。

## 5. 刷新与排障

- **手动**：`python3 scripts/quota_summary_sub2api.py --gateway-url http://127.0.0.1:8787 --out <summary_path>`（stdout 打印合并后 summary，exit 0/1/2）
- **定时**：把上面命令挂进 `probe_schedule.sh`（与 zcode 生产方同节奏，5-15 分钟一次即可；网关侧各通道自有 TTL 缓存 60-300s，无须更密）
- **网关起不来**：`launchctl kickstart -k gui/$(id -u)/com.sub2api.gateway`（launchd 守护名以 `launchd.py --status` 输出为准）
- **端点 404**：网关进程是旧代码——重启守护后 `/ui/api/quota` 才存在
- **测试**：`python3 tests/test-quota-summary-sub2api.py`（mock 网关响应，4 例：首次写入/合并保留/旧 lane 替换/不可达 fail-closed）

## 6. 并发与限流特性（各 token 来源实测口径）

| lane / token 来源 | 并发上限 | 限流特征 | 派发纪律 |
|---|---|---|---|
| `autoclaw`（智谱） | **1**（`concurrency_cap: 1`） | **严格**——调用速度过快即触发限流报错（用户实测口径）。单人单 token，无多账号轮换余地 | 串行派发；任务间隔留缓冲；限流错误按退避处理，不立即重试 |
| `qwenworkai`（千问/Qoder） | **2**（网关 CLI 信号量 `QW_MAX_CONCURRENT=2` 硬限） | 未观测到平台限流；瓶颈是 CLI 子进程本身（单请求分钟级） | 上限即网关信号量，PM 无须再收紧；勿派交互式/时限敏感任务 |
| `lobsterai`（有道） | 1（保守值） | 未观测到限流 | cap 1 为保守起点，实测无压力后可放宽 |
| `codebuddy`（腾讯） | 池轮换（默认 ≤3，多账户自动轮转） | 未观测到限流；多账户天然分摊 | 401/403/429 时网关自动换账户重试，PM 层无须介入 |

**通用纪律**：并发上限以个人配置 `concurrency` 与 lane `concurrency_cap` 为准（spawn-worker 副作用前原子占槽）；限流表现为上游 429/业务错误码时走失败恢复门分类，**不做立即重试**。AutoClaw 是唯一已知"快了必炸"的通道——对它宁可欠并发不可过并发。

## 7. 重新评估条件

- AutoClaw 积分 lane 的端点/签名/token 解密接线细节与当前卡点，记载于 **sub2api 仓库 `docs/DECISIONS.md` DEC-029**（本 skill 公开仓库不收录上游逆向情报）；接线完成后本表 autoclaw 行补 `remaining`/`expires_at`
- CodeBuddy 出现独立余额查询端点 → `codebuddy` lane 补余量
- sub2api 网关若下线 `/ui/api/quota` 或改 schema → 本生产方 exit 1，预检门按 stale fail-closed，不会误派
- 各通道限流特征变化（尤其 lobster/codebuddy 首次观测到限流）→ 更新 §6 表并同步个人配置 lane note
