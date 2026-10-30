#!/usr/bin/env python3
"""Read local session files, return metadata only, never output chat text."""

import argparse
import json
import os
import sys
import time
from pathlib import Path


PLATFORMS = {
    "claude-code": (".claude/projects", "*.jsonl", "cc"),
    "qwenwork": (".qwenworkcn/projects", "*.jsonl", "cc"),
    "qoderwork": (".qoderworkcn/projects", "*.jsonl", "cc"),
    "myagents": (".myagents/sessions", "*.jsonl", "cc"),
    "codex": (".codex/sessions", "rollout-*.jsonl", "codex"),
    "workbuddy": (".workbuddy/traces", "trace_*.json", "trace"),
}


def records(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(item, dict):
                yield item


def inspect_session(path, kind, requested_cwd):
    model, cwd, session_id = "", "", ""
    if kind == "trace":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        cwd = data.get("cwd", "")
        spans = data.get("spans", [])
        if not isinstance(spans, list):
            return None
        for span in spans:
            if not isinstance(span, dict) or span.get("type") != "generation":
                continue
            output = span.get("toolOutput", [])
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except ValueError:
                    continue
            if isinstance(output, dict):
                output = [output]
            if isinstance(output, list):
                for completion in output:
                    if isinstance(completion, dict) and completion.get("object") == "chat.completion":
                        candidate = completion.get("model")
                        if isinstance(candidate, str):
                            model = candidate
    else:
        for item in records(path):
            if kind == "codex":
                payload = item.get("payload")
                if not isinstance(payload, dict):
                    continue
                if item.get("type") == "session_meta":
                    session_id = payload.get("id", "")
                if item.get("type") != "turn_context":
                    continue
                cwd, model = payload.get("cwd", ""), payload.get("model", "")
            else:
                if isinstance(item.get("cwd"), str):
                    cwd = item["cwd"]
                if isinstance(item.get("sessionId"), str):
                    session_id = item["sessionId"]
                message = item.get("message")
                if isinstance(message, dict) and message.get("role") == "assistant":
                    candidate = message.get("model")
                    if isinstance(candidate, str):
                        model = candidate
    if not isinstance(model, str) or not model or "\n" in model or "\r" in model:
        return None
    if not isinstance(cwd, str):
        return None
    if cwd and os.path.realpath(cwd) != requested_cwd:
        return None
    if kind == "codex" and not cwd:
        return None
    return model, cwd, session_id if isinstance(session_id, str) else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", default="unknown")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--session-file", type=Path)
    parser.add_argument("--within", type=int, default=600)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.within < 1:
        parser.error("--within must be a positive number of seconds")
    cwd = os.path.realpath(args.cwd)

    def emit(status, model="", evidence="", reason="", session_id=""):
        result = {
            "schema_version": "2", "status": status, "model": model,
            "evidence": evidence, "reason": reason, "harness": args.harness,
            "cwd": cwd, "session_id": session_id,
            "binding": "explicit_file" if args.session_file else "unique_project_file",
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        elif status == "found":
            print(model)
        return 0 if status == "found" else 1

    if args.harness not in PLATFORMS:
        return emit("not_found", reason="unsupported or unknown harness; pass an explicit model")
    folder, pattern, kind = PLATFORMS[args.harness]
    root = Path.home() / folder
    if args.harness == "codex" and os.environ.get("CODEX_HOME"):
        root = Path(os.environ["CODEX_HOME"]) / "sessions"
    if args.session_file:
        candidates = [args.session_file.absolute()]
    elif not root.is_dir():
        return emit("not_found", reason="session directory does not exist")
    elif args.harness in {"myagents", "workbuddy"}:
        return emit("not_found", reason="flat session store requires --session-file to bind identity")
    else:
        if kind == "cc":
            encoded = "".join(c if c.isascii() and c.isalnum() else "-" for c in cwd)
            root = root / encoded
        candidates = sorted(root.rglob(pattern)) if root.is_dir() else []
    now, found = time.time(), []
    recent_files = 0
    for path in candidates:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if not args.session_file and not 0 <= now - path.stat().st_mtime <= args.within:
                continue
            recent_files += 1
            metadata = inspect_session(path, kind, cwd)
        except (OSError, UnicodeError, ValueError, RecursionError):
            continue
        if metadata:
            found.append((path, metadata))
    if not args.session_file and (len(found) > 1 or (kind == "codex" and recent_files > 1)):
        return emit("not_found", reason="ambiguous concurrent sessions; use --session-file or --model")
    if len(found) != 1:
        return emit("not_found", reason="no matching session with the requested cwd and model")
    path, (model, recorded_cwd, session_id) = found[0]
    if not args.session_file and not recorded_cwd and kind != "cc":
        return emit("not_found", reason="session identity is not bound; use --session-file")
    return emit("found", model, str(path), "observed session metadata; model may be an alias", session_id)


if __name__ == "__main__":
    sys.exit(main())
