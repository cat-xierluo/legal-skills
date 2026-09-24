#!/usr/bin/env python3
"""PreToolUse 门禁：默认拒绝未经明确授权的依赖安装与机器环境写入。"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from completion_authority import load_authority, load_completion, live_dispatch_matches


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


def load_authorization(
    path_text: str, encoded_text: str
) -> tuple[str, set[str], set[str], tuple[str, ...], str]:
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
    shell_policy = data.get("shell_policy", "exact_allowlist")
    if shell_policy not in {"exact_allowlist", "claude_auto"}:
        raise ValueError("shell_policy 必须是 exact_allowlist 或 claude_auto")
    source = data.get("authorization_source", "")
    commands = data.get("authorized_commands", [])
    allowed_shell = data.get("allowed_shell_commands", [])
    allowed_write_paths = data.get("allowed_write_paths", [])
    if (
        not isinstance(source, str)
        or not isinstance(commands, list)
        or not isinstance(allowed_shell, list)
        or not isinstance(allowed_write_paths, list)
    ):
        raise ValueError(
            "authorization_source/authorized_commands/allowed_shell_commands/"
            "allowed_write_paths 类型错误"
        )
    if any(not isinstance(item, str) or not item.strip() for item in commands):
        raise ValueError("authorized_commands 只能包含非空字符串")
    if any(not isinstance(item, str) or not item.strip() for item in allowed_shell):
        raise ValueError("allowed_shell_commands 只能包含非空字符串")
    if any(not isinstance(item, str) or not item.strip() for item in allowed_write_paths):
        raise ValueError("allowed_write_paths 只能包含非空字符串")
    normalized = {item.strip() for item in commands}
    normalized_shell = {item.strip() for item in allowed_shell}
    if normalized and not source.strip():
        raise ValueError("存在授权命令但缺少可审计 authorization_source")
    return source.strip(), normalized, normalized_shell, tuple(allowed_write_paths), shell_policy


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


def is_safe_sed_read_command(args: list[str]) -> bool:
    """Allow only `sed -n <numeric-range>p <file>` as a bounded read."""
    if len(args) != 3 or args[0] not in {"-n", "--quiet", "--silent"}:
        return False
    expression, path = args[1:]
    if not path or path.startswith("-"):
        return False
    return re.fullmatch(r"(?:[1-9][0-9]*|\$)(?:,(?:[1-9][0-9]*|\$))?p", expression) is not None


# v2.22.0 worker 默认权限放大（用户决策 2026-09-06）：worker 被隔离在专属分支
# worktree 内，push+PR 是必要交付路径；常规读取不应因复合形式（管道/;/&&/2>/dev/null）
# 被 fail-closed。safe 类从「裸命令白名单」升级为「分段校验」：命令先按顶层分隔符切
# 段，每段独立过段级白名单；任一段不安全即整体拒绝。force push、主干目标、远端删
# 除、子 shell、命令替换、非临时目录重定向仍 fail-closed。
READ_ONLY_PROGRAMS = {
    "pwd", "ls", "grep", "cat", "head", "tail", "wc", "stat", "file",
    "true", "false", "echo", "which", "type", "jq",
    "sort", "uniq", "cut", "tr", "basename", "dirname", "diff",
}
VERSION_ONLY_PROGRAMS = {"node", "npm", "pnpm", "yarn", "bun", "python", "python3"}
GIT_READ_SUBCOMMANDS = {
    "status", "diff", "log", "show", "rev-parse", "merge-base", "fetch", "ls-remote",
}
GIT_DELIVERY_SUBCOMMANDS = {"add", "commit", "push", "rebase"}
GIT_BRANCH_DISPLAY_FLAGS = {
    "", "-a", "-v", "-av", "-va", "-vv", "-avv", "-r", "-rv", "-ar", "-arv",
    "--all", "--list", "--show-current", "--verbose",
}
GIT_PUSH_FORBIDDEN_ARGS = {
    "--force", "-f", "--force-with-lease", "--force-if-includes",
    "--all", "--mirror", "--tags", "--follow-tags", "--delete", "-d",
}
PROTECTED_BRANCH_NAMES = {"main", "master"}
SEGMENT_SEPARATORS = {";", "&&", "&", "||", "|"}
DENIED_PUNCTUATION = {"<", "(", ")", ";;", "&>", ">&", "<<", "<<<", "<&", ">&"}
FD_REDIRECT_TOKENS = {">", ">>", ">&"}
ALLOWED_REDIRECT_STD_TARGETS = {"&1", "&2", "/dev/null"}


def _allowed_redirect_prefixes() -> tuple[str, ...]:
    prefixes = ["/tmp/", "/private/tmp/", "/var/folders/"]
    tmpdir = os.environ.get("TMPDIR", "").rstrip("/")
    if tmpdir:
        prefixes.append(tmpdir + "/")
    return tuple(prefixes)


def _is_allowed_redirect_target(target: str) -> bool:
    # A worktree can itself live under /tmp. Temporary-path permission must not
    # make the PM authority directory writable through `echo > receipt.json`.
    authority_path = os.environ.get("WORKER_AUTHORITY_RECEIPT_FILE", "")
    if authority_path:
        directory = os.path.realpath(os.path.dirname(authority_path))
        resolved = os.path.realpath(target)
        if resolved == directory or resolved.startswith(directory + os.sep):
            return False
    if target in ALLOWED_REDIRECT_STD_TARGETS:
        return True
    if target.startswith("&") or target.startswith("-"):
        return False
    # 临时目录前缀内不允许 `..` 穿越（`/tmp/../etc/hosts` 一类）。
    if "/../" in target or target.endswith("/.."):
        return False
    return target.startswith(_allowed_redirect_prefixes())


def _is_safe_git_push_args(args: list[str]) -> bool:
    for arg in args:
        if arg in GIT_PUSH_FORBIDDEN_ARGS:
            return False
        # Git accepts clustered short flags: `-qf` and `-vd` must retain the
        # same force/delete denial as standalone `-f` and `-d`.
        if arg.startswith("-") and not arg.startswith("--") and any(
            flag in arg[1:] for flag in ("f", "d")
        ):
            return False
        if (
            arg.startswith("--force-with-lease=")
            or arg.startswith("--force-if-includes=")
            or arg.startswith("--exec")
            or arg.startswith("--receive-pack")
        ):
            return False
        # `+src:dst` 强推语法与 `:dst` 远端删除语法整体拒绝。
        if arg.startswith("+") or arg.startswith(":"):
            return False
        dst = arg.rsplit(":", 1)[-1]
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/"):]
        if dst in PROTECTED_BRANCH_NAMES:
            return False
    return True


def _is_safe_git_args(args: list[str]) -> bool:
    if not args or args[0].startswith("-"):
        return False
    subcommand = args[0]
    rest = args[1:]
    if subcommand == "branch":
        return all(flag in GIT_BRANCH_DISPLAY_FLAGS for flag in rest)
    if subcommand == "remote":
        return all(flag in {"-v", "--verbose"} for flag in rest)
    if subcommand == "diff" and "--ext-diff" in rest:
        return False
    if subcommand == "commit" and any(arg in {"--no-verify", "-n"} for arg in rest):
        return False
    if subcommand == "rebase" and any(
        arg == "-x" or arg.startswith("--exec") for arg in rest
    ):
        return False
    if subcommand == "push":
        return _is_safe_git_push_args(rest)
    if subcommand == "fetch" and any(
        arg.startswith("--upload-pack") or arg.startswith("--negotiation-tip=")
        for arg in rest
    ):
        # file:// 传输时 --upload-pack 在本机执行，属命令执行逃逸。
        return False
    return subcommand in GIT_READ_SUBCOMMANDS | GIT_DELIVERY_SUBCOMMANDS


def _is_safe_gh_args(args: list[str]) -> bool:
    if len(args) >= 2 and args[0] == "pr" and args[1] in {
        "create", "view", "diff", "checks", "status",
    }:
        return True
    if args[:2] == ["auth", "status"]:
        return not any(
            arg in {"--refresh", "-h", "--with-token"} for arg in args[2:]
        )
    if args[:2] == ["repo", "view"]:
        return not any(arg in {"--edit", "-e", "--clone", "-c"} for arg in args[2:])
    return False


def _tokenize_worker_command(command: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        # POSIX shells only start a comment when `#` begins a word; shlex's
        # default commenters would truncate `tracked#name` and let the guard
        # authorize a different path from the one git actually receives.
        lexer.commenters = ""
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


def _split_worker_segments(tokens: list[str]) -> list[list[str]] | None:
    """Split tokens on top-level separators; validate redirects while walking.

    Returns None when the command uses denied shell constructs (subshells,
    input redirects, heredocs, command substitution) or redirects output to a
    non-temporary path.
    """
    segments: list[list[str]] = [[]]
    index = 0
    total = len(tokens)
    while index < total:
        token = tokens[index]
        if token in SEGMENT_SEPARATORS:
            segments.append([])
            index += 1
            continue
        if token in FD_REDIRECT_TOKENS:
            # fd 前缀形式：`2>` / `1>>` 会被切成独立的 fd 数字 token。
            if segments[-1] and segments[-1][-1] in {"1", "2"}:
                segments[-1].pop()
            if index + 1 >= total:
                return None
            if not _is_allowed_redirect_target(tokens[index + 1]):
                return None
            index += 2
            continue
        if token in DENIED_PUNCTUATION:
            return None
        if "$(" in token or "`" in token:
            return None
        segments[-1].append(token)
        index += 1
    return segments


def _is_safe_worker_segment(tokens: list[str]) -> bool:
    if not tokens:
        return False
    if any(
        token in SEGMENT_SEPARATORS
        or token in FD_REDIRECT_TOKENS
        or token in DENIED_PUNCTUATION
        for token in tokens
    ):
        return False
    program = os.path.basename(tokens[0])
    args = tokens[1:]
    if program in READ_ONLY_PROGRAMS:
        # sort 的 -o/--output 直接写文件，从只读类里排除。
        if program == "sort" and any(
            arg in {"-o", "--output"} or arg.startswith("--output=") for arg in args
        ):
            return False
        return True
    if program in VERSION_ONLY_PROGRAMS:
        return bool(args) and all(
            arg in {"--version", "-v", "-V", "version"} for arg in args
        )
    if program == "command":
        return (
            len(args) >= 2
            and args[0] in {"-v", "-V"}
            and not any(arg.startswith("-") and arg not in {"-v", "-V"} for arg in args[1:])
        )
    if program == "sed":
        # Arbitrary sed is not read-only (`w`, `e`, `-i`).  The common source
        # inspection form is safe enough to grant without enumerating every
        # path in spawn metadata; all other programs still require an exact
        # `--allow-shell-command` entry.
        return is_safe_sed_read_command(args)
    if program == "date":
        # v1.20.3 Task-028：仅允许读取时间（拒绝 -s/--set/--reference 改系统时间）。
        # 解决 worker 写 STATUS.updated_at 时 `date -u +"%Y-%m-%dT%H:%M:%SZ"` 被拦的撞坑
        # （v1.20.2 W2 实战：`SHELL_COMMAND_NOT_ALLOWLED` 拦 date，worker fallback 跳 STATUS bootstrap）。
        return not any(
            arg in {"-s", "--set", "--reference"}
            or arg.startswith("--reference=")
            for arg in args
        )
    if program == "rg":
        return not any(arg == "--pre" or arg.startswith("--pre=") for arg in args)
    if program == "find":
        return not any(
            arg in {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fls"}
            or arg.startswith("-fprint")
            for arg in args
        )
    if program == "git":
        return _is_safe_git_args(args)
    if program == "gh":
        return _is_safe_gh_args(args)
    return False


def is_safe_lifecycle_command(command: str) -> bool:
    """v2.22.0：安全段复合校验——每段须为只读或交付命令，整体才放行。"""
    tokens = _tokenize_worker_command(command)
    if not tokens:
        return False
    segments = _split_worker_segments(tokens)
    if segments is None:
        return False
    for segment in segments:
        if not segment:
            continue
        if not _is_safe_worker_segment(segment):
            return False
    return True


def claude_auto_protected_shell_reason(command: str, depth: int = 0) -> str | None:
    """Keep explicit worker Git boundaries while Claude auto judges ordinary Bash.

    This is not a general shell sandbox: opaque programs remain subject to Claude
    Code's native auto classifier and the user's settings.  Known high-risk Git
    operations must not be delegated to that classifier.
    """
    if depth > 3:
        return "shell wrapper nesting exceeds the protected-command limit"
    # Unlike the exact-allowlist parser, the auto classifier must inspect
    # commands with ordinary redirects (including `2>&1 | tail`).  Returning
    # no decision on a parse failure would let a protected operation through.
    if "\n" in command or "\r" in command:
        return "multiline shell commands require explicit PM authority"
    tokens = _tokenize_worker_command(command)
    if tokens is None:
        return "shell command cannot be parsed for protected operations"
    if not tokens:
        return None
    if any(token in {"(", ")", "<", "<<", "<<<", ";;"}
           or token.startswith(("$(", "<(", ">("))
           or "`" in token for token in tokens):
        return "opaque shell syntax requires explicit PM authority"
    segments = [[]]
    for token in tokens:
        if token in SEGMENT_SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    for segment in segments:
        # Assignment and leading redirect prefixes precede the executable in
        # POSIX shells.  They must not hide `git` or `gh` from this check.
        while segment:
            if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*=.*", segment[0]):
                segment = segment[1:]
                continue
            offset = 1 if segment[0] in {"0", "1", "2"} and len(segment) > 1 else 0
            if len(segment) > offset + 1 and segment[offset] in {">", ">>", ">&"}:
                segment = segment[offset + 2:]
                continue
            break
        if not segment:
            continue
        program = os.path.basename(segment[0])
        args = segment[1:]
        if program in {"exec", "nohup", "time"} and args:
            program, args = os.path.basename(args[0]), args[1:]
        if program == "sudo":
            return "privilege elevation is outside worker auto authority"
        if program in {"env", "command", "builtin"}:
            while args:
                if program == "env" and args[0] in {"-u", "--unset"}:
                    args = args[2:]
                elif args[0] == "--" or (program == "env" and "=" in args[0]):
                    args = args[1:]
                else:
                    break
            if args:
                program, args = os.path.basename(args[0]), args[1:]
        if program in {"bash", "sh", "zsh", "dash"} and len(args) >= 2:
            if args[0] in {"-c", "-lc", "-ic", "--command"}:
                nested = claude_auto_protected_shell_reason(args[1], depth + 1)
                if nested:
                    return nested
        if program == "eval" and args:
            nested = claude_auto_protected_shell_reason(" ".join(args), depth + 1)
            if nested:
                return nested
        if program == "git" and args:
            # Git global -C/-c/--git-dir/--work-tree options precede the verb.
            while args:
                if args[0] in {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}:
                    if args[0] == "-c" and len(args) > 1 and args[1].lower().startswith("alias."):
                        return "inline Git aliases can hide protected operations"
                    args = args[2:]
                    continue
                if args[0].startswith("-calias.") or args[0].startswith("--config-env=alias."):
                    return "inline Git aliases can hide protected operations"
                if args[0].startswith(("--git-dir=", "--work-tree=", "--namespace=")):
                    args = args[1:]
                    continue
                break
            if not args:
                continue
            subcommand, rest = args[0], args[1:]
            if subcommand == "push" and not _is_safe_git_push_args(rest):
                return "force push, protected-branch push and remote deletion require PM control"
            if subcommand == "commit" and any(arg in {"--no-verify", "-n"} for arg in rest):
                return "git commit --no-verify bypasses repository checks"
            if subcommand == "rebase" and any(
                arg == "-x" or arg.startswith("--exec") for arg in rest
            ):
                return "git rebase --exec runs an unreviewed shell command"
            if subcommand == "fetch" and any(arg.startswith("--upload-pack") for arg in rest):
                return "git fetch --upload-pack can execute a local program"
            if subcommand == "reset" and any(arg == "--hard" for arg in rest):
                return "git reset --hard is destructive"
            if subcommand == "clean" and any(arg.startswith("-f") or arg == "--force" for arg in rest):
                return "git clean --force is destructive"
            if subcommand == "branch" and any(arg in {"-D", "--delete", "--force"} for arg in rest):
                return "branch deletion requires PM control"
        if program == "gh" and args:
            # `gh -R owner/repo pr merge` is the same mutation as the direct
            # form; global repo selectors precede the command group.
            while args:
                if args[0] in {"-R", "--repo"} and len(args) > 1:
                    args = args[2:]
                elif args[0].startswith(("--repo=", "-R=")):
                    args = args[1:]
                else:
                    break
            if args and (args[0] == "api" or tuple(args[:2]) in {
                ("repo", "sync"), ("repo", "delete"), ("pr", "merge")
            }):
                return "GitHub mutation requires PM control"
    return None


GIT_RM_PATH_FORBIDDEN_CHARS = frozenset("*?[]{}$~`")
GIT_RM_TRACKED_MODES = {"100644", "100755", "120000"}


def _segment_invokes_git_rm(tokens: list[str]) -> bool:
    """Recognize git-rm intent broadly so exact Shell grants cannot bypass it."""
    if not tokens:
        return False
    for index, token in enumerate(tokens):
        if os.path.basename(token) != "git":
            continue
        if any(
            candidate.lower().startswith("git_config_key_")
            and "=alias." in candidate.lower()
            for candidate in tokens[:index]
        ) or any(
            candidate.lower().startswith("git_config_parameters=")
            and "alias." in candidate.lower()
            for candidate in tokens[:index]
        ):
            return True
        # `git -C <dir> rm`, absolute git binaries and prefixed/compound forms
        # are intentionally recognized here, then rejected by the exact parser.
        for candidate in tokens[index + 1:]:
            if candidate in SEGMENT_SEPARATORS or candidate in DENIED_PUNCTUATION:
                break
            if candidate == "rm":
                return True
            alias_candidate = candidate[2:] if candidate.startswith("-c") else candidate
            if re.fullmatch(
                r"alias\.[^=]+=(?:!.*\b)?rm(?:\s.*)?",
                alias_candidate,
                flags=re.IGNORECASE,
            ):
                return True
            if candidate.lower().startswith("--config-env=alias."):
                return True
        for option_index, candidate in enumerate(tokens[index + 1:], start=index + 1):
            if candidate == "--config-env" and option_index + 1 < len(tokens):
                if tokens[option_index + 1].lower().startswith("alias."):
                    return True
        return False
    return False


def _looks_like_git_rm(command: str, depth: int = 0) -> bool:
    # Dynamic executable names (`$g rm`, `$(printf git) rm`, brace/glob
    # expansion, backticks) cannot be evaluated safely at hook time.  Any rm
    # command shape combined with Shell expansion is high risk and must not
    # fall through to an exact allowed_shell_commands grant.
    if any(marker in command for marker in GIT_RM_PATH_FORBIDDEN_CHARS) and re.search(
        r"(?:^|[\s;&|()])rm(?:[\s;&|()]|$)", command
    ):
        return True
    tokens = _tokenize_worker_command(command)
    if not tokens:
        # An unparsable string that visibly invokes git rm is still high risk.
        return re.search(r"(?:^|[;&|\n]\s*|\s)(?:[^\s;&|]+/)?git\s+(?:-[^\s]+\s+)*rm(?:\s|$)", command) is not None
    segment: list[str] = []
    for token in tokens + [";"]:
        if token in SEGMENT_SEPARATORS:
            if _segment_invokes_git_rm(segment):
                return True
            for index, candidate in enumerate(segment):
                program = os.path.basename(candidate)
                if program in {"sh", "bash", "dash", "zsh"}:
                    for option_index in range(index + 1, len(segment) - 1):
                        option = segment[option_index]
                        if option == "--command" or re.fullmatch(r"-[A-Za-z]*c", option):
                            # Recursion is bounded for predictable hook latency,
                            # but reaching the cap must fail closed: another
                            # command wrapper remains a high-risk shell escape.
                            if depth >= 4 or _looks_like_git_rm(
                                segment[option_index + 1], depth + 1
                            ):
                                return True
                            break
                if program == "eval" and index + 1 < len(segment):
                    if depth >= 4 or _looks_like_git_rm(
                        " ".join(segment[index + 1:]), depth + 1
                    ):
                        return True
            segment = []
        else:
            segment.append(token)
    return False


def _canonical_repo_relative_path(path: str) -> bool:
    if not path or path.startswith(("/", "./", "../", ":")) or "\\" in path:
        return False
    if any(character in path for character in GIT_RM_PATH_FORBIDDEN_CHARS):
        return False
    if any(character in path for character in ("\n", "\r", "\x00")):
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _matches_frozen_write_scope(path: str, allowed_write_paths: tuple[str, ...]) -> bool:
    # Scope-guard globs remain useful for Edit/Write, but deletion authority is
    # deliberately narrower: only an exact canonical path string is authority.
    return path in allowed_write_paths


def _tracked_git_entry_mode(worktree: str, path: str) -> str | None:
    try:
        result = subprocess.run(
            [
                "git", "-C", worktree, "--literal-pathspecs", "ls-files",
                "--stage", "-z", "--error-unmatch", "--", path,
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    records = [record for record in result.stdout.split(b"\x00") if record]
    if len(records) != 1:
        return None
    try:
        header, record_path = records[0].split(b"\t", 1)
        mode, _object_id, stage = header.decode("ascii").split(" ", 2)
        decoded_path = record_path.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None
    if stage != "0" or decoded_path != path:
        return None
    return mode


def git_rm_authority_decision(command: str) -> tuple[bool, bool, str]:
    """Return (recognized, allowed, reason) for the narrow tracked-file deletion class."""
    if not _looks_like_git_rm(command):
        return False, False, ""

    tokens = _tokenize_worker_command(command)
    if tokens is None or len(tokens) != 4 or tokens[:3] != ["git", "rm", "--"]:
        return True, False, "只允许单段精确命令 git rm -- <一个 repo-relative tracked file>"
    path = tokens[3]
    if not _canonical_repo_relative_path(path):
        return True, False, "删除路径必须是无 pathspec、Shell 展开、绝对路径或遍历的规范仓库相对路径"
    authority_path = os.environ.get("WORKER_AUTHORITY_RECEIPT_FILE", "").strip()
    authority_sha = os.environ.get("WORKER_AUTHORITY_RECEIPT_CONTENT_SHA256", "").strip()
    if not authority_path or not authority_sha:
        return True, False, "缺少绑定启动快照的 PM authority receipt"
    try:
        receipt, _receipt_sha = load_authority(authority_path, authority_sha)
    except (OSError, ValueError, json.JSONDecodeError):
        return True, False, "PM authority receipt 不可验证或已漂移"
    snapshot = receipt.get("authorization_snapshot")
    frozen_paths = snapshot.get("allowed_write_paths") if isinstance(snapshot, dict) else None
    if not isinstance(frozen_paths, list) or any(
        not isinstance(item, str) or not item.strip() for item in frozen_paths
    ):
        return True, False, "PM authority receipt 的 allowed_write_paths 缺失或非法"
    allowed_write_paths = tuple(frozen_paths)
    if not allowed_write_paths:
        return True, False, "spawn 未冻结 allowed_write_paths；tracked 文件删除默认拒绝"
    if not _matches_frozen_write_scope(path, allowed_write_paths):
        return True, False, "删除路径未命中 spawn 时冻结的 allowed_write_paths"
    worktree = receipt.get("worktree")
    if not isinstance(worktree, str) or not os.path.isabs(worktree):
        return True, False, "PM authority receipt 缺少绝对 worktree 身份"
    worktree = os.path.realpath(worktree)
    try:
        root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True, False, "当前 Git worktree 身份不可验证"
    current_root = os.path.realpath(root_result.stdout.strip()) if root_result.returncode == 0 else ""
    current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    if current_root != worktree or os.path.realpath(os.getcwd()) != worktree:
        return True, False, "git rm 必须从 receipt 绑定的 worktree 根目录执行"
    if receipt.get("branch") != current_branch or not current_branch:
        return True, False, "当前分支与 PM authority receipt 不一致"

    mode = _tracked_git_entry_mode(worktree, path)
    if mode not in GIT_RM_TRACKED_MODES:
        return True, False, "目标不是唯一 stage-0 tracked 普通文件或符号链接；目录、gitlink 与未跟踪路径均拒绝"
    return True, True, ""


def _parse_long_options(
    args: list[str],
    *,
    boolean_options: set[str],
    value_options: set[str],
) -> dict[str, str | bool] | None:
    """Parse a deliberately small GNU-style option surface without positionals."""
    parsed: dict[str, str | bool] = {}
    index = 0
    while index < len(args):
        option = args[index]
        if option in parsed or not option.startswith("--") or "=" in option:
            return None
        if option in boolean_options:
            parsed[option] = True
            index += 1
            continue
        if option not in value_options or index + 1 >= len(args):
            return None
        value = args[index + 1]
        if not value or value.startswith("--"):
            return None
        parsed[option] = value
        index += 2
    return parsed


def _valid_bounded_timeout(value: object) -> bool:
    if not isinstance(value, str) or not value.isdigit():
        return False
    timeout = int(value)
    return 1 <= timeout <= 3_600_000


def _valid_orca_retry_request(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(
        r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
        value,
    ) is not None


def _trusted_orca_worker_handle() -> str | None:
    """Resolve the immutable worker handle; conflicting launch/metadata bindings fail closed."""
    handles: list[str] = []
    environment_handle = os.environ.get("ORCA_TERMINAL_HANDLE", "").strip()
    if environment_handle:
        handles.append(environment_handle)
    context = os.environ.get("WORKER_SESSION_CONTEXT", "").strip()
    if context and os.path.isabs(context):
        metadata = Path(context) / "METADATA.json"
        try:
            if metadata.is_file() and not metadata.is_symlink():
                value = json.loads(metadata.read_text(encoding="utf-8"))
                metadata_handle = value.get("session", {}).get("orca", {}).get("terminal_handle", "")
                if isinstance(metadata_handle, str) and metadata_handle.strip():
                    handles.append(metadata_handle.strip())
        except (OSError, TypeError, json.JSONDecodeError):
            return None
    if not handles or len(set(handles)) != 1:
        return None
    return handles[0]


def _normalize_shell_line_continuations(command: str) -> str:
    """Delete unquoted/double-quoted backslash-LF pairs as the shell does.

    Preserve single-quoted literals, escaped backslashes and the indentation
    after a continuation; replacing a pair with a space changes command words.
    """
    normalized: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        character = command[index]
        if character == "\\" and quote != "'" and index + 1 < len(command):
            following = command[index + 1]
            if following != "\n":
                normalized.extend((character, following))
            index += 2
            continue
        if character in {"'", '"'}:
            if not quote:
                quote = character
            elif quote == character:
                quote = ""
        normalized.append(character)
        index += 1
    return "".join(normalized)


def _tokenize_orca_protocol_command(command: str) -> list[str] | None:
    """Parse one native Orca command, including its documented ``\\\n`` layout."""
    if "\x00" in command:
        return None
    # Orca's live preamble renders long commands with POSIX line continuations.
    # shlex(punctuation_chars=...) otherwise emits every continued newline as a
    # positional token, so an exact copy of the native command is denied.
    normalized = _normalize_shell_line_continuations(command)
    if "\n" in normalized or "\r" in normalized:
        return None
    try:
        lexer = shlex.shlex(normalized, posix=True, punctuation_chars=";&|<>()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    if len(tokens) < 3 or any(
        token in {";", "&&", "&", "|", "||", "<", ">", "(", ")"}
        for token in tokens
    ):
        return None
    if any("$(" in token or "`" in token for token in tokens):
        return None
    if os.path.basename(tokens[0]) not in {"orca", "orca-ide", "orca-dev"}:
        return None
    if tokens[1] != "orchestration":
        return None
    return tokens


def _contains_orca_protocol_invocation(command: str, depth: int = 0) -> bool:
    """Recognize protocol intent independently of the narrow allow parser.

    This classifier only causes denial. Operators, wrappers and partial parse
    failures must not reclassify a protocol mutation as an ordinary exact task
    command. It is not a sandbox for arbitrary programs that execute scripts.
    """
    normalized = _normalize_shell_line_continuations(strip_heredoc_bodies(command))
    # Bound nested shell parsing; excessive nesting cannot become a generic
    # allowlist escape. Single-quoted command examples are data, not execution.
    if depth >= 16:
        return True
    single = double = escaped = False
    for index, character in enumerate(normalized):
        if escaped:
            escaped = False
            continue
        if character == "\\" and not single:
            escaped = True
            continue
        if character == "'" and not double:
            single = not single
            continue
        if character == '"' and not single:
            double = not double
            continue
        if not single and (character == "`" or normalized[index:index + 2] == "$("):
            start = index + (1 if character == "`" else 2)
            end = normalized.find("`" if character == "`" else ")", start)
            if _contains_orca_protocol_invocation(normalized[start:end if end >= 0 else None], depth + 1):
                return True
    lexer = shlex.shlex(normalized, posix=True, punctuation_chars=";&|<>()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    tokens: list[str] = []
    try:
        while True:
            token = lexer.get_token()
            if token is None:
                break
            tokens.append(token)
    except ValueError:
        # Preserve already decoded command words if a later argument is broken.
        pass

    def segment_has_protocol(segment: list[str]) -> bool:
        while segment and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", segment[0])
                           or segment[0] in {"if", "then", "elif", "else", "do", "!", "{"}):
            segment = segment[1:]
        # A leading redirect may precede the executable name.
        while len(segment) >= 2:
            offset = 1 if segment[0].isdigit() else 0
            if len(segment) > offset + 1 and segment[offset] in {">", ">>", "<", ">&", "<&"}:
                segment = segment[offset + 2:]
            else:
                break
        if not segment:
            return False
        program = os.path.basename(segment[0])
        if program in {"orca", "orca-ide", "orca-dev"}:
            return len(segment) > 1 and segment[1] == "orchestration"
        if program in {"command", "builtin", "exec", "env", "nohup", "sudo", "timeout", "nice", "setsid"}:
            # Search only executable-shaped words, avoiding recursive expansion
            # over a long chain of wrappers/options.
            executable_names = {"orca", "orca-ide", "orca-dev", "sh", "bash", "dash", "zsh", "ksh", "eval"}
            if any(segment_has_protocol(segment[index:]) for index in range(1, len(segment))
                   if os.path.basename(segment[index]) in executable_names):
                return True
            if program == "env":
                return any(option in {"-S", "--split-string"}
                           and _contains_orca_protocol_invocation(segment[index + 1], depth + 1)
                           for index, option in enumerate(segment[:-1]))
            return False
        if program in {"sh", "bash", "dash", "zsh", "ksh"}:
            return any(
                re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*|--command", option)
                and _contains_orca_protocol_invocation(segment[index + 1], depth + 1)
                for index, option in enumerate(segment[:-1])
            )
        if program == "eval":
            return _contains_orca_protocol_invocation(" ".join(segment[1:]), depth + 1)
        return False

    segment: list[str] = []
    for token in tokens + [";"]:
        if token and all(character in ";&|()\n" for character in token):
            if segment_has_protocol(segment):
                return True
            segment = []
        else:
            segment.append(token)
    return False


def _load_completion_authority(path_text: str) -> dict[str, str] | None:
    if not path_text:
        return None
    try:
        data = load_completion(
            path_text,
            os.environ.get("WORKER_AUTHORITY_RECEIPT_FILE", ""),
            os.environ.get("WORKER_AUTHORITY_RECEIPT_CONTENT_SHA256", ""),
        )
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != "multi-agent-orchestration.completion-authority.v1":
        return None
    required = {
        "state": "active",
        "task_id": "task_",
        "dispatch_id": "ctx_",
        "terminal_handle": "term_",
        "run_id": "run_",
    }
    for key, prefix in required.items():
        value = data.get(key)
        if key == "state":
            if value != prefix:
                return None
        elif not isinstance(value, str) or not value.startswith(prefix):
            return None
    capability_hash = data.get("capability_hash")
    process_incarnation = data.get("process_incarnation")
    if not isinstance(capability_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", capability_hash):
        return None
    if not isinstance(process_incarnation, str) or not process_incarnation:
        return None
    if not isinstance(data.get("runtime_id"), str) or not data["runtime_id"]:
        return None
    return {key: str(value) for key, value in data.items() if isinstance(value, str)}


def _matches_completion_authority(options: dict[str, str | bool], path_text: str) -> bool:
    authority = _load_completion_authority(path_text)
    if authority is None:
        return False
    capability = options.get("--dispatch-capability")
    if not isinstance(capability, str):
        return False
    return (
        options.get("--task-id") == authority["task_id"]
        and options.get("--dispatch-id") == authority["dispatch_id"]
        and options.get("--from") == authority["terminal_handle"]
        and hashlib.sha256(capability.encode("utf-8")).hexdigest() == authority["capability_hash"]
        and live_dispatch_matches(authority, os.environ.get("WORKER_ORCA_CLI_BIN", ""))
    )


def orca_worker_protocol_decision(command: str, completion_authority_file: str) -> tuple[bool, bool]:
    """Return ``(recognized, allowed)`` for the deliberately small Orca surface."""
    tokens = _tokenize_orca_protocol_command(command)
    if tokens is None:
        return _contains_orca_protocol_invocation(command), False

    subcommand = tokens[2]
    args = tokens[3:]
    if subcommand == "send":
        options = _parse_long_options(
            args,
            boolean_options={"--json"},
            value_options={
                "--type", "--subject", "--body", "--task-id", "--dispatch-id",
                "--outcome", "--files-modified", "--report-path", "--phase",
                "--payload", "--from", "--dispatch-capability", "--retry-request",
            },
        )
        if options is None:
            return True, False
        message_type = options.get("--type")
        if message_type not in {"worker_done", "heartbeat", "escalation"}:
            return True, False
        required = {"--type", "--subject", "--task-id", "--dispatch-id"}
        if message_type in {"worker_done", "escalation"}:
            required.add("--body")
        if not required.issubset(options):
            return True, False
        if "--retry-request" in options and not _valid_orca_retry_request(options.get("--retry-request")):
            return True, False
        if message_type == "worker_done":
            return True, (
                tokens[0] in {"orca", "orca-ide", "orca-dev", os.environ.get("WORKER_ORCA_CLI_BIN", "")}
                and options.get("--outcome") in {"succeeded", "failed"}
                and _matches_completion_authority(options, completion_authority_file)
            )
        return True, "--outcome" not in options

    if subcommand == "ask":
        options = _parse_long_options(
            args,
            boolean_options={"--json"},
            value_options={
                "--question", "--resume", "--options", "--timeout-ms", "--from",
                "--dispatch-capability", "--retry-request",
            },
        )
        if options is None:
            return True, False
        if options.get("--from") != _trusted_orca_worker_handle():
            return True, False
        has_question = "--question" in options
        has_resume = "--resume" in options
        if has_question == has_resume:
            return True, False
        if has_resume and "--options" in options:
            return True, False
        if "--retry-request" in options and not _valid_orca_retry_request(options.get("--retry-request")):
            return True, False
        return True, _valid_bounded_timeout(options.get("--timeout-ms"))

    if subcommand == "check":
        options = _parse_long_options(
            args,
            boolean_options={"--json", "--wait"},
            value_options={"--types", "--timeout-ms", "--retry-request", "--terminal", "--ack"},
        )
        if options is None:
            return True, False
        if options.get("--terminal") != _trusted_orca_worker_handle():
            return True, False
        if "--retry-request" in options and not _valid_orca_retry_request(options.get("--retry-request")):
            return True, False
        if "--ack" in options:
            return True, ("--wait" not in options and "--timeout-ms" not in options and "--types" not in options)
        if "--wait" in options:
            return True, _valid_bounded_timeout(options.get("--timeout-ms"))
        if "--timeout-ms" in options or "--types" in options:
            return True, False
        return True, True

    return True, False


def is_safe_orca_worker_protocol_command(command: str, completion_authority_file: str = "") -> bool:
    """Compatibility wrapper used by tests and callers that only need a bool."""
    return orca_worker_protocol_decision(command, completion_authority_file)[1]


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
    completion_authority_file = os.environ.get("WORKER_COMPLETION_AUTHORITY_FILE", "").strip()
    protected_files = {
        value
        for value in (
            auth_file,
            os.environ.get("WORKER_AUTHORITY_RECEIPT_FILE", "").strip(),
            os.environ.get("WORKER_GUARD_SETTINGS_FILE", "").strip(),
            os.environ.get("WORKER_GUARD_ATTESTATION_FILE", "").strip(),
            completion_authority_file,
        )
        if value
    }
    # Update 与 Edit/Write/NotebookEdit 同为文件写工具（Task-114-R4）：spawn 生成的
    # PreToolUse matcher 已含 Update，本分支若漏识别，implementer 可绕过不可变
    # 授权证据边界用 Update 改写 INSTALL_AUTHORIZATION.json 等 authority evidence。
    # Update 的 tool_input 与 Edit 同构（file_path/notebook_path），走同一条路径。
    if tool_name in {"Edit", "Write", "NotebookEdit", "Update"}:
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
        source, authorized, allowed_shell, _mirror_allowed_write_paths, shell_policy = load_authorization(
            auth_file,
            os.environ.get("WORKER_INSTALL_AUTH_B64", "").strip(),
        )
    except ValueError as exc:
        deny("INSTALL_AUTHORIZATION_INVALID", str(exc))
        return 0
    if shell_policy == "claude_auto" and os.environ.get(
        "WORKER_GUARD_BACKEND", ""
    ).strip().lower() not in {"claude-code", "claude_code"}:
        deny("INSTALL_AUTHORIZATION_INVALID", "claude_auto 仅适用于 Claude Code worker")
        return 0

    # Protocol authority outranks both generic shell and installation grants.
    protocol_recognized, protocol_allowed = orca_worker_protocol_decision(
        command, completion_authority_file
    )
    if protocol_recognized:
        if protocol_allowed:
            return 0
        deny(
            "ORCA_COMPLETION_AUTHORITY_INVALID",
            "Orca 协议命令与本次运行期 completion receipt 不匹配；立即停止，不得改写、包装或重试",
        )
        return 0
    # Tracked-file deletion is a high-risk built-in class.  It must run before
    # exact allowed_shell_commands so reauthorization cannot turn a dangerous
    # git-rm spelling into authority.  The scope comes only from the hash-bound
    # PM receipt, not the worker-readable mirror or process B64 copy.
    git_rm_recognized, git_rm_allowed, git_rm_reason = git_rm_authority_decision(command)
    if git_rm_recognized:
        if git_rm_allowed:
            return 0
        deny("GIT_RM_AUTHORITY_BLOCKED", git_rm_reason)
        return 0
    if not is_install_command(command):
        if shell_policy == "claude_auto":
            protected_reason = claude_auto_protected_shell_reason(command)
            if protected_reason:
                deny("CLAUDE_AUTO_PROTECTED_COMMAND", protected_reason)
            # No decision: Claude Code's auto classifier and settings rules run.
            return 0
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
