# OpenClaw 或其他 Agent 调度器

## 使用 Agent 任务，不使用裸 cron 冒充研究

调度器必须能执行一段完整 Agent 提示词。任务内容与 `workbuddy-deploy.md` 相同：调用 `legal-client-brief`，完成增量研究和三渠道校验，再构建本地 `_DRAFT` 草稿包。

建议任务定义包含：

- 明确日期窗口与 `daily/weekly/event` 频率；
- 明确三个配置文件的位置；
- 禁止自动外发；
- 失败时保留校验错误，不生成“成功”通知；
- 只把本地草稿路径交给人工复核。

## 仅打包已有 Markdown

如果系统只能执行命令，先由人工或 Agent 生成并校验 Markdown，再运行：

```bash
python3 scripts/build_report.py \
  --kind brief \
  --input archive/客户简报_<受众>_<cadence>_<period_end>_DRAFT.md \
  --moments-copy archive/朋友圈_<受众>_<period_end>_DRAFT.md \
  --wechat-draft archive/公众号_<受众>_<period_end>_DRAFT.md \
  --profile config/report-profile.md \
  --audience-profile config/audience-profile.md \
  --whitelist config/sources-whitelist.txt \
  --cadence <daily|weekly|event> \
  --period-start <YYYY-MM-DD> \
  --period-end <YYYY-MM-DD>
```

这条命令不会选题、检索、写正文或发送文件。已有同名派生文件时默认停止；人工确认要重建后才加 `--force`。

## 完成条件

- `validate_report.py` 返回 0；
- PDF 页数非零且每页 A4；
- `.meta.json` 与 PDF 哈希对应；
- `.checklist.md` 已生成；
- 没有外部发送、自动改名或自动复制发布版。
