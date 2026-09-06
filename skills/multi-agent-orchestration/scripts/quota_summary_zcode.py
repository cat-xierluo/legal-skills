#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zcode lane 额度 summary 适配器（quota-aware-routing.summary.v1 合并写入方）。

multi-agent-orchestration 的额度预检门（quota_preflight.py）与路由
（route_suggest.py）只消费中立合同文件；谁生产 summary 合同不限定。本脚本
把本机 zcode-quota 监测器的真实观测（BigModel coding plan 5h 窗口）转成
summary 里的 zcode fuel lane，作为该合同的生产方之一。

数据源优先级（全部只读，本脚本绝不接触凭证/解密逻辑——那是个人脚本
~/bin/zcode-quota 的职责，公开技能只消费其输出）：

  1. --stdin-obs   从 stdin 读 zcode-quota 的 obs JSON（watch 钩子直连，
                   数据天然是本轮新鲜观测，无新鲜度判断问题）；
  2. --watch-log   读 ~/.zcode/quota-watch-log.jsonl 末尾最新一条可解析且
                   ts 距今 ≤ --freshness-seconds 的记录；
  3. --script      调用 ~/bin/zcode-quota --json 现场拉一次。
   全部失败 → exit 1，不写文件（既有 summary 逐渐过期，消费方按
   stale_summary fail-closed——适配器绝不编造数据放行）。

合并语义（多生产方共存，2026-09-05 决策）：
  - 目标文件已存在且含其他 lane → 只替换 zcode lane，其余 lane 原样保留，
    generated_at 也保留原值：合并方不得替别的生产方"续期"，否则死掉的
    生产方 lane 会被虚报新鲜（2026-08-29 FaroPDF 事故方向相反面的教训：
    过期快照的余量不可采信）。provider-probe 停摆应表现为整体 stale 被
    预检门拒绝，而不是被 zcode lane 的刷新掩盖。
  - 文件不存在 / 只有 zcode lane → generated_at = 本次数据时刻。
  - 写入原子（同目录 tmp + os.replace），并发写不产生半截 JSON。

lane 记录（updated_at/source 为溯源附加键，v1 消费方忽略未知键）：
  {"type": "fuel",
   "remaining_percent": 100 - tokens_pct（钳到 [0,100]）,
   "resets_at": "<TOKENS_LIMIT.nextResetTime → ISO8601 本地时区>"（可缺省）,
   "health": "ok",
   "updated_at": "<本 lane 数据时刻>",
   "source": "stdin|watch-log|live-pull"}

退出码：0 已写入（stdout 打印合并后的 summary JSON）；
        1 无可用数据（watch-log 过期且现场拉取失败/输出畸形）；
        2 用法或输出路径不可写错误。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from typing import Any

SCHEMA_ID = "quota-aware-routing.summary.v1"

DEFAULTS = {
    "lane": "zcode",
    "watch_log": os.path.expanduser("~/.zcode/quota-watch-log.jsonl"),
    "script": os.path.expanduser("~/bin/zcode-quota"),
    "freshness_seconds": 300,   # watch 默认 120s 一轮，容忍 2 次丢轮
    "script_timeout": 25,
}

EXIT_OK = 0
EXIT_NO_DATA = 1
EXIT_USAGE = 2


def _parse_iso(value: Any) -> dt.datetime | None:
    """与 quota_preflight.py / route_suggest.py 相同的解析面：naive 按本地时区。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    return stamp


def _now_tz(now: dt.datetime | None) -> dt.datetime:
    current = now or dt.datetime.now().astimezone()
    return current if current.tzinfo else current.astimezone()


def _epoch_ms_to_iso(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    stamp = dt.datetime.fromtimestamp(value / 1000).astimezone()
    return stamp.isoformat(timespec="seconds")


def _usable_obs(obs: Any) -> dict[str, Any] | None:
    """obs 必须带数值 tokens_pct 才能构成 fuel 信号；其余字段可缺省。"""
    if not isinstance(obs, dict):
        return None
    pct = obs.get("tokens_pct")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return None
    return obs


def read_stdin_obs(stream: Any) -> dict[str, Any] | None:
    try:
        payload = json.load(stream)
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("ok") is True:
        payload = {k: v for k, v in payload.items() if k != "ok"}
    return _usable_obs(payload)


def read_watch_log(path: str, freshness_seconds: float,
                   now: dt.datetime) -> dict[str, Any] | None:
    """从日志末尾向前找第一条可解析、新鲜且有 tokens_pct 的观测。"""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        stamp = _parse_iso(rec.get("ts"))
        if stamp is None:
            continue
        if (_now_tz(now) - stamp).total_seconds() > freshness_seconds:
            return None  # 最新可解析记录已过期，更早的只会更旧
        obs = _usable_obs(rec)
        if obs is not None:
            return obs
    return None


def live_pull(script: str, timeout: float) -> dict[str, Any] | None:
    if not os.path.exists(script):
        return None
    try:
        proc = subprocess.run([script, "--json"], capture_output=True,
                              timeout=timeout, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
    if isinstance(payload, dict) and payload.get("ok") is True:
        payload = {k: v for k, v in payload.items() if k != "ok"}
    return _usable_obs(payload)


def build_lane(obs: dict[str, Any], source: str, data_ts: dt.datetime) -> dict[str, Any]:
    remaining = max(0.0, min(100.0, 100.0 - float(obs["tokens_pct"])))
    lane: dict[str, Any] = {
        "type": "fuel",
        "remaining_percent": round(remaining, 1),
        "health": "ok",
        "updated_at": data_ts.isoformat(timespec="seconds"),
        "source": source,
    }
    resets_at = _epoch_ms_to_iso(obs.get("five_hour_reset_at"))
    if resets_at:
        lane["resets_at"] = resets_at
    return lane


def merge_and_write(out_path: str, lane_name: str, lane: dict[str, Any]) -> dict[str, Any]:
    """合并写入：只替换目标 lane；其他 lane 与 generated_at 原样保留。"""
    existing: dict[str, Any] = {}
    try:
        with open(out_path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            existing = loaded
    except (OSError, json.JSONDecodeError):
        existing = {}

    old_lanes = existing.get("lanes") if isinstance(existing.get("lanes"), dict) else {}
    other_lanes = {k: v for k, v in old_lanes.items() if k != lane_name}
    generated_at = existing.get("generated_at")
    if other_lanes:
        # 有别的生产方：generated_at 是它们快照的时刻，合并方无权改写。
        if not _parse_iso(generated_at):
            generated_at = lane["updated_at"]
    else:
        generated_at = lane["updated_at"]

    summary = {
        "schema": SCHEMA_ID,
        "generated_at": generated_at,
        "lanes": {**other_lanes, lane_name: lane},
    }
    out_dir = os.path.dirname(os.path.abspath(out_path))
    tmp_path = os.path.join(out_dir, f".{os.path.basename(out_path)}.tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp_path, out_path)
    except OSError as exc:
        print(f"[quota_summary_zcode] 输出路径不可写: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="zcode lane 额度 summary 适配器（quota-aware-routing.summary.v1 合并写入方）")
    parser.add_argument("--out", required=True, help="summary JSON 目标路径（合并写入）")
    parser.add_argument("--lane", default=DEFAULTS["lane"], help="lane 名（默认 zcode）")
    parser.add_argument("--watch-log", default=DEFAULTS["watch_log"],
                        help="zcode-quota 观测日志路径")
    parser.add_argument("--script", default=DEFAULTS["script"],
                        help="zcode-quota 脚本路径（现场拉取回退）")
    parser.add_argument("--freshness-seconds", type=float,
                        default=DEFAULTS["freshness_seconds"],
                        help="watch-log 记录新鲜度上限（秒）")
    parser.add_argument("--script-timeout", type=float,
                        default=DEFAULTS["script_timeout"])
    parser.add_argument("--stdin-obs", action="store_true",
                        help="从 stdin 读 obs JSON（供 zcode-quota watch 钩子直连）")
    parser.add_argument("--now", default=None, help="ISO8601 当前时刻（可测性注入）")
    args = parser.parse_args(argv)

    now = _parse_iso(args.now) if args.now else None
    current = _now_tz(now)

    obs: dict[str, Any] | None = None
    source = ""
    if args.stdin_obs:
        obs = read_stdin_obs(sys.stdin)
        source = "stdin"
    if obs is None:
        obs = read_watch_log(args.watch_log, args.freshness_seconds, current)
        source = "watch-log"
    if obs is None:
        obs = live_pull(args.script, args.script_timeout)
        source = "live-pull"
    if obs is None:
        print("[quota_summary_zcode] 无可用数据：watch-log 过期且现场拉取失败，"
              "不写文件（消费方将按 stale/missing fail-closed）", file=sys.stderr)
        return EXIT_NO_DATA

    lane = build_lane(obs, source, current)
    summary = merge_and_write(args.out, args.lane, lane)
    json.dump(summary, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
