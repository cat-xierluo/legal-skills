# 通用 cron 部署说明

适用于：系统 crontab / launchd / Cloud Functions / GitHub Actions 等任何支持定时任务的平台。

## Linux / macOS crontab

```cron
# 编辑 crontab
crontab -e

# 加入（每周一 09:00）
0 9 * * 1 cd ~/.claude/skills/weekly-legal-briefing && \
  python3 scripts/run_one_period.py \
    --audience "科技型制造企业" \
    --period-number $(($(ls archive/法律周报_*.meta.json 2>/dev/null | wc -l) + 1)) \
    >> archive/_cron.log 2>&1
```

## macOS launchd（替代 cron）

```xml
<!-- ~/Library/LaunchAgents/com.lawyer.weekly-briefing.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.lawyer.weekly-briefing</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/{USERNAME}/.claude/skills/weekly-legal-briefing/scripts/run_one_period.py</string>
        <string>--audience</string>
        <string>科技型制造企业</string>
        <string>--period-number</string>
        <string>AUTO</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/{USERNAME}/.claude/skills/weekly-legal-briefing/archive/_cron.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/{USERNAME}/.claude/skills/weekly-legal-briefing/archive/_cron.err</string>
</dict>
</plist>
```

加载：`launchctl load ~/Library/LaunchAgents/com.lawyer.weekly-briefing.plist`

## GitHub Actions（云端版）

```yaml
# .github/workflows/weekly-briefing.yml
name: 每周法律周报
on:
  schedule:
    - cron: '0 1 * * 1'  # UTC 01:00 = 北京时间 09:00
  workflow_dispatch:      # 允许手动触发

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: 安装 Playwright + pymupdf
        run: pip install playwright pymupdf jinja2 markdown beautifulsoup4 pyyaml && python -m playwright install chromium
      - name: 生成本期 md（AI 步骤需用 actions/ai 或外部触发）
        run: |
          # 由 GitHub Action 调用大模型 API 或人工触发
          # 此处省略；产出应落 archive/{audience}_第N期_DRAFT.md
          echo "本期 md 应已就位"
      - name: 渲染 PDF
        run: |
          python3 scripts/run_one_period.py \
            --audience "科技型制造企业" \
            --period-number ${{ github.run_number }}
      - name: 上传 artifact
        uses: actions/upload-artifact@v4
        with:
          name: weekly-briefing-draft
          path: archive/法律周报_*_DRAFT.pdf
```

## 调试清单

- [ ] 首次部署后,手动跑一次确认能成功生成 PDF
- [ ] 检查 `archive/_cron.log` 有正常输出（不是 stack trace）
- [ ] 检查 `_meta.jsonl` 增量追加
- [ ] 复核时长 ≤ 15 分钟/期
- [ ] 7 天后第二次跑,确认期数自动递增

## 多个 audience 并行

每个 audience 各开一个 cron entry,分别指向不同的 `--audience` 参数：

```cron
0 9 * * 1 cd ~/.claude/skills/weekly-legal-briefing && python3 scripts/run_one_period.py --audience "科技型制造企业" --period-number AUTO
30 9 * * 1 cd ~/.claude/skills/weekly-legal-briefing && python3 scripts/run_one_period.py --audience "新能源企业" --period-number AUTO
```

> 注意：第一个跑完生成 _meta.jsonl,第二个 cron 时 `--period-number AUTO` 会读到正确期数（v2 完善）。
