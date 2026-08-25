# OpenClaw / Claude Code cron 部署说明

## crontab 条目

```cron
# 每周一 09:00 跑法律周报
0 9 * * 1 cd ~/.claude/skills/weekly-legal-briefing && \
  python3 scripts/run_one_period.py \
    --audience "科技型制造企业" \
    --period-number $(($(ls archive/法律周报_*.meta.json 2>/dev/null | wc -l) + 1)) \
    >> ~/.claude/skills/weekly-legal-briefing/archive/_cron.log 2>&1
```

> 上面的 `--period-number` 用 ls 文件数自动递增；如要更严谨,从 `archive/_meta.jsonl` 的最后一条记录的 `period` 字段读 + 1。

## 频道推送（可选,仅推送 DRAFT 提醒）

可在 OpenClaw 配置"频道推送"任务,跑完后向频道发：

```text
📰 {audience} 法律周报 第 {N} 期 _DRAFT 已生成
路径：archive/法律周报_{audience}_{YYYY}第{N}期_DRAFT.pdf
请 {editor} 复核后手动去掉 _DRAFT 后缀发布。
```

> 注意：此推送仅作为提醒,**不携带可发布版本**；发布动作永远人工。

## 辅助脚本 `scripts/run_one_period.py`

```python
#!/usr/bin/env python3
"""调度入口：跑一期法律周报。

Usage:
    python3 scripts/run_one_period.py --audience "科技型制造企业" --period-number N
"""
import argparse, subprocess, sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audience", required=True)
    ap.add_argument("--period-number", type=int, required=True)
    args = ap.parse_args()

    year = __import__("datetime").datetime.now().year
    audience_slug = args.audience.replace(" ", "_")
    md_path = SKILL_DIR / "archive" / f"法律周报_{audience_slug}_{year}第{args.period_number}期_DRAFT.md"
    html_path = md_path.with_suffix(".html")
    pdf_path = md_path.with_suffix(".pdf")
    meta_path = md_path.with_suffix(".meta.json")
    checklist_path = SKILL_DIR / "archive" / f"法律周报_{audience_slug}_{year}第{args.period_number}期_DRAFT.checklist.md"

    print(f"本期目标：{md_path.name}")

    # Step 1: 生成 md（由 AI 在 cron 上下文中完成）
    if not md_path.exists():
        print(f"[error] {md_path} 不存在;请先按 templates/briefing-skeleton.md 生成 md", file=sys.stderr)
        sys.exit(1)

    # Step 2: 渲染 HTML
    r = subprocess.run([
        "python3", str(SKILL_DIR / "scripts" / "render.py"),
        "--input", str(md_path),
        "--output", str(html_path),
        "--profile", str(SKILL_DIR / "config" / "report-profile.md"),
    ])
    if r.returncode != 0:
        sys.exit(r.returncode)

    # Step 3: 渲染 PDF
    r = subprocess.run([
        "python3", str(SKILL_DIR / "scripts" / "pdf.py"),
        "--input", str(html_path),
        "--output", str(pdf_path),
        "--profile", str(SKILL_DIR / "config" / "report-profile.md"),
    ])
    if r.returncode != 0:
        sys.exit(r.returncode)

    print(f"本期完成：{pdf_path.name}")

if __name__ == "__main__":
    main()
```

> 调度平台负责"提示词(选题+生成 md)"步骤；本脚本只负责"渲染"两步。

## 与 WorkBuddy 的关键差异

| 维度 | WorkBuddy | OpenClaw cron |
|---|---|---|
| 任务调度 | 平台 GUI | 系统 cron |
| 提示词载体 | 自动化任务的提示词字段 | 单独的提示词文件 / 频道命令 |
| 失败告警 | WorkBuddy 自带 | 邮件 / 频道（需自配） |
| 调试 | WorkBuddy GUI 日志 | `tail -f archive/_cron.log` |
| 推荐 | 图形化、易上手 | 系统级、稳定、跨平台 |
