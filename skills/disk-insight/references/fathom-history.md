# 只读复用 Fathom

本 Skill 参考 Fathom 的快照、同口径差分、同级下钻、事实与解释分离思路；脚本独立实现，不导入其代码。项目资料只作为设计输入，不代表授权推进 Fathom 的开发任务。

## 找到真实数据库

优先使用用户明确给出的 `FATHOM_DB` 或运行目录。默认自动检查常见发行版入口 `~/Library/Application Support/Fathom/data/fathom.db` 与开发版 `~/Library/Application Support/maoscripts/fathom/data/fathom.db`。两处可能并存，先看快照时间、扫描根和数据集，不能混合；需要搜索自定义位置时使用只按文件名 `fathom.db` 限定的 `--db-dir`，不要递归整个 HOME。

```bash
python3 "SKILL_DIR/scripts/disk_probe.py" fathom-list --db "/实际路径/fathom.db" --output "/私有输出目录/history.json"
python3 "SKILL_DIR/scripts/disk_probe.py" fathom-diff --db "/实际路径/fathom.db" --before 19 --after 24 --focus "$HOME/.codex" --depth 1 --output "/私有输出目录/growth.json"
```

ID 仅为示例，必须先列真实快照选择。日常优先使用 `history`：它按候选库、焦点和请求天数选择同数据集前后快照，返回可用库发现报告、目录差分、`volume_stats` 与 `container_capacity_samples`。时间窗与用户要求不同须说明。脚本使用 SQLite `mode=ro`、`query_only` 与读取事务，不调用 Fathom 的连接/迁移函数，不 VACUUM、checkpoint、改调度或触发扫描。只支持已核 schema 9；不支持的版本保留原库，改用定向采集。若 WAL 模式不能只读打开，报告失败，不用 `immutable=1` 忽略活跃 WAL 伪造一致性，也不把库和 WAL 拆开复制。

## 可比性与读数

- 比较键为 `root / min_kb / exclude_names / metric_version / plan_id`，缺失关键值拒绝差分；按实际时间正向比较。两张快照的质量、denied/vanished 等一并返回。
- `history` 优先选择覆盖请求天数的最近基准；没有满足天数的基准时才使用最早基准，并返回 `actual_days`。多个候选库按可比较快照的最新 after 时间选择，不用数据库路径名猜新旧。
- 用户目录的普通路径与 Data 卷下的别名路径不自动改写为同一路径。整盘 `/` 与 Data 卷不能互换；同一轮各卷或别名目录不能简单求和。
- `volume_stats` 与 `container_capacity_samples` 是物理容量线索；容量样本可能稍晚于同轮目录快照，脚本用最近样本并输出时间距离。目录累计读数不能换算成可释放空间；APFS clone/硬链接、活跃写入和共享剩余空间都可能让二者方向或幅度不同。Chrome `code_sign_clone` 这类 copy-on-write 应用副本必须先读容量历史，不得按 `du` 判断主要占用。
- 输出根自身和指定深度内目录，`size_kb × 1024` 为字节。父级已含后代，不对返回行求总收益。`delta_bytes` 仅在两侧都记录该目录时产生；单侧缺失写 `not_recorded_before/after`。
- `partial` 快照仍能支持已记录目录的有限比较，但不能证明整个区间全覆盖、缺失路径已删除、目录重命名或真实可回收量。快照创建时间与现时 stat 都写入分析。
- 数据集不匹配、legacy NULL 元数据、倒序时间、范围越界、schema 未知或 SQLite 错误：非零退出，无成功 JSON。不能靠补 0 绕过。
