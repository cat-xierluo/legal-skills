#!/usr/bin/env python3
"""PreToolUse 门禁：默认拒绝未经明确授权的依赖安装与机器环境写入。"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import base64
from pathlib import Path
from typing import Any


SEGMENT = (
    r"(?:^|[\n;&|]\s*|\bthen\s+|\$\(\s*|\(\s*|"
    r"(?:[^\s;&|()]+/)?(?:ba|da|z)?sh\s+(?:-[A-Za-z]*c|--command)\s+['\"]?\s*|"
    r"\beval\s+['\"]?\s*)"
)
PREFIX = (
    r"(?:env\s+)?(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*"
    r"(?:(?:sudo(?:\s+-\S+)*|command|builtin|nohup)\s+)*"
)
BIN = r"(?:[^\s;&|()]+/)?"

INSTALL_PATTERNS = [
    re.compile(SEGMENT + PREFIX + BIN + r"brew\s+install\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"(?:apt|apt-get|dnf|yum|zypper)\s+install\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"apk\s+add\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"pacman\s+-S\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"(?:choco|winget|scoop)\s+install\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"npm\s+(?:install|i|add|ci|link)\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"npm\s+exec\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"npx\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"pnpm\s+(?:install|i|add|link)\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"pnpm\s+dlx\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"yarn(?:\s+(?:install|add|global\s+add))?(?:\s*$|\s*[;&|])", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"yarn\s+dlx\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"bun\s+(?:install|add)\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"bunx\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"(?:pip|pip3|pipx)\s+install\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"python(?:3(?:\.\d+)?)?\s+-m\s+pip\s+install\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"(?:gem|cargo|go)\s+install\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"bundle\s+install\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"composer\s+install\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"(?:uv\s+sync|poetry\s+install)\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"uvx\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"corepack\s+enable\b", re.IGNORECASE),
    re.compile(SEGMENT + PREFIX + BIN + r"ln\s+-s\b", re.IGNORECASE),
    re.compile(
        SEGMENT + PREFIX + BIN + r"(?:curl|wget)\b[^\n]*\|\s*(?:sudo\s+)?(?:[^\s;&|()]+/)?(?:ba|da|z)?sh\b",
        re.IGNORECASE,
    ),
]


def deny(code: str, reason: str) -> None:
    backend = os.environ.get("WORKER_GUARD_BACKEND", "").strip().lower()
    hook_output: dict[str, Any] = {
        "permissionDecision": "deny",
        "permissionDecisionReason": f"{code}: {reason}",
    }
    if backend in {"claude-code", "claude_code", "claude"}:
        hook_output["hookEventName"] = "PreToolUse"
    print(json.dumps({"hookSpecificOutput": hook_output}, ensure_ascii=False))


def load_authorization(path_text: str, encoded_text: str) -> tuple[str, set[str], set[str]]:
    try:
        if encoded_text:
            raw = base64.b64decode(encoded_text, validate=True).decode("utf-8")
            data = json.loads(raw)
        else:
            if not path_text:
                raise ValueError("WORKER_INSTALL_AUTH_B64/WORKER_INSTALL_AUTH_FILE 均未设置")
            path = Path(path_text)
            if not path.is_file():
                raise ValueError(f"授权文件不存在：{path}")
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("授权"):
            raise
        raise ValueError(f"授权快照不可读或不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("授权文件根节点必须是对象")
    if data.get("policy") != "deny_by_default":
        raise ValueError("policy 必须是 deny_by_default")
    source = data.get("authorization_source", "")
    commands = data.get("authorized_commands", [])
    allowed_shell = data.get("allowed_shell_commands", [])
    if not isinstance(source, str) or not isinstance(commands, list) or not isinstance(allowed_shell, list):
        raise ValueError("authorization_source/authorized_commands/allowed_shell_commands 类型错误")
    if any(not isinstance(item, str) or not item.strip() for item in commands):
        raise ValueError("authorized_commands 只能包含非空字符串")
    if any(not isinstance(item, str) or not item.strip() for item in allowed_shell):
        raise ValueError("allowed_shell_commands 只能包含非空字符串")
    normalized = {item.strip() for item in commands}
    normalized_shell = {item.strip() for item in allowed_shell}
    if normalized and not source.strip():
        raise ValueError("存在授权命令但缺少可审计 authorization_source")
    return source.strip(), normalized, normalized_shell


def strip_heredoc_bodies(command: str) -> str:
    """Remove heredoc payload lines so documentation text is not treated as execution."""
    lines = command.splitlines()
    kept: list[str] = []
    delimiter: str | None = None
    strip_tabs = False
    marker = re.compile(r"<<(-?)[\t ]*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
    for line in lines:
        if delimiter is not None:
            candidate = line.lstrip("\t") if strip_tabs else line
            if candidate.strip() == delimiter:
                delimiter = None
                strip_tabs = False
            continue
        kept.append(line)
        match = marker.search(line)
        if match:
            strip_tabs = match.group(1) == "-"
            delimiter = match.group(2)
    return "\n".join(kept)


def is_install_command(command: str) -> bool:
    executable_text = strip_heredoc_bodies(command)
    return any(pattern.search(executable_text) for pattern in INSTALL_PATTERNS)


def is_safe_lifecycle_command(command: str) -> bool:
    """Allow a narrow set of direct, non-interpreter worker lifecycle commands."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    if not tokens or any(token in {";", "&&", "&", "|", "||", "<", ">", "(", ")"} for token in tokens):
        return False
    if any("$(" in token or "`" in token for token in tokens):
        return False

    program = os.path.basename(tokens[0])
    args = tokens[1:]
    read_only = {"pwd", "ls", "grep", "cat", "head", "tail", "wc", "stat", "file", "true", "false"}
    if program in read_only:
        return True
    if program == "rg":
        return not any(arg == "--pre" or arg.startswith("--pre=") for arg in args)
    if program == "find":
        return not any(
            arg in {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fls"}
            or arg.startswith("-fprint")
            for arg in args
        )
    if program == "git":
        if not args or args[0].startswith("-"):
            return False
        subcommand = args[0]
        if subcommand == "branch":
            return args[1:] == ["--show-current"]
        if subcommand == "diff" and "--ext-diff" in args[1:]:
            return False
        if subcommand == "commit" and any(arg in {"--no-verify", "-n"} for arg in args[1:]):
            return False
        return subcommand in {
            "status", "diff", "log", "show", "rev-parse", "merge-base",
            "fetch", "add", "commit",
        }
    if program == "gh":
        return len(args) >= 2 and args[0] == "pr" and args[1] in {
            "create", "view", "diff", "checks", "status",
        }
    return False


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        deny("INSTALL_GUARD_INPUT_INVALID", "PreToolUse 输入无法解析，按 fail-closed 阻断")
        return 0

    if not isinstance(payload, dict):
        deny("INSTALL_GUARD_INPUT_INVALID", "PreToolUse 输入不是对象，按 fail-closed 阻断")
        return 0
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        deny("INSTALL_GUARD_INPUT_INVALID", "tool_input 缺失或类型错误")
        return 0

    auth_file = os.environ.get("WORKER_INSTALL_AUTH_FILE", "").strip()
    protected_files = {
        value
        for value in (
            auth_file,
            os.environ.get("WORKER_AUTHORITY_RECEIPT_FILE", "").strip(),
            os.environ.get("WORKER_GUARD_SETTINGS_FILE", "").strip(),
            os.environ.get("WORKER_GUARD_ATTESTATION_FILE", "").strip(),
        )
        if value
    }
    if tool_name in {"Edit", "Write", "NotebookEdit"}:
        target = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(target, str) or not target.strip():
            deny("INSTALL_GUARD_INPUT_INVALID", "文件工具缺少目标路径")
            return 0
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = Path(os.getcwd()) / target_path
        target_real = os.path.realpath(target_path)
        if any(target_real == os.path.realpath(path) for path in protected_files):
            deny("INSTALL_AUTHORIZATION_IMMUTABLE", "worker 不得修改授权镜像、PM receipt 或门禁 settings")
        return 0

    if tool_name not in {"Bash", "Shell", "Terminal"}:
        return 0

    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        deny("INSTALL_GUARD_INPUT_INVALID", "Shell 工具缺少非空 command")
        return 0
    command = command.strip()

    try:
        source, authorized, allowed_shell = load_authorization(
            auth_file,
            os.environ.get("WORKER_INSTALL_AUTH_B64", "").strip(),
        )
    except ValueError as exc:
        deny("INSTALL_AUTHORIZATION_INVALID", str(exc))
        return 0

    if not is_install_command(command):
        if command in allowed_shell or is_safe_lifecycle_command(command):
            return 0
        deny(
            "SHELL_COMMAND_NOT_ALLOWLISTED",
            "Shell 命令未列入 spawn 的精确 allowed_shell_commands；按 fail-closed 阻断",
        )
        return 0
    if command in authorized and source:
        return 0

    deny(
        "DEPENDENCY_INSTALL_BLOCKED",
        "验证不等于安装授权；该精确命令未获批准。缺工具时写 STATUS=blocked/RESULT，"
        "由 PM 以 --allow-install-command 与 --install-authorization-source 显式授权",
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--classify-install":
        raise SystemExit(0 if is_install_command(sys.argv[2]) else 1)
    raise SystemExit(main())
