#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy session 提取验证脚本(最小验证用,非正式 dream_sweep 来源)。

目的:把 WorkBuddy 的 trace 文件(~/.workbuddy/traces/<sid>/trace_*.json)
还原成「用户问 / 工具调用 / 助手答」的可读会话流,验证提取质量是否
足够接入 self-evolve 作为第三来源。

数据结构(已探明):
  trace = {"trace": {...}, "spans": [...]}
  span 关键字段: name / type / spanId / parentId / startedAt / endedAt / status
  - generation span(LLM 调用):
      toolInput : JSON 字符串 → OpenAI messages 数组
                  [0] role=system(模型自述 + 注入的 system-reminder)
                  [1] role=user(content parts 里含 <user_query>真·用户输入</user_query>)
      toolOutput: JSON 字符串 → chat.completion
                  choices[0].message = {role:assistant, content, tool_calls}
  - 工具 span(Bash/Read/Write/Skill/TaskCreate/TaskUpdate/Glob/...):
      toolName / toolInput / toolOutput
  - mcp_tools span: 空分组标记,跳过
  - cli span: agentName,跳过

提取口径:
  - “用户问” = generation.toolInput 里出现 <user_query> 的那一条 message
    (agent 自循环的 generation 没有 <user_query>,不计为新用户输入)
  - “助手答” = generation.toolOutput 的 message.content(纯文本部分)
  - “工具调用” = 工具 span 的 toolName + 参数/结果摘要
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

USER_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.DOTALL)


def _parse_maybe_json(s):
    """toolInput/toolOutput 可能是 JSON 字符串,也可能已是对象;容错解析。"""
    if s is None:
        return None
    if not isinstance(s, str):
        return s
    try:
        return json.loads(s)
    except Exception:
        return s  # 留作纯文本


def _flatten_content(content):
    """OpenAI content 可能是 str / list[{type,text}] / dict;统一抽成纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and "text" in p:
                parts.append(str(p["text"]))
            elif isinstance(p, str):
                parts.append(p)
        return "\n".join(parts)
    if isinstance(content, dict):
        return str(content)
    return str(content)


def _short(s: str, n: int = 240) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n] + f"  …[+{len(s)-n}字]"


def extract_user_queries(messages) -> list[str]:
    """从 OpenAI messages 数组里提取所有 <user_query> 文本。"""
    out = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        text = _flatten_content(msg.get("content"))
        for m in USER_QUERY_RE.finditer(text):
            q = m.group(1).strip()
            if q:
                out.append(q)
    return out


# system prompt 里会“解释 <user_query> 标签”并带固定模板词,正则兜底时需过滤
_SYSTEM_TEMPLATE_HINTS = (
    "Here's what you're good at", "Research & writing", "Dig into",
    "powered by", "denoted by", "follow the USER",
)


def extract_user_queries_robust(raw) -> list[str]:
    """结构优先(parse 成功→只取 role=user,精准);
    截断兜底(parse 失败→原始字符串正则,过滤 system 模板误匹配)。"""
    parsed = _parse_maybe_json(raw)
    if isinstance(parsed, list):
        return extract_user_queries(parsed)  # 精准路径
    if isinstance(raw, str):
        # system 模板里有孤立开标签(“denoted by the <user_query> tag”),非贪婪
        # 正则会把它和远处真实 query 的闭合标签错配 → 先中和该固定写法
        cleaned = raw.replace("the <user_query> tag", "the user-query tag")
        out = []
        for m in USER_QUERY_RE.finditer(cleaned):
            q = m.group(1).strip()
            if q and not any(h in q for h in _SYSTEM_TEMPLATE_HINTS):
                out.append(q)
        return out
    return []


def parse_trace(path: Path) -> dict:
    """解析单个 trace 文件 → 结构化会话。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    spans = raw.get("spans", [])
    # 按 startedAt 排序还原时序
    spans = sorted(spans, key=lambda s: s.get("startedAt") or "")

    turns = []          # 时序事件流
    user_inputs_total = 0
    # WorkBuddy 每个 generation 都重发“累积的全部历史 user 消息”,同一条会在
    # 多个 generation 里重复(且循环),需按内容全局去重,保留首次出现时序
    seen_user_queries = set()
    model = None
    session_id = raw.get("trace", {}).get("sessionId") or raw.get("trace", {}).get("id")

    for s in spans:
        name = s.get("name")
        started = s.get("startedAt")
        if name == "generation":
            ti = _parse_maybe_json(s.get("toolInput"))
            to = _parse_maybe_json(s.get("toolOutput"))
            # 用户输入(WorkBuddy 每个 generation 都重发完整 messages,
            # 同一条 <user_query> 会在多次 generation 里重复 → 连续去重)
            queries = extract_user_queries_robust(s.get("toolInput"))
            for q in queries:
                key = q.strip()
                if key not in seen_user_queries:
                    seen_user_queries.add(key)
                    turns.append({"kind": "user", "ts": started, "text": q})
                    user_inputs_total += 1
            # 助手输出
            if isinstance(to, list) and to:
                msg = (to[0].get("choices") or [{}])[0].get("message", {}) if isinstance(to[0], dict) else {}
                if not model:
                    model = to[0].get("model") if isinstance(to[0], dict) else None
                content = _flatten_content(msg.get("content"))
                tool_calls = msg.get("tool_calls") or []
                if content.strip():
                    turns.append({"kind": "assistant", "ts": started, "text": content})
                if tool_calls:
                    names = []
                    for tc in tool_calls:
                        fn = (tc.get("function") or {}).get("name", "?") if isinstance(tc, dict) else "?"
                        names.append(fn)
                    turns.append({"kind": "assistant_tool_call", "ts": started, "tools": names})
        elif name in ("Bash", "Read", "Write", "Glob", "Skill", "TaskCreate", "TaskUpdate",
                      "Edit", "Grep", "WebFetch", "WebSearch"):
            ti = _parse_maybe_json(s.get("toolInput"))
            to = _parse_maybe_json(s.get("toolOutput"))
            ti_txt = _short(_flatten_content(ti) if not isinstance(ti, (list, dict)) else json.dumps(ti, ensure_ascii=False))
            to_txt = _short(_flatten_content(to) if not isinstance(to, (list, dict)) else json.dumps(to, ensure_ascii=False))
            turns.append({"kind": "tool", "ts": started, "name": name,
                          "input": ti_txt, "output": to_txt})
        # mcp_tools / cli 等跳过

    started_at = spans[0].get("startedAt") if spans else None
    ended_at = spans[-1].get("endedAt") if spans else None
    return {
        "source": "workbuddy",
        "trace_path": str(path),
        "session_id": session_id,
        "trace_id": raw.get("trace", {}).get("traceId") or raw.get("trace", {}).get("id"),
        "model": model,
        "started_at": started_at,
        "ended_at": ended_at,
        "span_count": len(spans),
        "user_input_count": user_inputs_total,
        "turn_count": len(turns),
        "turns": turns,
    }


def render_readable(summary: dict) -> str:
    """人类可读回放。"""
    lines = []
    lines.append(f"# WorkBuddy 会话回放")
    lines.append(f"trace: {summary['trace_path']}")
    lines.append(f"session_id: {summary['session_id']}  model: {summary['model']}")
    lines.append(f"时间: {summary['started_at']} → {summary['ended_at']}")
    lines.append(f"span: {summary['span_count']}  用户输入: {summary['user_input_count']}  事件: {summary['turn_count']}")
    lines.append("")
    for t in summary["turns"]:
        ts = (t.get("ts") or "")[11:19]  # HH:MM:SS
        k = t["kind"]
        if k == "user":
            lines.append(f"\n[{ts}] 👤 用户:")
            lines.append(_short(t["text"], 600))
        elif k == "assistant":
            lines.append(f"[{ts}] 🤖 助手:")
            lines.append(_short(t["text"], 600))
        elif k == "assistant_tool_call":
            lines.append(f"[{ts}] 🤖 助手(调用工具): {', '.join(t['tools'])}")
        elif k == "tool":
            lines.append(f"[{ts}] 🔧 {t['name']}:")
            lines.append(f"     in : {t['input']}")
            lines.append(f"     out: {t['output']}")
    return "\n".join(lines)


def auto_pick(n: int) -> list[Path]:
    """自动挑体积最大的 n 个 trace(体积≈对话长度)。"""
    root = Path.home() / ".workbuddy" / "traces"
    files = sorted(root.rglob("trace_*.json"), key=lambda p: p.stat().st_size, reverse=True)
    return files[:n]


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy trace → 会话流 提取验证")
    ap.add_argument("paths", nargs="*", help="trace 文件路径;不给则自动挑最大的几个")
    ap.add_argument("--auto", type=int, default=3, help="自动挑体积最大的 N 个(默认 3)")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON 而非可读文本")
    args = ap.parse_args()

    paths = [Path(p) for p in args.paths] if args.paths else auto_pick(args.auto)
    if not paths:
        print("没找到 trace 文件(~/.workbuddy/traces/)", file=sys.stderr)
        sys.exit(1)

    print(f"已选 {len(paths)} 个 trace:\n" + "\n".join(f"  {p.stat().st_size//1024}KB  {p}" for p in paths) + "\n",
          file=sys.stderr)

    for p in paths:
        try:
            summary = parse_trace(p)
        except Exception as e:
            print(f"\n!!! 解析失败 {p}: {e}", file=sys.stderr)
            continue
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(render_readable(summary))
        print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
