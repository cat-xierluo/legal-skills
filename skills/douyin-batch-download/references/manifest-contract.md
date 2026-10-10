# Manifest 契约 v1（schema_version=1）

> 建立日期：2026-10-10（DY-003）。本文件是 manifest 数据契约的唯一维护源；消费端（teardown / 插件 adapter）以本文件为准，不在各自文档复制字段清单。

## 目的与边界

- 解决旧 `video_metadata` 的两个不可证问题：**播放量缺失被填 0**（7389 条全 0，无法区分"平台未提供"与"真实零"）与 **INSERT OR REPLACE 不保历史**（指标增长趋势不可回溯）。
- v1 覆盖：作者/作品稳定 ID 关联、指标快照（现值+历史）、缺失语义、播放分母比例规则。**不覆盖**：本地资产绑定（source_video/cover/转录路径为 null，由 Task-002 封面卡与 DCM-004 流水线卡补齐）。

## 顶层结构

```text
manifest.json
├── schema_version: 1
├── generated_at: ISO8601(UTC)
├── source_db / video_root: 来源记录(只读导出)
├── counts: {authors, videos}
└── items[]: 每作品一条
    ├── schema_version: 1
    ├── author: {uid, sec_user_id, nickname, cohort}   # cohort=user_info_web.peer_type;昵称仅显示用,ID 才是关联键
    ├── video: {aweme_id, desc, published_at, duration_ms, local_filename}
    ├── assets: {source_video, cover, raw_transcript, corrected_transcript, frames, note}  # v1 全 null
    ├── metrics_snapshot: {current, history_len, missing_fields[]}
    └── derived: {digg_per_play, note}
```

## 指标快照表 `metric_snapshots`

```sql
CREATE TABLE metric_snapshots (
    aweme_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,      -- ISO8601(秒)
    source TEXT NOT NULL,           -- 'download-v2/aweme_list' | 'legacy/video_metadata'
    window TEXT,                    -- 观察窗口语义,未知为 NULL
    digg_count INTEGER, comment_count INTEGER,
    collect_count INTEGER, share_count INTEGER,
    play_count INTEGER,
    PRIMARY KEY (aweme_id, observed_at, source)
);
```

### 缺失语义（本契约核心）

| 存储值 | 含义 |
|---|---|
| `NULL` | 该指标**未提供/未知**（API 未返回、旧表 unknown_legacy） |
| `0` | 平台返回的**真实零** |

旧 `video_metadata.play_count = 0` 的行在导出/迁移时一律按 **unknown_legacy** 处理：值置 NULL，`missing_fields` 追加 `play_count:unknown_legacy`。

### 幂等与冲突

- 同 `(aweme_id, observed_at, source)` 且各指标值**完全一致** → 幂等忽略（重复导入安全）。
- 同键但任一指标不同 → **拒绝**（`ConflictError`，绝不覆盖）。采集端（download-v2）遇冲突时该轮以失败收场。
- 非法 `aweme_id`（空/非字符串）、非法 `observed_at`、非整数指标 → 拒绝（`ManifestError`）。

## 字段单位与时间

- `video.duration_ms`：毫秒（源 F2 `video.duration`）。≤0 视为未知 → null。
- `published_at`：`create_time`（epoch 秒）转 ISO8601(UTC)；0/负值 → null（未知）。
- `metrics_snapshot.current.observed_at`：观察时刻，非作品发布时刻。
- `window`：观察窗口语义（如"当日增量"）；未定义即 null，**不得臆造**。

## 播放分母规则

- `derived.digg_per_play` 仅当 `play_count` 为**非 NULL 且 > 0** 时计算；缺失/unknown_legacy/真实 0 → **null**。
- 任何消费端不得以点赞/评论/收藏量反推播放量，不得把未知播放命名为"互动率"。

## 导出与迁移（`scripts/manifest.py`）

- `export --db <src> --out <新目录>`：源库以 `mode=ro` 只读打开（前后哈希可比对）；输出目录已存在即拒绝；不写源库任何字节。
- `migrate-legacy --db <副本>`：在**副本**上把旧表行转为 `source='legacy/video_metadata'` 快照（play 置 NULL）；默认拒绝名为 `douyin_users.db` 的主位库。迁移只增表增行，旧表不动；回滚 = `DROP TABLE metric_snapshots`（可恢复）。
- 生产库的正式迁移须先在副本上完整验证并经用户采用确认，本契约不构成生产迁移授权。

## 消费端注意

- 作者与作品用 `uid`/`sec_user_id`/`aweme_id` 关联；**不得按 nickname JOIN**。
- `history_len > 0` 时 `current` 取排序最后一条（每 source 内按 observed_at）；完整历史需读源库快照表。
- 资产字段 v1 为 null 不代表"无资产"，仅"未绑定"；不得把 null 当作封面缺失的最终结论。
