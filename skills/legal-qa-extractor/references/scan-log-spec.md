# 扫描与归档规格说明

本文档定义 `archive/scan-log.json` 的结构规范和扫描行为，供定时任务和未来 Agent 理解。

---

## 一、watch_paths 配置

```json
"watch_paths": [
  {
    "path": "~/Desktop/Clawd/10 - ⚖️ 法律工作/工作文档/011 - 潜在项目",
    "last_scanned": "2026-05-10T23:00:00+08:00",
    "status": "active"
  }
]
```

- 每次全量扫描后更新 `last_scanned`
- `status`: `active` | `archived`

---

## 二、文件夹类型判断

| 命名模式 | 示例 | 类型 | 扫描方式 |
|----------|------|------|----------|
| 纯数字 | `24` | 归档容器 | 深度扫描内部每个子文件夹 |
| 日期区间 | `25 01-06`、`26 01-06` | 归档容器 | 深度扫描内部每个子文件夹 |
| 日期+姓名/公司 | `260323 张美金 浙江腾宇包装公司 咨询` | 直接项目 | 直接扫描内容文件 |
| 其他 | `240428 薛心澄房屋买卖转移登记` | 直接项目 | 直接扫描内容文件 |

**关键原则**：归档容器本身不输出 QA，其内部的每个子文件夹才是独立项目。

---

## 三、files 记录

```json
"files": {
  "path/to/file.md": {
    "content_hash": "sha256:abc123...",
    "last_modified": "2026-05-09",
    "last_extracted": "2026-05-10",
    "qa_count": 5,
    "status": "active"
  }
}
```

- `content_hash`：文件内容 SHA-256，仅计算文件内容，不含路径/mtime
- 增量判断：hash 一致 → 跳过；hash 变化或文件新增 → 触发提取
- `status`：`active` | `archived`（文件被移走后从 `files` 移到 `archived`）

---

## 四、projects 聚合

```json
"projects": {
  "240428 薛心澄房屋买卖转移登记": {
    "source_files": ["240428 薛心澄.../沟通记录1.md", "240428 薛心澄.../沟通记录2.md"],
    "last_extracted": "2026-05-10",
    "qa_count": 8,
    "output_file": "archive/extractions/2026-05-10_240428 薛心澄..._qa.md",
    "status": "active"
  }
}
```

- 一个项目 = 一个直接子文件夹（不含归档容器内的子项目）
- 多轮咨询合并：同一项目下所有 `.md/.txt` 文件合并为单份 QA 输出
- 去重：相同问题保留最新解答
- 输出文件命名：`{日期}_{项目名}_qa.md`

---

## 五、archived 记录

```json
"archived": {
  "011 - 潜在项目/24/240428 薛心澄": {
    "archived_at": "2026-05-01",
    "reason": "moved_to_archived_folder",
    "last_known_qa_count": 3
  }
}
```

- 用户归档操作后，将对应路径及其下文件标记为 `archived`
- 扫描时跳过所有 `status: archived` 的路径
- 定期清理 `archived` 记录（超过 6 个月的可删除）

---

## 六、扫描流程摘要

```
1. 加载 scan-log.json
2. 遍历 watch_paths 下的直接子文件夹
3. 判断每个文件夹类型（归档容器 / 直接项目）
4. 归档容器 → 递归获取所有子文件夹 → 每个子文件夹视为一个项目
5. 直接项目 → 直接作为项目处理
6. 对每个项目的文件计算 content_hash
7. 对比 scan-log：hash 变化或文件新增 → 触发提取
8. 提取完成 → 更新 files 和 projects 记录
9. 保存 scan-log.json
```
