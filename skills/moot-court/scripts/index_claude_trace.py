#!/usr/bin/env python3
"""被动索引本地 Claude CLI `--output-format stream-json --verbose` 原始流文件。

只读取一个已存在的 trace JSONL，不启动 Agent/CLI、不联网、不读取凭证配置，
仅用标准库。目标是把「主控真的派发过子代理」这一事实与原始事件绑定：
- 只索引 assistant 事件 message.content 中工具名属于子代理工具（默认 Agent、Task，
  以所用版本实际工具名为准）的 tool_use，并按 tool_use_id 关联 user 事件的 tool_result；
- 同一 tool_use_id 的重复相同事件去重；同 ID 但内容冲突则整体拒绝；
- 没有 tool_result 的调用记为 unfinished，不计入 completed；
- 坏 JSON 行、无子代理调用、缺完成等如实标注，不用来源自述冒充验证。

索引只能证明该 trace 中可观察到的调用，不能单独证明 G5、独立多 Agent 或领域正确性。
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

SCHEMA = "claude-trace-index.v1"
DEFAULT_SUBAGENT_TOOLS = ("Agent", "Task")
EXIT_OK = 0
EXIT_REJECTED = 2
EXIT_NOT_VERIFIED = 3
MAX_BAD_LINE_REPORT = 20
NOTES = [
    "索引只绑定 trace 中可观察的 tool_use/tool_result 事件，来源记录或 JSON 自述不是防伪证明。",
    "completed 仅表示该 trace 内存在配对的 tool_result 且未标错，不单独签出 G5/DOMAIN_VERIFIED。",
]


class TraceIndexError(Exception):
    """输入不适用或发生冲突，拒绝写出索引。"""


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content_text(content):
    """tool_result.content 可能是字符串或内容块数组，合并为纯文本。"""
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(parts)


def _tool_use_signature(block, message_id):
    prompt = block.get("input", {}).get("prompt")
    if not isinstance(prompt, str):
        prompt = json.dumps(block.get("input", {}), ensure_ascii=False, sort_keys=True)
    return (
        block.get("name"),
        message_id,
        block.get("input", {}).get("description"),
        block.get("input", {}).get("subagent_type"),
        _sha256_text(prompt),
        len(prompt),
    )


def _tool_result_signature(block):
    content = block.get("content")
    return (bool(block.get("is_error")), _sha256_text(_content_text(content) or ""))


def index_trace(trace_path, subagent_tools):
    """解析 trace，返回索引 dict；冲突抛 TraceIndexError。"""
    with open(trace_path, "rb") as handle:
        raw = handle.read()
    lines = raw.decode("utf-8", errors="replace").splitlines()

    summary = {
        "total_lines": len(lines),
        "blank_lines": 0,
        "bad_json_lines": 0,
        "bad_json_line_numbers": [],
        "event_type_counts": {},
        "other_tool_use": 0,
        "other_tool_results": 0,
        "duplicate_tool_use_events": 0,
        "duplicate_tool_result_events": 0,
    }
    calls = {}
    results = {}
    session_ids = []
    final_result_event = None

    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            summary["blank_lines"] += 1
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            summary["bad_json_lines"] += 1
            if len(summary["bad_json_line_numbers"]) < MAX_BAD_LINE_REPORT:
                summary["bad_json_line_numbers"].append(lineno)
            continue
        if not isinstance(event, dict):
            summary["bad_json_lines"] += 1
            if len(summary["bad_json_line_numbers"]) < MAX_BAD_LINE_REPORT:
                summary["bad_json_line_numbers"].append(lineno)
            continue

        etype = event.get("type")
        summary["event_type_counts"][etype] = summary["event_type_counts"].get(etype, 0) + 1
        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id not in session_ids:
            session_ids.append(session_id)

        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            if etype == "result":
                final_result_event = event
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            if etype == "assistant" and block.get("type") == "tool_use":
                name = block.get("name")
                call_id = block.get("id")
                if name not in subagent_tools or not isinstance(call_id, str):
                    summary["other_tool_use"] += 1
                    continue
                signature = _tool_use_signature(block, message.get("id"))
                if call_id in calls:
                    if calls[call_id]["_signature"] == signature:
                        summary["duplicate_tool_use_events"] += 1
                    else:
                        raise TraceIndexError(
                            "tool_use_id 冲突：%s 在第 %d 行与第 %d 行内容不一致，拒绝索引"
                            % (call_id, calls[call_id]["line"], lineno)
                        )
                    continue
                prompt = block.get("input", {}).get("prompt")
                if not isinstance(prompt, str):
                    prompt = json.dumps(block.get("input", {}), ensure_ascii=False, sort_keys=True)
                calls[call_id] = {
                    "tool_use_id": call_id,
                    "tool_name": name,
                    "line": lineno,
                    "message_id": message.get("id"),
                    "description": block.get("input", {}).get("description"),
                    "subagent_type": block.get("input", {}).get("subagent_type"),
                    "prompt_sha256": _sha256_text(prompt),
                    "prompt_chars": len(prompt),
                    "_signature": signature,
                    "status": "unfinished",
                    "result_line": None,
                    "result_is_error": None,
                    "result_sha256": None,
                    "result_preview": None,
                }
            elif etype == "user" and block.get("type") == "tool_result":
                call_id = block.get("tool_use_id")
                if call_id not in calls:
                    summary["other_tool_results"] += 1
                    continue
                signature = _tool_result_signature(block)
                if call_id in results:
                    if results[call_id]["_signature"] == signature:
                        summary["duplicate_tool_result_events"] += 1
                    else:
                        raise TraceIndexError(
                            "tool_use_id 结果冲突：%s 在第 %d 行与第 %d 行内容不一致，拒绝索引"
                            % (call_id, results[call_id]["line"], lineno)
                        )
                    continue
                text = _content_text(block.get("content"))
                results[call_id] = {
                    "line": lineno,
                    "is_error": bool(block.get("is_error")),
                    "sha256": _sha256_text(text or ""),
                    "preview": text[:300],
                    "_signature": signature,
                }
        if etype == "result":
            final_result_event = event

    completed = 0
    finished_with_error = 0
    unfinished = 0
    for call in calls.values():
        result = results.get(call["tool_use_id"])
        if result is None:
            unfinished += 1
            continue
        call["status"] = "completed_with_error" if result["is_error"] else "completed"
        call["result_line"] = result["line"]
        call["result_is_error"] = result["is_error"]
        call["result_sha256"] = result["sha256"]
        call["result_preview"] = result["preview"]
        if result["is_error"]:
            finished_with_error += 1
        else:
            completed += 1

    reasons = []
    if summary["bad_json_lines"]:
        reasons.append("bad_json_lines=%d" % summary["bad_json_lines"])
    if not calls:
        reasons.append("no_subagent_calls_found")
    elif completed == 0:
        reasons.append("no_completed_subagent_calls")
    summary.update({
        "subagent_calls_total": len(calls),
        "completed": completed,
        "completed_with_error": finished_with_error,
        "unfinished": unfinished,
    })
    verdict = "NOT_VERIFIED" if reasons else "VERIFIED_CALLS"

    index = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trace_path": os.path.abspath(trace_path),
        "trace_bytes": len(raw),
        "trace_sha256": hashlib.sha256(raw).hexdigest(),
        "subagent_tools_accepted": list(subagent_tools),
        "verdict": verdict,
        "not_verified_reasons": reasons,
        "session_ids": session_ids,
        "final_result": None,
        "calls": [calls[k] for k in sorted(calls)],
        "summary": summary,
        "notes": NOTES,
    }
    if isinstance(final_result_event, dict):
        index["final_result"] = {
            "subtype": final_result_event.get("subtype"),
            "num_turns": final_result_event.get("num_turns"),
            "session_id": final_result_event.get("session_id"),
        }
    for call in index["calls"]:
        call.pop("_signature", None)
    return index


def write_index(index, output_path, max_preview):
    """拒绝覆盖既有输出；只清理本次创建的半成品文件。"""
    if os.path.exists(output_path):
        raise TraceIndexError("输出文件已存在，拒绝覆盖：%s" % output_path)
    parent = os.path.dirname(os.path.abspath(output_path))
    if not os.path.isdir(parent):
        raise TraceIndexError("输出目录不存在：%s" % parent)
    for call in index["calls"]:
        if call.get("result_preview"):
            call["result_preview"] = call["result_preview"][:max_preview]
    payload = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_path = tempfile.mkstemp(prefix=".index-claude-trace-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, output_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="被动索引 Claude stream-json trace 中的子代理调用（Agent/Task）。")
    parser.add_argument("--trace", required=True, help="claude --output-format stream-json 的原始 JSONL")
    parser.add_argument("--output", required=True, help="要写出的索引 JSON（已存在则拒绝覆盖）")
    parser.add_argument("--subagent-tools", default=",".join(DEFAULT_SUBAGENT_TOOLS),
                        help="按所用版本实际工具名列出子代理工具，逗号分隔（默认 Agent,Task）")
    parser.add_argument("--max-preview", type=int, default=300,
                        help="tool_result 预览最大字符数（默认 300）")
    args = parser.parse_args(argv)

    tools = tuple(t.strip() for t in args.subagent_tools.split(",") if t.strip())
    if not tools:
        parser.error("--subagent-tools 不能为空")
    if os.path.exists(args.output):
        print("拒绝：输出文件已存在：%s" % args.output, file=sys.stderr)
        return EXIT_REJECTED
    if not os.path.isfile(args.trace):
        print("拒绝：trace 文件不存在或不是普通文件：%s" % args.trace, file=sys.stderr)
        return EXIT_REJECTED
    try:
        index = index_trace(args.trace, tools)
        write_index(index, args.output, args.max_preview)
    except TraceIndexError as exc:
        print("拒绝：%s" % exc, file=sys.stderr)
        return EXIT_REJECTED
    except OSError as exc:
        print("拒绝：读写失败：%s" % exc, file=sys.stderr)
        return EXIT_REJECTED

    summary = index["summary"]
    print("索引写出：%s" % args.output)
    print("verdict=%s 子代理调用=%d completed=%d unfinished=%d 坏JSON=%d" % (
        index["verdict"], summary["subagent_calls_total"], summary["completed"],
        summary["unfinished"], summary["bad_json_lines"]))
    if index["verdict"] == "NOT_VERIFIED":
        print("NOT_VERIFIED：%s" % "；".join(index["not_verified_reasons"]), file=sys.stderr)
        return EXIT_NOT_VERIFIED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
