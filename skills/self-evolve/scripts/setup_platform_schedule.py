#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""首装平台检测 + 定时任务配置建议生成器。

检测本机装了哪些 agent 平台(WorkBuddy / QwenWork / MyAgents),为每个检测到的
平台生成「每周跑一次 weekly-iteration-report」的定时任务配置建议(可复制粘贴)。

B 方向:只生成可复制粘贴的建议,**不主动调平台 API / 不创建调度**(尊重
self-evolve「skill 不创建调度」铁律,references/12:121)。用户拿到建议后,在各自
平台 GUI / CLI 手动导入。references/12:133 本就声明「检测平台 + 给配置建议是后续
setup 辅助的工作」,本脚本即这个辅助。

三平台都是 prompt-based(跑 LLM agent,不是裸 shell),触发命令统一包成一句 prompt:
  cd <skill-root> && python3 scripts/scheduler_run.py --task weekly-iteration-report \
      --run-now --trigger external
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from self_evolve_paths import SKILL_ROOT  # noqa: E402

TRIGGER_CMD = (
    f'cd "{SKILL_ROOT}" && python3 scripts/scheduler_run.py '
    f"--task weekly-iteration-report --run-now --trigger external"
)
PROMPT_TEMPLATE = (
    f"运行 bash: {TRIGGER_CMD}。读取脚本 stdout/stderr 并简要汇报:"
    "本周报告写到桌面哪个路径、扫了多少会话、发现哪些可沉淀资产、有无异常。"
)


def detect_platforms() -> list[str]:
    """逐个检测本机平台(可并存),返回检测到的 key 列表。"""
    found: list[str] = []
    if (Path.home() / ".workbuddy" / "workbuddy.db").exists():
        found.append("workbuddy")
    if (Path.home() / ".qwenworkcn" / ".status.json").exists():
        found.append("qwenwork")
    if (Path.home() / ".myagents").exists() and shutil.which("myagents"):
        found.append("myagents")
    if (Path.home() / ".openclaw" / "cron" / "jobs.json").exists() and shutil.which("openclaw"):
        found.append("openclaw")
    return found


def workbuddy_suggestion() -> str:
    """WorkBuddy:GUI「定时任务/Automation」新建,粘贴字段。调度用 RFC5545 RRULE。"""
    return "\n".join([
        "### WorkBuddy(在桌面端「定时任务 / Automation」新建,粘贴以下字段)",
        "",
        f"- 名称: Self Evolve 周度迭代报告",
        f"- 工作目录(cwds): [\"{SKILL_ROOT}\"]",
        f"- 计划(RRULE,每周一 09:00): `FREQ=WEEKLY;BYDAY=MO;BYHOUR=9`",
        f"- 权限模式: fullAccess",
        f"- 状态: 待配置后手动启用",
        f"- Prompt:",
        f"  ```",
        f"  {PROMPT_TEMPLATE}",
        f"  ```",
        "",
        "> WorkBuddy automation 只能 GUI 创建(无 CLI / 无文件导入),self-evolve 不代你创建。",
    ])


def qwenwork_suggestion() -> str:
    """QwenWork:GUI「定时任务/Cron」新建,或 app 内 qoder_cron。5-field cron。"""
    return "\n".join([
        "### QwenWork(在「定时任务 / Cron」新建,粘贴以下字段)",
        "",
        f"- name: Self Evolve 周度迭代报告",
        f"- description: 每周生成本机 self-evolve 脱敏 digest 写桌面",
        f"- schedule: {{ kind: \"cron\", expr: \"30 9 * * 1\", tz: \"<your-timezone>\" }}",
        f"- contextDirs: [\"{SKILL_ROOT}\"]",
        f"- enabled: false",
        f"- prompt:",
        f"  ```",
        f"  {PROMPT_TEMPLATE}",
        f"  ```",
        "",
        "> QwenWork 创建任务只在 app 内(qoder_cron 工具),Connector 不能创建。self-evolve 不代你创建。",
    ])


def myagents_suggestion() -> str:
    """MyAgents:有 CLI 可半自动。生成 task-action.md + create-direct 命令。"""
    return "\n".join([
        "### MyAgents(可用 CLI 半自动创建)",
        "",
        "1) 把下面内容存成 task-action 文件(例如 `self-evolve-weekly-action.md`):",
        "```markdown",
        "---",
        "name: self-evolve-weekly-iteration",
        "---",
        f"{PROMPT_TEMPLATE}",
        "```",
        "",
        "2) 填写本机时区并确认后再创建；以下示例不能直接执行:",
        "```text",
        "myagents task create-direct \\",
        '  --name "Self Evolve 周度迭代报告" \\',
        "  --taskMdFile self-evolve-weekly-action.md \\",
        "  --executionMode recurring \\",
        '  --cronExpression "30 9 * * 1" \\',
        "  --cronTimezone <your-timezone> \\",
        "  --runMode new-session --json",
        "```",
        "",
        "> MyAgents 是三平台里唯一能用 CLI 创建的;命令需你确认后执行(self-evolve 不自动跑)。",
    ])


def _load_enabled_tasks() -> list[dict]:
    """读 config/scheduled_tasks.yaml 的 enabled + external 任务(recommended_schedule.cron)。"""
    cfg = SKILL_ROOT / "config" / "scheduled_tasks.yaml"
    if not cfg.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    except Exception:
        return []
    tasks = data.get("tasks", []) if isinstance(data, dict) else []
    out: list[dict] = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        runner = t.get("runner") or {}
        if not runner.get("enabled"):
            continue
        sched = t.get("recommended_schedule") or t.get("schedule") or {}
        cron = sched.get("cron", "")
        timezone = sched.get("timezone", "")
        if not cron or not isinstance(timezone, str) or not timezone.strip() or "<" in timezone or ">" in timezone:
            continue
        out.append(
            {
                "id": str(t.get("id", "")),
                "name": str(t.get("name", t.get("id", ""))),
                "cron": str(cron),
            }
        )
    return out


def openclaw_suggestion() -> str:
    """OpenClaw:有 cron CLI,直接 --command 跑 scheduler_run(不需包 agent prompt)。"""
    tasks = _load_enabled_tasks()
    if not tasks:
        return "\n".join(
            [
                "### OpenClaw",
                "",
                "(未读到 config/scheduled_tasks.yaml 的 enabled 任务;先确认配置存在。)",
            ]
        )
    lines = [
        "### OpenClaw(用 `openclaw cron add` 直接挂,--command 跑 scheduler_run,无需 agent prompt)",
        "",
        "逐条粘贴到终端(或 OpenClaw GUI 导入):",
        "```bash",
    ]
    for t in tasks:
        cmd = f'python3 scripts/scheduler_run.py --task {t["id"]} --run-now --trigger external'
        lines.append(
            f"openclaw cron add \\\n"
            f'  --cron "{t["cron"]}" \\\n'
            f"  --command '{cmd}' \\\n"
            f'  --command-cwd "{SKILL_ROOT}" \\\n'
            f'  --name "self-evolve {t["id"]}" \\\n'
            f'  --description "{t["name"]}"'
        )
    lines.extend(
        [
            "```",
            "",
            "> 查看:`openclaw cron list`;手动试跑:`openclaw cron run <job>`;删除:`openclaw cron rm <job>`;状态:`openclaw cron status`。",
        ]
    )
    return "\n".join(lines)


_SUGGESTIONS = {
    "workbuddy": workbuddy_suggestion,
    "qwenwork": qwenwork_suggestion,
    "myagents": myagents_suggestion,
    "openclaw": openclaw_suggestion,
}

_PLATFORM_LABEL = {
    "workbuddy": "WorkBuddy",
    "qwenwork": "QwenWork",
    "myagents": "MyAgents",
    "openclaw": "OpenClaw",
}


def render(detected: list[str]) -> str:
    lines = [
        "# Self Evolve 定时任务配置建议(每周迭代报告)",
        "",
        f"检测到的平台: {', '.join(_PLATFORM_LABEL[p] for p in detected) or '(未检测到 WorkBuddy/QwenWork/MyAgents)'}",
        "",
        f"触发命令(三平台统一,包成 prompt): `{TRIGGER_CMD}`",
        "",
        "下面是每个检测到的平台对应的配置建议,**复制粘贴到各自平台导入**。",
        "self-evolve 不主动创建调度(B 方向:只给建议,尊重「skill 不创建调度」边界)。",
        "",
    ]
    for key in detected:
        lines.append(_SUGGESTIONS[key]())
        lines.append("")
    if not detected:
        lines.append("没检测到上述平台。若你用别的调度器(launchd / cron),直接把这条命令配成每周 cron:")
        lines.append(f"  `{TRIGGER_CMD}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="检测本机 agent 平台 + 生成每周迭代报告的定时任务配置建议")
    ap.add_argument("--json", action="store_true", help="输出结构化结果")
    args = ap.parse_args()

    detected = detect_platforms()
    if args.json:
        print(json.dumps(
            {"detected": detected, "trigger_cmd": TRIGGER_CMD, "skill_root": str(SKILL_ROOT)},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(render(detected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
